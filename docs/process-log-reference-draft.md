<!-- REFERENCE DRAFT ONLY. Facts come from the repo, commits and sessions.
     Rewrite it in your own words before it becomes PROCESS_LOG.md.
     Every [YOU: ...] is something only you can supply. Delete this banner. -->

# PROCESS_LOG.md

## 1. AI tools used

- **Claude Code** (Anthropic) for design discussion, step-by-step coaching, code review, test and evaluation runs, and README text. Opus 5.5 in the early sessions and Sonnet 5.5 in the later ones. It also ran three subagents: `research-architect` (design plans), `coding-coach` (guided steps) and `process-log-coach` (checkpoints).
- **NVIDIA NIM `nemotron-3-super-120b-a12b`** as the runtime model during development.
- **OpenAI `gpt-5.4-mini`** as the runtime model in the final version and on Cloud Run.
- **Jev (TypeSafe AI) `jev-1.13.0`**, tested as a request classifier in M0. The running app does not use it.
- Real MCP servers at runtime: GitHub, Context7 and Tavily.
- [YOU: any other AI tool you used outside these sessions, or write "none".]

I wrote most of the M1 to M4 code myself in step-by-step mode, and Claude reviewed it and found bugs. Claude wrote `changelens/report.py`, the render addition, the evaluation script, the test fixes, the README text and the diagram source when I asked it to. [YOU: correct this split if it is not accurate.]

## 2. Development narrative

I started by asking for a design before any code, and ended up with a LangGraph and FastAPI agent using GitHub, Context7 and Tavily over real MCP. Early on I told Claude, "I have never built AI projects before, when you give a task explain code references for each step," and that changed how every later step was taught. M1 to M3 gave me a deployed agent, failure handling tested with a stub server, and traces of tool choice and chaining. For M4 I built a repository review that saves each file it reads, then checks every quote against the saved text.

The first real review on Nemotron failed after 66 seconds because a 2,048-token limit cut off the structured output. After fixing that, the agent used all its tool rounds on directory listings and found nothing. Later runs timed out waiting for the model. I tried "what if I change the model to chatgpt models," tested `gpt-5.4-mini`, and the same review dropped to about 11 seconds. [YOU: one sentence on how you decided, and what you checked first.]

My own mistakes were mostly small: `async` on helper functions, the wrong data type, a boolean written backwards, and a graph edge left in twice. Claude's review caught them, and each one broke a test or a live run before I understood it. [YOU: name the one that took longest and how you found it.]

## 3. Verification approach

I did not rely on one successful run. `pytest` passes 104 tests, including 26 resilience tests that inject connection refusals, a 401, a 503, a slow tool, a tool error and a malformed response against a stub server. I ran an evaluation against the real servers: 9 of 9 no-tool queries made no tool calls, 12 of 12 tool queries used an accepted server, 5 of 5 chained queries used both servers, and recall and session isolation passed 5 of 5. Of 8 assumptions in four reviews, 7 had a quote that matched the saved text and one was shown as not verified. I deployed to Cloud Run and tested health, a normal question, recall, isolation, an invalid request and a full review (10.8 seconds warm, 30.8 seconds from a cold start).

The limits: one run per query, laptop timings, query labels written by Claude, and repeated reviews on two repositories varied between 1 and 3 usable out of 3. Only the structured review is checked by code, not the free text above it. The repair step for failed quotes never ran in a live test. Evidence is in `docs/evidence/`.

## 4. What I learned

[YOU: 2 to 3 sentences about what the AI tools could not do and you had to work out. Ideas from the record, if any are true for you: a plausible-looking answer that was wrong until you ran it; choosing the model from measured times, not from a recommendation; deciding what counted as "verified". Write only what you actually experienced.]
