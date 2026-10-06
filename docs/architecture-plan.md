# ChangeLens: Architecture and Planning Proposal v2 (design phase only)

> Produced by the `research-architect` subagent on 2026-10-05. It supersedes [v1](architecture-plan-v1.md).
> This is a plan only. Nothing has been implemented, run, measured or deployed.

**Claim tags**
- **[V: src §]** means the source says it.
- **[A]** is an assumption.
- **[O]** is an optional enhancement.
- **[T]** is a target hypothesis.
- **Missing** marks evidence not yet available.

**Sources**

| Key | Document |
|---|---|
| R | `requirements.md` |
| P | `Assignment_1_Description.pdf` (authoritative on wording) |
| B | `CHANGELENS_ARCHITECTURE_PLANNING_BRIEF.md` (its FastAPI-first scope is superseded) |
| E | Local environment facts |
| PC | Professor's clarification: **Missing** |

## Changes from v1
- **Scope widened.** v1 covered public Python/FastAPI repos with caching-first features. v2 covers any public GitHub repo, in any language, for any feature type.
- **Graph provenance.** `structural` edges come only from Python `ast`, as an optional depth boost. Edges in every other language are `inferred` and must cite file, line range and an exact quote that passes deterministic checks.
- **Large repos.** Budgeted expansion starts from an entry point. Every answer carries a "Read / Listed-not-read / Not explored" disclosure.
- **New §3.9, "Grader access and cost control".**
- **D2 (LLM) reworked.** The client is config-driven against any OpenAI-compatible endpoint. The deployed model is picked by a G0 tool-calling bake-off.
- **Environment updated.** Python 3.12.13 with a `python:3.12-slim` image. Pinned versions recorded. `LLM_*` environment variable names.
- **Cache dropped.** v1 had a cross-session source cache; v2 removes it (D17).
- **Corpus.** Now 8–10 repos covering at least 3 languages and at least 5 feature types, stratified by size tier.

## 1. Verified requirements (summary)
- **B1, framework:** exactly one framework. LangGraph + FastAPI + langchain-mcp-adapters is the tested stack. [V: R §2; P §2.1]
- **B2, MCP servers:** at least 2 real MCP servers; at least 3 earns the additional-server criterion. Each needs a manifest reachable at runtime, real `tools/list` and `tools/call`, and schema-correct arguments. Simulated responses get zero. [V: R §3.1, §7; P §2.2, §3.3, §7.1, §7.5]
- **B3, README rationale:** the README explains why the extra servers were included. [V: P §7.5]
- **B4, tool selection:**
  - The LLM picks tools by meaning and answers directly when no tool is needed.
  - It chains at least 2 calls when needed.
  - No keyword routing. [V: R §3.2; P §7.2]
- **B5, memory:** the built-in checkpointer, scoped by `session_id`, for at least 2 turns. A custom dict loses credit. "What did I ask you last?" must get a real answer. [V: R §3.3; P §2.2, §7.3]
- **B6, failures:** handle transport, tool-execution and malformed/invalid failures without crashing. [V: R §3.4; P §3.3, §7.1]
- **B7, endpoint:** `POST /chat` takes `{"query","session_id"}` and returns `{"response": str}`.
  - It must handle arbitrary reasonable queries.
  - It must stay live until grades are posted.
  - Crashing on any non-trivial query earns no credit. [V: R §3.5; P §4.2, §5, §7.4]
- **B8, Cloud Run:**
  - Multi-stage build, non-root user, `0.0.0.0`, read `PORT`, cloud LLM.
  - Deploy with `--allow-unauthenticated` and `--max-instances 1`.
  - Full and alpine images are discouraged. [V: P §4.3–4.4]
