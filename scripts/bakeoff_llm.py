"""G0 / S0c: LLM tool-calling bake-off for decision D2.

Binds real tool schemas (from the S0b tools/list dumps) to each candidate model
and scores only the model's FIRST decision per prompt. No tool is executed, so
this is a selection test, not MCP integration evidence.

Usage:
    python scripts/bakeoff_llm.py [--models m1,m2] [--prompts a.jsonl,b.jsonl] [--out g0]

Reads LLM_API_KEY / LLM_BASE_URL from .env at runtime; never prints them.
Writes redacted results to docs/evidence/<out>/bakeoff/. Each row is appended to
rows_<date>.jsonl as soon as it is scored, so an interrupted run keeps its rows.
A prompt may set "accept_tools" to require specific tool names, not just a server.
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import statistics
import sys
import time
from datetime import date
from pathlib import Path

import jsonschema
from dotenv import find_dotenv, load_dotenv
from openai import APIStatusError, OpenAI

sys.path.insert(0, str(Path(__file__).resolve().parent))
from probe_mcp import redact  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
EVIDENCE = ROOT / "docs" / "evidence" / "g0"  # tools_list.json dumps from S0b
PROMPTS = ROOT / "eval" / "bakeoff_prompts.jsonl"

DEFAULT_MODELS = [
    "nvidia/nemotron-3-ultra-550b-a55b",      # PDF-tested ("Nemotron 3 Ultra")
    "nvidia/nemotron-3.5-lightning-30b-a3b",  # PDF-tested ("Nemotron 3.5 Lightning")
    "nvidia/nemotron-3-super-120b-a12b",      # current default
    "openai/gpt-oss-20b",
    "moonshotai/kimi-k3",
    "mistralai/mistral-large",
]

TOOLS = {
    "github": ["get_file_contents", "search_code", "list_commits", "search_issues",
               "pull_request_read", "get_commit", "list_pull_requests", "search_pull_requests"],
    "context7": ["resolve-library-id", "query-docs"],
    "tavily": ["tavily_search", "tavily_extract"],
}

SYSTEM_PROMPT = (
    "You are ChangeLens, an assistant that helps developers understand and safely change "
    "public GitHub codebases. You can call tools: GitHub (read repository files, commits, "
    "pull requests and their diffs, issues, code search), Context7 (version-specific library documentation) and Tavily "
    "(web search). Call a tool only when it is needed to answer accurately. Answer directly "
    "from your own knowledge when no tool is needed. If the request is too ambiguous to act "
    "on (for example, no repository is named), ask one short clarifying question instead."
)

PAUSE_SECONDS = 1.6  # stay under the NIM free tier's ~40 requests/minute


def load_tools() -> tuple[list[dict], dict[str, tuple[str, dict]]]:
    """Return OpenAI tool specs and a map tool name -> (server, inputSchema)."""
    specs, index = [], {}
    for server, names in TOOLS.items():
        listed = json.loads((EVIDENCE / server / "tools_list.json").read_text())["tools"]
        for tool in listed:
            if tool["name"] in names:
                index[tool["name"]] = (server, tool["inputSchema"])
                specs.append({"type": "function", "function": {
                    "name": tool["name"],
                    "description": (tool["description"] or "")[:1000],
                    "parameters": tool["inputSchema"],
                }})
    return specs, index


def classify(message, index: dict) -> dict:
    """Score the model's first decision."""
    calls = message.tool_calls or []
    if not calls:
        text = message.content or ""
        decision = "clarify" if "?" in text else "none"
        return {"decision": decision, "tool": "", "schema_valid": None}
    call = calls[0]
    name = call.function.name
    if name not in index:
        return {"decision": "unknown_tool", "tool": name, "schema_valid": False}
    server, schema = index[name]
    try:
        jsonschema.validate(json.loads(call.function.arguments or "{}"), schema)
        valid = True
    except (json.JSONDecodeError, jsonschema.ValidationError):
        valid = False
    return {"decision": server, "tool": name, "schema_valid": valid}


