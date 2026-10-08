from langchain_core.messages import AIMessage, HumanMessage
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph
from langgraph.checkpoint.base import BaseCheckpointSaver
from changelens.state import ChangeLensState


async def ingest(state: ChangeLensState)->dict:
    text = state['query'].strip()
    return {"messages": [HumanMessage(content = text)]}

async def triage(state: ChangeLensState)->dict:
    return {}

async def agent(state: ChangeLensState)-> dict:
    earlier = len(state['messages'])-1
    last_text = state['messages'][-1].content
    return {"messages": [AIMessage(content=f"I see {earlier} earlier messages. You said: {last_text}")]}

async def render(state: ChangeLensState) -> dict:
    return {"response": state["messages"][-1].content}


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
    
    
