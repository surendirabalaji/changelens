# Process Log — CSCI 599 Assignment 1 (ChangeLens)

## 1. AI tools used

- **Claude Code** (Anthropic CLI). Main session model: Claude Opus 5.5 (`claude-opus-5-5`).
- **research-architect** (a custom Claude Code subagent, `.claude/agents/research-architect.md`). Runs on Opus 5.5. It is set up as a senior architect for ideation and system design checked against `requirements.md`. It can only read files (Read/Grep/Glob).
- **process-log-coach** (a custom Claude Code subagent, `.claude/agents/process-log-coach.md`). Runs on Sonnet. It reminds me to log progress at milestones and collects evidence into `docs/process-log-checkpoints.md`.


## 2. Development narrative

**Design phase (Oct 4–5, 2026).** Before writing any code, I set up `requirements.md` (my summary of the assignment PDF), `CLAUDE.md`, and a `research-architect` subagent to act as a senior architect during ideation. It suggested several AI SaaS ideas. I rejected some because they couldn't use real MCP data without mocking. For example, an AI deployment-monitoring tool needed actual running services to feed it data. After several rounds of ideas I chose a developer "second brain", narrowed it into ChangeLens, and wrote a planning brief for it. Then I asked the architect for a design-only plan:

> "Design and plan ChangeLens using `CHANGELENS_ARCHITECTURE_PLANNING_BRIEF.md`. First read project-root `requirements.md`, the supplied assignment PDF, and the professor's clarification. … Stay in design/planning mode: do not implement application code … Distinguish verified facts, assumptions, optional features, and target metrics. … End with the most important unresolved design decisions and the precise evidence needed to settle them."

The plan it produced, which I approved, uses LangGraph + FastAPI with three MCP servers: GitHub, Context7 and Tavily. Memory is the LangGraph checkpointer keyed by `session_id`. Every decision in it is still provisional until it passes the access checks (gate G0).

<!-- Implementation entries go here. Keep the whole narrative to 200–300 words. -->

## 3. Verification approach

Nothing has been verified yet; the project is still in design. The first step is gate G0: list each MCP server's tools and make one real tool call, confirm the GitHub token can't read a private repo, and check that the Dockerfile works as a non-root user.

## 4. What I learned

<!-- 2–3 sentences in your own words: what the AI tools could not do that you had to work out yourself. -->
