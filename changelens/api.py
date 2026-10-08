import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict

from langgraph.checkpoint.memory import InMemorySaver

from changelens.graph import build_graph



class ChatRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    query: str
    session_id: str


class ChatResponse(BaseModel):
    response: str

# One saver per process. Memory is lost on restart. It explains check 4. Cloud Run can also run several instances, so a later request might reach one with no memory of the session.
graph = build_graph(InMemorySaver())

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)


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


@app.get("/healthz")
async def get_health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest) -> ChatResponse:
    try:
        result = await graph.ainvoke(
            {"query":request.query},
            config={"configurable": {"thread_id": request.session_id}},
        )
    except Exception:
        logger.exception("Graph failed")
        return ChatResponse(response='I could not process that request. Please try again.')

    return ChatResponse(response=result["response"])
