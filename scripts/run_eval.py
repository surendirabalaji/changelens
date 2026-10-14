"""Compact evaluation of ChangeLens against the real MCP servers and the real LLM.

Runs the compiled graph in-process, the same way changelens/api.py does, so each
turn reports which tools were called. Results go to docs/evidence/eval/.

Usage: python scripts/run_eval.py [section ...]
Sections: tool_selection chain memory groundedness scenarios (default: all)
"""
import asyncio
import json
import statistics
import sys
import time
from contextlib import AsyncExitStack
from pathlib import Path

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langgraph.checkpoint.memory import InMemorySaver

from changelens.config import get_settings
from changelens.context import TurnContext
from changelens.graph import build_graph
from changelens.mcp_tools.session import open_tools

OUT_DIR = Path("docs/evidence/eval")
TURN_TIMEOUT_S = 120

FASTAPI_TEMPLATE = (
    "https://github.com/fastapi/full-stack-fastapi-template "
    "at e99fbaeba3b55190156ebae525ad9d481d76677e"
)

NO_TOOL = [
    "What is the capital of Australia?",
    "What is 17 times 23?",
    "Explain what a circuit breaker pattern is in software.",
    "What is the difference between a list and a tuple in Python?",
    "Hi! What can you help me with?",
    "Explain optimistic versus pessimistic locking.",
    "Write a one-line Python function that reverses a string.",
    "What does REST stand for?",
    "Can you explain that again more simply?",
]

# (query, accepted servers). A pass needs at least one call to an accepted server.
TOOL_NEEDED = [
    ("List the 3 most recent commits of the repository encode/httpx.", {"github"}),
    ("What Python versions does tiangolo/fastapi declare support for in its pyproject.toml?", {"github"}),
    ("Show me the first lines of the README of expressjs/express.", {"github"}),
    ("What are the top-level directories in the repo fastapi/full-stack-fastapi-template?", {"github"}),
    ("According to library documentation, how do I define a background task in FastAPI?", {"context7"}),
    ("Look up the library documentation: how does Express's res.redirect work?", {"context7"}),
    ("Using library documentation, what does the httpx AsyncClient timeout parameter do?", {"context7"}),
    ("From the library documentation for pydantic, how do I define a field validator?", {"context7"}),
    ("What is the latest news about the newest FastAPI release?", {"tavily", "github"}),
    ("Search the web: what is the most recent stable version of Node.js?", {"tavily"}),
    ("Search the web for recent security advisories about the Python requests library.", {"tavily"}),
    ("Search the web: what was announced at the most recent PyCon US?", {"tavily"}),
]

# (query, servers that must all be used). A pass needs 2+ calls and every server.
CHAINS = [
    ("Read backend/pyproject.toml of fastapi/full-stack-fastapi-template, find the FastAPI version it requires, and then use library documentation to explain what Depends does.", {"github", "context7"}),
    ("Check which web framework gothinkster/node-express-realworld-example-app declares in package.json, then look up that framework's library documentation on how routing works.", {"github", "context7"}),
    ("Read tiangolo/fastapi's pyproject.toml to find the Starlette version it requires, then search the web for the latest Starlette release.", {"github", "tavily"}),
    ("Look at brocoders/nestjs-boilerplate package.json, find the NestJS version, and use library documentation to explain NestJS guards.", {"github", "context7"}),
    ("Find the SQLModel version in backend/pyproject.toml of fastapi/full-stack-fastapi-template, then use library documentation to show how to write a select query.", {"github", "context7"}),
]

# (turns, final-turn check on the lowercased response)
MEMORY = [
    (["My project is called Orion and it uses PostgreSQL.", "What database does my project use?"], lambda r: "postgres" in r),
    (["My favourite web framework is Django.", "What did I say my favourite framework is?"], lambda r: "django" in r),
    (["Remember the code word PELICAN-42.", "Unrelated: what is 2 plus 2?", "What was the code word I gave you?"], lambda r: "pelican-42" in r),
    (["What is the capital of Australia?", "What did I just ask you?"], lambda r: "capital" in r and "australia" in r),
]