- **B9, secrets:** environment variables only. Commit `.env.example`; deploy with `--set-env-vars`. [V: R §4.2; P §4.5]
- **B10, README:** setup, run, deploy, cost, attribution, and three diagrams that match the code. [V: R §5; P §4.6, §7.4]
- **B11, process log:** four parts and a 200–300-word narrative in the student's own voice. [V: R §6; P §6.1]
- **B12, attribution:** `# Adapted from <URL> — <rationale>`. [V: P §6]
- **Budget facts:**
  - Cloud Run is backed by a $50 education credit. [V: P §3.4]
  - The NIM free tier allows about 40 requests per minute. [V: P §3.1]
  - The Tavily student plan gives 4,000 credits per month. [V: P §3.2]
  - GitHub MCP is free within API rate limits. [V: P §3.2]

**Conflicts and gaps**
- **C1:** R defers to the PDF wording, so this plan uses the stricter reading of the two.
- **C2:** P allows diagrams in `docs/`, but R requires them in README. They go in README.
- **C3:** R omits `--allow-unauthenticated`, the "what did I ask last" check, "manifest reachable at runtime", and the AI-voice warning. All are treated as binding.
- **C4 [A]:** P's sample Dockerfile installs to `/root/.local` and then runs as `appuser`. Prefer `/opt/venv` owned by the app user; verify in G0.
- **C5:** The deadline, the length of the grading window, and the grader's HTTP timeout are unknown.
- **C6:** Context7 is not on P's "confirmed accessible" list. It needs its own G0 evidence.
- **C7:** P §3.1 names "Nemotron 3 Ultra and Nemotron 3.5 Lightning" as the tested NIM models. The current default, `nemotron-3-super-120b-a12b`, is not listed and its tool calling is unverified.
- **C8:** P's examples use `OPENAI_*`; the project uses `LLM_*`. The README documents the mapping.
- **C9:** P's example image is `python:3.13-slim`; the project uses `python:3.12-slim`. This is compliant, because P only discourages full and alpine images.

## 2. Project vision
- **Purpose:** a developer's reasoning partner for changing any unfamiliar public GitHub codebase.
  - The developer supplies a repo, optionally a ref, and the change they want to make.
  - ChangeLens maps the relevant workflow and surfaces the assumptions the change relies on.
  - It finds evidence for and against those assumptions and proposes test scenarios.
  - All evidence is pinned to a commit SHA and line ranges.
- **Interview story:** the agent stays honest about depth.
  - It analyses Python deterministically (`structural`).
  - In any other language, every edge is a citation-checked `inferred` claim.
  - It discloses what it did not read.
  - It degrades to useful partial answers under explicit, measured budgets.
- **Differentiators:**
  - Dependent multi-server chains: GitHub → Context7 → Tavily.
  - An assumption ledger revised across turns.
  - A deterministic citation verifier.
  - A coverage disclosure.
  - Per-language and per-provenance metrics, including false-alarm rate.
- **Scope:**
  - Any public GitHub repo, any language, any feature type: caching, pagination, validation, auth, rate limiting, endpoints and CLI flags, config, retries and timeouts, logging, schema changes, refactors, and others.
  - Read-only. Repository code is never executed.
  - Non-GitHub hosts get an explanation, and the agent still offers general help.
- **General assistant:**
  - Conceptual questions use no tools.
  - Research questions go to Tavily.
  - Library API questions go to Context7.
  - Repository questions go to GitHub.
  - Ambiguous requests get a targeted clarification.

## 3. System design [A]

### 3.1 Flow and graph
- **Flow:** FastAPI `/chat` (validation, size caps, per-session lock, admission control, deadline) → LangGraph with `InMemorySaver` (`thread_id = session_id`) → guarded executor → `MultiServerMCPClient` → GitHub, Context7 and Tavily MCP servers.
- **Nodes:**
  - `ingest`
  - `plan` [O, flag; ablation]
  - `agent`: the LLM with allowlisted tools plus `update_investigation`
  - `tools`: guarded execution, Evidence records, a Python-only `ast` pass, and a budget ledger
  - `apply_update`
  - `synthesize`
  - `verify_citations`: `[E#]` must exist and quotes must match exactly; one repair pass
  - `render`: text, Mermaid, and optional HTML