def is_correct(row: dict, case: dict) -> bool:
    if row["decision"] not in case["accept"]:
        return False
    tools = case.get("accept_tools")
    return not tools or row["decision"] not in TOOLS or row["tool"] in tools


def run_model(client: OpenAI, model: str, prompts: list[dict], specs: list, index: dict,
              rows_path: Path) -> list[dict]:
    rows = []
    for case in prompts:
        row = {"model": model, "id": case["id"], "kind": case["kind"], "accept": "|".join(case["accept"])}
        started = time.monotonic()
        try:
            completion = client.chat.completions.create(
                model=model,
                messages=[{"role": "system", "content": SYSTEM_PROMPT},
                          {"role": "user", "content": case["prompt"]}],
                tools=specs,
                tool_choice="auto",
                temperature=0,
                max_tokens=512,
                timeout=90,
            )
            row.update(classify(completion.choices[0].message, index))
            row["error"] = ""
        except APIStatusError as error:
            row.update({"decision": "api_error", "tool": "", "schema_valid": None,
                        "error": redact(f"HTTP {error.status_code}: {str(error)[:160]}")})
        except Exception as error:
            row.update({"decision": "api_error", "tool": "", "schema_valid": None,
                        "error": redact(f"{type(error).__name__}: {str(error)[:160]}")})
        row["latency_s"] = round(time.monotonic() - started, 2)
        row["correct"] = is_correct(row, case)
        rows.append(row)
        with open(rows_path, "a") as handle:
            handle.write(redact(json.dumps(row)) + "\n")
        time.sleep(PAUSE_SECONDS)
    return rows


def summarize(model: str, rows: list[dict]) -> dict:
    answered = [r for r in rows if r["decision"] != "api_error"]
    tool_rows = [r for r in rows if r["schema_valid"] is not None]
    latencies = [r["latency_s"] for r in answered]
    return {
        "model": model,
        "selection_correct": f"{sum(r['correct'] for r in rows)}/{len(rows)}",
        "no_tool_correct": f"{sum(r['correct'] for r in rows if r['kind'] == 'no_tool')}"
                           f"/{sum(r['kind'] == 'no_tool' for r in rows)}",
        "schema_valid": f"{sum(bool(r['schema_valid']) for r in tool_rows)}/{len(tool_rows)}",
        "api_errors": sum(r["decision"] == "api_error" for r in rows),
        "http_429": sum("HTTP 429" in r["error"] for r in rows),
        "median_latency_s": round(statistics.median(latencies), 2) if latencies else None,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--models", default=",".join(DEFAULT_MODELS))
    parser.add_argument("--prompts", default=str(PROMPTS), help="comma-separated JSONL prompt files")
    parser.add_argument("--out", default="g0", help="evidence subfolder under docs/evidence/")
    opts = parser.parse_args()

    load_dotenv(find_dotenv(usecwd=True))
    client = OpenAI(api_key=os.environ["LLM_API_KEY"], base_url=os.environ["LLM_BASE_URL"])
    prompts = [json.loads(line) for path in opts.prompts.split(",")
               for line in Path(path).read_text().splitlines() if line.strip()]
    specs, index = load_tools()

    out_dir = ROOT / "docs" / "evidence" / opts.out / "bakeoff"
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = date.today().isoformat()
    rows_path = out_dir / f"rows_{stamp}.jsonl"
    all_rows, summaries = [], []
    for model in opts.models.split(","):
        rows = run_model(client, model, prompts, specs, index, rows_path)
        all_rows.extend(rows)
        summary = summarize(model, rows)
        summaries.append(summary)
        print(json.dumps(summary), flush=True)

    with open(out_dir / f"bakeoff_{stamp}.csv", "w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(all_rows[0]))
        writer.writeheader()
        writer.writerows(all_rows)
    (out_dir / f"summary_{stamp}.json").write_text(redact(json.dumps(
        {"tools_bound": sorted(index), "prompt_count": len(prompts), "models": summaries}, indent=2)) + "\n")
    print(f"saved -> {out_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
