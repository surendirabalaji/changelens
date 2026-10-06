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
