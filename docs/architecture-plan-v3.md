# ChangeLens v3: Decision-Memory Code Review — Architecture Plan

> Produced by the `research-architect` subagent on 2026-10-06 from the student's redesign brief, then revised with the student (D18: Jev triage).
> Replaces the earlier v1 and v2 drafts, which were removed from the repository (see git history).
> **Status (updated 2026-10-13): this is the original plan for milestones M0 to M10. Only M0 to M4 were built.** Built: the LangGraph agent with three real MCP servers, failure handling, session memory, Cloud Run deployment, and Workflow A (grounded repository review). **Not built:** Workflow B (revising a decision), Workflow C (rechecking against a pull request), the HTML report store, cost controls (M7), the full B1/B2 evaluation (M9), a separate `commit_memory` node, and the Jev classifier in the running app. Where this plan differs from the code, the code and `README.md` are correct. Tags below: **[V: src]** = checked against a file in this repo; **[A]** = assumption; **[O]** = optional; **[T]** = target to test, not a result.
> Evidence read: `requirements.md`, `docs/evidence/g0/**` (S0b probes, S0c bake-off `bakeoff/summary_partial.md`), `requirements.txt`, `.env.example`.

## Context
The student asked to rework the earlier v2 design before building started. The new framing:
- ChangeLens is a stack-open, decision-memory layer for code review.
- It has three workflows: A (initial review), B (correction) and C (recheck against a later PR or commit).
- Decisions, assumptions and evidence are stored as structured records.
- Measured claims are limited to the benchmark batches.

The research-architect read `requirements.md` (present, authoritative), the v2 docs, the S0b MCP probe evidence (`docs/evidence/g0/**`) and the S0c bake-off (`docs/evidence/g0/bakeoff/summary_partial.md`). This plan records its redesign.

**Status:** this is a design only. Nothing is built, measured or deployed. Numbers marked [T] are targets to test.

## Changes from v2
**Carried over:**
- **D1:** LangGraph, FastAPI and `langchain-mcp-adapters` (langgraph 1.2.13, adapters 0.3.2, mcp 1.30.0).
- **D2:** NIM `nemotron-3-super-120b-a12b`. Bake-off: 17/18 correct selections, 4/4 no-tool, 12/12 schema-valid, 1.36 s median. It still needs to be re-checked for the PR tools and long structured output (S0d).
- **D3–D5:** GitHub, Context7 and Tavily as remote streamable-HTTP servers, all probed with real calls.
- **D6:** `InMemorySaver` with `thread_id = session_id`.
- **D8:** `structural` edges come from `ast`; every other edge is `inferred` and must cite its evidence.
- **D15:** any public repo.
- **D17:** no cache shared across sessions.
- **Carried-over mechanisms:** citation check, budget ledger, coverage disclosure, test-only stub server for fault injection.
- **Tool-calling path, updated after M0 (E11 and E12 in `docs/evidence/m0/README.md`):**
  - The guarded executor is a `ToolCallInterceptor` from adapter 0.3.2. It receives the raw `CallToolResult` (`isError` and the SHA resource URI) before the adapter converts it. This replaces the S0b plan to bypass the adapter with the raw `ClientSession`.
  - One MCP session per server per turn is passed to `load_mcp_tools(session=...)`. This avoids a new handshake on every call: about 0.25 s each, and GitHub calls are about 2× slower on a fresh session.

**Changed:**
1. A first-class `DecisionRecord`, `Assumption` and `Evidence` schema in checkpoint state. Workflows A, B and C; C is new.
2. The graph becomes triage plus modes. There are 9 nodes and only 3 call the LLM, which covers all 11 roles from the brief.
3. The GitHub allowlist grows: `pull_request_read` (`get`, `get_files`, `get_diff`), `get_commit` and `list_branches`. They are listed in `tools_list.json` but have **never been called**.
4. Evaluation is organised by batch:
   - B1 Python/FastAPI;
   - B2 Node/Express or NestJS;
   - B3 Java/Spring (optional).

   The libraries already checked for access become an off-batch smoke set.
5. A new headline metric: stale-assumption detection, compared against the same model with message-only memory.

### New decision D18: Jev for request classification (student's choice)
Source: https://typesafe.ai/blog/introducing-system-one-models-and-jev

**What the post says:**
- Jev is a cloud-API model that returns schema-typed outputs with confidence scores.
- It is trained with RL for calibrated decisions. It is not keyword-based, so it complies with R §3.2.
- Speed: 70–500 ms.
- Price: $0.042 per million input tokens; output is free.

