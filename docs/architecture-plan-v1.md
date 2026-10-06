# ChangeLens: Architecture and Planning Proposal (design phase only)

## Context
The user asked research-architect to design ChangeLens from `CHANGELENS_ARCHITECTURE_PLANNING_BRIEF.md` for CSCI 599 Assignment 1: an agent with three real MCP servers, LangGraph checkpointer memory scoped by `session_id`, the exact `/chat` contract, and a Cloud Run deployment.

This is a plan only. Nothing has been implemented, run, measured or deployed. The plan does not authorize implementation; that is a later, separate phase.

**Claim tags**
- **[V: src §]** means the source says it.
- **[A]** is an assumption.
- **[O]** is an optional enhancement.
- **[T]** is a target hypothesis.
- **Missing** marks evidence that couldn't be checked from the files.

**Sources**

| Key | Document | Status |
|---|---|---|
| R | `assignemnt1/requirements.md` | Read |
| P | `assignemnt1/Assignment_1_Description.pdf` | Read, all 12 pages |
| B | `assignemnt1/CHANGELENS_ARCHITECTURE_PLANNING_BRIEF.md` | Read |
| PC | Professor's clarification | **Missing.** Only the summary in B §7 exists. |
| — | `changelens-concept.html` | **Missing** |
| — | Prior stack | `Phase 1/requirements.txt`: fastapi, uvicorn, openai, pydantic. No LangGraph or MCP packages. |

## 1. Verified requirements (summary)
- **B1, framework:** exactly one framework. LangGraph + FastAPI + langchain-mcp-adapters is the tested stack. [V: R §2; P §2.1]
- **B2, MCP servers:** at least 2 real MCP servers; at least 3 earns the additional-server criterion. Each needs a manifest reachable at runtime, real `tools/list` and `tools/call`, and arguments that match the schema. Simulated responses get zero. [V: R §3.1, §7; P §2.2, §3.3, §7.1, §7.5]
- **B3, README rationale:** the README explains why the extra servers were included. [V: P §7.5]
- **B4, tool selection:** the LLM picks tools by meaning, answers directly when no tool is needed, and chains at least 2 calls when needed. No keyword routing. [V: R §3.2; P §7.2]
- **B5, memory:** the built-in checkpointer, scoped by `session_id`, for at least 2 turns. A custom dict loses credit. "What did I ask you last?" must be answered. [V: R §3.3; P §7.3]
- **B6, failures:** handle transport, tool-execution and malformed/invalid failures without crashing. [V: R §3.4; P §3.3]
- **B7, endpoint:** `POST /chat` takes `{"query","session_id"}` and returns `{"response": str}`. It stays live until grades are posted. [V: R §3.5; P §4.2, §5]
- **B8, Cloud Run:** multi-stage Docker build, non-root user, bind 0.0.0.0, read `PORT`, cloud LLM. Deploy with `--allow-unauthenticated` and `--max-instances 1`. [V: P §3.1, §4.3–4.4]
- **B9, secrets:** environment variables only. Commit `.env.example`; deploy with `--set-env-vars`. [V: R §4.2; P §4.5]
- **B10, README:** setup, run, deploy, cost, attribution, and three diagrams that match the code. [V: R §5; P §4.6, §7.4]
- **B11, process log:** four parts and a 200–300-word narrative in your own voice. AI-sounding logs are graded skeptically. [V: R §6; P §6.1]
- **B12, attribution:** use `# Adapted from <URL> — <rationale>`. [V: P §6]

**Conflicts and gaps**
- **C1:** R says to defer to the PDF wording, so this plan uses the stricter reading of the two.
- **C2:** P allows diagrams in docs/, but R requires them in README. They go in README.
- **C3:** R omits `--allow-unauthenticated`, the "what did I ask last" check, "manifest reachable at runtime", and the AI-voice warning. All are treated as binding.
- **C4 [A]:** P's sample Dockerfile installs to `/root/.local` and then runs as `appuser`, who probably can't read it. Verify in G0.
- **C5:** The deadline, the grader's timeout and the available credentials are unknown.
- **C6:** Context7 is not on P's "confirmed accessible" list, so it needs its own G0 evidence.