- **Exits:**
  - the LLM makes no tool calls (the no-tool path);
  - the budget runs out;
  - the deadline is reached;
  - the repair limit is hit.
- The budget and deadline exits still run `synthesize` on the evidence gathered, and the result is labelled partial.
- **Stack (E):**

  | Package | Version |
  |---|---|
  | langgraph | 1.2.13 |
  | langchain-mcp-adapters | 0.3.2 |
  | mcp | 1.30.0 |
  | langchain-openai | 1.6.7 |
  | fastapi | 0.142.2 |

  Python is 3.12.13. No Node runtime is needed if all servers are remote.

### 3.2 MCP servers

| Server | Role | Config | Fallback |
|---|---|---|---|
| GitHub | Repo metadata, tree, code search, file reads at a pinned SHA, issues/PRs | Remote HTTP, read-only allowlist, fine-grained public-only PAT | Local stdio binary |
| Context7 | Version-pinned library docs for any ecosystem; a version mismatch is flagged | Hosted HTTP plus API key | `mcp-server-fetch` |
| Tavily | Upstream issues, releases, CVEs, general research | Hosted HTTP plus API key | Graceful degradation |

- **Discovery:** runs at startup, tolerates failures, and retries lazily. The `inputSchema` is checked before every call.
- **Missing:**
  - which GitHub tools exist for tree listing and code search;
  - their truncation limits;
  - Context7 coverage outside Python.

### 3.3 Evidence and graph model
- **Records:**
  - **Investigation:** repo, SHA, languages, manifests, entry points, budget, coverage. Superseded when the ref moves.
  - **Evidence:** immutable. Holds the URL, SHA, path, lines, exact excerpt and extraction method.
  - **Assumption:** lifecycle with history.
  - **Concern:** contradiction, missing, or speculative.
  - **Scenario:** with its basis. Nothing is `executed` in v1.
- **Edge provenance:**

  | Label | Produced by | Acceptance check |
  |---|---|---|
  | `structural` | Python `ast` on source fetched through MCP | Node IDs resolve to parsed symbols at file:line. Dynamic dispatch, DI and middleware are recorded as limitations. |
  | `inferred` | The LLM, in any language | Cites an Evidence ID with file and lines. The quote matches the fetched text exactly, and the cited lines contain the target identifier. Otherwise the edge is rejected or downgraded to a concern. |
  | `proposed` | The change plan | Linked to an assumption |
  | `runtime_observed` | Never produced in v1 | — |

- **Language detection:** deterministic, from manifests and file extensions. It sets the provenance mode and the Context7 lookups. It does not route tools.
- **Budgeted expansion:**
  1. Resolve the entry point. The user may name it; otherwise use code search, then manifest or README hints. If it's ambiguous, ask.
  2. Expand outward with a frontier ranked by the LLM, limited by files, bytes, depth and tool calls.
  3. Skip vendored, generated, binary and lock files.
- **Coverage disclosure:** every repo answer ends with:
  - **Read:** n files;
  - **Listed, not read:** m files;
  - **Not explored:** the remaining tree;
  - **Why it stopped.**

  Deterministic code builds it from the budget ledger.

### 3.4 Memory
- The checkpointed state holds:
  - messages (tool outputs truncated);
  - the investigation and evidence (excerpts capped);
  - assumptions, graph, concerns and scenarios;
  - budget usage and failures.
- Message trimming caps growth.
- There is no cross-session cache (D17).
- A `session_id` is not authentication, and this is documented.

### 3.5 Failures
Every failure ends in one of three outcomes: full recovery, a useful partial result, or a safe failure.