**Why use it:**
- `triage` runs on every turn. Moving it off NIM saves about 1 call per turn against the ~40 requests-a-minute limit, and should cut no-tool latency.

**Integration (2026-10-06).** Sources:
- https://www.langchain.com/blog/building-a-harness-with-jev
- https://www.langchain.com/blog/building-prod-with-jev-and-langgraph
- https://docs.typesafe.ai/introduction (overview page only)
- TypeSafe's `typesafe-ai` skill guide, pasted by the student (MIT licence). It is vendor guidance on how to write questions, read confidence and use patterns.

What the sources show:
- **Packages:**
  - LangChain package: `langchain-typesafe`, class `TypeSafeClassifier`.
  - Official SDK: `typesafe-sdk`. **We use the official SDK** (see the docs check below).
  - Both read the API key from `TYPESAFE_API_KEY`.
- **Question types:**
  - `Choice` returns `choice`, `probabilities` and `confidence`.
  - `Score` returns `score`, `probabilities` and `confidence`.
  - `Noul` is a yes/no that returns a value from 0 to 1.

  Questions can be mixed in one call and are evaluated in parallel and in isolation. `state` can be text, structured data or LangChain messages.
- **Typed answers only. Jev does not extract free text.** This confirms the design: the repo URL, SHA and PR number are parsed deterministically, and the proposed change and constraints are read by `agent`.
- **Reported speed (vendor and partner claims, UNVERIFIED for this workload):**
  - 5–6× faster than Claude Sonnet on a document-classification step.
  - Browserbase's median `act()` time fell from 1.97 s to 0.46 s.
  - LangChain's post also links to related middleware (`ModelRouterMiddleware`, `AutoModeMiddleware`). Not used here.

**`triage` as one Jev call.** The state is the query, a summary of the stored decision ledger and the last few messages. The questions:
- `intent`: a `Choice` over {conceptual, repo_review, revise_decision, recheck, memory_recall, clarify, out_of_scope}.
- `target_decision`: a `Choice` over the session's current `decision_id`s plus `none`. It is asked only when the ledger is not empty.
- ~~`needs_clarification`: a `Noul`.~~ **Dropped after M0 (E14).** It was poorly calibrated for this task: 0.39–0.58 on clear-cut cases. Clarification now comes from the `clarify` intent and the code rule below.

