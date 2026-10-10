#!/usr/bin/env bash
# Usage: GCP_PROJECT_ID=my-project ./deploy.sh [--dry-run] [--no-smoke] [--yes]
set -euo pipefail
umask 077
cd "$(dirname "${BASH_SOURCE[0]}")"

ENV_FILE="${ENV_FILE:-.env}"
REGION="${GCP_REGION:-us-west1}"
PROJECT_ID="${GCP_PROJECT_ID:-}"
SERVICE="${SERVICE:-changelens}"
REPO="${REPO:-changelens}"
IMAGE="${IMAGE:-changelens}"
MIN_INSTANCES="${MIN_INSTANCES:-0}"
CONCURRENCY="${CONCURRENCY:-10}"
DRY_RUN=0
SMOKE=1
ASSUME_YES=0
WORK_DIR=""
cleanup() { if [ -n "$WORK_DIR" ]; then rm -rf -- "$WORK_DIR"; fi; }
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
log() { printf '[deploy] %s\n' "$*" >&2; }
die() { log "ERROR: $*"; exit 1; }
usage() { printf 'Usage: GCP_PROJECT_ID=PROJECT ./deploy.sh [--dry-run] [--no-smoke] [--yes]\n'; }
run() {
  if [ "$DRY_RUN" -eq 1 ]; then
    printf '[dry-run] '; printf '%q ' "$@"; printf '\n'
  else
    "$@"
  fi
}
while [ "$#" -gt 0 ]; do
  case "$1" in
    --dry-run) DRY_RUN=1 ;;
    --no-smoke) SMOKE=0 ;;
    --yes) ASSUME_YES=1 ;;
    --help|-h) usage; exit 0 ;;
    *) usage >&2; log "ERROR: Unknown option: $1"; exit 2 ;;
  esac
  shift
done

# Preflight: no cloud resources are changed here, including in dry-run mode.
for tool in gcloud python3 git; do
  command -v "$tool" >/dev/null 2>&1 || die "Install $tool before running this script."
done
if [ "$SMOKE" -eq 1 ] && [ "$DRY_RUN" -eq 0 ]; then
  command -v curl >/dev/null 2>&1 || die "Install curl for smoke tests."
fi
[ -n "$PROJECT_ID" ] || die "Set GCP_PROJECT_ID to your project ID."
[ -f "$ENV_FILE" ] || die "Environment file does not exist: $ENV_FILE"
[ -f Dockerfile ] || die "Dockerfile is missing from the project root."
[ -f requirements.txt ] || die "requirements.txt is missing."
[ -f main.py ] || die "main.py is missing (required by this Dockerfile)."
[ -d changelens ] || die "changelens/ is missing."
case "$MIN_INSTANCES" in 0|1) ;; *) die "MIN_INSTANCES must be 0 or 1 when maximum instances is 1." ;; esac
case "$CONCURRENCY" in ''|*[!0-9]*) die "CONCURRENCY must be a positive integer." ;; esac
[ "$CONCURRENCY" -ge 1 ] && [ "$CONCURRENCY" -le 1000 ] || die "CONCURRENCY must be between 1 and 1000."
if [ -f scripts/env_to_yaml.py ]; then
  ENV_HELPER=scripts/env_to_yaml.py
elif [ -f env_to_yaml.py ]; then
  ENV_HELPER=env_to_yaml.py
else
  die "Place env_to_yaml.py in the project root or scripts/."
fi
log "Project: $PROJECT_ID | Region: $REGION | Service: $SERVICE"
if [ "$ASSUME_YES" -eq 0 ]; then
  printf 'Continue with this project and region? [y/N] ' >&2
  read -r answer || die "No confirmation received. Use --yes for noninteractive execution."
  case "$answer" in y|Y|yes|YES) ;; *) die "Cancelled." ;; esac
fi
ACCOUNT="$(gcloud auth list --project "$PROJECT_ID" --filter=status:ACTIVE --format='value(account)')"
[ -n "$ACCOUNT" ] || die "No active gcloud account. Run: gcloud auth login"
ENABLED="$(gcloud services list --enabled --project "$PROJECT_ID" --format='value(config.name)')"
for api in run.googleapis.com cloudbuild.googleapis.com artifactregistry.googleapis.com; do
  if ! printf '%s\n' "$ENABLED" | python3 -c 'import sys; sys.exit(0 if sys.argv[1] in sys.stdin.read().splitlines() else 1)' "$api"; then
    die "Enable required APIs first: gcloud services enable run.googleapis.com cloudbuild.googleapis.com artifactregistry.googleapis.com --project $PROJECT_ID"
  fi
done

# Validate credentials before the build; temporary files stay outside the repo.
WORK_DIR="$(mktemp -d "${TMPDIR:-/tmp}/changelens-deploy.XXXXXX")"
chmod 700 "$WORK_DIR"
ENV_YAML="$WORK_DIR/env.yaml"
python3 "$ENV_HELPER" --input "$ENV_FILE" --output "$ENV_YAML"

# Explicit Cloud Build upload allowlist. Includes Dockerfile and .dockerignore.
# gcloud upload filtering is separate from Docker build-context filtering.
UPLOAD_IGNORE="$WORK_DIR/upload.gcloudignore"
cat > "$UPLOAD_IGNORE" <<'IGNORE'
*
!Dockerfile
!.dockerignore
!requirements.txt
!main.py
!changelens/
!changelens/**
**/__pycache__
**/__pycache__/**
**/*.pyc
**/.env
**/.env.*
IGNORE
log "Cloud Build uploads only Dockerfile, .dockerignore, requirements.txt, main.py, and changelens/."

