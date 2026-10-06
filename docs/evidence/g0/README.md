# G0 / S0b: MCP access probe findings (2026-10-06)

The scripts that produced this evidence are `scripts/probe_mcp.py` (raw MCP SDK, mcp 1.30.0) and `scripts/probe_adapter.py` (langchain-mcp-adapters 0.3.2). Keys were loaded from `.env` at runtime, sent only in headers, and redacted from all output. A secret scan of this folder found no keys.

## Discovery (`tools/list`): all three servers reachable over streamable HTTP

| Server | Endpoint | Auth | Tools |
|---|---|---|---|
| GitHub | `https://api.githubcopilot.com/mcp/` with `X-MCP-Readonly: true` | Fine-grained PAT (public repos, read-only), Bearer header | 29 (read-only set) |
| Context7 | `https://mcp.context7.com/mcp` | `CONTEXT7_API_KEY` header | 2: `resolve-library-id`, `query-docs` |
| Tavily | `https://mcp.tavily.com/mcp/` | Bearer header | 5: `tavily_search`, `tavily_extract`, `tavily_crawl`, `tavily_map`, `tavily_research` |

The GitHub read-only set includes `get_file_contents` (files and directories), `search_code`, `list_commits`, `get_commit`, `issue_read` and `search_issues`. There is no dedicated tree tool; directory listings come from `get_file_contents` on a directory path.

## Invocation (`tools/call`)

| Case | File | Result |
|---|---|---|
| GitHub read a public file (`encode/httpx` `pyproject.toml`) | `github/call_ok.json` | `isError=False`. The file text arrives as an **embedded resource with a SHA-pinned URI** (`repo://encode/httpx/sha/<sha>/contents/pyproject.toml`). |
| GitHub read the private `surendirabalaji/changelens` | `github/pat_negative.json` | `isError=True`, **404**. The token cannot see the private repo, so the negative test passed. |
| GitHub missing file | `github/call_not_found.json` | `isError=True`, "file does not exist" |
| GitHub invalid arguments | `github/call_bad_args.json` | `isError=True`, "parameter owner is not of type string" |
| Context7 resolve `httpx` | `context7/call_resolve_ok.json` | `/encode/httpx`, versions 0.27.2 and 0.28.1 listed |
| Context7 version-pinned docs (`/encode/httpx/0.28.1`) | `context7/call_docs_ok.json` | Docs cite `github.com/encode/httpx/blob/0.28.1/...`, so version pinning works |
| Context7 invalid arguments | `context7/call_bad_args.json` | `isError=True`, input validation error |
| Tavily search | `tavily/call_ok.json` | Real results with URLs |
| Tavily invalid arguments | `tavily/call_bad_args_exception.json` | **Raised `McpError`** (JSON-RPC protocol error), not an `isError` result |

## Findings that change the design

1. **Errors arrive in two shapes.** GitHub and Context7 return `isError=True` results. Tavily raises a protocol-level `McpError`. The guarded executor must classify both.
2. **The adapter (0.3.2) hides `isError`.** Through `MultiServerMCPClient` tools, the GitHub not-found call *returned normally*, with no flag and no exception (`adapter/error_surfacing.json`). Tavily's `McpError` is still raised.
3. **The adapter drops the SHA-pinned resource URI.** The file text survives, but the `repo://…/sha/…` URI does not.
4. **Consequence for S1 (provisional):** the executor needs the raw `CallToolResult`. The options are an adapter hook, if one exists in 0.3.2, or keeping discovery in the adapter but invoking through an MCP `ClientSession`. Decide in S1.

## Not covered yet
- Corpus access: at least 5 repos across 3 or more languages at pinned SHAs.
- A real transport failure (unreachable endpoint). Planned for S3.
- How `search_code` truncates and paginates on large repos.
- Rate-limit figures.
