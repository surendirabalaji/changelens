# PROCESS_LOG.md

## 1. AI tools used

- **Claude Code** (Anthropic) : I have extensively used Claude Code as my coding agent for the assignment. Initially the Claude was set to help me ideate, design, build, and verify an MCP-powered agent with session memory for deployment on Google Cloud Run. I used opus-5.5 as my model during the design and ideation phase since it needed strong reasoning and thinking skills. I also created two subagents :

    - **research-architect** (a custom Claude Code subagent, `.claude/agents/research-architect.md`). Runs on Opus 5.5. It is set up as a senior architect for ideation and system design checked against `requirements.md`. It can only read files (Read/Grep/Glob).
    - **coding-coach** (a custom Claude Code subagent, `.claude/agents/coding-coach.md`). Runs on Sonet-5.5. It is set up as a that teacher who teaches while I code. It explains a task and gives one step at a time (Guide mode, the default), reviews my changes (Review mode), and writes the code only when I explicitly ask (Implement mode).
    - **process-log-coach** (a custom Claude Code subagent, `.claude/agents/process-log-coach.md`). Runs on Sonnet. It reminds me to log progress at milestones and collects evidence into `docs/process-log-checkpoints.md`.

- **NVIDIA NIM `nemotron-3-super-120b-a12b`** as the runtime model during development.

- **OpenAI `gpt-5.4-mini`** as the runtime model in the final version and on Cloud Run.

- **Jev (TypeSafe AI) `jev-1.13.0`**, tested as a request classifier in M0. The running app does not use it.

- Real MCP servers at runtime: GitHub, Context7 and Tavily.

## 2. Development narrative

Before writing any code, I set up `requirements.md` (my summary of the assignment PDF), `CLAUDE.md`, and a `research-architect` subagent to act as a senior architect during ideation. It suggested several AI SaaS ideas. I rejected some because they couldn't use real MCP data without mocking. For example, an AI deployment-monitoring tool needed actual running services to feed it data. After several rounds of ideas I chose a developer "second brain", narrowed it into ChangeLens, and wrote a planning brief for it. Then I asked the architect for a design-only plan:

Before I started my development I did set up my `requirements.md` (my summary of the assignment PDF), `CLAUDE.md`, and a `research-architect` subagent to act as a senior architect during ideation. There were several suggestions of ideas it gave but I did discard many due to feasibility constraints and the requirements I had to meet to all the rubrics. After which I chose this idea of code reviewing agent with citations and evidences.

> "Design and plan ChangeLens using `CHANGELENS_ARCHITECTURE_PLANNING_BRIEF.md`. First read project-root `requirements.md`, the supplied assignment PDF, and the professor's clarification. … Stay in design/planning mode: do not implement application code … Distinguish verified facts, assumptions, optional features, and target metrics. … End with the most important unresolved design decisions and the precise evidence needed to settle them."

Then in the next stages I realized the previous Idea could be done within a Claude  session with web search enabled. Then I  gave a redesign brief to turn ChangeLens as a decision-memory layer for code review. It would remember what the programmer decided about a change and warn he/she when later code changes makes that decision stale. I ran tests with chosen MCP servers ( GitHub, Tavily and Context-7) which were the required ones to fetch me the data I need though the tools it had. Before any app code, I had real calls made to GitHub (12), Context7 (7) and Tavily (2), plus a model bake-off. Tested the latency and chose the budget constraints for the MCP servers. I also tested different models for development to check if I could get the results in seconds as it was a requirement.

I also laid out milestones to be achieved which helped me to develop the project incrementally in stages. M1 was meant for skeleton. M2 was for failure handling and M3 covered tool selection, chaining traces and M4 added evidence capture, stack detection, structured synthesis, and quote checking. During the development I faced struggles in structuring the response to make sure it is relevant and does not leak the tool call names. I also had issues when the tool calls were truncated due to the budget constraints I had. To address them I had to write helper functions and use prompts like

> "If a tool result ends with a note like [truncated: showing N of M "
    "characters], you saw only part of it. Say so.\n"
    "Only state what the tool results say. If you are inferring, say so.\n"

> "You cannot look anything more up in this turn. Do not call tools."
"Answer from what you already have. Say in plain words what you could not "
"check. Do not mention budgets, rounds or limits. Do not paste long tool "

