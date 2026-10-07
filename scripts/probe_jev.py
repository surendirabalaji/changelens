"""M0 / D18 probe: Jev vs Nemotron for ChangeLens request triage.

Runs the labelled cases in eval/triage_prompts.jsonl through:
  * Jev (TypeSafe System One) - one system_one call per case with three questions:
    intent (Choice), target_decision (Choice built per request from the session ledger),
    needs_clarification (Noul). Run twice to measure answer stability.
  * Nemotron (NIM, OpenAI-compatible) - one structured-output call with the same definitions.
Then simulates the D18 fallback rule (Jev unless ambiguous across the tool/no-tool split,
between two real decisions, or failed -> Nemotron) and records an invalid-request check
and the models listed for the account.

Keys are read from .env at runtime and scrubbed from saved output.
Writes docs/evidence/m0/jev/{rows.jsonl,summary.json}.
"""
from __future__ import annotations

import asyncio
import json
import os
import statistics
import sys
import time
from pathlib import Path

from dotenv import find_dotenv, load_dotenv
from openai import OpenAI
from typesafe_sdk import AsyncTypeSafeClient, Choice, Noul, RetryPolicy, TypeSafeError

sys.path.insert(0, str(Path(__file__).resolve().parent))
from probe_mcp import redact  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
CASES = ROOT / "eval" / "triage_prompts.jsonl"
OUT_DIR = ROOT / "docs" / "evidence" / "m0" / "jev"
NEMOTRON = "nvidia/nemotron-3-super-120b-a12b"
JEV_RUNS = 2
MARGIN = 0.25           # fallback when the top-two intents cross groups within this margin
NOUL_BAND = (0.35, 0.65)
PAUSE_SECONDS = 1.6     # NIM free tier ~40 requests/minute
NEM_MAX_TOKENS = 1024

INTENTS = {
    "conceptual": {
        "what": "A general software-engineering or concept question answerable from general knowledge, "
                "without reading a specific repository, pull request, commit, or stored decision.",
        "not_for": "Questions that name a specific repository, PR, or commit, or refer to a stored decision."},
    "repo_review": {
        "what": "Asks to analyze a specific public repository or its code about a proposed change or design "
                "question that is not already a stored decision in `ledger`.",
        "not_for": "Correcting or rechecking a decision that is already in `ledger`."},
    "revise_decision": {
        "what": "Gives a correction, new constraint, or new fact that should change a decision stored in "
                "`ledger`, and asks to update that decision, its assumptions, or its tests.",
        "not_for": "Checking whether a stored decision still holds against new code, a PR, or a commit."},
    "recheck": {
        "what": "Asks whether a decision stored in `ledger` still holds against a pull request, commit, "
                "branch, or newer version of the code.",
        "not_for": "New analysis with no stored decision involved."},
    "memory_recall": {
        "what": "Asks what was asked, said, or decided earlier in this conversation; answerable from "
                "`recent_turns` and `ledger` alone without reading any code.",
        "not_for": "Requests to change or recheck a decision."},
    "clarify": {
        "what": "A request about the user's code that is too vague to act on: it lacks the repository, the "
                "pull request number, or which decision is meant, and that cannot be inferred from `ledger` "
                "or `recent_turns`.",
        "not_for": "Requests where the missing detail is clear from the conversation."},
    "out_of_scope": {
        "what": "Not about software engineering, code, repositories, or the stored decisions.",
        "not_for": "Any programming or software-design question."},
}
GROUP = {"conceptual": "no_tool", "memory_recall": "no_tool", "clarify": "no_tool", "out_of_scope": "no_tool",
         "repo_review": "tool", "recheck": "tool", "revise_decision": "decision"}

D1 = {"decision_id": "D1", "repo": "fastapi/full-stack-fastapi-template",
      "proposed_change": "Cache GET /items responses for five minutes", "status": "active"}
D2 = {"decision_id": "D2", "repo": "brocoders/nestjs-boilerplate",
      "proposed_change": "Apply NestJS CacheInterceptor globally", "status": "active"}