**How the questions are written** (from TypeSafe's `typesafe-ai` skill guide, supplied by the student on 2026-10-06; vendor guidance):
- Each question has **instructions** for the judgement and **criteria** that define each option. Question IDs are not sent to the model, so the full meaning goes into the question itself.
- Every `Choice` includes a no-match outcome: `none` for `target_decision`, and `out_of_scope` for `intent`.
- `state` uses named JSON fields: `{query, ledger_summaries[{decision_id, proposed_change, status}], recent_turns}`. Questions refer to these with backticked paths.
- Independent questions go in **one** call and run in parallel. A second call is made only when an earlier answer is needed to build new state.

**Fallback policy.** `Choice` confidence measures how concentrated the probabilities are, not whether the answer is correct. So a low score alone does not trigger the fallback. Nemotron runs instead only when one of these holds:
- the top two intents fall on **different sides of the tool / no-tool split** and the margin between them is below a threshold (tuned in M0 on our labelled set);
- `target_decision` is uncertain between two real decisions;
- the call errors or times out.

A near-tie between two harmless options, such as `conceptual` vs `clarify`, is accepted. The routers read only these typed fields.

**Ambiguous targets (policy v3; the student's call on 2026-10-06):** a recheck with `target_decision = none` stays a `recheck`. Triage does not turn it into `clarify`.
- The agent resolves the PR's repository from the query and the ledger, then rechecks every active decision on that repository.
- It asks a clarifying question only when it can't resolve the repository, for example "latest PR" with decisions on two repos.
- Policy v2's code-side clarify rule is dropped.

**M0 result** (`docs/evidence/m0/README.md` §7):
- Jev `jev-1.13.0` and Nemotron super were equally accurate: 29/30 request types and 27/27 targets.
- Jev's p95 was **0.20 s** against Nemotron's 4.54 s.
- After the student relabelled `q2` as `recheck`, Jev, Nemotron and policy v3 each score 30/30, with 0 fallbacks and 0 tool/no-tool crossings. The label changed after the results were seen, so held-out validation in M3 decides.
- **D18: GO.** Triage uses `RetryPolicy(max_retries=1, timeout≈2 s)` (E15).

**Optional Jev uses, after M6 [O].** These are not part of the build. Each must beat its Nemotron or code version in an ablation before it is adopted.
- **Workflow C impact filter.** One `Noul` per (assumption, changed-file summary): "does this change touch the condition this assumption depends on?". It runs before the LLM judgement and cuts the LLM calls in recheck. This follows the vendor's "verify and escalate" and "respond to changing state" patterns.
- **Citation pre-check in `check_decision`.** A `Noul` asks "does this excerpt support this claim?". Unclear cases go on to the existing deterministic checks and LLM repair. This follows the vendor's citation-check cookbook.
- **Repo-reference selection.** When the query contains several URLs, code finds the candidates and a `Choice` picks the one the user meant. The model selects; it never generates. This follows the vendor's "select instead of generate" pattern.

**Scope:**
- Jev only picks the mode. All allowlisted tools stay bound to Nemotron in `agent`, so the LLM still makes the final tool choice (R §3.2).
- This adds a second model provider. It is **not** a framework and **not** an MCP server, so it adds no MCP credit.
- Placeholder in `.env.example`: `TYPESAFE_API_KEY`. The SDK expects this name.

**Checked against the TypeSafe docs (2026-10-06).** Pages read: `sdk/python.md`, `api.md`, `primitives/choice.md`, `primitives/noul.md`, `confidence.md`, `concepts/state.md`.
- **SDK: we use the official `typesafe-sdk`, not `langchain-typesafe`.**
  - It provides `AsyncTypeSafeClient` (async context manager) with `system_one(state=..., questions=...)`.
  - The `triage` node calls it directly. LangGraph nodes are already async, so no LangChain wrapper is needed and there is one less dependency.
  - Optional extra: `[http2]`.
- **HTTP API.**
  - Endpoint: `POST https://api.typesafe.ai/v1/systemone`, authenticated with `Authorization: Bearer <TYPESAFE_API_KEY>`.
  - The `model` field takes `"jev-latest"`. The docs list no pinned version, so we record the `model` string from each response in traces for reproducibility.
  - Responses include `usage.input_tokens` and `usage.output_tokens`, which go into the budget ledger.
- **Runtime labels: CONFIRMED.** `Choice` criteria are a map in each request: option → description, which can be a string, a `{what, not_for, examples}` object, or null. The limit is ≤255 options. So `target_decision` options are built from the session's ledger on every call.
- **Outputs.**
  - `Choice`: `choice`, `probabilities` (they sum to 1) and `confidence` = `(p_max − 1/n)/(1 − 1/n)`, which is 0 for an even split and 1 for certainty.
  - `Noul`: the probability of yes, from 0 to 1. A value near 0.5 means uncertain, not "medium".
  - The SDK docs name the response fields in two ways: `response.choices[k]` and `response.answers[k]`. The SDK summary also called a Noul "boolean". We confirm the actual types against the installed SDK in M0.
- **Error mapping into §Failure handling.**
  - 401 (bad key): tool-execution error. No retry; use the Nemotron fallback.
  - 422 (validation): malformed request. This is a code bug, so log it and use the fallback.
  - 429 (rate limit) and 529 (overloaded): one retry with exponential backoff if the deadline allows, as the docs advise. Otherwise use the fallback.
  - Connection errors or timeouts: transport error. Use the fallback.
  - Jev failing never fails the turn.
- **State.**
  - Text only: a string, an object or an array of text. We use an object with named fields, as the docs recommend.
  - Accuracy is lower for non-English text, including CJK.
- **Confidence thresholds.** The docs suggest proceeding above 0.9 and escalating or clarifying below 0.5, set separately for each action according to its cost. This matches our fallback policy, and the actual thresholds are tuned in M0.

**Still missing evidence:**
- Rate-limit numbers.
- The maximum size of `state`. The docs list none, so we cap it ourselves at about 4k characters by trimming `recent_turns`.
- Data retention and privacy for text sent as `state`. It is public repo text, but that should be confirmed.
- Pricing and free credit, and whether the key stays valid through the grading window.
- Prompt-injection behaviour. The docs give no guidance. Because Jev only picks among options and the routers read only typed fields, injected text can at worst cause a misroute, never a tool call.
- Cookbooks to read when the optional uses are taken up: `cookbooks/function_calling.md`, `cookbooks/citation_check.md`.

**Risk:**
- It is a new vendor, and the claims come from its own marketing.
- Mitigation: Nemotron fallback, the comparison in the evaluation, and a config switch `TRIAGE_BACKEND=jev|nemotron`.

### Conflicts found
| # | Conflict | Resolution |
|---|---|---|
| F1 | A "request classifier" vs the ban on keyword routing in R §3.2 | `triage` is a learned classifier: Jev, with a Nemotron structured-output fallback (see D18). It never matches on keywords. All allowlisted tools stay bound in `agent`, so the LLM makes the final tool choice. |
| F2 | A "per project" ledger and "later" rechecks vs session-scoped memory | The ledger is session-scoped and lasts only while the instance runs. The pitch says rechecks happen "later in the same session". A pasteable decision summary is optional. |
| F3 | "Tavily or Fetch" | Keep Tavily, which was probed. Fetch is a fallback only and is not probed. |
| F4 | Evaluated stacks vs the corpus that was checked | Only `full-stack-fastapi-template` is a real backend app. More app repos and PRs are needed. |
| F5 | There is no compare or range-diff tool | Recheck uses the PR `get_files` and `get_diff`, or `get_commit full_patch`, plus a drift check on cited excerpts at the new SHA. |
| F6 | 11 LLM nodes vs the NIM limit of about 40 requests per minute | Only 3 nodes call the LLM. |
| F7 | "Reviewer effort" needs a study with people | Optional and qualitative; no claim made. |
| F8 | The professor's clarification (**RESOLVED 2026-10-06**; the student supplied the professor's answer) | Verbatim: *"Does not count as real MCP integration, as it can be very few lines of code, and fails the test as 'Hard-coded / simulated tool responses that never touch the wire = zero credit on MCP integration'. All MCP servers that will count must 'wrap real external systems or data sources'. What you suggest I would consider 'gaming' the system."* (This was the answer to whether a student-built FastMCP server returning seeded or simulated data counts.) **Effect:** GitHub, Context7 and Tavily all wrap real external systems, so all three count. No student-built server is counted. The fault-injection stub server is test-only. It is never deployed, never listed in the runtime server manifest and never claimed as an integration. |
| F10 | The grader expects a response in **under 60 s** (student, 2026-10-06; "preferably"). v2 and v3 allowed 90 s for Workflow A. | Hard internal deadline of **50 s** for each turn. See "Latency constraint" under the budget section. Workflow A gets fewer tool calls, reads in parallel, and can **continue across turns**. |
| F9 | `search_code` searches all of GitHub and probably only default branches | Require a `repo:` qualifier. Recheck never uses search for PR-head code. |

## Requirements summary (`requirements.md`)
- **R1:** exactly one framework (LangGraph).
- **R2:** at least 2 real MCP servers, at least 3 for the additional-server credit, and nothing simulated.
- **R3:** the LLM chooses tools by meaning, can answer with no tool, can chain calls, and does no keyword routing.
- **R4:** checkpointer memory scoped by `session_id`, across at least 2 turns.
- **R5:** handles transport, tool-execution and malformed-response failures without crashing.
- **R6:** `POST /chat` takes `{query, session_id}` and returns `{response}`.
- **R7:** Cloud Run with a multi-stage build, a non-root user and `0.0.0.0:$PORT`.
- **R8:** secrets only in environment variables.
- **R9:** the README has 3 diagrams that match the code, plus cost and attribution.
- **R10:** the student writes `PROCESS_LOG.md`.
- **R11:** adapted code is attributed.
- **Also:** "what did I ask last" must work, `--allow-unauthenticated`, and a runtime server manifest.

## Vision
ChangeLens is a decision-memory layer for code review.
- **Workflow A:** it maps the affected workflow, extracts assumptions, grounds them in evidence pinned to a SHA or version, suggests tests, and stores the decision.
- **Workflow C:** it compares each assumption against the PR or commit and returns supported, weakened, contradicted or unaffected, citing the changed evidence.
- **Stack-open:** every response carries a support-boundary label, either "evaluated batch" or "unevaluated stack, best-effort".

## System design
```
Client → FastAPI POST /chat (validate, query cap, per-session lock, semaphore, deadline)
 → LangGraph StateGraph ⇄ InMemorySaver(thread_id=session_id)
 → Guarded MCP executor (adapter ToolCallInterceptor on raw CallToolResult; one session per server per turn; tools/list discovery)
     → GitHub (api.githubcopilot.com/mcp, X-MCP-Readonly, public-only PAT)
     → Context7 (mcp.context7.com/mcp, API key)
     → Tavily (mcp.tavily.com/mcp, Bearer)
 → NIM nemotron-3-super-120b-a12b (agent, synthesize, triage fallback)
 → Jev (TypeSafe AI) for triage classification (D18)
 → [optional] HTML report store (TTL, random tokens, never read by the graph — not memory)
```
**The models handle:** intent (Jev, with a Nemotron fallback), evidence planning, tool choice, inferred edges, assumptions, judgements, decision and tests.

**Deterministic code handles:**
- URL and scope validation;
- schema checks;
- retries and the circuit breaker;
- evidence normalisation;
- stack detection from manifests;
- `ast` edges;
- impact matching and drift checks;
- citation and status rules;
- ledger merges;
- budget and coverage;
- rendering.

## LangGraph nodes and edges
| Node | Type | Role from the brief |
|---|---|---|
| `ingest` | Deterministic | Loads state, sets budget and deadline, caps the query |
| `triage` | **Jev** (TypeSafe AI's System One model) as the classifier, with Nemotron structured output as the fallback | Intent ∈ {conceptual, repo_review, revise_decision, recheck, memory_recall, clarify, out_of_scope}, plus a confidence score and `target_decision_id` (picked from the stored ledger summaries). The free-text fields (repo URL, SHA, PR number) are parsed deterministically. That counts as input parsing, not routing. The proposed change and constraints are left for `agent` to read. If Jev's confidence is low, or Jev fails, the Nemotron structured call runs instead. |
| `agent` | LLM with all tools bound; the prompt depends on the mode | Repo resolver, evidence planner, tool selection |
| `tools` | Deterministic | MCP executor: schema pre-check, scope guard, retries and circuit breaker, error classification (`isError` and `McpError`), Evidence, budget |
| `apply_update` | Deterministic | Stack detector, revision pinning, `ast` edges, impact matcher and excerpt drift check |
| `synthesize` | LLM, structured output | Assumption extractor, inferred edges, contradiction judgement, decision and tests. Output depends on the mode: a new record, patch operations, or a status per assumption. |
| `check_decision` | Deterministic | Cited IDs must exist and quotes must match exactly. Status rules: contradicted needs a contradicting citation; supported needs a supporting citation; mixed evidence is at most weakened. One repair loop. |
| `commit_memory` | Deterministic, through reducers | Creates or revises the record, adds `revision_history`, marks superseded items |
| `render` | Deterministic | Markdown and Mermaid report, coverage, support label, optional HTML link |

**Edges.** Every router is a pure function of state.
- `ingest→triage`.
- `triage→agent`, or `triage→render` for clarify or out-of-scope.
- `agent→tools` when there are tool calls and the budget allows.
- `agent→synthesize` in review, revise or recheck mode, or when the budget runs out (the answer is marked partial).
- `agent→render` in conceptual or memory-recall mode. **This is the no-tool path.**
- `tools→apply_update→agent`.
- `synthesize→check_decision`. Then `commit_memory` if it passes, back to `synthesize` once for a repair, or on to `commit_memory` with the failing claims flagged.
- `commit_memory→render→END`.

**Typical chains:**
| Workflow | Chain | Budget |
|---|---|---|
| A | manifest at the SHA → version → Context7 `resolve-library-id` → `query-docs` → route, service and test reads → Tavily only if needed | ≤10 calls, ≤1 Tavily; independent reads in parallel |
| B | Mostly no tools | ≤4 calls |
| C | PR `get` (head and base SHA) → `get_files` → impact match → reads at the head SHA, plus `get_diff` | ≤10 calls |

## MCP plan
| Server | Verified | Still missing |
|---|---|---|
| GitHub | 29 read-only tools. `get_file_contents` with a SHA URI works. Not-found, bad-argument and private-repo cases all return `isError`. | Successful traces for `pull_request_read` (get, get_files, get_diff), `get_commit full_patch` and `list_commits perPage=1`. Diff truncation. Branch behaviour and pagination of `search_code`. Rate limits, including the separate code-search limit. |
| Context7 | Resolve and query work; versions pin (httpx 0.28.1) | Coverage and versions for FastAPI, Starlette, Express and NestJS; quota |
| Tavily | Search works; bad arguments raise `McpError` | Credits per search and extract; rate limit |
| Fetch (fallback) | Not probed | README, transport, runtime image |

Also still missing:
- whether adapter 0.3.2 has an interceptor hook (which would avoid the raw-session path);
- the session lifecycle on streamable HTTP.

Each server provides something the others don't:
- GitHub: code at a revision.
- Context7: documented behaviour at a version.
- Tavily: upstream reality outside the repo.

The test cases are designed so that each server is genuinely needed.

## Memory design
**Checkpoint state** (`thread_id = session_id`):
- `messages`: `add_messages` reducer, trimmed. Tool outputs are truncated because the full content is in `evidence`.
- `repo_context`: owner and name, `base_revision`, stack (frameworks with versions and manifest evidence, confidence, support boundary).
- `evidence`: dict keyed by ID. Immutable and appended only. Excerpts ≤1.5k characters, ≤150 entries, unreferenced entries evicted first.
- `decisions`: dict, with a patch-operations reducer.
- `active_decision_id`, `workflow_graph` (each edge has a provenance), `last_turn`.

There is no store shared across threads and no project ledger. The HTML store is not memory.

**Schemas.** The brief's fields are kept, plus:
- **DecisionRecord** + `acceptance ∈ {proposed, user_accepted}`. Each `revision_history` entry holds `{turn, at_revision, cause, prior/new status, summary}`.
- **Assumption** + typed `invalidation_triggers {kind: path_glob|symbol|concept, value}` and `superseded_by`.
- **Evidence:** the `evidence_id` is a hash of (url, revision, path, lines), plus `extraction_method`, `excerpt_sha256` and `trust=untrusted_data`.
- **TestScenario:** `setup`, `action`, `expected`, basis evidence, `tests_assumption_id`, `execution_status=not_executed`.

**Workflow B:** `triage` picks the target decision; `synthesize` emits patch operations (supersede A2 with A2′ whose origin is `user`); `commit_memory` records the history; at most 4 tool calls.

**Workflow C:** `unaffected` moves only `current_revision_checked` forward. `concept` triggers catch semantic changes such as discount logic added in a new file.

**Measured in M0 (E13):**
- `InMemorySaver` stores the full message list in every checkpoint and has **no pruning API**; only `delete_thread` exists.
- In a synthetic test, one session reached 98 MB after 50 turns when tool output stayed in `messages`, and 27 MB when it was trimmed.

**Rules:**
- Tool output never goes into `messages`. It lives in `evidence`.
- Keep only the last N messages.
- Cap `evidence` at 150 entries.
- Evict sessions idle past a TTL with `delete_thread`.
- M7 measures memory under load to choose 512Mi or 1Gi.

## Failure handling
| Category | Handling |
|---|---|
| Transport | One retry with jitter, then the circuit opens. "Source unavailable" goes to the LLM. Evidence gathered so far is kept and the answer is labelled partial. |
| Tool execution (`isError` or `McpError`) | Auth error: explain, no retry. Not found: ask the user. 429: retry once if time allows, else partial. Invalid arguments: one LLM repair. Unsupported: explain. |
| Malformed | Rejected as evidence and never citable. Retry once if safe. LLM output gets one repair, then a text fallback from validated evidence. |
| Domain | Oversized repo: expand from the entry point and disclose. Ambiguous stack: best-effort label. No entry point: ask. Conflicting evidence: show both, mark weakened. Moved head: pin the SHA from `get`. Docs missing: Tavily plus a disclosed gap. Budget out: partial plus coverage. |
| Injection | Excerpts treated as untrusted data. Allowlist and scope guard outside the prompt. No secrets in context. Tools read-only. |
| LLM 429 or 5xx | One retry, then safe failure. Top-level handler always returns `{response}`. |

Faults are injected with a test-only stub server, and by overriding a real server URL to an unreachable address. Never on the graded live revision.

## API mapping
- `POST /chat` takes `{query, session_id}`; the pydantic model forbids extra fields. It returns `{response}`.
- The repo, PR, commit, change and constraints all go inside `query`.
- An invalid body gets a 4xx whose body is still `{response}`.
- An oversized query gets a 200 with an explanation.
- Extra routes: `/healthz` and `/reports/{token}` (optional).

## Evaluation (batched)
**Batches:**
- **B1** FastAPI: 3 repos, 1 confirmed.
- **B2** Express or NestJS: 3 repos.
- **B3** Spring: optional.
- **Off-batch smoke set:** chi, cobra, ripgrep, hono. Never pooled into batch metrics.

**Issue families:** caching, pagination, auth, validation, rate limiting and timeouts.

**Pinning:** every case uses the pre-change SHA, and post-cutoff Tavily results are screened out.

| Metric | Method | Baseline (only this differs) | Target [T] |
|---|---|---|---|
| Tool selection | About 48 turns (≥10 no-tool, ≥4 clarification, ≥4 recall) with accepted alternative paths | (a) `triage` off. (b) **Jev triage vs Nemotron triage**, everything else identical; also report triage accuracy, p50/p95 latency and cost for each. | ≥85% |
| Multi-step | ≥15 tasks with dependent arguments; the chain is present and the answer is correct | Single-pass planner | ≥70% |
| Latency | p50/p95 per class (no-tool ≥40, A ≥20, B ≥20, C ≥15 runs), ≥10 cold starts, concurrency 1 and 3 | HTML off, `triage` off | No-tool p95 ≤8 s, A ≤55 s, B ≤30 s, C ≤55 s; **every class must stay under the 60 s grader limit, including cold starts** |
| Resilience | 3 categories × 3 servers × {discovery, invocation} × 3 runs, plus LLM faults | Recovery off | 0 crashes, 0 fabrications, ≥80% full or partial |
| Memory | ≥20 interleaved sessions; recall, correction, recheck; adversarial isolation | No checkpointer; messages only | ≥90% pass, 0 leaks |
| Groundedness | ≥100 claims labelled by a human | `check_decision` off | ≥95% supported, 0 fake IDs |
| Cost | Tokens at a stated reference price + Tavily credits + Cloud Run | B turn vs re-running A; bounded vs fixed context | Median B ≤30% of A |
| **Stale-assumption detection** | ≥12 (decision, real PR) pairs, ≥4 unaffected controls; precision and recall | Same model and tools, message memory only | +20 points recall, no loss in precision |

## Risks
| Risk | Mitigation |
|---|---|
| Too few app repos or PRs | Probe early in M0; fall back to `get_commit` rechecks |
| Large diffs | `get_files` first, cap the diff, disclose what was skipped |
| Nemotron unreliable at long structured output | Check in S0d; fall back to per-assumption calls or a model set by config |
| NIM limit of about 40 requests per minute | 3 LLM nodes, semaphore, budgets |
| Instance replacement wipes decisions | Document it; pasteable summary; optional `min-instances 1` |
| Semantic misses in recheck | LLM review of diffs plus a measured comparison with the baseline |
| Workflow graphs outside Python | All edges `inferred` with citations |
| Grader timeout (expects under 60 s) | 50 s hard deadline; a synthesis reserve that cannot be skipped; parallel reads; resumable reviews; cold starts measured. If cold-start p95 goes over the limit, the student can consider `--min-instances 1`, which costs money. |
| Scope creep | Compliance line at M3; HTML and Java optional |
| Session leakage | No cross-thread store; isolation tests |

## README diagrams
1. **Architecture:** `/chat`, then the 9 nodes and `InMemorySaver` (decisions, evidence, messages), then the executor and the 3 servers with URLs and auth, plus NIM. The HTML store is dashed and labelled "not memory".
2. **Tool invocation flow:** triage → agent → schema and scope check → `tools/call` → the 3 failure branches → Evidence → loop; the no-tool and budget exits; `synthesize` → check → commit. Workflow C shown as an inset.
3. **Deployment:**
   - `.env` → `deploy.sh`, which **the student runs** (Claude never does) → Cloud Build → Artifact Registry → Cloud Run.
   - Cloud Run settings: us-west1, unauthenticated, max 1 instance, env vars, non-root, `$PORT`.
   - Outbound HTTPS to NIM and the 3 MCP servers.

## Phased build plan
| Milestone | Scope | Verification (`docs/evidence/<m>/`) |
|---|---|---|
| M0 Evidence top-up | PR and commit tool traces; Context7 FastAPI, Express and NestJS; ≥5 app repos with PRs; S0d bake-off re-run; **Jev probe**: the student gets a key, Claude reads the API docs, then about 30 labelled triage prompts (including runtime decision-ID labels) run on Jev and on Nemotron | JSON dumps; go or no-go on D2 and on **D18** (Jev accuracy ≥ Nemotron and p95 lower → keep Jev; otherwise Nemotron becomes primary) |
| M1 Skeleton and deploy | Contract, ingest→triage→agent⇄tools→render, checkpointer, raw executor, Dockerfile, `deploy.sh` (the student runs it) | Two-turn recall; isolation; non-root; live smoke test |
| M2 Failures | Classification, retry and circuit breaker, stub server | `pytest tests/resilience`; real transport failure via URL override |
| M3 Selection, chaining, README | Prompts, traces, 3 diagrams | No-tool → 0 calls; manifest→Context7 chain; Tavily case. **Compliance line.** |
| M4 Workflow A | Evidence, stack, `ast`, synthesize, check, commit | Cited reviews on one B1 repo and one B2 repo; quote-vs-SHA script |
| M5 Workflow B | Patch operations, history | Supersede history; ≤4 calls; no leaks |
| M6 Workflow C | Impact match, drift, verdicts | One contradicting PR and one unaffected control |
| M7 Cost controls | Semaphore, caps, lite mode | Burst of 5 causes no 5xx |
| M8 HTML (optional) | Store, CSP, escaping | `<script>` escape test; expired token returns 404 |
| M9 Evaluation | B1 and B2 metrics | Each metric has a denominator, a baseline and traces; misses reported |
| M10 Readiness | README, attribution, cost, secret scan | Fresh-clone build; 10 unseen live queries |

## Missing evidence (for the student or Claude to obtain)
1. ~~The professor's original clarification text.~~ Resolved; see F8.
2. ~~GitHub PR and commit tools.~~ Done in M0 (E1, E2, E7). Still open: measured rate limits.
3. ~~Context7 coverage.~~ Done in M0 (E3–E5). Still open: quota.
4. Tavily: responses don't report credits (E6). Still open: published pricing and rate limit.
5. ~~Batch repos.~~ Proposed and checked in M0 (`docs/evidence/m0/corpus/`). The student may swap in their own.
6. ~~Adapter interceptor and session lifecycle.~~ Done in M0 (E11, E12).
7. ~~`InMemorySaver` growth.~~ Measured in M0 (E13).
8. Cold-start time on Cloud Run. The grader expects under 60 s (F10); the Cloud Run request timeout is set above 60 s in `deploy.sh`.
9. Dated prices for LLM tokens, Cloud Run, and NIM credit and expiry.
10. ~~S0a status.~~ The student confirmed on 2026-10-06 that gcloud setup and the budget alert are done.
11. Fetch details, only if it is adopted.
12. Jev (D18). Now known from the docs: the SDK (`typesafe-sdk`, async), the endpoint, auth, error codes, runtime labels (confirmed) and the confidence formula. Still open:
    - rate-limit numbers;
    - the maximum size of `state`;
    - data retention;
    - pricing and credit through grading;
    - response field types, checked against the installed SDK.

## The "budget" in this design
These are per-request limits that keep one `/chat` call within cost, rate-limit and timeout bounds. All numbers are [A] until measured.
- **Tool-call budget for each turn:** A ≤10 calls (≤1 Tavily), B ≤4, C ≤10.
- **Time limit for each turn:** a hard deadline of 50 s (F10: the grader expects under 60 s).

  When either limit runs out, the graph goes to `synthesize` using the evidence it already has, marks the answer **partial**, and shows what was not checked.

### Latency constraint (F10): staying under 60 s
- **Deadline budget for each turn** [A, to be tuned in M1 and M4 from measured traces]:
  - `triage`: ≤1 s with Jev, ≤4 s with the Nemotron fallback.
  - Tool loop: stops at **T+30 s**. This was T+38 s before M0 (E8).
  - `synthesize` and `check_decision`: **reserve of ≥15 s** that the tool loop cannot use. M0 measured Nemotron super at 9.5–14.7 s for a full `DecisionRecord` in `json_schema` mode. Output is capped at about 900 tokens: at most 4 assumptions and 4 tests, short strings.
  - Every budget is enforced with `asyncio.wait_for`, and LLM clients use `max_retries=0`. The OpenAI client applies `timeout` to each attempt and retries twice by default, so one call took 181 s in M0 (E9).
  - `render`: ≤1 s.
  - The response is sent by **T+50 s**, which leaves ≥10 s for network time and slow scheduling.
- **Parallel reads.** When the agent asks for several independent tool calls in one step (for example, route, service and test files at the same SHA), the `tools` node runs them together with `asyncio.gather`, under a cap on how many run at once for each server. Dependent chains stay sequential.
- **Synthesis cutoff.** If the reserve is reached during `synthesize`, the turn returns the deterministic report built from validated evidence (the existing text fallback). It never waits past the deadline.
- **Resumable reviews.** Evidence and the partly built `DecisionRecord` (`acceptance=proposed`, `coverage.pending`) are saved to the checkpoint even when a turn is partial.
  - The response ends with *"Reply 'continue' to check: …"*.
  - On the next turn, `triage` (intent `repo_review`, with the same `target_decision`) picks up from the pending coverage list instead of starting over. A large Workflow A review therefore spans 2–3 turns under 60 s each, instead of one turn that times out.
  - This uses framework-native session memory directly, so it also strengthens R4.
- **Cold starts.** Measure them in M1 using the live URL (≥10 runs). If cold-start p95 plus a Workflow A turn goes over 60 s, the options are:
  - lazy MCP sessions with discovery at startup;
  - a smaller image;
  - the student enabling `--min-instances 1`, which costs money; the student decides.
- **Cloud Run request timeout** in `deploy.sh`: 120 s. It is a safety margin above the internal deadline, never the actual limit.
- **Budget ledger:** counts calls, tokens and Tavily credits for each turn. This is the data for the cost metric.
- **Daily cost budget (M7):** once it is spent, the service switches to a cheaper mode that still uses tools.

