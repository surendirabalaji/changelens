from typing import TypedDict, Annotated

from langchain_core.messages import AnyMessage
from langgraph.graph import add_messages

from changelens.schemas import DecisionRecord, Evidence

def merge_evidence(old, new):
        return {**new, **(old or {})}


class ChangeLensState(TypedDict):
    messages : Annotated[list[AnyMessage], add_messages]
    query: str
    response: str
    tool_rounds: int
    evidence: Annotated[dict[str, Evidence], merge_evidence]
    decisions: dict[str, DecisionRecord]
    repo_context: dict
    intent: str
    repo_url: str
    revision: str
    active_decision_id: str
    repair_notes: list[str]
    repairs_done: int
