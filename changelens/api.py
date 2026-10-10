from contextlib import AsyncExitStack
import logging
import time

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict

from langgraph.checkpoint.memory import InMemorySaver

from changelens.config import get_settings
from changelens.context import TurnContext
from changelens.errors import describe
from changelens.graph import build_graph
from changelens.mcp_tools.session import open_tools


logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)


class ChatRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    query: str
    session_id: str


class ChatResponse(BaseModel):
    response: str

# One saver per process. Memory is lost on restart. It explains check 4. Cloud Run can also run several instances, so a later request might reach one with no memory of the session.
graph = build_graph(InMemorySaver())

app = FastAPI()

@app.exception_handler(Exception)
async def catch_all_exceptions(request: Request, exc: Exception) -> JSONResponse:
    logger.exception("Unhandled error")
    return JSONResponse(
        status_code=500,
        content={"response": "Something went wrong on the server. Please try again."},
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    logger.warning("Rejected invalid /chat request")
    return JSONResponse(
        status_code=422,
        content={
            "response": (
                "The request body must be JSON with exactly the fields "
                "'query' and 'session_id', both strings."
            )
        },
    )


@app.get("/health")
async def get_health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest) -> ChatResponse:
    started = time.monotonic()
    stack = AsyncExitStack()
    try:
        settings = get_settings()
        opened = await open_tools(stack)                  # no asyncio.wait_for around this line
        result = await graph.ainvoke(
            {"query": request.query},
            config={"configurable": {"thread_id": request.session_id},
                    "recursion_limit": 2 * settings.max_tool_rounds + 10},
            context=TurnContext(tools=opened.tools, started_at=started,sources=opened.available, unavailable=opened.unavailable),
        )
    except Exception:
        logger.exception("Graph failed")
        return ChatResponse(response="I could not process that request. Please try again.")
    finally:
        try:
            await stack.aclose()
        except Exception as error:
            logger.warning("Closing MCP session failed (%s)", describe(error))
    return ChatResponse(response=result["response"])
