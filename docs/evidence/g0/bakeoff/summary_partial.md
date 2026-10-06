# S0c LLM bake-off: partial results (2026-10-06)

**Status:** partial. The run was stopped by the student after 4 of 6 models, at about 37 minutes in. `moonshotai/kimi-k3` and `mistralai/mistral-large` were not tested. The script (`scripts/bakeoff_llm.py`) writes its CSV and JSON only when it finishes, so per-prompt rows were not saved. The table below is copied from the script's printed per-model summaries.

## Setup
- **Prompts:** 18 labelled prompts in `eval/bakeoff_prompts.jsonl`:
  - 4 no-tool;
  - 4 GitHub;
  - 3 Context7;
  - 3 Tavily;
  - 2 clarify;
  - 2 chained first steps (expected first call: GitHub).
- **Tools bound:** 8 real schemas from the S0b `tools/list` dumps:
  - GitHub: `get_file_contents`, `search_code`, `list_commits`, `search_issues`;
  - Context7: `resolve-library-id`, `query-docs`;
  - Tavily: `tavily_search`, `tavily_extract`.
- **Scoring:** only the model's first decision. No tool was executed, so this is a selection test, not MCP integration evidence.
  - A reply with no tool call counts as "clarify" if it contains a `?`, and "none" otherwise.
  - Tool arguments are validated with `jsonschema` against the server's declared `inputSchema`.
- **Endpoint and settings:** NVIDIA NIM through its OpenAI-compatible endpoint; `temperature=0`, `max_tokens=512`, 90 s timeout, about 1.6 s pause between calls.
- **Sample:** one run per model. With n=18, differences of one or two prompts are within noise.

## Results

| Model | Selection correct | No-tool correct | Schema-valid tool calls | API errors | HTTP 429 | Median latency |
|---|---|---|---|---|---|---|
| `nvidia/nemotron-3-ultra-550b-a55b` (PDF-tested) | 15/18 | 2/4 | 11/11 | 1 | 0 | 4.91 s |
| `nvidia/nemotron-3.5-lightning-30b-a3b` (PDF-tested) | 16/18 | 3/4 | 12/13 | 0 | 0 | 5.12 s |
| `nvidia/nemotron-3-super-120b-a12b` (current default) | **17/18** | **4/4** | **12/12** | 0 | 0 | **1.36 s** |
| `openai/gpt-oss-20b` | 15/18 | 4/4 | 7/10 | 0 | 0 | 2.46 s |

The cause of the one API error for Nemotron 3 Ultra was not captured, because per-row details were lost when the run was stopped.

## Decision (D2)
- Keep `nvidia/nemotron-3-super-120b-a12b` as the model, which is already the default in `.env.example`. It had the best selection, no-tool and schema-validity scores, and the lowest latency, in this sample.
- **Caveat:** this rests on a small, single run. S4's live selection tests continue to check the choice, and D2 can be revisited if they show problems.