| Category | Handling |
|---|---|
| Transport | One jittered retry. Then a circuit breaker and a structured "unavailable" message, so the LLM picks another source. |
| Tool execution | Auth errors are not retried. Not-found asks the user. A 429 is retried once if time allows. Invalid arguments get one repair attempt. (**Missing:** how errors surface in adapters 0.3.2.) |
| Malformed | Pydantic evidence adapters reject the result, so it can never be cited. |
| Domain limits | Explained to the user: oversized repos, no entry point, `ast` failures (fall back to `inferred`), version mismatches, conflicts, exhausted budgets. |
| LLM provider | 429, 5xx or a malformed tool call gets one retry. Then an [O] fallback provider, otherwise a safe failure. |
| Top level | A final handler always returns `{"response"}`. |

- **Fault injection:** a test-only stub server, never counted as an integration.

### 3.6 API
- Exact pydantic request model.
- An invalid body gets a 4xx with a `{"response"}` body.
- An overlong query gets a 200 with an explanation.
- `GET /healthz` and `GET /reports/{token}` are [O].

### 3.7 HTML [O]
- Autoescaping, strict CSP, 128-bit TTL tokens, size caps.
- Edge styling by provenance and a coverage panel.

### 3.8 Security
- **Credentials:** environment variables only. No secrets in the LLM's context. Logs are redacted.
- **PAT:** must be denied on the private `surendirabalaji/changelens`. This is a G0 negative test.
- **Untrusted content:** repo and web text are treated as data. The tool allowlist is enforced outside the prompt.

### 3.9 Grader access and cost control

**Binding limits on any restriction**
- Graders send arbitrary reasonable queries. [V: R §3.5; P §4.2, §7.4]
- The URL stays live until grades are posted. [V: P §5]
- No keyword routing. [V: P §7.2]
- The endpoint is public. [V: P §4.2, §4.4]

**ALLOWED (recommended)**

| Control | Why it is compliant |
|---|---|
| README "Suggested demo repos and queries": 3–4 small repos in different languages with SHAs, labelled **suggestions, not limits** | Documentation only |
| Per-request budgets: LLM steps, tool calls, files, bytes, Tavily calls, tokens per call, deadline. Each stops with an honest partial answer plus the disclosure. | Useful response, no crash |
| Size tiers chosen from repo metadata returned by a real tool call | Not keyword routing |
| Clarifying question for huge or ambiguous scopes | Good behaviour |
| `--max-instances 1`, modest concurrency, an in-process semaphore | P §4.4 |
| Global daily token budget with a reserved grading floor, then "lite mode" (smaller budgets, still LLM tool selection) | Stays live and tool-capable |
| Query-length cap (provisional 4,000 characters) with an explanation | Reasonable-input bound |
| Small tool allowlist and truncated tool outputs | Discovery is still real |
| Provider-side spend alerts; Tavily credit monitoring | External to the app |
| Lenient rate limit with an explanatory `{"response"}` | Acceptable if generous |

**NOT ALLOWED or risky**

| Practice | Problem |
|---|---|
| Refusing repos outside the demo list, or refusing languages | Violates "arbitrary reasonable queries" and D15 |
| API key, password or Google auth on `/chat` | Breaks the contract and `--allow-unauthenticated` |
| Extra required request fields | Breaks the contract |
| Choosing tools or fast paths from keywords | P §7.2: no credit |
| Hard caps that take the service down during grading | P §5 |
| Tight rate limits that error on normal grader bursts | Risky under P §7.4 |
| Cross-session answer caching or canned responses | Looks like memorized answers; cross-session leakage |
| Silent truncation | Undermines groundedness |

**Cost drivers (all [A])**
- **Formula:** cost per query = Σ over LLM steps of (input tokens × p_in + output tokens × p_out) + Tavily credits + Cloud Run time. GitHub costs $0 within rate limits.
- **No-tool turn:** 1 LLM call of roughly 3–8k input tokens, dominated by the system prompt and tool schemas.
- **Investigation:** 4–10 LLM steps, roughly 40–150k input and 3–10k output tokens in total; 3–15 GitHub calls; 0–3 Tavily calls.
- **NIM free tier:** costs $0 but is limited to about 40 requests per minute. A few overlapping investigations could hit 429, which the semaphore and step budget mitigate.
- **Missing:** NIM key credit or expiry terms; paid-fallback prices; Tavily credits per call.