REVIEWS = [
    ("fastapi-template", f"Review {FASTAPI_TEMPLATE}. Read backend/pyproject.toml and backend/app/api/routes/items.py. I want to change the list endpoint to cursor pagination. What assumptions could that break?"),
    ("polar", "Review https://github.com/polarsource/polar at a206238. Read server/pyproject.toml and find the file that lists items from the database. I want to add cursor pagination. What assumptions could that break?"),
    ("express-realworld", "Review https://github.com/gothinkster/node-express-realworld-example-app at 30b68e1. Read package.json and find the route that lists articles. I want to change pagination. What assumptions could that break?"),
    ("nestjs-boilerplate", "Review https://github.com/brocoders/nestjs-boilerplate at 9620f15. Read package.json and one controller that lists users. I want to change pagination. What assumptions could that break?"),
]


def percentile(values: list[float], pct: float) -> float:
    ordered = sorted(values)
    index = min(len(ordered) - 1, round(pct * (len(ordered) - 1)))
    return ordered[index]


async def run_turn(graph, query: str, session_id: str, with_tools: bool = True) -> dict:
    """Run one /chat-equivalent turn and describe what happened.

    The whole turn, including opening and closing the MCP connections, is
    bounded by HARD_TURN_TIMEOUT_S. `stage` records where a hang happened.
    """
    started = time.monotonic()
    record = {"session_id": session_id, "query": query}
    stage = {"name": "start"}
    stack = AsyncExitStack()

    async def attempt() -> None:
        stage["name"] = "open_tools"
        if with_tools:
            opened = await open_tools(stack)
            context = TurnContext(
                tools=opened.tools,
                tool_servers=opened.tool_servers,
                started_at=started,
                sources=opened.available,
                unavailable=opened.unavailable,
            )
            servers = opened.tool_servers
        else:
            context = TurnContext(tools=[], started_at=started)
            servers = {}

        stage["name"] = "graph"
        result = await graph.ainvoke(
            {"query": query},
            config={
                "configurable": {"thread_id": session_id},
                "recursion_limit": 2 * get_settings().max_tool_rounds + 10,
            },
            context=context,
        )

        messages = result["messages"]
        last_human = max(
            i for i, m in enumerate(messages) if isinstance(m, HumanMessage)
        )
        turn_messages = messages[last_human:]
        calls = [
            call["name"]
            for m in turn_messages
            if isinstance(m, AIMessage)
            for call in m.tool_calls
        ]
        call_args = {}
        for m in turn_messages:
            if isinstance(m, AIMessage):
                for call in m.tool_calls:
                    call_args[call["id"]] = call
        tool_log = []
        for m in turn_messages:
            if isinstance(m, ToolMessage):
                call = call_args.get(m.tool_call_id, {})
                tool_log.append({
                    "tool": m.name,
                    "args": call.get("args"),
                    "status": m.status,
                    "result_start": str(m.content)[:140].replace("\n", " "),
                })
        tokens = {"input": 0, "output": 0}
        for m in turn_messages:
            if isinstance(m, AIMessage) and m.usage_metadata:
                tokens["input"] += m.usage_metadata.get("input_tokens", 0)
                tokens["output"] += m.usage_metadata.get("output_tokens", 0)

        decision = None
        decision_id = result.get("active_decision_id")
        if decision_id:
            found = (result.get("decisions") or {}).get(decision_id)
            if found is not None:
                decision = {
                    "assumptions": len(found.assumptions),
                    "grounded": sum(1 for a in found.assumptions if a.grounded),
                    "tests": len(found.tests),
                }

        record.update(
            ok=True,
            response=result["response"],
            tools_called=calls,
            servers_called=sorted({servers.get(name, "?") for name in calls}),
            tokens_agent_calls=tokens,
            decision=decision,
            tool_log=tool_log,
            evidence_count=len(result.get("evidence") or {}),
            evidence_paths=[
                f"{e.path}@{e.revision[:7]}"
                for e in (result.get("evidence") or {}).values()
            ],
            stack=(result.get("repo_context") or {}).get("support"),
        )

    try:
        await asyncio.wait_for(attempt(), timeout=TURN_TIMEOUT_S)
    except asyncio.TimeoutError:
        record.update(ok=False, error=f"HARD TIMEOUT {TURN_TIMEOUT_S}s in stage '{stage['name']}'",
                      response="", tools_called=[], servers_called=[], decision=None)
    except Exception as error:
        record.update(ok=False, error=f"{type(error).__name__} in stage '{stage['name']}': {error}"[:300],
                      response="", tools_called=[], servers_called=[], decision=None)
    finally:
        stage["name"] = "close"
        try:
            await asyncio.wait_for(stack.aclose(), timeout=15)
        except BaseException as error:
            record["close_error"] = type(error).__name__
    record["seconds"] = round(time.monotonic() - started, 1)
    return record


