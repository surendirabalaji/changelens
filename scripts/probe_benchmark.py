"""M0 probe: are candidate benchmark app repos usable for batches B1/B2?

For each repo, through real GitHub MCP: metadata (language, size, archived, last
push), latest commit SHA, the dependency manifest read at that SHA (and whether it
declares the expected framework), and how many recent closed PRs are merged
non-bot changes (candidates for Workflow C rechecks).

Writes redacted evidence to docs/evidence/m0/corpus/benchmark_candidates.json.
"""
from __future__ import annotations

import asyncio
import re
import sys
from pathlib import Path

from dotenv import find_dotenv, load_dotenv
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

sys.path.insert(0, str(Path(__file__).resolve().parent))
import probe_mcp  # noqa: E402
from probe_corpus import first_json, text_of  # noqa: E402
from probe_mcp import describe, redact, server_config  # noqa: E402

# (batch, owner, repo, manifest paths to try in order, framework marker in the manifest)
CANDIDATES = [
    ("B1", "fastapi", "full-stack-fastapi-template", ["backend/pyproject.toml"], "fastapi"),
    ("B1", "Netflix", "dispatch", ["pyproject.toml", "setup.py", "requirements-base.txt"], "fastapi"),
    ("B1", "polarsource", "polar", ["server/pyproject.toml"], "fastapi"),
    ("B1", "nsidnev", "fastapi-realworld-example-app", ["pyproject.toml"], "fastapi"),
    ("B2", "gothinkster", "node-express-realworld-example-app", ["package.json"], '"express"'),
    ("B2", "brocoders", "nestjs-boilerplate", ["package.json"], "@nestjs/core"),
    ("B2", "Unleash", "unleash", ["package.json"], '"express"'),
    ("B2", "lujakob", "nestjs-realworld-example-app", ["package.json"], "@nestjs/core"),
    ("B2", "immich-app", "immich", ["server/package.json"], "@nestjs/core"),
]

BOT_TITLE = re.compile(r"(bump|update .* requirement|dependabot|renovate|pre-commit|lock file|deps)", re.I)


def resource_text(result) -> str:
    """Text of embedded resources (file contents) plus plain text parts."""
    parts = []
    for c in result.content:
        if getattr(c, "type", "") == "resource":
            parts.append(getattr(c.resource, "text", "") or "")
        elif getattr(c, "type", "") == "text":
            parts.append(c.text)
    return "\n".join(parts)


async def probe_repo(session: ClientSession, batch: str, owner: str, repo: str,
                     manifests: list[str], marker: str) -> dict:
    record = {"batch": batch, "repo": f"{owner}/{repo}"}

    meta = first_json(text_of(await session.call_tool(
        "search_repositories", {"query": f"repo:{owner}/{repo}", "perPage": 1}))) or {}
    items = meta.get("items") or meta.get("repositories") or []
    if items:
        item = items[0]
        record.update({
            "language": item.get("language"),
            "size_kb": item.get("size"),
            "stars": item.get("stargazers_count") or item.get("stars"),
            "archived": item.get("archived"),
            "pushed_at": item.get("pushed_at"),
        })

    commits = await session.call_tool("list_commits", {"owner": owner, "repo": repo, "perPage": 1, "fields": ["sha"]})
    match = re.search(r'"sha"\s*:\s*"([0-9a-f]{40})"', text_of(commits))
    if commits.isError or not match:
        record["status"] = "commit lookup failed"
        record["detail"] = redact(text_of(commits))[:300]
        return record
    record["sha"] = match.group(1)

    for manifest in manifests:
        contents = await session.call_tool(
            "get_file_contents", {"owner": owner, "repo": repo, "path": manifest, "sha": record["sha"]})
        if not contents.isError:
            body = resource_text(contents)
            uris = [str(c.resource.uri) for c in contents.content if getattr(c, "type", "") == "resource"]
            record.update({"manifest": manifest, "resource_uri": uris[0] if uris else None,
                           "framework_declared": marker.lower() in body.lower()})
            break
    else:
        record["manifest"] = None

    prs = await session.call_tool("list_pull_requests", {
        "owner": owner, "repo": repo, "state": "closed", "perPage": 50,
        "fields": ["number", "title", "merged_at"]})
    pr_items = first_json(text_of(prs)) or []
    merged = [p for p in pr_items if isinstance(p, dict) and p.get("merged_at")]
    human = [p for p in merged if not BOT_TITLE.search(p.get("title") or "")]
    record.update({
        "closed_prs_seen": len(pr_items),
        "merged_prs": len(merged),
        "merged_non_bot_prs": len(human),
        "sample_prs": [{"number": p["number"], "title": (p.get("title") or "")[:100],
                        "merged_at": p["merged_at"]} for p in human[:5]],
    })
    record["status"] = "ok" if record.get("manifest") and not record.get("archived") else "check"
    return record


async def run() -> list[dict]:
    url, headers = server_config("github")
    records = []
    async with streamablehttp_client(url, headers=headers) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            for batch, owner, repo, manifests, marker in CANDIDATES:
                try:
                    record = await probe_repo(session, batch, owner, repo, manifests, marker)
                except Exception as error:
                    record = {"batch": batch, "repo": f"{owner}/{repo}", "status": "exception",
                              "detail": redact(describe(error))}
                records.append(record)
                print(f"{record['batch']} {record['repo']:48} {record.get('language') or '?':11} "
                      f"{str(record.get('size_kb') or '?'):>8} KB archived={record.get('archived')} "
                      f"manifest={record.get('manifest')} fw={record.get('framework_declared')} "
                      f"merged_human_prs={record.get('merged_non_bot_prs')} {record['status']}")
    return records


def main() -> int:
    load_dotenv(find_dotenv(usecwd=True))
    probe_mcp.EVIDENCE_ROOT = probe_mcp.EVIDENCE_BASE / "m0"
    records = asyncio.run(run())
    path = probe_mcp.save("corpus", "benchmark_candidates", {"candidates": records})
    print(f"saved -> {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
