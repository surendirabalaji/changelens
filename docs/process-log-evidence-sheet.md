# Evidence sheet for PROCESS_LOG.md

Facts only, gathered from the repo and the working sessions. This is not the log. Write the log yourself, in your own words. Anything marked ASK is something only you know.

## Section 1: AI tools used (facts)

| Tool | Used for | Version / model | Source |
|---|---|---|---|
| Claude Code (main session) | Design discussion, coaching, code review, test runs, evaluation scripts, README and docs | Opus 5.5 earlier (CP-003), Sonnet 5.5 in the final sessions | `docs/process-log-checkpoints.md` |
| `research-architect` subagent | Architecture and design planning (v1 to v3 plans) | not confirmed | `docs/architecture-plan-v*.md` |
| `coding-coach` subagent | Step-by-step guidance (Guide mode) for M1 to M4 | not confirmed | session |
| `process-log-coach` subagent | Checkpoints CP-001 to CP-004 | Sonnet 5.5 | `docs/process-log-checkpoints.md` |
| NVIDIA NIM `nemotron-3-super-120b-a12b` | Runtime LLM during M0 to M4 | as named | `docs/evidence/m0`, `m4` |
| OpenAI `gpt-5.4-mini` | Runtime LLM after the switch (evaluation, live service) | as named (you set it in `.env`) | `docs/evidence/eval`, `live` |
| Jev (TypeSafe AI) `jev-1.13.0` | Triage classifier tested in M0 only | `typesafe-sdk` 0.7.2 | `docs/evidence/m0/jev`; NOT used by the running app |
| MCP servers: GitHub, Context7, Tavily | Real tools called at runtime | hosted | `README.md` |
| ASK | Any other AI use (ChatGPT, Copilot, a chat tool for the PDF, anything else) | | |

Which parts were written how (from the sessions): you wrote most of the code in Guide mode for M1 to M4 steps 1 to 6, with Claude reviewing and finding bugs. Claude wrote `changelens/report.py`, the `render` addition, the evaluation script `scripts/run_eval.py`, the test fixes, the README text and the diagrams' Mermaid source, on your explicit request. Claude also made the later live-run fixes you approved (excerpt limits, the repair step, the prompt change). State the split yourself in your words.

## Section 2: Narrative material (200 to 300 words in total)

Timeline (git and checkpoints):
- M0 (Oct 5 to 7): design plans v1 to v3, MCP probes, a Nemotron vs Jev bake-off. Picked LangGraph, FastAPI, three MCP servers.
- M1: skeleton and first Cloud Run deploy (PR #6).
- M2: failure handling, circuit breaker, stub server, resilience tests (PR #7).
- M3 (`d95ff10`): tool selection and chaining traces, README diagrams.
- M4 (`69fed1d`): Workflow A (evidence capture, stack detection, structured synthesis, quote checking).
- Model switch from Nemotron to `gpt-5.4-mini`, the evaluation, the Cloud Run redeploy and live checks.

Real blockers, with evidence you can point to:
1. The first live review on Nemotron failed after 66 s. A 2,048-token limit starved the structured output. `docs/evidence/m4/run1_*`.
2. Run 2: no crash, but 0 assumptions. The agent spent all 5 tool rounds on directory listings. `run2_*`. Fixed with prompt rules in `REPO_REVIEW_NOTE`.
3. Run 3 worked (4 of 4 grounded, 49.3 s). But two more attempts failed on a 30 s model timeout (`scenario_attempt1/2_*`). Led to the timeout fallback and to the model switch.
4. The evaluation hung once for 28 minutes in an unguarded step. Led to a hard timeout in the runner. `api.py` has the same unguarded call (not fixed).
5. Nemotron vs Jev in M0: a first run used `max_tokens=200`, which starved Nemotron and gave 11 of 30 false failures. Caught and rerun. (From CP-003.)

Bugs you hit and fixed (your own account of how you found them):
`async def` on pure helpers (triage, `build_evidence`); `TypedDict` instead of `BaseModel`; `Field` imported from `dataclasses`; a wrong boolean in `evidence.py` (`a['x'] or b is None`); the wrong object passed to `detect_stack`; evidence key polluted with `repo_context`; deleted schema classes; a missing graph edge and a duplicate edge; a syntax error from a stray argument in `ingest`.

Prompts you wrote this session that you could quote (verbatim, copy from your own chat history):
- "I have never built AI projects before, when you give a task explain code references for each step." (Oct 7, also saved in memory)
- "Since I am new to the AI development, sometimes i find it hard to understand... Just explain what we are trying to achieve in a milestone or step and how we are trying to achieve."
- "what if I change the model to chatgpt models. I have api key"
- "make the changes yourself and give the questions I will test it myself"
- "ok Run the testing. Make sure you test all scenarios. And run the evaluation as well"
ASK: add a prompt from M1 or M2 only if you can paste it exactly.

## Section 3: Verification (what actually ran)

| What | Result | Where |
|---|---|---|
| `pytest` | 104 passed | repo |
| `pytest tests/resilience` (stub server: connection refused, 401, 503, slow tool, tool error, malformed response, recovery) | 26 passed | `docs/evidence/m2/` |
| Live failure runs with real servers (M2) | see files | `docs/evidence/m2/` |
| Tool-selection traces on real MCP (M3) | none / GitHub then Context7 / Tavily | `docs/evidence/m3/` |
| Evaluation on `gpt-5.4-mini` | 9/9 no-tool, 12/12 tool-needed, 5/5 chains, 5/5 memory and isolation, 7/8 grounded assumptions, 0 of 50 turns over 60 s | `docs/evidence/eval/summary.md` |
| Repeated reviews, 3 per repo | 4/6, then 4/6, then 5/6 usable; the quote check never showed an unverified quote as verified | `docs/evidence/eval/review_repeat3_*` |
| Live Cloud Run checks | health, non-code, tool, recall, isolation, 422, review (4/4 grounded, 10.8 s), follow-up | `docs/evidence/live/` |
| Cold start | review 30.8 s cold, health 12.7 s cold | `docs/evidence/live/cold_start.json` |

Limits to state: one run per query, laptop latency, I wrote the query labels and pass rules (review them), no baseline for tool selection, token counts exclude the synthesis call, the repair loop never fired in live runs, the follow-up answers about "not verified" mixed the quote check with real-world doubts, the agent's prose is not machine-checked, `api.py` has an unguarded MCP open.

Deviations to state plainly: no separate `commit_memory` node; no repair loop at first (added later); Jev triage not used (regex URL parsing instead, which is input parsing and not intent routing); Workflows B and C not built; M3 not merged until now; the model switched from Nemotron to `gpt-5.4-mini`.

## Section 4: What you learned (2 to 3 sentences, only yours)

Questions to answer in your own words:
1. Which bug took you longest, and how did you find it?
2. What did the AI get wrong, or what did you have to work out that it did not tell you?
3. Why did you switch the model, and what convinced you?
4. What would you do differently on the next project?

## Housekeeping before submission
- Move or copy the final log to `PROCESS_LOG.md` at the repo root (`requirements.md` §5).
- Keep §2 to 200 to 300 words.
- ASK: any M1 evidence (URL, curl, latency) from the first deploy?