def save(rows: list[dict], name: str) -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    with open(OUT_DIR / f"{name}.jsonl", "w") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")


async def tool_selection() -> list[dict]:
    graph = build_graph(InMemorySaver())
    rows = []
    for i, query in enumerate(NO_TOOL):
        row = await run_turn(graph, query, f"ev-notool-{i}")
        row.update(kind="no_tool", expected="no tool calls", passed=row["ok"] and not row["tools_called"])
        rows.append(row)
        print("no_tool", row["passed"], row["seconds"], row["tools_called"], flush=True)
    for i, (query, accepted) in enumerate(TOOL_NEEDED):
        row = await run_turn(graph, query, f"ev-tool-{i}")
        row.update(kind="tool_needed", expected=sorted(accepted),
                   passed=row["ok"] and bool(accepted & set(row["servers_called"])))
        rows.append(row)
        print("tool", row["passed"], row["seconds"], row["servers_called"], "want", sorted(accepted), flush=True)
    save(rows, "tool_selection")
    return rows


async def chain() -> list[dict]:
    graph = build_graph(InMemorySaver())
    rows = []
    for i, (query, needed) in enumerate(CHAINS):
        row = await run_turn(graph, query, f"ev-chain-{i}")
        row.update(kind="chain", expected=sorted(needed),
                   passed=row["ok"] and len(row["tools_called"]) >= 2 and needed <= set(row["servers_called"]))
        rows.append(row)
        print("chain", row["passed"], row["seconds"], row["servers_called"], "want", sorted(needed), flush=True)
    save(rows, "chain")
    return rows


async def memory() -> list[dict]:
    graph = build_graph(InMemorySaver())
    rows = []
    for i, (turns, check) in enumerate(MEMORY):
        sid = f"ev-mem-{i}"
        last = None
        for query in turns:
            last = await run_turn(graph, query, sid)
            rows.append({**last, "kind": "memory_turn"})
        passed = bool(last and last["ok"] and check(last["response"].lower()))
        rows.append({"kind": "memory_result", "session_id": sid, "passed": passed, "seconds": 0})
        print("memory", i, passed, flush=True)

    # Isolation: a code word given in one session must not appear in another.
    a = await run_turn(graph, "Remember the code word ZEBRA-77.", "ev-iso-A")
    a2 = await run_turn(graph, "What is the code word I gave you?", "ev-iso-A")
    b = await run_turn(graph, "What is the code word I gave you?", "ev-iso-B")
    rows += [{**a, "kind": "iso_turn"}, {**a2, "kind": "iso_turn"}, {**b, "kind": "iso_turn"}]
    own = "zebra-77" in a2["response"].lower()
    leak = "zebra-77" in b["response"].lower()
    rows.append({"kind": "memory_result", "session_id": "isolation", "passed": own and not leak,
                 "recalled_in_own_session": own, "leaked_to_other_session": leak, "seconds": 0})
    print("isolation own=", own, "leak=", leak, flush=True)
    save(rows, "memory")
    return rows