LEDGERS = {
    "none": ([], []),
    "L1": ([D1], ["user: Analyze fastapi/full-stack-fastapi-template; can we cache GET /items for five minutes?",
                  "assistant: Recorded decision D1: caching is safe only if item results are not user-specific "
                  "and all filters are in the cache key."]),
    "L2": ([D1, D2], ["user: Analyze fastapi/full-stack-fastapi-template; can we cache GET /items for five minutes?",
                      "assistant: Recorded decision D1 (conditional on non-user-specific results).",
                      "user: In brocoders/nestjs-boilerplate, can we apply CacheInterceptor globally?",
                      "assistant: Recorded decision D2: only if authenticated endpoints such as /auth/me are excluded."]),
}

INTENT_INSTRUCTIONS = ("Which kind of request is `query`, given the conversation in `recent_turns` and the "
                       "stored engineering decisions in `ledger`?")
TARGET_INSTRUCTIONS = ("Which stored decision in `ledger` does `query` refer to? Choose none if it refers to no "
                       "stored decision or if it is unclear which one is meant.")
CLARIFY_INSTRUCTIONS = ("Is `query` too ambiguous to act on without first asking the user a question, because it "
                        "does not say which repository, pull request, or decision it means and that cannot be "
                        "inferred from `ledger` or `recent_turns`?")


def state_for(case: dict) -> dict:
    ledger, turns = LEDGERS[case["ledger"]]
    return {"query": case["query"], "ledger": ledger, "recent_turns": turns}


def jev_questions(ledger: list[dict]) -> dict:
    questions = {"intent": Choice(instructions=INTENT_INSTRUCTIONS, criteria=INTENTS),
                 "needs_clarification": Noul(instructions=CLARIFY_INSTRUCTIONS)}
    if ledger:
        criteria = {d["decision_id"]: f"{d['repo']}: {d['proposed_change']}" for d in ledger}
        criteria["none"] = "No stored decision, or it is unclear which one."
        questions["target_decision"] = Choice(instructions=TARGET_INSTRUCTIONS, criteria=criteria)
    return questions


def top_two(probabilities: dict[str, float]) -> list[tuple[str, float]]:
    return sorted(probabilities.items(), key=lambda kv: kv[1], reverse=True)[:2]


def needs_fallback(row: dict) -> bool:
    if row.get("jev_error"):
        return True
    (first, p1), (second, p2) = top_two(row["jev_intent_probs"])
    if GROUP[first] != GROUP[second] and p1 - p2 < MARGIN:
        return True
    target_probs = row.get("jev_target_probs") or {}
    real = [kv for kv in top_two(target_probs) if kv[0] != "none"] if len(target_probs) > 2 else []
    if len(real) == 2 and real[0][1] - real[1][1] < MARGIN:
        return True
    return NOUL_BAND[0] < row["jev_noul"] < NOUL_BAND[1]


def needs_fallback_v2(row: dict) -> bool:
    """Policy v2: same as v1 but ignores the needs_clarification Noul (poorly calibrated in run 1)."""
    if row.get("jev_error"):
        return True
    (first, p1), (second, p2) = top_two(row["jev_intent_probs"])
    if GROUP[first] != GROUP[second] and p1 - p2 < MARGIN:
        return True
    target_probs = row.get("jev_target_probs") or {}
    real = [kv for kv in top_two(target_probs) if kv[0] != "none"] if len(target_probs) > 2 else []
    return len(real) == 2 and real[0][1] - real[1][1] < MARGIN


def compose_v2(intent: str | None, target: str | None, ledger_size: int) -> str | None:
    """Code-side policy: a decision-bound request with no identifiable decision needs clarification."""
    if intent in ("recheck", "revise_decision") and ledger_size > 1 and target == "none":
        return "clarify"
    return intent


async def run_jev(client: AsyncTypeSafeClient, case: dict) -> dict:
    state = state_for(case)
    started = time.monotonic()
    try:
        result = await client.system_one(state=state, questions=jev_questions(state["ledger"]))
    except TypeSafeError as error:
        return {"jev_error": redact(f"{type(error).__name__}: {str(error)[:200]}"),
                "jev_latency_s": round(time.monotonic() - started, 3)}
    intent = result.choices["intent"]
    target = result.choices.get("target_decision")
    return {
        "jev_latency_s": round(time.monotonic() - started, 3),
        "jev_model": result.model,
        "jev_input_tokens": result.usage.input_tokens,
        "jev_intent": intent.choice,
        "jev_intent_conf": round(intent.confidence, 3),
        "jev_intent_probs": {k: round(v, 4) for k, v in intent.probabilities.items()},
        "jev_target": target.choice if target else "none",
        "jev_target_probs": {k: round(v, 4) for k, v in target.probabilities.items()} if target else {},
        "jev_noul": round(result.nouls["needs_clarification"].noul, 3),
        "jev_error": "",
    }


