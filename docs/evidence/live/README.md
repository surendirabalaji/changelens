# Live Cloud Run checks (2026-10-13)

Service: https://changelens-g7b7dxmyuq-uw.a.run.app (model gpt-5.4-mini). Raw responses: `live_checks.json`.
Plain HTTP requests from a laptop, one run each.

| Check | Result | Time |
|---|---|---|
| GET /health (first request after deploy) | 200 `{"status":"ok"}` | 0.1 s |
| Non-code question ("capital of Australia") | "Canberra", no tools | 3.4 s |
| Library question | Answered with a Context7 source | 9.0 s |
| Recall: give code word, then ask for it (same session) | Returned `PELICAN-42` | 3.3 s, 3.5 s |
| Isolation: another session asks for the code word | "no code word appears in the conversation" | 3.7 s |
| Invalid body (missing session_id) | HTTP 422 with the explanatory message | 0.1 s |
| Repository review (FastAPI template, pinned commit) | 4 of 4 assumptions grounded, 3 tests, stack `fastapi >=0.141.1` evaluated batch | 10.8 s |
| Follow-up in the review session | Answered from the saved review | 3.9 s |

Limits: the service had just been deployed, so the first health call was fast and a true cold start was NOT measured. One run per check. The follow-up answer about "not verified" items mixed the quote check with real-world doubts from the review text.
