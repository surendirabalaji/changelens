
import asyncio
import sys
from contextlib import AsyncExitStack

from langchain_mcp_adapters.client import MultiServerMCPClient

from changelens.config import get_settings
from changelens.errors import describe
from changelens.graph import message_text
from changelens.mcp_tools.connections import build_connections,ALLOWED_TOOLS
from changelens.mcp_tools.loader import load_allowed_tools
from changelens.mcp_tools.session import open_tools


SMOKE_CALLS: dict[str, dict] = {
    "context7": {
        "name": "resolve-library-id",
        "args": {
            "libraryName": "fastapi",
            "query": "dependencies",
        },
    },
    "github": {
        "name": "get_file_contents",
        "args": {
            "owner": "encode",
            "repo": "httpx",
            "path": "pyproject.toml",
        },
    },
    "tavily": {
        "name": "tavily_search",
        "args": {
            "query": "What is LangGraph?",
            "search_depth": "basic",
        },
    },
}

REQUIRED_ENV: dict[str, str] = {
    "context7": "CONTEXT7_API_KEY",
    "github": "GITHUB_PAT",
    "tavily": "TAVILY_API_KEY",
}


async def run(server: str) -> int:
    settings = get_settings()
    connections = build_connections(settings)

    if server not in connections:
        print(f"{server}: missing {REQUIRED_ENV[server]}")
        return 3

    client = MultiServerMCPClient(connections)

    async with client.session(server) as session:
        tools = await load_allowed_tools(session, server)

        expected = len(ALLOWED_TOOLS[server])
        actual = len(tools)

        print(
            f"{server}: connected, "
            f"allowed={actual}, expected={expected}"
        )

        for tool in tools:
            print(f"  - {tool.name}")

        if actual != expected:
            print(
                f"{server}: COUNT MISMATCH "
                f"(expected {expected}, got {actual})"
            )
            return 1

        call = SMOKE_CALLS[server]
        tool = next(
            (tool for tool in tools if tool.name == call["name"]),
            None,
        )

        if tool is None:
            print(
                f"{server}: smoke tool {call['name']} "
                "not found"
            )
            return 1

        print(f"{server}: calling {call['name']}")

        message = await tool.ainvoke(
            {
                "type": "tool_call",
                "name": call["name"],
                "args": call["args"],
                "id": "smoke-1",
            }
        )

        content = message_text(message.content)

        print(
            f"{server}: status={message.status} "
            f"tool_call_id={message.tool_call_id} "
            f"chars={len(content)}"
        )
        print(f"{server}: excerpt: {content[:200]!r}")

        return 0 if message.status == "success" else 1


async def run_all() -> int:
    async with AsyncExitStack() as stack:
        opened = await open_tools(stack)

        print(f"Available: {opened.available}")
        print(f"Unavailable: {opened.unavailable}")

        # The loader keeps the first occurrence of duplicate
        # tool names. Associate each name with its first server.
        owners: dict[str, str] = {}

        for server in ALLOWED_TOOLS:
            for name in ALLOWED_TOOLS[server]:
                owners.setdefault(name, server)

        grouped: dict[str, list[str]] = {
            server: [] for server in ALLOWED_TOOLS
        }

        for tool in opened.tools:
            server = owners.get(tool.name)
            if server is not None:
                grouped[server].append(tool.name)

        mismatch = False

        for server in ALLOWED_TOOLS:
            names = grouped[server]
            expected = len(ALLOWED_TOOLS[server])

            print(
                f"{server}: allowed={len(names)}, "
                f"expected={expected}"
            )

            for name in names:
                print(f"  - {name}")

            if server in opened.available and len(names) != expected:
                print(f"{server}: COUNT MISMATCH")
                mismatch = True

        print(f"Unavailable servers: {list(opened.unavailable)}")

        if opened.unavailable or mismatch:
            return 1

        return 0


def main() -> int:
    choices = (*SMOKE_CALLS, "all")

    if len(sys.argv) != 2 or sys.argv[1] not in choices:
        print(
            "usage: python -m scripts.smoke_mcp_tools "
            f"{{{'|'.join(choices)}}}"
        )
        return 2

    server = sys.argv[1]

    try:
        if server == "all":
            return asyncio.run(run_all())

        return asyncio.run(run(server))

    except Exception as error:
        print(f"{server}: FAILED {describe(error)}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
