# CSCI 599 Assignment 1 — Tool-Using Agent with MCP Integration
**Requirements Specification**  
Fall 2026 · Individual Assignment · 15% of course grade

---

## 1. Objective

Build and deploy an LLM-powered agent that:
- Reasons over user queries
- Selects and invokes tools exposed via **at least two MCP servers**
- Uses the real Model Context Protocol (tools/list + tools/call)
- Maintains conversational memory across turns (session-scoped)
- Runs as a live web service on **Google Cloud Run**

This assignment demonstrates learning objectives related to agentic architectures, production framework implementation with MCP, and cloud deployment.

---

## 2. Framework Choice (Pick Exactly One)

| Framework              | Recommendation                          | Primary Docs |
|------------------------|-----------------------------------------|--------------|
| **LangGraph**          | **Strongly recommended** (course tested stack with FastAPI + langchain-mcp-adapters) | https://docs.langchain.com/oss/python/langgraph/overview |
| OpenAI Agents SDK      | Viable                                  | https://openai.github.io/openai-agents-python/ |
| Google ADK             | Viable                                  | https://google.github.io/adk-docs/ |

Same rubric applies regardless of choice.

---

## 3. Mandatory Functional Requirements

### 3.1 MCP Integration (Minimum 2 servers, 3 for full credit)

- Integrate **≥ 2 MCP servers**. Canonical recommended pair:
  - **Filesystem MCP** — `@modelcontextprotocol/server-filesystem` (Node)
  - **Tavily Search MCP**
- Additional servers (for the 10% criterion) examples:
  - `@modelcontextprotocol/server-sqlite`
  - `mcp-server-fetch` (or Node equivalent)
  - Open-Meteo weather MCP (no key)
  - GitHub MCP server
  - Student-authored MCP server (must expose ≥1 tool with valid JSON Schema)

**Hard requirements**:
- Real MCP protocol usage: `tools/list` (discovery + input schemas) and `tools/call`
- Framework adapters (e.g. `langchain-mcp-adapters`) are allowed and recommended
- **Papa’s rule**: Hard-coded / simulated tool responses that never touch the wire = **zero credit** on MCP integration

### 3.2 Agent Reasoning & Tool Selection

- Correctly select the right tool (or no tool) based on query semantics
- Answer from LLM knowledge alone when no tool is needed
- Chain **≥ 2 tool calls** when the task requires multi-step reasoning
- No hard-coded keyword routing

### 3.3 Conversational Memory

- Use the **framework’s built-in memory primitives** only:
  - LangGraph → checkpointer (MemorySaver / SQLite / etc.)
  - OpenAI Agents SDK → sessions
  - Google ADK → equivalent
- Memory must be **session-scoped** via a `session_id` (or thread_id) passed in the request
- Must remember conversation across **≥ 2 turns** while the Cloud Run instance is alive
- Durable persistence across instance replacement / scale-to-zero is **not required**
- Custom dictionary-based memory = **loses credit**

### 3.4 Failure Handling (All Three Categories Required)

Agent must handle gracefully (no crash, useful response):
1. **Connection / transport failures** (server unavailable or transport closes)
2. **Tool execution errors** (valid call reaches server but tool fails)
3. **Malformed / invalid responses** (unparseable or schema-violating response)

### 3.5 API Contract (Cloud Run)

```
POST /chat
Content-Type: application/json

Request:
{
  "query": "string",
  "session_id": "string"
}

Response:
{
  "response": "string"
}
```

- Must handle arbitrary reasonable queries (not just memorized test cases)
- Service must remain available until grades are posted

---

## 4. Deployment Requirements (Google Cloud Run)

### 4.1 Infrastructure
- Live Cloud Run URL required (localhost-only = zero)
- Multi-stage Docker build
- Non-root runtime user
- Bind to `0.0.0.0` and read the `PORT` environment variable (Cloud Run injects it)
- Cloud-accessible LLM backend only (Ollama allowed for local testing only)
- Region recommendation: `us-west1`
- `--max-instances 1` recommended to keep in-memory session state on one instance

### 4.2 Secrets & Configuration
- No API keys or secrets in source code or git
- Provide `.env.example` with placeholders
- Use environment variables for all credentials
- Load local `.env` for development; pass via `--set-env-vars` for deployment

### 4.3 LLM Backend Options (in recommended order)
1. OpenAI GPT-5 (or current equivalent) via `OPENAI_API_KEY`
2. NVIDIA NIM free Developer keys (OpenAI-compatible endpoint)
3. Gemma via Ollama — **local testing only**, never deploy

---

## 5. Submission Deliverables

1. **Live Cloud Run URL**
2. **Source ZIP** (exclude `.env`, `node_modules`, virtualenvs, secrets). Canonical filenames: `main.py`, `deploy.sh`, `README.md`, etc.
3. **PROCESS_LOG.md** (root of submission)
4. **README.md** (inside the ZIP) containing:
   - Setup, run, and deploy instructions
   - Cost disclosure
   - Attribution for external MCP servers
   - **Three required diagrams** that match the actual implementation:
     1. **System Architecture** — endpoint, agent state graph, MCP client, each named MCP server, LLM, memory/checkpointer, request/response arrows
     2. **Tool Invocation Flow** — full loop: query → reasoning → tool selection → MCP tools/call → result → synthesis (with loop-back for additional calls)
     3. **Deployment Topology** — local env → Docker image → Artifact Registry → Cloud Run → live URL + environment-variable flow

---

## 6. Process Log Requirements (PROCESS_LOG.md)

Must contain (in your own voice):
1. **AI tools used** — every LLM / tool (Claude, GPT, Gemini, Grok, Copilot, Cursor, Ollama, etc.) + versions if known
2. **Development narrative** — chronological, 200–300 words, specific productive prompts, what worked / didn’t / how you unblocked
3. **Verification approach** — how you tested beyond “it ran once” (error injection, multi-turn memory checks, tool inspection, etc.)
4. **What you learned** — 2–3 sentences on what the AI tools could not do that you had to figure out yourself

---

## 7. Rubric (100% base, no separate bonus)

| Criterion                        | Weight | Full Credit Expectation |
|----------------------------------|--------|-------------------------|
| MCP integration correctness      | 25%    | ≥2 real MCP servers, real discovery + invocation, correct argument schemas, all 3 failure modes handled |
| Agent reasoning & tool selection | 25%    | Correct tool (or no-tool) selection, multi-step chaining when needed |
| Memory implementation            | 20%    | Framework-native, session-scoped, works across ≥2 turns |
| Code quality & documentation     | 20%    | Readable code, working deployment, complete README + 3 accurate diagrams, substantive PROCESS_LOG.md |
| Additional MCP servers           | 10%    | ≥3 total servers, actually invoked, rationale documented in README |

---

## 8. Academic Integrity Highlights

- Individual work only
- AI-assisted development is **expected and allowed**
- Attribute any substantially adapted external code in both comments **and** PROCESS_LOG.md
- MCP server implementations and frameworks do not require special attribution beyond normal imports + README citation of servers used

---

*This document is a clean, structured extraction of the official Assignment 1 description (CSCI 599, Fall 2026). Always refer to the original PDF for authoritative wording.*
