from typing import TypedDict, Annotated

from langchain_core.messages import AnyMessage
from langgraph.graph import add_messages


class ChangeLensState(TypedDict):
    messages : Annotated[list[AnyMessage], add_messages]
    query: str
    response: str

