
"""Show what a Tavily search really returns, and check which phrases appear in it.

Usage (from the repo root, with .venv active):
    python -m scripts.check_tavily_grounding "FastAPI README raw github"
    python -m scripts.check_tavily_grounding "FastAPI README" --find samuelcolvin --show 1500
    python -m scripts.check_tavily_grounding "FastAPI README" --args-json '{"max_results": 5}'

Prints the search result text only. It never prints settings, headers or keys.
"""
import argparse
import asyncio
import json
import sys

from langchain_mcp_adapters.client import MultiServerMCPClient

from changelens.config import get_settings
from changelens.errors import describe
from changelens.graph import message_text
from changelens.mcp_tools.connections import build_connections
from changelens.mcp_tools.loader import load_allowed_tools

TOOL_NAME = "tavily_search"

# Phrases taken from the model's reply that looked suspicious. Replace as needed.
DEFAULT_PHRASES = [
    "camo.githubusercontent.com",
    "logo-teal.png",
    "coverage-badge.samuelcolvin.workers.dev",
    "Standards-based",
    "Minimize code duplication",
    "Fast to code",
]


async def run(query: str, phrases: list[str], show: int, extra_args: dict) -> int:
    connections = build_connections(get_settings())
    if "tavily" not in connections:
        print("tavily: missing TAVILY_API_KEY")
        return 3

    client = MultiServerMCPClient(connections)
    async with client.session("tavily") as session:
        tools = await load_allowed_tools(session, "tavily")
        tool = next((t for t in tools if t.name == TOOL_NAME), None)
        if tool is None:
            print(f"tavily: tool {TOOL_NAME} not found")
            return 1

        message = await tool.ainvoke(
            {
                "type": "tool_call",
                "name": TOOL_NAME,
                "args": {"query": query, **extra_args},
                "id": "check-1",
            }
        )

    text = message_text(message.content)
    print(f"status={message.status} chars={len(text)}")
    print("--- result text (first {} chars) ---".format(show))
    print(text[:show])
    print("--- phrase check (case-insensitive) ---")
    lowered = text.lower()
    for phrase in phrases:
        found = "FOUND    " if phrase.lower() in lowered else "NOT FOUND"
        print(f"{found}  {phrase}")

    return 0 if message.status == "success" else 1


def main() -> int:
    parser = argparse.ArgumentParser(description="Check what a Tavily search returns.")
    parser.add_argument("query", help="the search query")
    parser.add_argument("--find", action="append", default=None,
                        help="phrase to look for in the result (repeatable)")
    parser.add_argument("--show", type=int, default=2000,
                        help="how many characters of the result to print")
    parser.add_argument("--args-json", default="{}",
                        help='extra tool arguments as JSON, for example \'{"max_results": 5}\'')
    options = parser.parse_args()

    try:
        extra_args = json.loads(options.args_json)
    except json.JSONDecodeError:
        print("--args-json is not valid JSON")
        return 2

    phrases = options.find if options.find else DEFAULT_PHRASES
    try:
        return asyncio.run(run(options.query, phrases, options.show, extra_args))
    except Exception as error:
        print(f"tavily: FAILED {describe(error)}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
