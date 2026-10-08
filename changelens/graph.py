import asyncio
import logging
import time

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph
from langgraph.checkpoint.base import BaseCheckpointSaver
from changelens.config import get_settings
from changelens.llm import get_llm
from changelens.state import ChangeLensState


SYSTEM_PROMPT = "You are ChangeLens, a code-review decision assistant. Answer briefly. You can recall earlier turns in this conversation."

logger = logging.getLogger(__name__)

def message_text(content: str | list) -> str:
    if isinstance(content, str):
        return content
    parts = [p if isinstance(p, str) else p.get("text", "") for p in content]
    return "".join(parts)

async def ingest(state: ChangeLensState)->dict:
    text = state['query'].strip()
    return {"messages": [HumanMessage(content = text)]}

async def triage(state: ChangeLensState)->dict:
    return {}

async def agent(state: ChangeLensState)-> dict:

    settings = get_settings()
    llm = get_llm()
    messages = [SystemMessage(content=SYSTEM_PROMPT), *state["messages"]]
    started = time.monotonic()
    ai_message = await asyncio.wait_for(
        llm.ainvoke(messages),timeout= settings.llm_timeout_s
    )
    logger.info("agent LLM call took %.2f s", time.monotonic() - started)
    return {"messages": [ai_message]}

async def render(state: ChangeLensState) -> dict:
    text = message_text(state["messages"][-1].content).strip()
    if text is "":
        raise ValueError("empty model reply")

    return {"response": text}


def build_graph(checkpointer : BaseCheckpointSaver) -> CompiledStateGraph:
    builder = StateGraph(ChangeLensState)
    builder.add_node(ingest)
    builder.add_node(triage)
    builder.add_node(agent)
    builder.add_node(render)

    builder.add_edge(START,"ingest")
    builder.add_edge("ingest","triage")
    builder.add_edge("triage","agent")
    builder.add_edge("agent","render")
    builder.add_edge("render",END)
    return builder.compile(checkpointer=checkpointer)
    
    
