# Process log checkpoints (internal evidence ledger, NOT the submission)

Statuses: pending | student-confirmed | documented (cite PROCESS_LOG.md section)
Rule: a milestone is "documented" only after PROCESS_LOG.md reflects it.
Each entry: ID, date, type, summary, evidence paths, AI tools, status, open questions, next baseline.

---

## CP-001 | 2026-10-05 | Architecture decision (design phase)

- **Baseline:** none (first checkpoint). Not a git repo, so there is no commit ref. Time of day unknown; the brief was last modified Oct 5 14:45.
- **Milestone:** the research-architect subagent produced an architecture plan from the planning brief. The student approved it. No application code was written, no commands or installs were run, and nothing was deployed.
- **Prompt (excerpt, student to Claude Code):**
  > "Design and plan ChangeLens using `CHANGELENS_ARCHITECTURE_PLANNING_BRIEF.md`. First read project-root `requirements.md`, the supplied assignment PDF, and the professor's clarification. ... Stay in design/planning mode: do not implement application code, edit the repository, run commands ... Distinguish verified facts, assumptions, optional features, and target metrics. ... End with the most important unresolved design decisions and the precise evidence needed to settle them"
- **Decisions in the plan (all provisional, per the plan's own register):**
  - D1: LangGraph + FastAPI + langchain-mcp-adapters.
  - D3: GitHub remote MCP, read-only, with a PAT limited to public repos.
  - D4: Context7 (highest risk).
  - D5: Tavily.
  - D6: InMemorySaver with thread_id = session_id.
  - A citation-verification node.
  - Seven evaluation metrics with baselines.
  - Gates G0–G5 and 14 register entries (D1–D14). D2 (the LLM) is blocked on credentials.
- **Architect flags (raised by the AI, not by the student):**
  - The professor's clarification is missing; only the brief's summary of it exists.
  - `changelens-concept.html` is missing.
  - The PDF's sample Dockerfile may break when run as a non-root user. UNVERIFIED; checked at G0.
  - requirements.md leaves out items the PDF includes: `--allow-unauthenticated`, the "what did I ask you last" test, "manifest reachable at runtime", and the AI-voice warning. The coach confirmed these are absent from requirements.md but did not re-read the PDF.
  - Context7 is not on the PDF's list of confirmed servers.
  - D14: the architect recommends an early skeleton deploy, which departs from the brief's "deploy last" order.
  - After approval, the assistant did not start coding, because the brief reserves implementation for a later phase.
- **Evidence:**
  - Plan: `/Users/surensfolder/.claude/plans/research-architect-agent-pasted-content-validated-moler.md` (§7–9). It lives outside the project; consider copying it into `docs/`.
  - `CHANGELENS_ARCHITECTURE_PLANNING_BRIEF.md`
  - `requirements.md`
  - `.claude/agents/research-architect.md`
- **AI tools observed:**
  - Main session: Claude Code on Opus 5.5 (`claude-opus-5-5`).
  - research-architect subagent: `model: opus` in its frontmatter.
  - process-log-coach subagent: `model: sonnet` in its frontmatter.
  - The student says research-architect runs on Opus 5.5 and process-log-coach on Sonnet. This matches the `opus` and `sonnet` aliases in the frontmatter.
  - Tools used outside this session (for example, to draft the brief, requirements.md or the agent files): UNCONFIRMED. Ask the student.
- **Student-provided context (2026-10-05, the student's account, summarized):**
  - Before the project started, the student wrote `requirements.md`, `CLAUDE.md` and `.claude/agents/research-architect.md` (a senior-architect persona for ideation that fits the assignment).
  - research-architect proposed several AI SaaS ideas. Some were dropped because they would have depended on mocked MCP behaviour.
  - After several ideation rounds, the student chose the "second-brain" idea. Per brief line 7, ChangeLens is the developer-focused scope of that idea.
  - The student also set up the process-log coach to remind them to log at regular intervals.
  - Supporting evidence: brief line 187 records the professor rejecting a student-built app with planted incidents, which likely relates to the mocking constraint. The student should confirm this link.
  - Rejected example (student, 2026-10-05): AI deployment monitoring, which needed actual running services to feed it data.
  - Not yet captured: how many rounds there were and their dates. The earlier ideation sessions left no files in the project.
- **Verification performed:** NONE. G0 has not started.
- **Reminder:** delivered 2026-10-05.
- **Status:** DOCUMENTED. The student reviewed it on 2026-10-05 and removed the "other tools" note, so the AI tools list is final for this phase. PROCESS_LOG.md §1 (AI tools), §2 (design-phase paragraph and prompt) and §3 (no verification yet). The student asked Claude to add the prompt and supporting content, built from the student's own statements. §4 (What I learned) is left for the student.
- **Open student questions:**
  - Q1: Did you change, question or reject anything in the plan before approving it, such as D14 vs. "deploy last" or the choice of servers? Why?
  - Q2: Do you have the professor's clarification or the concept HTML? What do they say about hosted third-party servers?
- **Next baseline:** CP-001. The next checkpoint should cover the first G0 evidence (`tools/list` dumps, the PAT denial test, the non-root Dockerfile check) or any change to the plan.
- **Evidence gaps:** no commit refs; the coach did not re-read the PDF; the professor's clarification is missing; outside tool use is unconfirmed.

---

## CP-002 | 2026-10-06 | Architecture decision (v3 redesign, D18 Jev triage)

- **Baseline:** CP-001. Commits since CP-001:
  - 9017e7b: S0b probes.
  - 24e0aa4: S0b corpus check and the S0c harness.
  - 0b4a13f: S0c partial bake-off and the D2 decision.

  The v3 changes are committed on branch `design-v3-changelens`, branched from 0b4a13f. Time of day unknown.
- **Milestone:** the student pasted a redesign brief:
  - ChangeLens as a decision-memory layer for code review;
  - Workflows A, B and C;
  - DecisionRecord, Assumption and Evidence schemas;
  - evaluation batched by stack;
  - a comparison with Claude Code;
  - 11 deliverables.

  research-architect (Opus) produced `docs/architecture-plan-v3.md`. It kept D1, D2, D3–D5, D6, D8, D15, D17 and the raw ClientSession executor, and flagged conflicts F1–F9. The student rejected the first approval and added D18. No application code, tests or deployment this session.
- **Prompt (student, excerpt):**
  > "Before we begin building I want you to rework on the system and the design we have. The below is the redesign path I had in my mind. Read the existing sytstem design and rework to accomodate the below."
- **Student correction (student-reported, rejected first approval):**
  > "for request classifer let us try to use jev. Heard that it is doing a good job.What is the budget thing in the design?"
  - Claude explained the per-turn tool and time budget, the budget ledger and the daily cost cap.
  - The student supplied https://typesafe.ai/blog/introducing-system-one-models-and-jev. Claude fetched it:
    - a cloud "System One" model;
    - schema-typed outputs with confidence scores;
    - claimed 70–500 ms;
    - $0.042/MTok input.

    These are vendor claims only and are UNVERIFIED.
  - D18: Jev for the triage node, a Nemotron structured-output fallback, a `TRIAGE_BACKEND` switch, a Jev probe in M0 and a Jev-vs-Nemotron ablation.
  - Missing evidence: Jev API docs, rate limits, runtime labels, data retention.
  - The student then approved the revised plan.
- **Architect flags (raised by the AI):**
  - F1: the classifier vs the no-keyword-routing rule.
  - F2: a per-project ledger vs session-scoped memory, so the ledger is session-scoped only.
  - F3: "Tavily or Fetch". Keep Tavily, which was probed; Fetch is not probed.
  - F4: only `full-stack-fastapi-template` is a real backend app in the checked corpus.
  - F5: GitHub MCP has no compare or range-diff tool.
  - F6: 3 LLM nodes instead of 11, because of the NIM limit of about 40 requests/min.
  - F7: "reviewer effort" needs a human study. It is optional and no claim is made.
  - F8: the professor's clarification is still only paraphrased.
  - F9: `search_code` searches all of GitHub, so the design requires a `repo:` qualifier.
- **Evidence:**
  - `docs/architecture-plan-v3.md` (the full design is in the project).
  - `docs/design.md` (superseded note).
  - `.env.example` (placeholders for `JEV_API_KEY` and `TRIAGE_BACKEND`).
  - `CLAUDE.md` (current-design pointer).
  - Plan file: `/Users/surensfolder/.claude/plans/research-architect-agent-before-rustling-muffin.md`, outside the project.
  - Inputs the architect read: `docs/evidence/g0/**` (the S0b probes and `summary_partial.md`).
- **AI tools observed:**
  - Main session: Claude Code on Opus 5.5 (`claude-opus-5-5`).
  - research-architect subagent: `model: opus`.
  - process-log-coach: Sonnet 5.5 (`claude-sonnet-5-5`).
  - Jev: planned component only, not used yet.
  - Nemotron on NIM: planned and bake-off LLM. Confirm the exact model list for the S0c bake-off from `docs/evidence/g0/`.
- **Verification performed:** NONE for v3, which is design only. The S0b and S0c results exist in commits but the coach did not review them.
- **Reminder:** delivered 2026-10-06.
- **Status:**
  - v3 redesign and D18: PENDING. The student reported the rejection and the Jev decision; neither is in PROCESS_LOG.md yet.
  - S0b MCP probes (9017e7b, 24e0aa4): PENDING, undocumented.
  - S0c partial bake-off and D2 decision (0b4a13f): PENDING, undocumented.
  - PROCESS_LOG.md still reflects only the CP-001 design phase. The §2 narrative is estimated at about 210–230 words, so new entries will need condensing to stay within 200–300.
- **Open student questions:**
  - Q1 (carried over from CP-001): did you change or reject anything in the plan before approving it? Partly answered by the Jev change. D14 vs "deploy last" is still open.
  - Q2 (carried over from CP-001): do you have the professor's clarification or the concept HTML? F8 is still open.
  - Q3: why Jev for triage, and did the architect's answer change your mind about anything else?
  - Q4: which S0b and S0c results surprised you or changed D2?
- **Next baseline:** CP-002. The next checkpoint should cover the M0 evidence top-up (PR and commit tool traces, Context7 coverage, batch repos, S0d bake-off re-run, Jev probe) or any change to the plan.
- **Evidence gaps:**
  - Jev API docs, limits and data retention.
  - The coach did not read the contents of `docs/evidence/g0/**`.
  - Commit dates are unknown.

---

## CP-003 | 2026-10-06 | Verification milestone (M0 evidence top-up)

- **Baseline:** CP-002.
  - M0 is committed as `8865a22` on branch `m0-evidence`, branched from `design-v3-changelens` @ dac4cf0.
  - It is pushed, with draft PR #5 stacked on PR #4. PR #4 is open and not merged.
  - Time of day unknown.
- **Milestone:** M0 evidence top-up. Real calls to the GitHub, Context7 and Tavily MCP servers, the Nemotron LLMs on NIM and Jev, run before any application code. The coach read `docs/evidence/m0/README.md`, not the raw files or scripts. The student asked what M0/M1 mean and Claude explained.
- **Prompt (student, verbatim):**
  > "you propose and check the candidates now. Later I will change the list if mine is compatible.Go ahead and run the steps"
- **Student decisions before M0 (student-reported):**
  - Will merge PR #4.
  - Has the TypeSafe key, and wrote `TYPESAFE_API_KEY` into `.env` themselves. Claude never read `.env`.
  - The existing keys are valid.
  - Claude may fetch the TypeSafe docs.
  - The grader expects responses "under 60s preferably".
  - S0a (gcloud setup and budget alert) is done by the student.
  - The student will write PROCESS_LOG themselves.
- **Professor answer (F8 resolved; student-pasted; recorded in dac4cf0):**
  - A student-built simulated MCP server does not count.
  - Counting servers must "wrap real external systems or data sources".
  - The professor called the idea "gaming" the system.
  - The raw message is not saved in the repo.
- **Results** (as reported in the README; measured from the laptop, not Cloud Run):
  - **S0d bake-off:** Nemotron super 25/25 selection and 4/4 no-tool, 1.35 s median. Lightning 24/25. One run per model, first decision only. D2 is confirmed.
  - **Structured `DecisionRecord`:** super 6/6 valid in 9.0–27.6 s. Lightning 0/6 (cut off at the token limit, or timed out after up to 181 s).
  - **Jev vs Nemotron triage, 30 labelled cases:**
    - Both 29/30 on request type and 27/27 on target.
    - Jev p95 0.197 s against Nemotron's 4.544 s.
    - D18 is GO under the decision rule set before the test.
  - **Other measurements:**
    - A fork PR can return empty files and diff with `isError=False`.
    - Context7 reports a missing version as plain text, not an error.
    - Reusing a session saves about 0.25–0.7 s per call.
    - `InMemorySaver` reached 98 MB per session after 50 turns untrimmed (synthetic sizes, run offline).
  - **Design changes:** 15 findings (E1–E15) changed the design.
    - The executor becomes an adapter interceptor.
    - The synthesis reserve grows to 15 s and the tool loop stops at T+30 s.
    - Budgets use `asyncio.wait_for` with `max_retries=0`.
    - The Noul is dropped and a code-side clarify rule is added (policy v2).
- **Claude mistakes (worth logging honestly):**
  - (a) The first Jev-vs-Nemotron run used `max_tokens=200`, which starved Nemotron's reasoning and caused 11/30 false failures. Caught and re-run; kept as `rows_run1_max200.jsonl`.
  - (b) An edit failed to apply, so run 2 started with the bug. Claude stopped it and restarted.
  - (c) Policy v2 was tuned on the same 30 cases. Its 0/30 fallbacks and 30/30 correct need held-out validation in M3.
  - (d) The triage labels were written by Claude and need the student's review.
- **Evidence:**
  - `docs/evidence/m0/**`, with `README.md` as the summary.
  - `scripts/probe_*.py` and `scripts/bakeoff_llm.py`.
  - `eval/bakeoff_prompts_s0d.jsonl` and `eval/triage_prompts.jsonl`.
  - `docs/architecture-plan-v3.md`.
  - `requirements.txt` (typesafe-sdk 0.7.2).
- **AI tools observed:**
  - Main session: Claude Code on Opus 5.5 (`claude-opus-5-5`).
  - process-log-coach: Sonnet 5.5 (`claude-sonnet-5-5`).
  - Bake-off and runtime LLMs: `nemotron-3-super-120b-a12b` and `nemotron-3.5-lightning-30b-a3b`, through NIM.
  - Jev through `typesafe-sdk` 0.7.2, served as `jev-1.13.0` (the `jev-latest` alias).
  - AI use outside this session: UNCONFIRMED.
- **Verification performed:**
  - Real MCP, LLM and Jev calls:
    - GitHub 12, Context7 7, Tavily 2;
    - 9 benchmark repos;
    - 25 bake-off prompts × 2 models;
    - 6 structured cases per model;
    - 30 triage cases × 2 Jev runs.
  - Secret-pattern scan of the new evidence, scripts and prompts: clean.
  - `py_compile` on all scripts: pass.
  - **Limits:**
    - Latency measured from the laptop only.
    - One bake-off run per model.
    - Triage labels not yet reviewed by the student.
    - Policy v2 tuned on the test cases.
    - Checkpoint growth uses synthetic sizes.
    - No unit tests, session-isolation, multi-turn or failure-injection checks yet.
- **Reminder:** delivered 2026-10-06.
- **Status:**
  - M0 evidence top-up: PENDING.
  - F8 professor answer: PENDING (student-reported).
  - Still PENDING from CP-002: v3 redesign and D18; S0b probes (9017e7b, 24e0aa4); S0c bake-off and D2 (0b4a13f).
  - PROCESS_LOG.md was checked on 2026-10-06 and still reflects only the CP-001 design phase:
    - §1 lacks Nemotron, Jev and TypeSafe.
    - §3 still says nothing has been verified.
    - §2 is about 210–230 words, so the new material will need condensing.
- **Open student questions:**
  - Q1 (carried over from CP-002): D14, early skeleton deploy vs "deploy last".
  - Q2 (carried over from CP-001 and CP-002): the professor's clarification. Partly answered by the F8 reply; does more of it exist?
  - Q3–Q4 (carried over from CP-002): why Jev for triage; which S0b/S0c results surprised you or changed D2.
  - Q5: review the 30 labels in `eval/triage_prompts.jsonl`. Do you agree with labelling `q2` as "clarify"?
  - Q6: what surprised you most in M0, and did you accept or change any of its design consequences?
- **Next baseline:** CP-003. The next checkpoint should cover M1 (Cloud Run skeleton and live latency) or any change to the plan.
- **Evidence gaps:**
  - The coach did not read the scripts, raw JSONL or `docs/evidence/g0/**`.
  - Unknown: rate limits, Context7 quota, Jev data retention and how long the key stays valid.
  - Pending: held-out validation of policy v2 (M3) and Cloud Run measurements (M1).

---

## CP-004 | 2026-10-13 | Build phase M1 to M4 (Workflow A)

- **Baseline:** CP-003 (M0, 8865a22 / PR #5). Current: d95ff10 "m3 - completed" on feature/m3 (not merged); feature/m4 has uncommitted changes: M changelens/graph.py, state.py; new changelens/evidence.py, report.py, schemas.py, stack.py, triage.py; docs/evidence/m4/. Merged since CP-003: PR #6 (M1 skeleton and Cloud Run deploy), PR #7 (M2 failure handling).
- **Milestones reviewed:**
  - M1 skeleton and deploy: no evidence file in docs/evidence/; Cloud Run result unverified.
  - M2 resilience: docs/evidence/m2/resilience_run.txt (11 selected tests, 9 visible PASSED in lines 1-40), live logs A-app.log, B-app.log, A1-A5, B1-B2 (contents not read).
  - M3 tool selection and chaining: docs/evidence/m3/01_no_tool.txt, 02_manifest_context7_chain.txt (GitHub x3 then Context7, 9 tools from 3 servers loaded in 2.56 s), 03_tavily.txt; README diagrams (not checked against code).
  - M4 Workflow A: docs/evidence/m4/README.md. run1 failed at 66.2 s (LengthFinishReasonError, max_tokens 2048); run2 38.6 s, 0 assumptions; run3 49.3 s, 4/4 grounded, 4 tests not executed. Target fastapi/full-stack-fastapi-template @ e99fbae.
- **Student-reported (no artifact):** student wrote most code with Claude coaching in Guide mode; Claude wrote M4 step 7 (report.py/render) on explicit request and applied the Claude-proposed live-run fixes only as snippets the student pasted. Student fixed: async def on pure helpers, TypedDict vs BaseModel, wrong boolean in evidence.py, wrong object passed to detect_stack, deleted schema classes, missing graph edge, duplicate edge. Live-run bugs: max_tokens 2048 starving structured output; tool budget spent on directory listings.
- **Deviations:** no commit_memory node, no repair loop, no Jev triage (regex), no pytest files for M4 modules, 3 older tests failing since M3 (render footer text, guard structuredContent, api test).
- **AI tools observed:** Claude Code (main session); research-architect; coding-coach subagent (model not confirmed); process-log-coach Sonnet 5.5 (claude-sonnet-5-5); runtime nemotron-3-super-120b-a12b via NIM; Jev jev-1.13.0 (not wired into the app yet). Outside-session AI use: UNCONFIRMED.
- **Flags:**
  - PROCESS_LOG.md is at docs/PROCESS_LOG.md. requirements.md section 5 (line 127) says root of submission, and no root copy exists (confirmed 2026-10-13).
  - Log sections are stale (see Status).
- **Reminder:** delivered 2026-10-13.
- **Status:** ALL PENDING. PROCESS_LOG.md still covers only the CP-001 design phase (checked 2026-10-13: section 1 lacks Nemotron, Jev, coding-coach; section 3 says nothing verified; section 4 empty). Carried over pending from CP-001..003: v3 redesign and D18, S0b/S0c, M0 results, F8 professor answer.
- **Open questions (student, own voice):**
  - Q1. Which fixed bug took longest, and how did you find it?
  - Q2. What made you suspect max_tokens (run1) and the directory-listing budget (run2)? Which fix was yours?
  - Q3. Why did you ask Claude to write step 7, and what did you check afterwards?
  - Q4. Why was Jev triage deferred? Is it a time decision?
  - Q5. What did the AI coaching not resolve that you worked out yourself?
  - Q6. Any M1 evidence (Cloud Run URL, latency, curl output)? Did you decide to merge M3 before M4?
  - Carried from CP-003: triage labels review (Q5), Q6.
- **Next baseline:** CP-004. Next checkpoint covers the PROCESS_LOG.md update, M3 merge, M4 commit and tests, and any final submission review.
- **Evidence gaps:** no M1 evidence; m2/m3 contents beyond the excerpts not read; M4 raw run files and source not read by the coach; test run status after M3 unknown; Cloud Run latency unmeasured.