## 4. Evaluation [T]
- **Corpus:** 8–10 public repos covering at least 3 languages (Python, TS/JS, Go, plus an optional fourth) and at least 5 feature types.
  - Three size tiers: small (<200 files), medium, large.
  - 2 repos are held out.
  - Each repo has historical feature requests pinned to the SHA before the change.
- **Leakage controls:** SHA pinning, date cutoffs, and screening Tavily results.
- **Reporting:** stratified by language, provenance and size tier.
- **Baselines:** each one changes only the feature under test.

| Metric | Measurement | Baseline | Target |
|---|---|---|---|
| Tool Selection | ≥40 labelled turns | `plan` off | ≥85% |
| Multi-step success | ≥20 dependent tasks | Single parallel pass | ≥75% |
| Latency | ≥100 warm and ≥20 cold; concurrency 1 and 3 | HTML off | No-tool p95 ≤10 s; investigation p95 ≤ deadline (60–90 s, provisional) |
| Error resilience | Category × server × phase, 3 repeats each, plus LLM faults | Recovery off | 0 crashes; ≥80% full or partial |
| Memory | ≥20 interleaved sessions | Stateless | ≥90% correct, 0 leaks |
| Groundedness | ≥100 claims | `verify_citations` off | ≥95% supported, 0 fabricated |
| Cost per query | Tokens, credits and run time per class | Fixed-context read | Within ceiling; ≥20% lower median |

- **Product checks:**
  - edge precision for `structural` vs. `inferred`;
  - `ast` ablation on Python repos;
  - disclosure accuracy (target 100%);
  - false-alarm rate;
  - assumption revision;
  - unsupported-repo handling.

## 5. Risks

| Risk | Mitigation |
|---|---|
| Shallow analysis outside Python | `inferred` labelling, citation checks, disclosure, per-language metrics |
| Wrong inferred edges | Lexical check, downgrade to a concern, measure precision |
| Huge repos and tree truncation | Code search first, entry-point expansion, ask for scope |
| NIM tool calling unreliable | G0 bake-off, config switch, [O] fallback |
| NIM 429 or key expiry before grades are posted | Semaphore, step budget, fallback, check key terms |
| Budget used up during grading | Reserved floor, lite mode, alerts; never go hard-down |
| Grader timeout | Internal deadline below the Cloud Run timeout; early partial results |
| Prompt injection | Data-only framing, allowlist outside the prompt, no secrets in context |
| GitHub rate limit | Per-request budgets |
| Context7 gaps | Fetch fallback; disclose the gap |
| Third server looks like padding | Evaluation cases that need it |
| 512Mi memory | Byte caps; measure; 1Gi if needed |
| Dockerfile non-root path | `/opt/venv`; verify in G0 |

## 6. Diagrams (mapping; redraw from the final code)
1. **System architecture:** client → FastAPI `/chat` → LangGraph nodes ↔ `InMemorySaver`; the deployed LLM labelled; `MultiServerMCPClient` → GitHub, Context7 and Tavily; the optional HTML store.
2. **Tool loop:** query → `ingest` → reasoning → selection → `tools/call` → validation → loop back. Includes the no-tool, budget/deadline/partial and failure branches, and `verify_citations` → final response.
3. **Deployment:** `.env` → local Docker → `gcloud builds submit` → Artifact Registry → Cloud Run in us-west1 (`--max-instances 1`, `--set-env-vars`) → URL, with outbound HTTPS to the LLM and the 3 servers.

## 7. Decision register

