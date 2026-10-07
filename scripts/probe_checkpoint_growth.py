"""M0 probe (offline, no network): how fast does InMemorySaver grow per session?

Simulates a ChangeLens-shaped state (messages with add_messages, an append-only
evidence dict, a decisions dict) through a 4-node graph, so each turn writes several
checkpoints. Reports serialized saver size after each block of turns, with and
without trimming tool output in messages. Writes docs/evidence/m0/library/checkpoint_growth.json.
"""
from __future__ import annotations

import json
import pickle
import sys
from pathlib import Path
from typing import Annotated, TypedDict

from langchain_core.messages import AIMessage, HumanMessage
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages

OUT = Path(__file__).resolve().parent.parent / "docs" / "evidence" / "m0" / "library" / "checkpoint_growth.json"
EXCERPT = "x" * 1500          # evidence excerpt cap from the design
EVIDENCE_PER_TURN = 5
TURNS = 50


def merge(left: dict, right: dict) -> dict:
    return {**left, **right}


class State(TypedDict):
    messages: Annotated[list, add_messages]
    evidence: Annotated[dict, merge]
    decisions: Annotated[dict, merge]
    turn: int


def build(tool_output_chars: int):
    def ingest(state: State) -> dict:
        return {"turn": state.get("turn", 0) + 1}

    def tools(state: State) -> dict:
        turn = state["turn"]
        evidence = {f"ev-{turn}-{i}": {"excerpt": EXCERPT, "source_url": "https://github.com/o/r/blob/sha/f.py"}
                    for i in range(EVIDENCE_PER_TURN)}
        return {"evidence": evidence, "messages": [AIMessage(content="t" * tool_output_chars)]}

    def synthesize(state: State) -> dict:
        turn = state["turn"]
        return {"decisions": {"D1": {"revision": turn, "summary": "s" * 2000}}}

    def render(state: State) -> dict:
        return {"messages": [AIMessage(content="r" * 2500)]}

    graph = StateGraph(State)
    for name, fn in (("ingest", ingest), ("tools", tools), ("synthesize", synthesize), ("render", render)):
        graph.add_node(name, fn)
    graph.add_edge(START, "ingest")
    graph.add_edge("ingest", "tools")
    graph.add_edge("tools", "synthesize")
    graph.add_edge("synthesize", "render")
    graph.add_edge("render", END)
    saver = InMemorySaver()
    return graph.compile(checkpointer=saver), saver


def saver_bytes(saver: InMemorySaver) -> int:
    return len(pickle.dumps((dict(saver.storage), dict(saver.writes), dict(saver.blobs))))


def run(tool_output_chars: int) -> list[dict]:
    app, saver = build(tool_output_chars)
    config = {"configurable": {"thread_id": "s1"}}
    points = []
    for turn in range(1, TURNS + 1):
        app.invoke({"messages": [HumanMessage(content="q" * 300)]}, config)
        if turn in (1, 5, 10, 20, 30, 50):
            checkpoints = sum(1 for _ in saver.list(config))
            points.append({"turn": turn, "checkpoints": checkpoints, "saver_kb": round(saver_bytes(saver) / 1024, 1)})
    saver.delete_thread("s1")
    points.append({"after_delete_thread_kb": round(saver_bytes(saver) / 1024, 1)})
    return points


def main() -> int:
    result = {
        "assumptions": {"evidence_per_turn": EVIDENCE_PER_TURN, "excerpt_chars": len(EXCERPT),
                        "nodes_per_turn": 4, "note": "synthetic sizes; offline; one session"},
        "untrimmed_tool_output_20k_chars": run(20_000),
        "trimmed_tool_output_1k_chars": run(1_000),
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
