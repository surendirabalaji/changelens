"""M0 probe: cost of a fresh MCP session per tool call vs a reused session.

langchain-mcp-adapters 0.3.2 opens and initializes a new session for every tool call
when no session is passed. For each server, times: connect+initialize, and a cheap
real tools/call, over a few repeats; then the same calls on one reused session.
Writes redacted evidence to docs/evidence/m0/library/session_overhead.json.
"""
from __future__ import annotations

import asyncio
import json
import statistics
import sys
import time
from pathlib import Path

from dotenv import find_dotenv, load_dotenv
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

sys.path.insert(0, str(Path(__file__).resolve().parent))
from probe_mcp import describe, redact, server_config  # noqa: E402

OUT = Path(__file__).resolve().parent.parent / "docs" / "evidence" / "m0" / "library" / "session_overhead.json"
REPEATS = 3
CALLS = {
    "github": ("list_commits", {"owner": "fastapi", "repo": "full-stack-fastapi-template", "perPage": 1, "fields": ["sha"]}),
    "context7": ("resolve-library-id", {"libraryName": "fastapi", "query": "dependencies"}),
    "tavily": ("tavily_search", {"query": "fastapi dependency caching", "max_results": 1}),
}


async def fresh(server: str) -> dict:
    url, headers = server_config(server)
    tool, args = CALLS[server]
    started = time.monotonic()
    async with streamablehttp_client(url, headers=headers) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            handshake = time.monotonic() - started
            result = await session.call_tool(tool, args)
            call = time.monotonic() - started - handshake
    return {"handshake_s": round(handshake, 3), "call_s": round(call, 3), "isError": result.isError}


async def reused(server: str) -> list[float]:
    url, headers = server_config(server)
    tool, args = CALLS[server]
    timings = []
    async with streamablehttp_client(url, headers=headers) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            for _ in range(REPEATS):
                started = time.monotonic()
                await session.call_tool(tool, args)
                timings.append(round(time.monotonic() - started, 3))
    return timings


async def main_async() -> int:
    load_dotenv(find_dotenv(usecwd=True))
    report = {"repeats": REPEATS, "note": "measured from the developer laptop, not Cloud Run", "servers": {}}
    for server in CALLS:
        try:
            runs = [await fresh(server) for _ in range(REPEATS)]
            reuse = await reused(server)
            report["servers"][server] = {
                "fresh_session_runs": runs,
                "median_handshake_s": statistics.median(r["handshake_s"] for r in runs),
                "median_call_on_fresh_session_s": statistics.median(r["call_s"] for r in runs),
                "reused_session_call_s": reuse,
                "median_call_on_reused_session_s": statistics.median(reuse),
            }
        except Exception as error:  # probe: record every failure shape
            report["servers"][server] = {"error": redact(describe(error))}
        print(server, json.dumps(report["servers"][server]), flush=True)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(redact(json.dumps(report, indent=2)) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main_async()))