## 2. Project vision
- **Purpose:** help a developer change an unfamiliar FastAPI codebase safely, using evidence pinned to commit SHAs and line ranges.
- **Differentiators:** dependent multi-server chains (GitHub → Context7 → Tavily), an assumption ledger revised across turns, citation verification, and measured false-alarm rates.
- **v1 scope:** public Python/FastAPI repos, one route or feature area per investigation, caching first. Read-only; repository code is never executed.
- **General queries:** stays a general assistant. Conceptual questions use no tools, research goes to Tavily, repo questions go to GitHub, and anything out of scope gets a clear explanation.

## 3. System design [A]
**Flow:** FastAPI `/chat` (validation, per-session lock, deadline) → LangGraph graph with `InMemorySaver` (`thread_id = session_id`) → guarded executor → `MultiServerMCPClient` → GitHub, Context7 and Tavily MCP servers.

**Nodes:**
- `ingest`
- `plan` **[O, flag; used for ablation]**
- `agent`: LLM with about 12 allowlisted tools plus `update_investigation`
- `tools`: guarded execution, Evidence records, Python `ast` structural pass
- `apply_update`: deterministic validation
- `synthesize`
- `verify_citations`: `[E#]` must exist and quotes must match exactly; one repair pass
- `render`: text, Mermaid and optional HTML

**Exits:**
- the LLM makes no tool calls (the no-tool path);
- the budget runs out (provisional: 8 calls per turn);
- the deadline is reached (provisional: 60 s);
- the repair limit is hit.

**MCP servers:**

| Server | Configuration | Fallback |
|---|---|---|
| GitHub | Remote HTTP, read-only, fine-grained PAT limited to public repos | Local stdio binary |
| Context7 | Version-pinned docs; a version mismatch is flagged | `mcp-server-fetch` |
| Tavily | Issues, releases, general research | — |

- **Discovery:** runs at startup, tolerates failures, and retries lazily.

**Memory:**
- The checkpointed state holds messages (tool outputs truncated), investigation, evidence, assumptions, graph, concerns, scenarios, budget and failures.
- The HTML artifact store and the immutable source cache sit outside it; neither is conversational memory.
- Message trimming caps growth.
- A `session_id` is not authentication, and this is documented.

**Failures:** each ends as full recovery, partial result, or safe failure.
- **Transport:** one jittered retry, then a circuit breaker and a structured "unavailable" message so the LLM can choose another source.
- **Tool execution:** auth errors are not retried; not-found asks the user; 429 is retried once if time allows; invalid arguments get one repair attempt. Arguments are checked against the `inputSchema` before every call.
- **Malformed:** pydantic evidence adapters reject the result, so it can never be cited.
- **Domain limits:** explained to the user.
- **Top level:** a final handler always returns `{"response"}`.
- **Fault injection:** a test-only stub server, never counted as an integration.

**Evidence model:**
- Records: Investigation (pinned SHA, superseded when the ref moves), Evidence (immutable), Assumption (lifecycle with history), Graph (`structural` comes from `ast` only; no `runtime_observed` in v1), Concern (contradiction / missing / speculative), Scenario (with its basis; nothing is `executed` in v1).
- Deterministic code validates structure. The LLM interprets.

**API:** exact pydantic request model. An invalid body gets a 4xx with a `{"response"}` body. `GET /reports/{token}` is **[O]**.

**HTML [O]:** graph, ledger and scenarios; autoescaping; strict CSP; 128-bit tokens with a TTL; size caps.

**Security:**
- **Credentials:** environment variables only. No secrets in the LLM's context. Logs are redacted.
- **Untrusted content:** repository and web text are treated as data, never as instructions.
- **Spend:** per-turn budgets and a rate limit.

## 4. Evaluation [T]
- **Corpus:** 6–8 public FastAPI repos (2 held out), with historical feature requests pinned to the commit before each change.
- **Leakage controls:** SHA pinning and date cutoffs.
- **Baselines:** each one changes only the feature under test.

| Metric | Baseline | Target |
|---|---|---|
| Tool Selection (≥40 turns) | `plan` off | ≥85% |
| Multi-step success (≥20 dependent tasks) | Single parallel pass | ≥75% |
| Latency (≥100 warm, ≥20 cold; concurrency 1 and 3) | HTML off | Investigation p95 ≤ 60 s; no-tool p95 ≤ 10 s (provisional) |
| Error resilience (category × server × phase, 3 repeats each) | Recovery off | 0 crashes; ≥80% full or partial |
| Memory (≥20 interleaved sessions) | Stateless | ≥90% correct, 0 leaks |
| Groundedness (≥100 claims) | `verify_citations` off | ≥95% supported, 0 fabricated |
| Cost per query | Fixed-context baseline | ≥20% lower median (**Missing:** prices) |