I also faced issues when there were token limits for structured outputs. Had to find the right one to fit them. Finally during the verification on cloud run end to end I felt Nemotron model was taking too much time so switched to Chatgpt-5.4-mini.

## 3. Verification approach

I used automated tests, inspected real tool calls, and checked the deployed service after each step (step here refers to the steps under each milestone). The full  `pytest`  suite passed 104 tests, 26 of them resilience tests. Sometimes test cases failed due to the mismatch of the expected vs actual response. And sometimes due to the helper functions I used which removed the necessary contents unnecessarily.
To probe error handling, I used a stub MCP server to simulate an unavailable server (connection refused), HTTP 401 and 503 responses, slow tools, tool errors, malformed responses, and recovery. I also ran live failure scenarios with real servers. These checks exercised the failure paths after each step based on the changes done  beyond a successful request, and the evidence is saved in  `docs/evidence/`.

I looked at the actual MCP execution logs to find out what tools were used by the agent and how they were chained together. M3 development test execution logs were saved showing a reply where there was no need for any tools, then the GitHub API request followed by Context7, then Tavily Search. I had manually tested the circuit breaker to ensure that the connection retries does not hold up a lot of time. Had to choose the right deadline for each of the connections. Ran several test cases to make sure there is enough time in the allotted budget. Specified them in config file.

> tool_loop_stop_s: float  =  30.0
llm_max_retries: int  =  0
llm_timeout_s: float  =  30.0
max_tool_rounds: int  =  5
mcp_connect_deadline_s: float  =  5
mcp_retry_jitter_s: float  =  0.3
mcp_connection_timeout: float  =  10.0
mcp_open_budget_s: float  =  20.0
tool_call_timeout_s: float  =  15.0
breaker_failure_threshold: int  =  2
breaker_cooldown_s: float  =  30.0

Each milestone had 7 steps. So after each step I had checks to be completed whose results were given to the LLM-as-judge and I personally read the logs to ensure everything was as expected. I had also checks where it checked when the mcp urls were configured with wrong urls.

> Start the app with Tavily's URL pointing at nothing, then ask for something that needs web search:
TAVILY_MCP_URL=http://127.0.0.1:9/mcp/ uvicorn main:app --port 8099
curl -s localhost:8099/chat -H 'content-type: application/json' \
  -d '{"query":"What is the top news about Python today?","session_id":"down-1"}'
The setting is tavily_mcp_url in changelens/config.py, so the environment variable TAVILY_MCP_URL overrides it.

Strored the evidence of each milestone in `evidence` folder. I also inspected the latency and response structure whether it mentioned the sources correctly. When tools were unavailable initially the response was revealing that that tool was not available and could not answer it. Which was harmful, so I added prompts to ensure this did not happen.

During the final check I felt Nemotron was too slow due to its time consuming nature during thinking process. This was supported by the tests I ran with evaluation scripts. I choose to use   `gpt-5.4-mini`  which I evaluated on no-tool requests, tool-needed requests, chained calls, conversation memory, session isolation, and grounded repository reviews. It passed 9/9 no-tool cases, 12/12 tool-needed cases, 5/5 chaining cases, and 5/5 memory and isolation cases. Seven of 8 assumptions were grounded, and none of the 50 turns took longer than 60 seconds.  Repeated these reviews, with three runs per repository, produced 4/6, 4/6, and 5/6 usable reviews across successive batches. The quote checker never marked an unverified quote as verified.

After redeployment, I checked Cloud Run health, non-code responses, tool use, recall, session isolation, HTTP 422 validation, a repository review, and a follow-up. The live review produced four grounded assumptions in 10.8 seconds. Cold starts took 30.8 seconds for a review and 12.7 seconds for health. Evaluation and live evidence are in  `docs/evidence/eval/`  and  `docs/evidence/live/`.

## 4. What I learned

Learned how to use Claude Code in a right way for assistance in development. Learned to create subagents and test them . Learned to evaluate each step I developed. The most important thing was I learned to judge the code my coding agent gave and identify where it could go wrong and reiterate till I get all my criteria met. I also learned different ways to evaluate an AI agent.
