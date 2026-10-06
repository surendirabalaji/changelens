"""G0 probe: can candidate corpus repos be read at a pinned SHA through GitHub MCP?

For each repo: fetch metadata (language, size) via search_repositories, pin the
latest commit SHA via list_commits, then read the dependency manifest at that SHA
via get_file_contents. Writes redacted evidence to docs/evidence/g0/corpus/.
"""
from __future__ import annotations

import asyncio
import json
import re
import sys
from pathlib import Path

from dotenv import find_dotenv, load_dotenv
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

sys.path.insert(0, str(Path(__file__).resolve().parent))
from probe_mcp import describe, redact, save, server_config  # noqa: E402

CANDIDATES = [
    ("encode", "httpx", "pyproject.toml"),
    ("pallets", "click", "pyproject.toml"),
    ("fastapi", "full-stack-fastapi-template", "backend/pyproject.toml"),
    ("expressjs", "express", "package.json"),
    ("honojs", "hono", "package.json"),
    ("go-chi", "chi", "go.mod"),
    ("spf13", "cobra", "go.mod"),
    ("BurntSushi", "ripgrep", "Cargo.toml"),
]


def text_of(result) -> str:
    return "\n".join(c.text for c in result.content if getattr(c, "type", "") == "text")


def first_json(text: str):
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None


async def probe_repo(session: ClientSession, owner: str, repo: str, manifest: str) -> dict:
    record = {"repo": f"{owner}/{repo}", "manifest": manifest}

    meta = await session.call_tool("search_repositories", {"query": f"repo:{owner}/{repo}", "perPage": 1})
    data = first_json(text_of(meta)) or {}
    items = data.get("items") or data.get("repositories") or []
    if items:
        item = items[0]
        record["language"] = item.get("language")
        record["size_kb"] = item.get("size")
        record["stars"] = item.get("stargazers_count") or item.get("stars")

    commits = await session.call_tool("list_commits", {"owner": owner, "repo": repo, "perPage": 1})
    match = re.search(r'"sha"\s*:\s*"([0-9a-f]{40})"', text_of(commits))
    if commits.isError or not match:
        record["status"] = "commit lookup failed"
        record["detail"] = redact(text_of(commits))[:300]
        return record
    record["sha"] = match.group(1)

    contents = await session.call_tool(
        "get_file_contents", {"owner": owner, "repo": repo, "path": manifest, "sha": record["sha"]}
    )
    uris = [c.resource.uri for c in contents.content if getattr(c, "type", "") == "resource"]
    record["status"] = "error" if contents.isError else "ok"
    record["resource_uri"] = str(uris[0]) if uris else None
    if contents.isError:
        record["detail"] = redact(text_of(contents))[:300]
    return record


async def run() -> list[dict]:
    url, headers = server_config("github")
    records = []
    async with streamablehttp_client(url, headers=headers) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            for owner, repo, manifest in CANDIDATES:
                try:
                    record = await probe_repo(session, owner, repo, manifest)
                except Exception as error:
                    record = {"repo": f"{owner}/{repo}", "status": "exception", "detail": redact(describe(error))}
                records.append(record)
                print(f"{record['repo']:42} {record.get('language') or '?':11} "
                      f"{str(record.get('size_kb') or '?'):>7} KB  {record['status']:6} "
                      f"{(record.get('sha') or '')[:12]}")
    return records


def main() -> int:
    load_dotenv(find_dotenv(usecwd=True))
    records = asyncio.run(run())
    path = save("corpus", "corpus_access", {"candidates": records})
    print(f"saved -> {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
