"""Render the project's Markdown docs to readable HTML next to each .md file.

The .md files stay the source of truth; the .html files are generated views.
Re-run after editing any doc:

    python scripts/render_docs.py

Renders docs/**/*.md (including docs/evidence/*/README.md) with CommonMark + GFM tables
and strikethrough, adds a table of contents, light/dark theme, Mermaid diagrams, and
rewrites links between rendered docs from .md to .html. Writes docs/index.html.
"""
from __future__ import annotations

import html
import re
import sys
from pathlib import Path

from markdown_it import MarkdownIt
from mdit_py_plugins.anchors import anchors_plugin

ROOT = Path(__file__).resolve().parent.parent
DOCS = ROOT / "docs"
MERMAID_CDN = "https://cdn.jsdelivr.net/npm/mermaid@11/dist/mermaid.min.js"

STYLE = """
:root {
  --bg: #fbfbfa; --surface: #ffffff; --text: #1f2328; --muted: #59636e; --border: #d8dee4;
  --accent: #0b6bcb; --code-bg: #f2f4f6; --row-alt: #f6f8fa; --mark: #fff3c4;
}
@media (prefers-color-scheme: dark) {
  :root:not([data-theme="light"]) {
    --bg: #0f1115; --surface: #161a20; --text: #e6e8eb; --muted: #9aa4af; --border: #2c333c;
    --accent: #6cb6ff; --code-bg: #1d232b; --row-alt: #1a1f26; --mark: #4a3f12;
  }
}
:root[data-theme="dark"] {
  --bg: #0f1115; --surface: #161a20; --text: #e6e8eb; --muted: #9aa4af; --border: #2c333c;
  --accent: #6cb6ff; --code-bg: #1d232b; --row-alt: #1a1f26; --mark: #4a3f12;
}
* { box-sizing: border-box; }
body { margin: 0; background: var(--bg); color: var(--text);
  font: 16px/1.65 -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif; }
.layout { display: grid; grid-template-columns: 1fr; max-width: 1280px; margin: 0 auto; padding: 0 16px; }
@media (min-width: 1100px) { .layout { grid-template-columns: 260px minmax(0, 1fr); gap: 40px; } }
nav.toc { display: none; }
@media (min-width: 1100px) {
  nav.toc { display: block; position: sticky; top: 0; align-self: start; max-height: 100vh; overflow-y: auto;
    padding: 24px 0; font-size: 14px; }
}
nav.toc a { color: var(--muted); text-decoration: none; display: block; padding: 3px 0; }
nav.toc a:hover { color: var(--accent); }
nav.toc .h3 { padding-left: 14px; font-size: 13px; }
nav.toc .home { font-weight: 600; color: var(--text); margin-bottom: 10px; }
main { min-width: 0; padding: 24px 0 80px; }
.banner { font-size: 13px; color: var(--muted); border-bottom: 1px solid var(--border); padding-bottom: 10px;
  margin-bottom: 20px; display: flex; flex-wrap: wrap; gap: 8px 16px; justify-content: space-between; }
.banner button { font: inherit; color: var(--muted); background: none; border: 1px solid var(--border);
  border-radius: 6px; padding: 2px 10px; cursor: pointer; }
h1 { font-size: 2em; line-height: 1.25; margin: 0.2em 0 0.6em; }
h2 { font-size: 1.5em; border-bottom: 1px solid var(--border); padding-bottom: 0.3em; margin-top: 2em; }
h3 { font-size: 1.2em; margin-top: 1.6em; }
h1, h2, h3, h4 { scroll-margin-top: 16px; }
a { color: var(--accent); }
p, li { overflow-wrap: anywhere; }
code { background: var(--code-bg); border-radius: 4px; padding: 0.1em 0.35em; font-size: 0.88em;
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; }
pre { background: var(--code-bg); border-radius: 8px; padding: 14px 16px; overflow-x: auto; font-size: 13.5px;
  line-height: 1.5; }
pre code { background: none; padding: 0; font-size: inherit; }
pre.mermaid { background: var(--surface); border: 1px solid var(--border); text-align: center; }
blockquote { margin: 1em 0; padding: 0.4em 1em; border-left: 4px solid var(--accent); color: var(--muted);
  background: var(--surface); border-radius: 0 6px 6px 0; }
.table-wrap { overflow-x: auto; margin: 1em 0; border: 1px solid var(--border); border-radius: 8px; }
table { border-collapse: collapse; width: 100%; font-size: 14.5px; background: var(--surface); }
th, td { border-bottom: 1px solid var(--border); padding: 8px 12px; text-align: left; vertical-align: top; }
th { background: var(--row-alt); font-weight: 600; }
tr:nth-child(even) td { background: var(--row-alt); }
tr:last-child td { border-bottom: none; }
del { color: var(--muted); }
hr { border: none; border-top: 1px solid var(--border); margin: 2em 0; }
.index-list { list-style: none; padding: 0; }
.index-list li { padding: 12px 0; border-bottom: 1px solid var(--border); }
.index-list .path { color: var(--muted); font-size: 13px; }
"""