GIT_SHA="$(git rev-parse --short HEAD)" || die "Run this from a Git repository with at least one commit."
if [ -n "$(git status --porcelain)" ]; then GIT_SHA="${GIT_SHA}-dirty"; fi
TAG="$(date -u +%Y%m%d-%H%M%S)-${GIT_SHA}"
REGISTRY="${REGION}-docker.pkg.dev/${PROJECT_ID}/${REPO}"
IMAGE_URL="${REGISTRY}/${IMAGE}:${TAG}"

# Listing errors propagate; only a successful list with no match means missing.
REPOSITORIES="$(gcloud artifacts repositories list --project "$PROJECT_ID" --location "$REGION" --format='value(name)')"
if ! printf '%s\n' "$REPOSITORIES" | python3 -c 'import sys; target=sys.argv[1]; sys.exit(0 if any(x.rsplit("/",1)[-1] == target for x in sys.stdin.read().splitlines()) else 1)' "$REPO"; then
  run gcloud artifacts repositories create "$REPO" \
    --repository-format=docker --location "$REGION" --project "$PROJECT_ID" --quiet
else
  FORMAT="$(gcloud artifacts repositories describe "$REPO" --location "$REGION" --project "$PROJECT_ID" --format='value(format)')"
  [ "$FORMAT" = DOCKER ] || die "Existing repository must use Docker format."
fi

run gcloud builds submit . --tag "$IMAGE_URL" --project "$PROJECT_ID" --ignore-file "$UPLOAD_IGNORE"
run gcloud run deploy "$SERVICE" \
  --project "$PROJECT_ID" --region "$REGION" --image "$IMAGE_URL" \
  --allow-unauthenticated --port 8080 --cpu 1 --memory 1Gi --cpu-boost \
  --timeout 120 --concurrency "$CONCURRENCY" \
  --min-instances "$MIN_INSTANCES" --max-instances 1 \
  --env-vars-file "$ENV_YAML" --quiet

if [ "$DRY_RUN" -eq 1 ]; then
  log "Dry run complete. No repository, build, or deployment was created; smoke tests skipped."
  exit 0
fi
URL="$(gcloud run services describe "$SERVICE" --project "$PROJECT_ID" --region "$REGION" --format='value(status.url)')"
REV="$(gcloud run services describe "$SERVICE" --project "$PROJECT_ID" --region "$REGION" --format='value(status.latestReadyRevisionName)')"
[ -n "$URL" ] && [ -n "$REV" ] || die "Could not resolve deployed URL and revision."
log "URL: $URL"
log "Revision: $REV"
log "Image: $IMAGE_URL"
if [ "$SMOKE" -eq 0 ]; then exit 0; fi

# Response bodies are parsed without printing secrets/configuration descriptions.
BODY="$WORK_DIR/body"
HTTP_CODE=""
request() {
  local method="$1" endpoint="$2" expected="$3" payload="${4:-}" stats seconds
  if [ "$method" = GET ]; then
    stats="$(curl -sS --max-time 70 -o "$BODY" -w '%{http_code} %{time_total}' "$URL$endpoint")" || die "HTTP request failed: $endpoint"
  else
    stats="$(curl -sS --max-time 70 -o "$BODY" -w '%{http_code} %{time_total}' \
      -H 'Content-Type: application/json' --data "$payload" "$URL$endpoint")" || die "HTTP request failed: $endpoint"
  fi
  HTTP_CODE="${stats%% *}"
  seconds="${stats#* }"
  log "$method $endpoint -> HTTP $HTTP_CODE in ${seconds}s"
  python3 - "$BODY" <<'PY'
import json, sys
try:
    value = json.load(open(sys.argv[1], encoding="utf-8"))
except (ValueError, OSError):
    print("[smoke] Response was not valid JSON.")
else:
    if isinstance(value, dict) and isinstance(value.get("response"), str):
        print(value["response"])
PY
  [ "$HTTP_CODE" = "$expected" ] || die "Expected HTTP $expected from $endpoint."
}
chat_json() {
  python3 -c 'import json,sys; print(json.dumps({"query":sys.argv[1],"session_id":sys.argv[2]}))' "$1" "$2"
}
request GET /health 200
python3 - "$BODY" <<'PY'
import json,sys
try:
    value=json.load(open(sys.argv[1], encoding="utf-8"))
    ok=isinstance(value,dict) and value.get("status")=="ok"
except (ValueError,OSError):
    ok=False
if not ok:
    sys.exit("Health check failed: expected status=ok.")
PY
CODE_WORD="$(python3 -c 'import secrets; print(secrets.token_hex(12))')"
SESSION="smoke-${CODE_WORD}"
request POST /chat 200 "$(chat_json "Remember this code word exactly: $CODE_WORD" "$SESSION")"
request POST /chat 200 "$(chat_json 'What is the code word I asked you to remember? Return it exactly.' "$SESSION")"
python3 - "$BODY" "$CODE_WORD" <<'PY'
import json,sys
value=json.load(open(sys.argv[1], encoding="utf-8"))
if sys.argv[2] not in value.get("response", ""):
    sys.exit("Memory smoke test failed: code word was not recalled.")
PY
request POST /chat 200 "$(chat_json 'What is the code word I asked you to remember?' "new-${CODE_WORD}")"
python3 - "$BODY" "$CODE_WORD" <<'PY'
import json,sys
value=json.load(open(sys.argv[1], encoding="utf-8"))
if sys.argv[2] in value.get("response", ""):
    sys.exit("Session isolation smoke test failed: code word leaked.")
PY
request POST /chat 422 '{"query":"hi"}'
log "All smoke tests passed."
