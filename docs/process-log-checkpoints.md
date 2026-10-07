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
