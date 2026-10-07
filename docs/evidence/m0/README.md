# M0 evidence top-up (2026-10-06)

**Scope:** check the missing evidence listed in `docs/architecture-plan-v3.md` before any app code is written. Every MCP result here comes from a real `tools/call` against the live remote servers. Secrets were loaded from `.env` at runtime and scrubbed from saved files (`scripts/probe_mcp.py::redact`). LLM and Jev calls were real API calls.

**Measured from:** the developer laptop, not Cloud Run. Latencies are indicative; M1 re-measures them on the live URL.

**Status of decisions:**
- **D2 (Nemotron super): GO.**
- **D18 (Jev for triage): GO, with a revised policy.**

The next section lists the design changes that follow.

## Design changes required by this evidence

| # | Finding | Change to the design |
|---|---|---|
| E1 | A PR from a fork can return **empty `get_files` and `get_diff` with `isError=False`** even though it has commits (#2484). | Treat "commits > 0 but 0 files" as **missing evidence**, never as "unaffected". Fall back to `pull_request_read get_commits` → `get_commit` for each commit, which worked on the fork commit. |
| E2 | `get_files` defaults to 30 files per page (the large PR has 41). `get_diff` returned **212 KB untruncated**. | Page through `get_files` and read patches only for affected files. Never pass a full `get_diff` to the LLM; cap each file's patch and disclose what was skipped. |
| E3 | Context7 returns a missing version as **plain text with `isError=False`** ("Version … not found. Available versions: …"). | The executor detects this text and classifies it as a tool error. It retries once with the nearest listed version **at or below** the detected one and records the version mismatch in the evidence. |
| E4 | A version-pinned Context7 query can return snippets from **`blob/master`** (NestJS v11.1.16). Express v5.1.0 and FastAPI 0.115.13 cited pinned tags. | `Evidence.revision_or_version` comes from **the snippet's source URL**, not from the requested ID. If they differ, label the snippet "version-unpinned". |
| E5 | The FastAPI ID with versions is `/fastapi/fastapi` (0.115.13, 0_116_1, 0.118.2, 0.122.0, 0.128.0). It was not in the top resolve result (`/websites/fastapi_tiangolo`, which has no versions). Starlette and the website IDs list no versions. | The stack detector maps known frameworks to their versioned Context7 IDs. Otherwise it uses the resolved ID and labels the evidence "unversioned docs". |
| E6 | Tavily `tavily_extract` returned 28.7 KB for one page. No Tavily response reports credits used. | Cap extracted text when building evidence. Credit cost comes from Tavily's published pricing, labelled as such and not measured. |
| E7 | Code search results carry **file blob SHAs, not commit SHAs**. | Never treat a search hit as evidence. Re-read the file with `get_file_contents` at the pinned commit SHA first. |
| E8 | Nemotron super writes a valid `DecisionRecord` 6/6 times, but takes **9–28 s** (944–1,888 output tokens). | Synthesis output is compact: at most about 900 tokens, at most 4 assumptions and 4 tests, short strings, `json_schema` mode. The synthesis reserve grows from 10 s to **15 s**, and the tool loop stops at about T+30 s. Revisit after measuring on Cloud Run. |
| E9 | The OpenAI client's `timeout=60` did **not** bound the call: Lightning calls ran 100–181 s, and the last ended with `APITimeoutError` after 181 s. The timeout applies **to each attempt**, and the client retries twice by default (`max_retries=2`), so a call can last about 3 × 60 s. | LLM clients use `max_retries=0`; the graph controls retries. The 50 s turn deadline and per-node budgets are enforced with `asyncio.wait_for`. |
| E10 | Nemotron 3.5 Lightning **cannot** produce a `DecisionRecord`: 0/6, cut off at the token limit after 69–179 s. | Lightning is not a fallback for synthesis. |
| E11 | The adapter (0.3.2) has `ToolCallInterceptor`, which receives the **raw `CallToolResult`** (`isError` and the resource URI) and can retry, short-circuit or return a LangGraph `Command`. | The guarded executor is built **as an interceptor** instead of bypassing the adapter. This replaces the raw `ClientSession` workaround from S0b. |
| E12 | Without an explicit session the adapter opens **a new MCP session for every tool call**: a 0.23–0.30 s handshake, and the first call is slower (GitHub median 1.31 s fresh vs 0.61 s reused). | Open **one session per server per `/chat` turn**, lazily, and pass it to `load_mcp_tools(session=...)`. |
| E13 | `InMemorySaver` stores the full message list in every checkpoint, so it grows faster than linearly. In a synthetic test one session reached 98 MB after 50 turns without trimming and 27 MB with tool output trimmed. There is no pruning API; `delete_thread` frees everything. | Keep tool output out of `messages` (it lives in `evidence`). Keep only the last N messages. Cap evidence at 150 entries. Evict idle sessions with `delete_thread` (LRU by idle time). Measure under M7 load before choosing 512Mi or 1Gi. |
| E14 | Jev's `needs_clarification` yes/no question is **poorly calibrated** for this task: 0.39–0.58 on clear-cut cases. It caused 6 of 7 fallbacks in run 1. | Drop the question from the fallback rule. ~~Decide "clarify" in code when a recheck or revision has target `none`.~~ That code rule was **removed** after the student relabelled `q2` as `recheck` (**policy v3**, §7). The agent asks a clarifying question only when it can't resolve the PR's repository. |
| E15 | The TypeSafe SDK's default `RetryPolicy` allows **up to 30 s** of retries per call. An invalid request returned **400 `TypeSafeBadRequestError`**, not the documented 422. `jev-latest` resolved to **`jev-1.13.0`**. | Triage uses `RetryPolicy(max_retries=1, timeout≈2 s)` and records the concrete model string in traces. The failure map adds 400 next to 422. |

## 1. GitHub PR and commit tools (`github/`)
All calls returned `isError=False`.

| File | Call | Result |
|---|---|---|
| `list_prs_closed.json` | `list_pull_requests` state=closed, 30 per page, filtered fields | 30 PRs. The `additions` and `changed_files` fields are not returned by the list endpoint. |
| `pr_small_get.json` | `pull_request_read get` #2484 | Fork head `H-XX-D/...@af56548f47`, 2 commits, closed and not merged |
| `pr_small_files.json`, `pr_small_diff.json` | `get_files` and `get_diff` #2484 | **Empty** (`[]` and an empty string), with no error flag (E1) |
| `commit_fork_head_full.json` | `get_commit` with `detail=full_patch` on the fork's head SHA, through the base repo | Works: `backend/app/api/deps.py` +1/−1 |
| `pr_large_get.json` | `get` #2478 | 41 files changed, +5,388/−52, 7 commits |
| `pr_large_files.json`, `pr_large_files_page2.json` | `get_files` page 1 and page 2 | 30 + 11 files, all with patches; 147 KB + 76 KB (E2) |
| `pr_large_diff.json` | `get_diff` #2478 | 212 KB, untruncated (E2) |
| `list_commits_head.json` | `list_commits` with perPage=1 and fields=[sha] | Latest commit pinned: `e99fbaeb…` |
| `list_branches.json` | `list_branches` with perPage=5 | 4 branches. `master` is protected and its SHA matches the latest commit. |
| `search_code_scoped.json` | `search_code` for "get_current_user repo:fastapi/full-stack-fastapi-template" | 1 hit, `backend/app/api/deps.py`, blob SHA only (E7) |

**Rate limits:** the MCP responses don't expose GitHub's rate-limit headers. GitHub publishes 5,000 REST requests an hour for an authenticated token and a separate, lower limit for code search; these figures are **published, not measured**. The budget allows ≤10 calls per turn, so the main risk is code search; M2 handles 429s.

## 2. Context7 coverage (`context7/`)

| Framework | Resolved ID | Versions | Docs query |
|---|---|---|---|
| FastAPI | `/websites/fastapi_tiangolo` (top result); `/fastapi/fastapi` has versions | 0.115.13, 0_116_1, 0.118.2, 0.122.0, 0.128.0 | OK at 0.115.13; snippet cites `blob/0.115.13` |
| FastAPI, version not listed | `/fastapi/fastapi/0.115.0` | — | "Version not found" text with `isError=False` (E3) |
| Starlette | `/kludex/starlette` | none listed | OK, unversioned (cites `blob/main`) |
| Express | `/expressjs/express` | v5.1.0, 4_21_2, v5.2.0 | OK at v5.1.0; cites `blob/v5.1.0` |
| NestJS | `/nestjs/nest` | v11_1_6, v10_4_15, v10_4_6, v11.1.16, v12.0.1 | v11.1.16 queried, but the snippet cites `blob/master` (E4) |

Response sizes were 1.9–6.5 KB. Quota is not shown in responses and is still unknown.

## 3. Tavily (`tavily/`)
- `tavily_search` (basic, 3 results): 4 KB, server `response_time` 0.97 s. It returned real fastapi-cache issues, including one where the cache ignored a header.
- `tavily_extract` (1 URL): 28.7 KB of raw content (E6).
- Neither response has a usage or credit field.

## 4. Benchmark repo candidates (`corpus/benchmark_candidates.json`)
Script: `scripts/probe_benchmark.py`. Every candidate could be read at a pinned SHA, and every manifest declares the expected framework.

| Batch | Repo | Status | Merged non-bot PRs (last 50 closed) | Proposed role |
|---|---|---|---|---|
| B1 | fastapi/full-stack-fastapi-template | active | 7 | small or medium (already verified) |
| B1 | polarsource/polar (`server/`) | active | 41 | large, oversized-repo case |
| B1 | Netflix/dispatch | **archived** (2025) | 24 | frozen history; auth and permission changes |
| B1 | nsidnev/fastapi-realworld-example-app | archived | 2 (README and CI only) | **dropped** |
| B2 | brocoders/nestjs-boilerplate | active | 8 | medium NestJS |
| B2 | immich-app/immich (`server/`) | active | 42 | large NestJS |
| B2 | Unleash/unleash | active | 3 in the window (mostly CI) | Express; use older PRs |
| B2 | lujakob/nestjs-realworld-example-app | active, old | 4 | small backup |
| B2 | gothinkster/node-express-realworld-example-app | active | 1 | backup |

The student may replace these with their own list. The final (decision, PR) pairs are chosen in M9.

## 5. S0d bake-off re-run (`bakeoff/`)
Setup:
- **Prompts:** the original 18 plus 7 Workflow C prompts (`eval/bakeoff_prompts_s0d.jsonl`), which require the right **GitHub tool**, not just the right server.
- **Tools bound:** 12, adding `pull_request_read`, `get_commit`, `list_pull_requests` and `search_pull_requests`.
- **Scoring:** first decision only, no execution; one run per model.

| Model | Selection correct | No-tool correct | Schema-valid calls | Errors / 429s | Median latency |
|---|---|---|---|---|---|
| nemotron-3-super-120b-a12b | **25/25** | 4/4 | 18/18 | 0 / 0 | 1.35 s |
| nemotron-3.5-lightning-30b-a3b | 24/25 (`c73` went to Tavily) | 4/4 | 18/18 | 0 / 0 | 0.92 s |

**D2 is confirmed:** super gets every Workflow C tool choice right. Per-row files: `rows_2026-10-06.jsonl`, `bakeoff_2026-10-06.csv`, `summary_2026-10-06.json`.

## 6. Structured `DecisionRecord` output (`structured/`)
Script: `scripts/probe_structured.py`.
- **Cases:** 3, built from real M0 evidence.
- **Modes:** `json_schema` and `json_object`.
- **Settings:** `max_tokens=2500`.

| Model | Valid / citations OK | Latency | Output tokens |
|---|---|---|---|
| super | **6/6 and 6/6** | 9.0–27.6 s (`json_schema`: 9.5–14.7 s) | 944–1,888 |
| lightning | 0/6 | 69–179 s, mostly cut off at the token limit | 401–2,500 |

In `json_schema` mode, super produced richer records (2–4 assumptions, against 1–2 in `json_object`) with similar or lower latency. See E8–E10.

## 7. Jev vs Nemotron triage (`jev/`)
**Setup:**
- **Script:** `scripts/probe_jev.py`.
- **Cases:** 30 labelled cases in `eval/triage_prompts.jsonl`, covering all 7 request types, with ledgers of 0, 1 or 2 stored decisions. **The labels were written by Claude and still need the student's review.**
- **SDK:** `typesafe-sdk` 0.7.2 with `AsyncTypeSafeClient`, `RetryPolicy(max_retries=1, timeout=5)`, `timeout=5`.
- **Jev:** one `system_one` call per case with three questions: `intent` (a Choice with structured criteria), `target_decision` (a Choice built from the ledger on each request) and `needs_clarification` (a Noul). Each case ran twice.
- **Nemotron super:** `json_object` mode with the same definitions.

**Run 1** (`rows_run1_max200.jsonl`, `summary_run1_max200.json`) is **not a fair comparison**. Nemotron's `max_tokens=200` starved its reasoning tokens, causing 11 of 30 failures with empty or cut-off content. That was a probe bug, kept here for the record. Jev's results in run 1 matched run 2.

**Run 2** (`rows.jsonl`, `summary.json`), with Nemotron at `max_tokens=1024`, `finish_reason=length` 0 times and a median of 179 output tokens:

| Metric | Jev (`jev-1.13.0`) | Nemotron super |
|---|---|---|
| Request type correct | 29/30 | 29/30 |
| Crossings between the tool and no-tool groups | 1 | 1 |
| Target decision correct (27 scored) | 27/27 | 27/27 |
| Latency p50 / p95 (from the laptop) | **0.117 s / 0.197 s** | 1.503 s / 4.544 s |
| Errors | 0 | 0 |
| Same answer across 2 runs | 29/30 | (1 run) |
| Mean confidence when correct / wrong | 0.963 / 0.86 | — |
| Input tokens | 32,074 for 30 cases (about 1.07k per call, about $0.000045 at $0.042/MTok) | — |

**The one miss** is `q2`, "Recheck our decision against the latest PR." with two stored decisions. Both models chose `recheck` and picked target `none`. The request is a recheck whose target can't be identified. My `clarify` label is arguably a policy decision rather than the classifier's job.

**Fallback policies:**
- **v1 (as designed):** fall back on a near-tie that crosses the tool/no-tool split, a near-tie between two real decisions, or a `needs_clarification` value between 0.35 and 0.65. **9/30 fallbacks**, nearly all triggered by the Noul, whose values sat between 0.39 and 0.58 even on clear-cut cases (E14).
- **v2:** drop the Noul from the rule, and add a code rule: a recheck or revision with more than 1 stored decision and target `none` becomes `clarify`. **0/30 fallbacks, 30/30 correct.** v2 was tuned on these same 30 cases after run 1, so **it must be confirmed on held-out cases in M3** before the number counts.

**Errors:** an empty `Choice` returned **HTTP 400 `TypeSafeBadRequestError`** ("Choice question must have at least one choice"), not 422 (E15).

**Models for this account:** `jev-latest` and `jev-preview`, both released 2026-09-10. `jev-latest` served as `jev-1.13.0`.

**Relabel by the student (2026-10-06, after run 2):** the student judged `q2` to be a `recheck` ("what is there to clarify"). That agrees with both models.
- **Code rule removed:** v2's code-side clarify rule would now turn a correct answer into a wrong one, so it is dropped. This is **policy v3**: v2's fallback triggers with no clarify rule. Clarification moves into the agent, which asks only when the PR's repository can't be resolved, for example "latest PR" with decisions on two repos.
- **Rescore** (`rescore_after_relabel.json`, saved rows only, no new calls): Jev 30/30, Nemotron 30/30, policy v3 30/30 with 0/30 fallbacks and 0 tool/no-tool crossings.
- **Caveat:** the label changed after seeing the answers, so this is not an independent test. Held-out validation in M3 still decides.

**D18 decision rule (set in the plan before the test):** keep Jev if it is at least as accurate as Nemotron and has lower p95. **Met: equal accuracy, about 23× lower p95. D18 is GO**, with Nemotron as the fallback and the v2 policy.

## 8. Library checks (`library/`)
- **Adapter interceptor (E11):** `langchain_mcp_adapters/interceptors.py` defines `ToolCallInterceptor` and `MCPToolCallRequest`. Interceptors run before `_convert_call_tool_result`, so they see raw `CallToolResult.isError` and the resource content.
- **Session per call (E12):** `session_overhead.json`.

| Server | Handshake (median) | Call on a fresh session | Call on a reused session |
|---|---|---|---|
| GitHub | 0.25 s | 1.31 s | 0.61 s |
| Context7 | 0.23 s | 1.93 s | 1.89 s |
| Tavily | 0.24 s | 0.70 s | 0.31 s |

- **Checkpoint growth (E13):** `checkpoint_growth.json` (offline, synthetic sizes). `langgraph` 1.2.13 with `langgraph-checkpoint` 4.2.0 has no checkpoint pruning API, only `delete_thread` and `adelete_thread`.

| Turns in one session | 10 | 20 | 50 |
|---|---|---|---|
| Tool output left in messages (20k chars) | 4.4 MB | 16.4 MB | 98 MB |
| Tool output trimmed (1k chars) | 1.3 MB | 4.7 MB | 27 MB |

## Still open after M0
- Rate-limit numbers for GitHub code search, Context7, Tavily and Jev (published figures only, or unknown).
- Context7 quota.
- Jev data retention, pricing and how long the key stays valid through grading.
- Cloud Run cold-start time and in-region latency (M1).
- Whether policy v2 holds on held-out cases (M3).
- **Student review of the 30 triage labels in `eval/triage_prompts.jsonl`.**