## 5. Risks
| Risk | Mitigation |
|---|---|
| Remote GitHub MCP access with the PAT | Local stdio server |
| Context7 unknowns | `mcp-server-fetch` |
| Grader timeout | Internal deadline and early partial results |
| Generic grader questions | General-assistant behaviour |
| Limits of static analysis | Narrow scope; list limitations |
| False alarms | Separate concern kinds and measure them |
| Third server looks like padding | Evaluation cases that need it |
| Public endpoint spend | Budgets, rate limit, spend caps |
| 512Mi memory | Measure in G1; consider 1Gi |
| Python 3.14 locally vs. 3.13 in the image | Pin 3.13 locally |
| AI-voice process log | You write it yourself |

## 6. Diagrams (redraw from the final code)
1. **Architecture:** client → FastAPI → LangGraph ↔ checkpointer / LLM / MCP client → the three servers.
2. **Tool loop:** includes the no-tool exit, the budget exit and the failure branches.
3. **Deployment:** `.env` → local Docker → `gcloud builds submit` → registry → Cloud Run in us-west1 with `--set-env-vars`, plus outbound HTTPS to the LLM and the MCP servers.

## 7. Decision register
| ID | Decision | Status and evidence needed |
|---|---|---|
| D1 | LangGraph + FastAPI | Provisional |
| D2 | LLM (GPT-5 vs. NIM) | **Blocked** on which credential you hold |
| D3 | GitHub remote | Provisional |
| D4 | Context7 | Highest risk |
| D5 | Tavily remote | Provisional |
| D6 | `InMemorySaver` | Provisional |
| D7 | Planner flag | Decided by ablation |
| D8 | `ast`-only structure | Provisional |
| D9 | 4xx `{"response"}` for invalid bodies | Provisional |
| D10 | 60 s deadline | Placeholder |
| D11 | HTML | Optional, after G2 |
| D12 | `--set-env-vars` | Per P |
| D13 | 512Mi | Measure |
| D14 | Deploy a skeleton early (G1) | Deviates from the brief's "deploy last" order |

## 8. Gates and backlog (not started)
- **G0, access validation:** `tools/list` and one `tools/call` dump per server; the PAT is denied on a private repo; at least 5 repos accessible; versions pinned; the Dockerfile non-root path checked.
- **G1, grounded workflow deployed:** cited caching analysis on 2 repos; a no-tool query makes 0 tool calls; the 2-turn recall test passes on the live URL; all 3 failure categories are injected without a crash.
  - Fallback: plain ReAct + citation check, which is still compliant.
- **G2, corrections and scenarios:** assumptions superseded with history; no cross-session leak.
- **G3, HTML [O]:** escaping tests pass; tokens expire.
- **G4, evaluation:** every metric reports its denominator, baseline and raw traces; met or missed is stated honestly.
- **G5, readiness:** fresh-clone build; secret scan of the ZIP; 10 rephrased unseen queries on the live URL; diagrams match the code.
- **Test scenarios:** contract shape, no-tool, clarification, out-of-domain, private-repo refusal, oversized input, moved ref, README prompt injection, budget exhaustion, each failure on each server, concurrent requests on one session, two sessions on the same repo, restart loss.

## 9. Unresolved decisions and the evidence to settle them
1. **Professor's clarification:** the original text, to decide whether hosted third-party servers count.
2. **GitHub remote MCP:** whether it works with a public-only fine-grained PAT. Needs a `tools/list` dump, one pinned-SHA read and one denied private-repo read.
3. **Latency:** the grader's HTTP timeout and the Cloud Run request timeout.
4. **Context7:** auth, version coverage and failure behaviour.
5. **langchain-mcp-adapters:** how failures surface (`isError` vs. exceptions) and the session lifecycle in the pinned version.
6. **LLM:** which credential you hold, dated pricing, spend caps, and a tool-calling smoke test.
7. **Memory APIs:** thread deletion and message trimming in the pinned LangGraph version.
8. **Schedule:** the deadline and your weekly hours.
9. **Corpus:** whether the shortlisted repos and pre-change SHAs are viable.

## Verification of this plan
Nothing can be verified until the evidence for G0 is collected. G0 is the first gate in the implementation phase.

Once you accept the architecture decisions, run `process-log-coach` and record a checkpoint in `docs/process-log-checkpoints.md`. You write `PROCESS_LOG.md` yourself.