THEME_SCRIPT = """
<script>
(function () {
  var key = "changelens-docs-theme";
  try { var saved = localStorage.getItem(key); if (saved) document.documentElement.dataset.theme = saved; } catch (e) {}
  window.toggleTheme = function () {
    var dark = document.documentElement.dataset.theme
      ? document.documentElement.dataset.theme === "dark"
      : window.matchMedia("(prefers-color-scheme: dark)").matches;
    var next = dark ? "light" : "dark";
    document.documentElement.dataset.theme = next;
    try { localStorage.setItem(key, next); } catch (e) {}
  };
})();
</script>
"""


def build_parser() -> MarkdownIt:
    md = MarkdownIt("commonmark", {"html": True}).enable(["table", "strikethrough"])
    md.use(anchors_plugin, min_level=1, max_level=3)

    default_fence = md.renderer.rules["fence"]

    def fence(renderer, tokens, idx, options, env):
        token = tokens[idx]
        if token.info.strip() == "mermaid":
            env["has_mermaid"] = True
            return f'<pre class="mermaid">{html.escape(token.content)}</pre>\n'
        return default_fence(tokens, idx, options, env)

    md.add_render_rule("fence", fence)
    return md


def rewrite_links(body: str, source: Path, rendered: set[Path]) -> str:
    """Point relative links at rendered docs to their .html versions."""
    def replace(match: re.Match) -> str:
        href = match.group(1)
        path_part, _, anchor = href.partition("#")
        if "://" in href or not path_part.endswith(".md"):
            return match.group(0)
        target = (source.parent / path_part).resolve()
        if target not in rendered:
            return match.group(0)
        new = path_part[:-3] + ".html" + (f"#{anchor}" if anchor else "")
        return f'href="{new}"'
    return re.sub(r'href="([^"]+)"', replace, body)


def toc_from(tokens) -> list[tuple[int, str, str]]:
    entries = []
    for i, token in enumerate(tokens):
        if token.type == "heading_open" and token.tag in ("h2", "h3"):
            text = tokens[i + 1].content
            entries.append((int(token.tag[1]), token.attrs.get("id", ""), text))
    return entries


def page(title: str, source_rel: str, index_rel: str, toc: list, body: str, mermaid: bool) -> str:
    toc_html = "".join(
        f'<a class="h{level}" href="#{html.escape(anchor)}">{html.escape(re.sub(r"[`*]", "", text))}</a>'
        for level, anchor, text in toc)
    mermaid_html = ""
    if mermaid:
        mermaid_html = (
            f'<script src="{MERMAID_CDN}"></script>\n<script>\n'
            "var dark = document.documentElement.dataset.theme ? document.documentElement.dataset.theme === 'dark'"
            " : window.matchMedia('(prefers-color-scheme: dark)').matches;\n"
            "mermaid.initialize({ startOnLoad: true, theme: dark ? 'dark' : 'default', securityLevel: 'strict' });\n"
            "</script>\n")
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(title)}</title>
<style>{STYLE}</style>
{THEME_SCRIPT}
</head>
<body>
<div class="layout">
<nav class="toc"><a class="home" href="{index_rel}">ChangeLens docs</a>{toc_html}</nav>
<main>
<div class="banner"><span>Generated from <code>{html.escape(source_rel)}</code>. Edit the .md file, then run
<code>python scripts/render_docs.py</code>.</span><span><a href="{index_rel}">All docs</a>
<button type="button" onclick="toggleTheme()">Light / dark</button></span></div>
{body}
</main>
</div>
{mermaid_html}</body>
</html>
"""


def first_heading(tokens, fallback: str) -> str:
    for i, token in enumerate(tokens):
        if token.type == "heading_open" and token.tag == "h1":
            return re.sub(r"[`*]", "", tokens[i + 1].content)
    return fallback


def main() -> int:
    md = build_parser()
    sources = sorted(DOCS.rglob("*.md"))
    rendered = {p.resolve() for p in sources}
    index_entries = []
    for source in sources:
        text = source.read_text(encoding="utf-8")
        env: dict = {}
        tokens = md.parse(text, env)
        body = md.renderer.render(tokens, md.options, env)
        body = re.sub(r"<table>", '<div class="table-wrap"><table>', body).replace("</table>", "</table></div>")
        body = rewrite_links(body, source, rendered)
        title = first_heading(tokens, source.stem)
        source_rel = source.relative_to(ROOT).as_posix()
        index_rel = Path("../" * (len(source.relative_to(DOCS).parts) - 1) + "index.html").as_posix()
        out = source.with_suffix(".html")
        out.write_text(page(title, source_rel, index_rel, toc_from(tokens), body, env.get("has_mermaid", False)),
                       encoding="utf-8")
        index_entries.append((title, out.relative_to(DOCS).as_posix(), source_rel))
        print(f"rendered {source_rel} -> {out.relative_to(ROOT).as_posix()}")

    items = "".join(
        f'<li><a href="{href}">{html.escape(title)}</a><div class="path">{html.escape(src)}</div></li>'
        for title, href, src in index_entries)
    index_body = f"<h1>ChangeLens docs</h1><ul class=\"index-list\">{items}</ul>"
    (DOCS / "index.html").write_text(
        page("ChangeLens docs", "docs/", "index.html", [], index_body, False), encoding="utf-8")
    print("rendered docs/index.html")
    return 0


if __name__ == "__main__":
    sys.exit(main())
