"""G0 probe: how langchain-mcp-adapters surfaces MCP results and errors to LangChain.

Loads tools from all three servers through MultiServerMCPClient (the layer the
agent will use) and invokes one success case and two error shapes:
an isError result (GitHub not-found) and a protocol-level McpError (Tavily bad args).
Writes redacted evidence to docs/evidence/g0/adapter/.
"""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

from dotenv import find_dotenv, load_dotenv
from langchain_mcp_adapters.client import MultiServerMCPClient

sys.path.insert(0, str(Path(__file__).resolve().parent))
from probe_mcp import describe, redact, save, server_config  # noqa: E402

CASES = [
    ("github", "get_file_contents", {"owner": "encode", "repo": "httpx", "path": "pyproject.toml"}),
    ("github", "get_file_contents", {"owner": "encode", "repo": "httpx", "path": "does/not/exist.py"}),
    ("tavily", "tavily_search", {"max_results": "many"}),
]


def connections() -> dict:
    result = {}
    for name in ("github", "context7", "tavily"):
        url, headers = server_config(name)
        result[name] = {"transport": "streamable_http", "url": url, "headers": headers}
    return result


async def run() -> list[dict]:
    client = MultiServerMCPClient(connections())
    findings = []
    for server, tool_name, args in CASES:
        tools = {t.name: t for t in await client.get_tools(server_name=server)}
        tool = tools[tool_name]
        record = {"server": server, "tool": tool_name, "arguments": args}
        try:
            output = await tool.ainvoke(args)
            record["outcome"] = "returned"
            record["output_type"] = type(output).__name__
            record["output_preview"] = redact(str(output)[:400])
        except Exception as error:
            record["outcome"] = "raised"
            record["exception"] = redact(describe(error))[:600]
            record["exception_type"] = type(error).__name__
        findings.append(record)
        print(json.dumps({k: record[k] for k in record if k != "arguments"})[:500])
    return findings


def main() -> int:
    load_dotenv(find_dotenv(usecwd=True))
    findings = asyncio.run(run())
    path = save("adapter", "error_surfacing", {"cases": findings})
    print(f"saved -> {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
