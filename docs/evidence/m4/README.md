# M4 live evidence (Workflow A, FastAPI template)

Target: `fastapi/full-stack-fastapi-template` at `e99fbaeba3b55190156ebae525ad9d481d76677e` (from the M0 corpus).
Real MCP (GitHub) and real NIM Nemotron. Local uvicorn on port 8099. No secrets in these files (grepped).

| Run | Query | Wall time | Outcome |
|---|---|---|---|
| run1 | "Read pyproject.toml first, then the items route" | 66.2 s | **Failed.** Agent's final call returned empty text (`finish_reason=length`, 2048 max_tokens). `synthesize` raised `LengthFinishReasonError`. `render` raised. User saw the generic error. |
| run2 | same, after raising synthesize `max_tokens` to 4000, shortening the synthesis prompt, and letting `render` accept an empty agent text when a decision exists | 38.6 s | No crash. Stack detected (fastapi >=0.141.1, evaluated batch). **0 assumptions**: the agent spent all 5 tool rounds on commit/directory reads and never read `items.py`. Synthesizer said evidence was insufficient (no invention). |
| run3 | same, after adding "few rounds / no repeated directory listings / batch reads" to `REPO_REVIEW_NOTE`, and naming the file in the query | 49.3 s | **4 of 4 assumptions grounded** (quotes match the saved excerpt of `backend/app/api/routes/items.py`), 4 tests (not executed), stack label shown. |

## Limits (state these honestly)
- Only the structured "Decision review" block is machine-checked. The agent's free-text answer above it (e.g. its line numbers such as "line 20", and items 7-10) is not checked by `check_decision`.
- A matching quote proves the citation is real, not that the assumption is true. Status stays `unverified`.
- 49.3 s is close to the 50 s internal deadline; the last agent prose call took 16.7 s.
- One query on one repo, one run each. Not a benchmark.
- The pyproject excerpt is capped at 1500 characters; a truncated TOML fails to parse (stack detection returns none). Not hit here.
- Unit/pytest tests for the M4 modules do not exist yet; 3 older tests fail from M3 changes (render footer, guard structuredContent, api limit).

## Follow-up scenarios (2026-10-13)
After fixing the agent timeout, adding the one-sentence rule and putting the latest decision review into the agent prompt.
`scenario_attempt1/2_*`: before the fixes, turn 1 failed twice (agent LLM call exceeded the 30 s timeout). In attempt 1 the model also accepted a follow-up about "assumption A3" although no review existed.
`scenario_attempt3_*`: after the fixes, 3 turns in one session. Turn 1 full decision review (47.5 s, 4/4 grounded). Turn 2 quoted A3 and its file from the review. Turn 3 reported all assumptions matched.
`scenarios/`: one JSON per scenario.

| Scenario | Result | Time |
|---|---|---|
| s3 isolation: session A reviews a repo; session B asks "what did I ask earlier?" and "quote for A1?" | **Pass.** B knew nothing and leaked nothing. | B: 4.5 s, 6.1 s |
| s3 review in session A (two runs) | Run 1: decision review shown, but the agent's text was cut off at the length limit; 57.0 s. Run 2 (clean server log `server_rerun.log`): **synthesis timed out at 30 s, only the agent prose returned, no decision review; 61.8 s, over the 60 s limit.** | 57.0 s, 61.8 s |
| s4 no entry point named (auth flow) | Honest: said it had not read the auth files; 0 assumptions. | 33.2 s |
| s5 Express router | Honest but unhelpful: could not find the router source, 0 assumptions, stack not detected (never read package.json). 5 rounds spent. | 44.1 s, 27.1 s |
| s6 non-code ("capital of Australia", then "what did I just ask?") | **Pass.** Direct answer, no tools, correct recall. | 4.0 s, 4.0 s |
| s7 nonexistent repo | **Pass.** Clear "could not be found", no invented assumptions. | 8.2 s |

Notes: the first batch for s3 to s7 was served by a leftover process because port 8099 was in use, so that batch has no server log. s3 run 2 and s5 run 2 have a clean log. Latency is from a laptop, one run each.
Open problem: a repository review can exceed 60 s when the agent's last call (10 to 16 s) and the synthesis call (up to the 30 s timeout) both run long.
