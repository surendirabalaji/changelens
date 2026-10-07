# CSCI 599 Assignment 1 — Tool-Using Agent with MCP

LLM-powered agent that reasons over queries, selects and invokes tools via real MCP servers, maintains session-scoped conversational memory, and runs as a live service on Google Cloud Run.

**Authoritative requirements:** Always treat `requirements.md` as the source of truth for assignment constraints, rubric, API contract, diagrams, and grading criteria.  
If this file conflicts with `requirements.md` on assignment constraints, follow `requirements.md` and flag the mismatch.

The final tech stack, framework, MCP servers, memory approach, and architecture will be decided with the help of the `research-architect` subagent. Do not treat any implementation choice as fixed until it has been validated against `requirements.md`.

## Key Files & Layout

The layout and setup commands below assume Python provisionally. Update them after the stack is selected.

**Current design:** `docs/architecture-plan-v3.md`. The stack in it:
- Python, LangGraph and FastAPI, with `langchain-mcp-adapters`.
- GitHub, Context7 and Tavily as remote MCP servers.
- NIM Nemotron as the main LLM.
- Jev as the triage classifier.

It is a design only. Nothing is built yet.

- `requirements.md` — Binding assignment requirements and rubric (read this first for any compliance claim)
- `main.py` — Application entrypoint
- `deploy.sh` — Build & deploy script
- `.env.example` — Placeholders only (never commit real secrets)
- `PROCESS_LOG.md` — Required development narrative
- `docs/**/*.html` — Generated readable views of the docs. After editing any `docs/**/*.md`, run `python scripts/render_docs.py`. Never hand-edit the HTML.
- `README.md` — Must contain the diagrams required by requirements.md
- `.claude/agents/` — Custom subagents (including `research-architect`)

## Commands

```bash
# Local development (provisional — update after stack is selected)
cp .env.example .env          # then fill credentials
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
# Run command will depend on the chosen framework (see README after design is finalized)

# Docker & Deploy
# Exact commands will be defined once the stack is chosen
# Follow the deployment section in requirements.md and the final README
```

## Hard Rules

- Never commit secrets. Inject them at runtime through environment variables or a managed secret store.
- Never read, print, inspect, edit or overwrite `.env` (or any `.env.*` file except `.env.example`), not even key names, lengths or prefixes. Use `.env.example` for variable names. If something in `.env` needs checking or changing, tell me what and why, and I will do it. Project code may load `.env` at runtime via `python-dotenv`, but its contents must never be shown to Claude.
- Never act in Google Cloud or any other cloud account. This covers `gcloud` commands (including read-only ones), REST calls to cloud APIs, running `deploy.sh`, and changes to billing, APIs, IAM, Cloud Build, Artifact Registry or Cloud Run. Instead, tell me exactly what to run or click and why it is needed; I will do it myself. Claude may write scripts such as `deploy.sh`, but must not run them.
- Production and integration verification must use real MCP. Unit tests may use clearly identified mocks; resilience tests may inject controlled failures.
- Memory must use the framework’s built-in primitives and be session-scoped as required by requirements.md.
- Handle required MCP failures with clear error responses and appropriate fallbacks. Use bounded retries only for transient failures when retrying is safe; never fabricate successful tool results.
- Handle varied queries within the supported scope, including unseen phrasing, clarification requests, and queries requiring no tools.
- Keep diagrams in README.md accurate to the actual implementation.

## Code Style

- Prefer clear, readable code over cleverness.
- Use type hints on public functions where the language supports them.
- Meaningful names, minimal dead code, no leftover debug prints.
- Attribute any substantially adapted external code in both comments and PROCESS_LOG.md.

## Workflow Preferences

- Before claiming compliance with any rubric item, consult `requirements.md`.
- Prefer ambitious, resume-worthy designs that still fully satisfy the assignment.
- Use the `research-architect` subagent for project ideation, architecture, MCP selection, memory design, failure handling, and evaluation planning.
- After changes to the agent loop, memory, or MCP integration, verify affected behavior, including multi-turn recall, session isolation, and relevant failure modes. Verify all required failure categories before submission.
- Update PROCESS_LOG.md with real decisions, blockers, and verification steps as you go.

## Evaluation Mindset

Design and implement with measurable quality in mind:
- Tool selection accuracy (including no-tool cases)
- Multi-step success on tasks that genuinely require chained tool calls
- Latency (p50/p95), error resilience under the required failure modes
- Memory fidelity across turns and session isolation
- Groundedness of answers that depend on tool results
- Cost awareness

Baselines should differ from the main system only in the feature under test.

## Process Log Coaching

Invoke the `process-log-coach` subagent after meaningful architecture
decisions, implementation milestones, debugging breakthroughs, and
verification runs, and before ending a session with undocumented work.

Provide the changes since the previous checkpoint, relevant prompts,
test output, and evidence paths. Surface its reminder to me.

Maintain its checkpoint records in docs/process-log-checkpoints.md
so future invocations can identify new and still-undocumented work.
Do not mark a milestone documented until PROCESS_LOG.md reflects it.

I write PROCESS_LOG.md myself. Help me gather evidence and organize
my thoughts; do not automatically write or overwrite my narrative.
