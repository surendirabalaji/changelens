"""G0 access probe: real MCP tools/list and tools/call against one remote server.

Usage:
    python scripts/probe_mcp.py --server github
    python scripts/probe_mcp.py --server github --call get_file_contents \
        --args '{"owner": "...", "repo": "...", "path": "README.md"}' --label call_ok

Writes redacted evidence to docs/evidence/g0/<server>/. Secrets are loaded from
.env at runtime, sent only in HTTP headers, and scrubbed from everything this
script prints or saves.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

from dotenv import find_dotenv, load_dotenv
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

SECRET_VARS = ("LLM_API_KEY", "GITHUB_PAT", "TAVILY_API_KEY", "CONTEXT7_API_KEY")
EVIDENCE_ROOT = Path(__file__).resolve().parent.parent / "docs" / "evidence" / "g0"
PREVIEW_CHARS = 600


def server_config(name: str) -> tuple[str, dict[str, str]]:
    """Return (url, headers) for a server. Keys go in headers, never in the URL."""
    if name == "github":
        return "https://api.githubcopilot.com/mcp/", {
            "Authorization": f"Bearer {os.environ['GITHUB_PAT']}",
            "X-MCP-Readonly": "true",
        }
    if name == "context7":
        return "https://mcp.context7.com/mcp", {
            "CONTEXT7_API_KEY": os.environ["CONTEXT7_API_KEY"],
        }
    if name == "tavily":
        return "https://mcp.tavily.com/mcp/", {
            "Authorization": f"Bearer {os.environ['TAVILY_API_KEY']}",
        }
    raise SystemExit(f"unknown server: {name}")


def redact(text: str) -> str:
    """Replace any secret value that appears in text."""
    for var in SECRET_VARS:
        value = os.environ.get(var)
        if value:
            text = text.replace(value, f"[REDACTED:{var}]")
    return text


def describe(error: BaseException) -> str:
    """Flatten exception groups (raised by the SDK's task groups) into one line per leaf."""
    if isinstance(error, BaseExceptionGroup):
        return " | ".join(describe(sub) for sub in error.exceptions)
    return f"{type(error).__name__}: {error}"


def save(server: str, label: str, payload: dict) -> Path:
    out_dir = EVIDENCE_ROOT / server
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{label}.json"
    path.write_text(redact(json.dumps(payload, indent=2, default=str)) + "\n")
    return path


async def probe(server: str, tool: str | None, tool_args: dict, label: str) -> int:
    url, headers = server_config(server)
    meta = {"server": server, "url": url, "probed_at": datetime.now(timezone.utc).isoformat()}

    async with streamablehttp_client(url, headers=headers) as (read, write, _):
        async with ClientSession(read, write) as session:
            init = await session.initialize()
            meta["server_info"] = init.serverInfo.model_dump()

            if tool is None:
                listed = await session.list_tools()
                tools = [
                    {"name": t.name, "description": t.description, "inputSchema": t.inputSchema}
                    for t in listed.tools
                ]
                path = save(server, label or "tools_list", {**meta, "tool_count": len(tools), "tools": tools})
                print(f"{server}: {len(tools)} tools -> {path}")
                for t in tools:
                    print(f"  - {t['name']}")
                return 0

            result = await session.call_tool(tool, tool_args)
            content = [c.model_dump() for c in result.content]
            path = save(server, label or f"call_{tool}", {
                **meta, "tool": tool, "arguments": tool_args,
                "isError": result.isError, "content": content,
            })
            text = " ".join(c.get("text", "") for c in content if c.get("type") == "text")
            print(f"{server}.{tool}: isError={result.isError} -> {path}")
            print(redact(text[:PREVIEW_CHARS]))
            return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--server", required=True, choices=["github", "context7", "tavily"])
    parser.add_argument("--call", help="tool name to invoke; omit to list tools")
    parser.add_argument("--args", default="{}", help="tool arguments as JSON")
    parser.add_argument("--label", default="", help="evidence file name (without .json)")
    opts = parser.parse_args()

    load_dotenv(find_dotenv(usecwd=True))
    try:
        return asyncio.run(probe(opts.server, opts.call, json.loads(opts.args), opts.label))
    except Exception as error:  # report every failure shape without leaking secrets
        detail = redact(describe(error))
        save(opts.server, (opts.label or "probe") + "_exception", {"server": opts.server, "error": detail})
        print(f"{opts.server}: FAILED {detail}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