| ID | Decision | Status |
|---|---|---|
| D1 | LangGraph + FastAPI, pinned | Provisional |
| D2 | Config-driven OpenAI-compatible LLM. Development: NIM `nemotron-3-super-120b-a12b`. Deployed: G0 bake-off (PDF-tested Nemotron 3 Ultra and 3.5 Lightning first, then `gpt-oss-20b`, `mistral-large`, `kimi-k3`). | **Blocked on G0** |
| D3 | GitHub remote MCP, read-only allowlist | Provisional |
| D4 | Context7 | Highest risk; fetch fallback |
| D5 | Tavily remote | Provisional |
| D6 | `InMemorySaver`, `thread_id = session_id` | Provisional |
| D7 | Planner flag | Decided by ablation |
| D8 | `ast`-only structural edges; others inferred with citations; budgeted expansion with disclosure | **Decided** |
| D9 | 4xx with `{"response"}` for invalid bodies | Provisional |
| D10 | 60–90 s deadline | Placeholder |
| D11 | HTML | Optional, after G2 |
| D12 | `--set-env-vars` | Per P |
| D13 | 512Mi | Measure |
| D14 | Deploy a skeleton early (G1) | Kept |
| D15 | Any public GitHub repo, any language, any feature | **Decided (student)** |
| D16 | Grader cost controls per §3.9 | Proposed |
| D17 | No cross-session cache | Proposed |
| D18 | `LLM_*` names documented against `OPENAI_*` | Proposed |
| D19 | Suggested demo repos, non-exclusive | Proposed |
| D20 | Status code when overloaded (429 vs. 200 + explanation) | Open |

## 8. Gates (detailed staging is the next step)
- **G0, access validation:**
  - one `tools/list` and one `tools/call` dump per server;
  - the PAT is denied on the private repo;
  - at least 5 corpus repos across 3 or more languages;
  - the LLM bake-off;
  - the Dockerfile non-root check;
  - NIM key terms recorded.
- **G1, grounded workflow deployed:**
  - cited analysis on 2 repos in different languages;
  - a no-tool query makes 0 calls;
  - 2-turn recall on the live URL;
  - 3 failure categories injected without a crash;
  - a budget-exhaustion disclosure.
  - Fallback: ReAct + citation check + disclosure.
- **G2, corrections and scenarios:** assumption history; no leaks; lite mode verified.
- **G3, HTML [O].**
- **G4, evaluation:** full metrics with strata and raw traces.
- **G5, readiness:**
  - fresh-clone build;
  - ZIP secret scan;
  - 10 unseen queries, including at least 2 repos not on the suggested list;
  - diagrams match the code;
  - spend floor confirmed.
- **Test scenarios:**
  - contract, no-tool, clarification, out-of-domain;
  - private repo, non-GitHub URL, empty repo;
  - non-Python repo, monorepo, no entry point, binary-heavy repo;
  - oversized query, moved ref, prompt injection;
  - budget exhaustion and lite mode, NIM 429;
  - each failure on each server;
  - concurrent requests on one session, two sessions on one repo, restart loss.

## 9. Unresolved decisions and the evidence to settle them
1. **Professor's clarification:** the original text.
2. **NIM:** the tested model IDs, key credit or expiry terms, and the bake-off results.
3. **GitHub MCP:** whether it works with a public-only PAT; which tree and search tools exist and how they truncate; the rate limit.
4. **Context7:** auth and cross-ecosystem coverage.
5. **Adapters 0.3.2:** how errors surface and the session lifecycle.
6. **Timing:** the grader's HTTP timeout, the Cloud Run timeout, and the length of the grading window.
7. **GCP budget:** whether it can hard-cap or only alert; fallback prices; Tavily credits per call.
8. **Memory APIs:** thread deletion and trimming in langgraph 1.2.13.
9. **Corpus:** the repo list, pre-change SHAs, and the demo repos.
10. **Schedule:** the deadline and weekly hours.
11. **D20:** the status code for overload.