def nemotron_messages(case: dict) -> list[dict]:
    state = state_for(case)
    decision_ids = [d["decision_id"] for d in state["ledger"]] + ["none"]
    system = (
        "You classify requests for ChangeLens, a code-review assistant. Intent definitions:\n"
        + json.dumps(INTENTS, indent=1)
        + f"\nReturn JSON: {{\"intent\": one of {list(INTENTS)}, \"target_decision\": one of {decision_ids}, "
          "\"needs_clarification\": true or false}. JSON only."
    )
    return [{"role": "system", "content": system}, {"role": "user", "content": json.dumps(state)}]


def run_nemotron(client: OpenAI, case: dict) -> dict:
    started = time.monotonic()
    try:
        completion = client.chat.completions.create(
            model=NEMOTRON, messages=nemotron_messages(case), response_format={"type": "json_object"},
            # Run 1 used 200, which starved the model's reasoning tokens (empty or cut-off content).
            temperature=0, max_tokens=NEM_MAX_TOKENS, timeout=30)
        finish = completion.choices[0].finish_reason
        parsed = json.loads(completion.choices[0].message.content)
        return {"nem_latency_s": round(time.monotonic() - started, 3), "nem_intent": parsed.get("intent"),
                "nem_target": parsed.get("target_decision") or "none",
                "nem_clarify": parsed.get("needs_clarification"), "nem_finish": finish,
                "nem_completion_tokens": getattr(completion.usage, "completion_tokens", None), "nem_error": ""}
    except Exception as error:  # probe: record every failure shape
        return {"nem_latency_s": round(time.monotonic() - started, 3), "nem_intent": None, "nem_target": None,
                "nem_error": redact(f"{type(error).__name__}: {str(error)[:200]}")}