async def groundedness() -> list[dict]:
    graph = build_graph(InMemorySaver())
    rows = []
    for name, query in REVIEWS:
        row = await run_turn(graph, query, f"ev-review-{name}")
        row.update(kind="review", repo=name)
        rows.append(row)
        print("review", name, row["seconds"], row["decision"], "evidence", row.get("evidence_count"), flush=True)
    # Baseline: identical request, but no tools, so there is nothing to cite.
    base = await run_turn(graph, REVIEWS[0][1], "ev-review-baseline", with_tools=False)
    base.update(kind="review_baseline_no_tools", repo="fastapi-template")
    rows.append(base)
    print("baseline no tools", base["seconds"], base["decision"], flush=True)
    save(rows, "groundedness")
    return rows


async def empty_reviews() -> list[dict]:
    """Re-run the two reviews that produced 0 assumptions, with tool arguments logged."""
    graph = build_graph(InMemorySaver())
    rows = []
    for name, query in REVIEWS:
        if name not in ("express-realworld", "nestjs-boilerplate"):
            continue
        row = await run_turn(graph, query, f"ev-empty-{name}")
        row.update(kind="review", repo=name)
        rows.append(row)
        print("review", name, row["seconds"], row["decision"], flush=True)
    save(rows, "empty_review_debug")
    return rows


async def scenarios() -> list[dict]:
    graph = build_graph(InMemorySaver())
    rows = []

    async def go(label: str, query: str, sid: str):
        row = await run_turn(graph, query, sid)
        row.update(kind="scenario", scenario=label)
        rows.append(row)
        print("scenario", label, row["seconds"], flush=True)
        return row

    await go("no_entry_point", "Review https://github.com/fastapi/full-stack-fastapi-template and tell me what a change to the auth flow could break.", "ev-sc-noentry")
    await go("express_router", "Review https://github.com/expressjs/express and tell me what assumptions the router makes about request paths.", "ev-sc-express")
    await go("fake_repo", "Review https://github.com/this-owner/does-not-exist-12345 and list its assumptions.", "ev-sc-fake")
    await go("followup_1_review", REVIEWS[0][1], "ev-sc-followup")
    await go("followup_2_quote", "From the decision review you just gave me, what exact quote supports assumption A3, and which file is it from?", "ev-sc-followup")
    await go("followup_3_unverified", "Which of your assumptions are NOT verified, if any?", "ev-sc-followup")
    await go("followup_4_unknown_id", "What exact quote supports assumption A9?", "ev-sc-followup")
    await go("invalid_ask_new_session", "What exact quote supports assumption A1?", "ev-sc-nosession")
    save(rows, "scenarios")
    return rows


