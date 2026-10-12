# ChangeLens

A tool-using agent for code-review questions, built for CSCI 599 Assignment 1. It answers from the model's own knowledge when no lookup is needed, and otherwise chooses among tools exposed by three real MCP servers (GitHub, Context7, Tavily). It keeps per-session conversational memory and runs on Google Cloud Run.

- **Live URL:** `TODO: paste the Cloud Run URL`
- **Framework:** LangGraph (with FastAPI and `langchain-mcp-adapters`)
- **LLM:** NVIDIA NIM, `nvidia/nemotron-3-super-120b-a12b`, through its OpenAI-compatible endpoint

## API

```
POST /chat
Content-Type: application/json

{"query": "string", "session_id": "string"}
```

Response: `{"response": "string"}`. Any other body gets a 422 whose body is still `{"response": "..."}`. `GET /health` returns `{"status": "ok"}`.

```bash
curl -s "$URL/chat" -H 'content-type: application/json' \
  -d '{"query":"What does the fastapi Depends function do?","session_id":"demo-1"}'
```

## Diagrams

### 1. System architecture

![System architecture](docs/1.%20System%20architecture-1.png)

### 2. Tool invocation flow

![Tool invocation flow](docs/Tool%20Invocation.png)

### 3. Deployment topology

![Cloud Run deployment topology](docs/Cloud%20Run%20deployment%20topology-2.png)

## How it works

For every `/chat` request the service:

1. Connects to each MCP server and runs `tools/list`. Only an allowlist of 9 read-only tools is kept.
2. Runs a LangGraph state graph: `ingest → triage → agent ⇄ tools → render`. `triage` is currently a pass-through.
3. Lets the LLM decide, by the meaning of the query, whether to answer directly or call tools. There is no keyword routing.
4. Saves the conversation in the framework checkpointer, keyed by `session_id`.

### MCP servers

| Server | Endpoint | Tools kept | Why it is needed |
|---|---|---|---|
| GitHub | `https://api.githubcopilot.com/mcp/` | 6 | Reads code and files from public repositories |
| Context7 | `https://mcp.context7.com/mcp` | 2 | Library documentation for a specific version |
| Tavily | `https://mcp.tavily.com/mcp/` | 1 | Web search for news and release notes |

All three wrap real external systems. Nothing is simulated in production. These are hosted third-party servers used as clients, so there is nothing to install. Attribution: `TODO: confirm provider names for each server`. Credentials are read from environment variables.

### Memory

LangGraph's built-in `InMemorySaver` checkpointer, with `thread_id = session_id`. Different `session_id` values never see each other's messages. Memory lives in the running instance, so it is lost when the instance restarts. Cloud Run is deployed with `--max-instances 1` so one instance holds all sessions.

### Failure handling

All three required categories return a useful HTTP 200 answer and never crash the request:

| Category | Handling |
|---|---|
| Connection or transport failure | One jittered retry within the time budget. A per-server circuit breaker then skips the server for a cooldown period. The answer states which source was unavailable. |
| Tool execution error | The error kind is classified (for example not found, auth, rate limited). Only transient kinds are retried. The model receives plain failure text and cannot cite a result that was not obtained. |
| Malformed or unreadable response | A guard wraps every `tools/call` (`changelens/mcp_tools/guard.py`). It rejects a successful response that has only non-text content, a response that fails MCP validation, and invalid structured content or output schema. Each becomes a fixed "Tool error (malformed)" result, so the model cannot use the unusable content. This is treated as non-transient: no retry, and the circuit breaker is not tripped, because the server did answer. Oversized results are cut at 8,000 characters with a visible truncation note. |

Limits: at most 5 tool rounds and 30 s of tool time per request. When either is spent the model is given no tools and must answer from what it has.

## Setup and run locally

Requires Python 3.12.

```bash
cp .env.example .env            # then fill in your own keys
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn changelens.api:app --port 8080
```

Keys needed: `LLM_API_KEY` (NVIDIA NIM), `GITHUB_PAT` (fine-grained, public repositories, read-only), `TAVILY_API_KEY`, `CONTEXT7_API_KEY`. `TYPESAFE_API_KEY` and `TRIAGE_BACKEND` are for a planned classifier and are not used yet.

## Deploy to Cloud Run

Prerequisites: a Google Cloud project with the Cloud Run, Cloud Build and Artifact Registry APIs enabled, and `gcloud auth login` done.

```bash
GCP_PROJECT_ID=your-project ./deploy.sh
```

The script validates the environment file, builds the multi-stage image with Cloud Build, pushes it to Artifact Registry, deploys with `--allow-unauthenticated --max-instances 1 --timeout 120` in `us-west1`, passes the keys with `--env-vars-file`, and runs smoke tests: health, two-turn recall, session isolation and a 422 check. Use `--dry-run` to preview without creating anything. The container runs as a non-root user and binds `0.0.0.0:$PORT`.

## Tests and evidence

- Resilience tests (stub MCP server, test-only, never deployed): `pytest tests/resilience`
- Real-server failure runs: `docs/evidence/m2/`
- Tool selection and chaining traces, with live MCP servers: `docs/evidence/m3/`
  - no tool needed: `docs/evidence/m3/01_no_tool.txt` (0 tool calls)
  - GitHub manifest, then Context7 `resolve-library-id`, then `query-docs`: `docs/evidence/m3/02_manifest_context7_chain.txt` (5 rounds)
  - web search: `docs/evidence/m3/03_tavily.txt` (1 round)

### Agent reasoning and tool selection (requirements §3.2)

| Requirement | How it is met | Evidence |
|---|---|---|
| Select the right tool, or no tool, by meaning | The LLM sees the schemas of the 9 discovered tools and chooses. Three queries led to three different choices: none, GitHub then Context7, and Tavily. | the three `docs/evidence/m3/` traces |
| Answer from LLM knowledge when no tool is needed | `What is 2+2?` made no tool call and the answer came from the model | `01_no_tool.txt` |
| Chain at least 2 tool calls for multi-step tasks | 5 dependent rounds: GitHub file reads find the pinned FastAPI version, then Context7 `resolve-library-id` and `query-docs` fetch the documentation for it | `02_manifest_context7_chain.txt` |
| No hard-coded keyword routing | `triage` is a pass-through, and the only routing function, `route_after_agent` in `changelens/graph.py`, checks whether the model's reply contains tool calls | `changelens/graph.py` |

## Cost disclosure

`TODO: fill with your own figures and dates.`

| Item | Basis |
|---|---|
| LLM (NVIDIA NIM developer key) | `TODO` |
| Cloud Run | `TODO` |
| Cloud Build and Artifact Registry | `TODO` |
| GitHub, Context7, Tavily | `TODO` |

## Known limitations

- Memory is in-process: it is lost when the instance restarts, and sessions do not survive scale-to-zero.
- With web search unavailable, an answer can still state a version number from library documentation in its first sentence. A fixed note at the end says the newest releases were not checked.
- The tool-round limit (5) can run out before a long multi-file investigation finishes. The answer then says what it could not check.
