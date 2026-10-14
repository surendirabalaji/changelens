import hashlib
import json
import re

from changelens.schemas import Evidence


FILE_READ_PREFIX = "successfully downloaded text file"
MAX_EXCERPT_CHARS = 4000
# Dependencies often start thousands of characters into a manifest.
MAX_MANIFEST_EXCERPT_CHARS = 6000
MANIFEST_FILENAMES = {"requirements.txt", "pyproject.toml", "package.json"}
TRUNCATION_NOTE = re.compile(
    r"\n?\[truncated: showing \d+ of \d+ characters\]\s*\Z"
)

def build_evidence(call: dict, text: str) -> Evidence | None:
    if call.get("name") != "get_file_contents":
        return None

    if not text.startswith(FILE_READ_PREFIX):
        return None

    args = call.get("args") or {}
    path = args.get("path")
    if not path:
        return None

    # Remove the first line containing the download status.
    _, separator, content = text.partition("\n")
    if not separator:
        return None

    
    content = TRUNCATION_NOTE.sub("", content)

    filename = path.rsplit("/", 1)[-1].lower()
    limit = (
        MAX_MANIFEST_EXCERPT_CHARS
        if filename in MANIFEST_FILENAMES
        else MAX_EXCERPT_CHARS
    )
    excerpt = content[:limit]
    line_count = len(excerpt.splitlines())

    excerpt_sha256 = hashlib.sha256(
        excerpt.encode("utf-8")
    ).hexdigest()

    if not args.get("owner") or not args.get("repo"):
        return None
    url = f"https://github.com/{args['owner']}/{args['repo']}"
    revision = args.get("sha") or args.get("ref") or "unpinned"

    # Include provenance and content in a stable evidence ID.
    identity = json.dumps(
        [url, revision, path, excerpt_sha256],
        ensure_ascii=False,
    )
    evidence_id = hashlib.sha256(
        identity.encode("utf-8")
    ).hexdigest()[:16]

    return Evidence(
        url=url,
        revision=revision,
        path=path,
        lines=f"1-{line_count}" if line_count else "",
        excerpt=excerpt,
        excerpt_sha256=excerpt_sha256,
        extraction_method="github_get_file_contents",
        trust="untrusted_data",
        id=evidence_id,
    )