def summarize() -> str:
    def load(name):
        path = OUT_DIR / f"{name}.jsonl"
        return [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []

    lines = ["# Evaluation summary", ""]
    ts = load("tool_selection")
    no_tool = [r for r in ts if r["kind"] == "no_tool"]
    needed = [r for r in ts if r["kind"] == "tool_needed"]
    all_rows = list(ts)
    if ts:
        lines += ["## Tool selection",
                  f"- No-tool queries: {sum(r['passed'] for r in no_tool)}/{len(no_tool)} made 0 tool calls",
                  f"- Tool-needed queries: {sum(r['passed'] for r in needed)}/{len(needed)} called an accepted server",
                  f"- Overall: {sum(r['passed'] for r in ts)}/{len(ts)}",
                  "- Misses:"]
        for r in ts:
            if not r["passed"]:
                lines.append(f"  - [{r['kind']}] {r['query'][:80]} -> called {r['servers_called']} (want {r['expected']}) {r.get('error','')}")
        lines.append("")
    ch = load("chain")
    all_rows += ch
    if ch:
        lines += ["## Multi-step chaining",
                  f"- {sum(r['passed'] for r in ch)}/{len(ch)} made 2+ calls across every required server",
                  "- Misses:"]
        for r in ch:
            if not r["passed"]:
                lines.append(f"  - {r['query'][:80]} -> {r['tools_called']} servers {r['servers_called']} {r.get('error','')}")
        lines.append("")
    mem = load("memory")
    all_rows += [r for r in mem if r["kind"] in ("memory_turn", "iso_turn")]
    results = [r for r in mem if r["kind"] == "memory_result"]
    if results:
        lines += ["## Memory and isolation",
                  f"- {sum(r['passed'] for r in results)}/{len(results)} checks passed (recall sessions plus one isolation check)"]
        for r in results:
            if not r["passed"]:
                lines.append(f"  - FAILED: {r}")
        lines.append("")
    gr = load("groundedness")
    all_rows += [r for r in gr if r["kind"] == "review"]
    if gr:
        reviews = [r for r in gr if r["kind"] == "review"]
        with_record = [r for r in reviews if r.get("decision")]
        n_ass = sum(r["decision"]["assumptions"] for r in with_record)
        n_ok = sum(r["decision"]["grounded"] for r in with_record)
        lines += ["## Groundedness (check_decision)",
                  f"- Reviews that produced a decision record: {len(with_record)}/{len(reviews)}",
                  f"- Assumptions whose quote matched the saved file text: {n_ok}/{n_ass}",
                  f"- Assumptions flagged NOT VERIFIED: {n_ass - n_ok}"]
        for r in reviews:
            lines.append(f"  - {r['repo']}: {r['decision']} evidence={r.get('evidence_count')} stack={r.get('stack')} {r['seconds']}s {r.get('error','')}")
        base = [r for r in gr if r["kind"] == "review_baseline_no_tools"]
        if base:
            lines.append(f"- Baseline, no tools (same request): decision={base[0]['decision']}, evidence={base[0].get('evidence_count')}")
        lines.append("")
    sc = load("scenarios")
    all_rows += sc
    ok_rows = [r for r in all_rows if r.get("ok")]
    if ok_rows:
        lines += ["## Latency (seconds, laptop to real services, one run each)"]
        groups = {}
        for r in ok_rows:
            key = r.get("kind")
            groups.setdefault(key, []).append(r["seconds"])
        for key, vals in sorted(groups.items()):
            lines.append(f"- {key}: n={len(vals)} p50={statistics.median(vals):.1f} p95={percentile(vals, 0.95):.1f} max={max(vals):.1f}")
        over = [r for r in ok_rows if r["seconds"] > 60]
        lines.append(f"- Turns over 60 s: {len(over)}/{len(ok_rows)}")
        fails = [r for r in all_rows if not r.get("ok", True)]
        lines.append(f"- Turns that errored: {len(fails)}")
        tin = sum(r.get("tokens_agent_calls", {}).get("input", 0) for r in ok_rows)
        tout = sum(r.get("tokens_agent_calls", {}).get("output", 0) for r in ok_rows)
        lines.append(f"- Agent-call tokens over {len(ok_rows)} turns: input {tin}, output {tout} (excludes the separate synthesis call)")
        lines.append("")
    if sc:
        lines += ["## Scenario outputs", "See scenarios.jsonl (read the responses; these are judged by hand)", ""]
    return "\n".join(lines)


async def main(sections: list[str]) -> None:
    table = {"empty_reviews": empty_reviews, "tool_selection": tool_selection, "chain": chain, "memory": memory,
             "groundedness": groundedness, "scenarios": scenarios}
    default = [name for name in table if name != "empty_reviews"]
    for name in sections or default:
        await table[name]()
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    text = summarize()
    (OUT_DIR / "summary.md").write_text(text)
    print(text)


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1:]))