def pct(values: list[float], q: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    return round(ordered[min(len(ordered) - 1, int(round(q * (len(ordered) - 1))))], 3)


def summarize(rows: list[dict]) -> dict:
    def accuracy(key: str) -> str:
        return f"{sum(r[key] == r['intent'] for r in rows)}/{len(rows)}"

    def crossings(key: str) -> int:
        return sum(1 for r in rows if r[key] in GROUP and GROUP[r[key]] != GROUP[r["intent"]])

    scored = [r for r in rows if r["target"] != "any"]
    jev_lat = [r["jev_latency_s"] for r in rows if not r["jev_error"]]
    nem_lat = [r["nem_latency_s"] for r in rows if not r["nem_error"]]
    fallback_rows = [r for r in rows if r["fallback"]]
    return {
        "cases": len(rows),
        "jev_model": next((r["jev_model"] for r in rows if r.get("jev_model")), None),
        "jev_intent_accuracy": accuracy("jev_intent"),
        "nemotron_intent_accuracy": accuracy("nem_intent"),
        "combined_intent_accuracy": accuracy("combined_intent"),
        "combined_v2_intent_accuracy": accuracy("combined_v2_intent"),
        "combined_v2_group_crossings": crossings("combined_v2_intent"),
        "fallback_v2_rate": f"{sum(r['fallback_v2'] for r in rows)}/{len(rows)}",
        "nemotron_finish_length": sum(r.get("nem_finish") == "length" for r in rows),
        "nemotron_median_completion_tokens": statistics.median(
            [r["nem_completion_tokens"] for r in rows if r.get("nem_completion_tokens")] or [0]),
        "jev_group_crossings": crossings("jev_intent"),
        "nemotron_group_crossings": crossings("nem_intent"),
        "combined_group_crossings": crossings("combined_intent"),
        "jev_target_accuracy": f"{sum(r['jev_target'] == r['target'] for r in scored)}/{len(scored)}",
        "nemotron_target_accuracy": f"{sum(r['nem_target'] == r['target'] for r in scored)}/{len(scored)}",
        "fallback_rate": f"{len(fallback_rows)}/{len(rows)}",
        "jev_stable_across_runs": f"{sum(r['jev_stable'] for r in rows)}/{len(rows)}",
        "jev_latency_p50_s": pct(jev_lat, 0.5), "jev_latency_p95_s": pct(jev_lat, 0.95),
        "nemotron_latency_p50_s": pct(nem_lat, 0.5), "nemotron_latency_p95_s": pct(nem_lat, 0.95),
        "jev_errors": sum(bool(r["jev_error"]) for r in rows),
        "nemotron_errors": sum(bool(r["nem_error"]) for r in rows),
        "jev_mean_conf_correct": round(statistics.mean(
            [r["jev_intent_conf"] for r in rows if r.get("jev_intent") == r["intent"]] or [0]), 3),
        "jev_mean_conf_wrong": round(statistics.mean(
            [r["jev_intent_conf"] for r in rows if r.get("jev_intent") not in (None, r["intent"])] or [0]), 3),
        "jev_input_tokens_total": sum(r.get("jev_input_tokens") or 0 for r in rows),
        "note": "Latency measured from the developer laptop, not Cloud Run. Labels written by Claude; student "
                "review pending. Policy v2 was tuned on these same 30 cases after run 1; it must be validated "
                "on held-out cases before being trusted.",
    }


async def invalid_request_check(client: AsyncTypeSafeClient) -> dict:
    try:
        await client.system_one(state="x", questions={"bad": {"type": "choice", "criteria": {}}})
        return {"outcome": "accepted (no error)"}
    except TypeSafeError as error:
        return {"outcome": type(error).__name__, "detail": redact(str(error)[:200])}


async def main_async() -> int:
    load_dotenv(find_dotenv(usecwd=True))
    cases = [json.loads(line) for line in CASES.read_text().splitlines() if line.strip()]
    nim = OpenAI(api_key=os.environ["LLM_API_KEY"], base_url=os.environ["LLM_BASE_URL"])
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    rows_path = OUT_DIR / "rows.jsonl"
    rows_path.write_text("")

    retry = RetryPolicy(max_retries=1, timeout=5.0)
    async with AsyncTypeSafeClient(retry=retry, timeout=5.0) as client:
        try:
            models = await client.models.list()
            model_list = [m.model_dump() for m in models.models]
        except TypeSafeError as error:
            model_list = [{"error": redact(f"{type(error).__name__}: {str(error)[:200]}")}]
        rows = []
        for case in cases:
            runs = [await run_jev(client, case) for _ in range(JEV_RUNS)]
            row = {**case, **runs[0]}
            row["jev_stable"] = len({r.get("jev_intent") for r in runs}) == 1 and \
                len({r.get("jev_target") for r in runs}) == 1
            row["jev_latency_runs_s"] = [r["jev_latency_s"] for r in runs]
            row.update(run_nemotron(nim, case))
            row["fallback"] = needs_fallback(row)
            row["combined_intent"] = row["nem_intent"] if row["fallback"] else row["jev_intent"]
            ledger_size = len(LEDGERS[case["ledger"]][0])
            row["fallback_v2"] = needs_fallback_v2(row)
            chosen_intent, chosen_target = ((row["nem_intent"], row["nem_target"]) if row["fallback_v2"]
                                            else (row.get("jev_intent"), row.get("jev_target")))
            row["combined_v2_intent"] = compose_v2(chosen_intent, chosen_target, ledger_size)
            rows.append(row)
            with open(rows_path, "a") as handle:
                handle.write(redact(json.dumps(row)) + "\n")
            print(f"{case['id']:3} label={case['intent']:15} jev={row.get('jev_intent')!s:15} "
                  f"conf={row.get('jev_intent_conf')} nem={row.get('nem_intent')!s:15} "
                  f"fallback={row['fallback']} jev_ms={int(row['jev_latency_s'] * 1000)}", flush=True)
            time.sleep(PAUSE_SECONDS)
        invalid = await invalid_request_check(client)

    summary = {**summarize(rows), "invalid_request_check": invalid, "models_listed": model_list}
    (OUT_DIR / "summary.json").write_text(redact(json.dumps(summary, indent=2)) + "\n")
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main_async()))
