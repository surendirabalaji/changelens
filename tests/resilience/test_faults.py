"""REAL MCP wire, FAKE server behavior."""

from contextlib import AsyncExitStack
import time
from types import SimpleNamespace

import httpx
import pytest
from langchain_core.messages import AIMessage, ToolMessage
from langgraph.checkpoint.memory import MemorySaver
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client
from mcp.types import ImageContent

from changelens import api, graph
from changelens.context import TurnContext
from changelens.errors import FailureKind
from changelens.mcp_tools import session
from changelens.mcp_tools.session import open_tools


pytestmark = pytest.mark.resilience


def make_context(opened) -> TurnContext:
    return TurnContext(
        tools=opened.tools,
        sources=opened.available,
        unavailable=opened.unavailable,
        started_at=time.monotonic(),
        tool_servers=opened.tool_servers,
    )


async def execute_tool(opened, name: str) -> ToolMessage:
    call = {
        "name": name,
        "args": {},
        "id": f"{name}-call",
        "type": "tool_call",
    }

    state = {
        "messages": [
            AIMessage(content="", tool_calls=[call])
        ],
        "tool_rounds": 0,
    }

    runtime = SimpleNamespace(context=make_context(opened))
    update = await graph.run_tools(state, runtime)

    assert len(update["messages"]) == 1

    reply = update["messages"][0]

    assert isinstance(reply, ToolMessage)
    assert reply.tool_call_id == call["id"]
    assert reply.name == name

    return reply


def observe_failures(monkeypatch, breaker):
    """Observe classification while preserving real breaker updates."""
    kinds: list[FailureKind] = []
    original = breaker.record_failure

    def counted(server, kind):
        kinds.append(kind)
        original(server, kind)

    monkeypatch.setattr(breaker, "record_failure", counted)
    return kinds


def test_stub_starts_and_restarts(
    free_port,
    start_stub,
    use_stub,
):
    stub = start_stub(free_port)
    use_stub(stub.url)

    assert stub.process is not None
    assert stub.process.poll() is None

    original_url = stub.url

    stub.restart()

    assert stub.url == original_url
    assert stub.process is not None
    assert stub.process.poll() is None


@pytest.mark.asyncio
async def test_success(
    free_port,
    start_stub,
    use_stub,
    breaker,
    tool_attempts,
):
    stub = start_stub(free_port)
    use_stub(stub.url)

    async with AsyncExitStack() as stack:
        opened = await open_tools(stack)

        assert opened.available == ("stub",)
        assert opened.unavailable == ()
        assert opened.tool_servers["stub_ok"] == "stub"

        reply = await execute_tool(opened, "stub_ok")

        assert reply.status == "success"
        assert reply.content == "Stub lookup succeeded."
        assert tool_attempts == ["stub_ok"]
        assert breaker.allow("stub") is True


@pytest.mark.asyncio
async def test_refused_connection_opens_breaker(
    free_port,
    use_stub,
    breaker,
    connect_attempts,
    monkeypatch,
):
    use_stub(f"http://127.0.0.1:{free_port}/mcp")
    kinds = observe_failures(monkeypatch, breaker)

    async with AsyncExitStack() as stack:
        opened = await open_tools(stack)

    assert opened.unavailable == ("stub",)
    assert connect_attempts == ["stub", "stub"]
    assert kinds == [
        FailureKind.TRANSPORT,
        FailureKind.TRANSPORT,
    ]
    assert breaker.allow("stub") is False

    connect_attempts.clear()
    started = time.monotonic()

    async with AsyncExitStack() as stack:
        opened = await open_tools(stack)

    assert opened.unavailable == ("stub",)
    assert connect_attempts == []
    assert time.monotonic() - started < 0.5


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("status", "expected_kind", "expected_attempts"),
    [
        (401, FailureKind.AUTH, 1),
        (503, FailureKind.TRANSPORT, 2),
    ],
)
async def test_http_fault(
    status,
    expected_kind,
    expected_attempts,
    free_port,
    start_stub,
    use_stub,
    breaker,
    connect_attempts,
    monkeypatch,
):
    stub = start_stub(free_port, http_fault=status)
    use_stub(stub.url)

    kinds = observe_failures(monkeypatch, breaker)

    async with AsyncExitStack() as stack:
        opened = await open_tools(stack)

    assert opened.unavailable == ("stub",)
    assert len(connect_attempts) == expected_attempts
    assert kinds == [expected_kind] * expected_attempts

    if status == 401:
        assert breaker.allow("stub") is True
    else:
        assert breaker.allow("stub") is False


@pytest.mark.asyncio
async def test_slow_tool_retries_and_opens_breaker(
    free_port,
    start_stub,
    use_stub,
    breaker,
    tool_attempts,
    monkeypatch,
):
    stub = start_stub(free_port)
    use_stub(stub.url)

    kinds = observe_failures(monkeypatch, breaker)

    async with AsyncExitStack() as stack:
        opened = await open_tools(stack)
        reply = await execute_tool(opened, "stub_slow")

        assert reply.status == "error"
        assert reply.content == graph.FAILURE_TEXT[FailureKind.TIMEOUT]
        assert tool_attempts == ["stub_slow", "stub_slow"]
        assert kinds == [
            FailureKind.TIMEOUT,
            FailureKind.TIMEOUT,
        ]
        assert breaker.allow("stub") is False


@pytest.mark.asyncio
async def test_tool_error_is_not_retried(
    free_port,
    start_stub,
    use_stub,
    breaker,
    tool_attempts,
):
    stub = start_stub(free_port)
    use_stub(stub.url)

    async with AsyncExitStack() as stack:
        opened = await open_tools(stack)
        by_name = {tool.name: tool for tool in opened.tools}

        # The guard's error prefix is separate from graph.py's
        # plain-language final ToolMessage.
        raw = await by_name["stub_tool_error"].ainvoke({
            "name": "stub_tool_error",
            "args": {},
            "id": "raw-tool-error",
            "type": "tool_call",
        })

        assert raw.status == "error"
        assert graph.message_text(raw.content).startswith(
            "Tool error (tool_error):"
        )

        breaker.record_failure("stub", FailureKind.TRANSPORT)

        reply = await execute_tool(opened, "stub_tool_error")

        assert reply.status == "error"
        assert reply.content == graph.DEFAULT_TOOL_ERROR_TEXT
        assert tool_attempts == ["stub_tool_error"]

        # A returned non-transient error must reset earlier failures.
        breaker.record_failure("stub", FailureKind.TRANSPORT)
        assert breaker.allow("stub") is True


@pytest.mark.asyncio
async def test_malformed_image_response(
    free_port,
    start_stub,
    use_stub,
    breaker,
    tool_attempts,
):
    stub = start_stub(free_port)
    use_stub(stub.url)

    # Inspect the raw SDK response before the production guard.
    async with streamable_http_client(stub.url) as streams:
        read_stream, write_stream, _ = streams

        async with ClientSession(read_stream, write_stream) as client:
            await client.initialize()
            raw = await client.call_tool("stub_malformed", {})

            print("Raw malformed stub response:", raw.model_dump())

            assert raw.isError is False
            assert raw.structuredContent is None
            assert len(raw.content) == 1
            assert isinstance(raw.content[0], ImageContent)

    async with AsyncExitStack() as stack:
        opened = await open_tools(stack)

        breaker.record_failure("stub", FailureKind.TRANSPORT)
        reply = await execute_tool(opened, "stub_malformed")

        assert reply.status == "error"
        assert reply.content == graph.FAILURE_TEXT[FailureKind.MALFORMED]
        assert tool_attempts == ["stub_malformed"]

        # MALFORMED proves reachability and resets earlier failures.
        breaker.record_failure("stub", FailureKind.TRANSPORT)
        assert breaker.allow("stub") is True

@pytest.mark.asyncio
async def test_recovery_after_cooldown(
    free_port,
    start_stub,
    use_stub,
    breaker,
    fake_clock,
    connect_attempts,
):
    url = f"http://127.0.0.1:{free_port}/mcp"
    use_stub(url)

    async with AsyncExitStack() as stack:
        opened = await open_tools(stack)

    assert opened.unavailable == ("stub",)
    assert breaker.allow("stub") is False

    stub = start_stub(free_port)
    assert stub.url == url

    fake_clock.advance(31.0)
    connect_attempts.clear()

    async with AsyncExitStack() as stack:
        opened = await open_tools(stack)

        assert opened.available == ("stub",)
        assert connect_attempts == ["stub"]
        assert breaker.allow("stub") is True
        assert breaker.allow("stub") is True

        reply = await execute_tool(opened, "stub_ok")
        assert reply.status == "success"


class FaultAnswerLLM:
    """FAKE LLM: request a real tool, then answer from its error message."""

    def __init__(self) -> None:
        self.seen_reply: ToolMessage | None = None

    def bind_tools(self, tools):
        assert any(tool.name == "stub_slow" for tool in tools)
        return self

    async def ainvoke(self, messages):
        reply = next(
            (
                message
                for message in reversed(messages)
                if isinstance(message, ToolMessage)
                and message.tool_call_id == "graph-slow-call"
            ),
            None,
        )

        if reply is None:
            return AIMessage(
                content="",
                tool_calls=[{
                    "name": "stub_slow",
                    "args": {},
                    "id": "graph-slow-call",
                    "type": "tool_call",
                }],
            )

        self.seen_reply = reply
        assert reply.status == "error"

        return AIMessage(
            content=(
                "I could not complete the lookup. "
                + graph.message_text(reply.content)
            )
        )


@pytest.mark.asyncio
async def test_graph_answers_from_tool_failure(
    free_port,
    start_stub,
    use_stub,
    monkeypatch,
):
    stub = start_stub(free_port)
    use_stub(stub.url)

    llm = FaultAnswerLLM()
    monkeypatch.setattr(graph, "get_llm", lambda: llm)

    compiled = graph.build_graph(MemorySaver())

    async with AsyncExitStack() as stack:
        opened = await open_tools(stack)

        result = await compiled.ainvoke(
            {"query": "Look up information using the slow source."},
            config={
                "configurable": {
                    "thread_id": "resilience-graph",
                }
            },
            context=make_context(opened),
        )

    expected = (
        "I could not complete the lookup. "
        + graph.FAILURE_TEXT[FailureKind.TIMEOUT]
    )

    assert llm.seen_reply is not None
    assert isinstance(result["response"], str)
    assert result["response"] == expected

    replies = [
        message
        for message in result["messages"]
        if isinstance(message, ToolMessage)
        and message.tool_call_id == "graph-slow-call"
    ]

    assert len(replies) == 1
    assert replies[0].status == "error"


@pytest.mark.asyncio
async def test_http_answers_from_real_tool_failure(
    free_port,
    start_stub,
    use_stub,
    monkeypatch,
):
    stub = start_stub(free_port)
    use_stub(stub.url)

    llm = FaultAnswerLLM()
    monkeypatch.setattr(graph, "get_llm", lambda: llm)
    monkeypatch.setattr(
        api,
        "graph",
        graph.build_graph(MemorySaver()),
    )
    monkeypatch.setattr(api, "get_settings", session.get_settings)
    monkeypatch.setattr(api, "open_tools", session.open_tools)

    transport = httpx.ASGITransport(app=api.app)

    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://test",
    ) as client:
        response = await client.post(
            "/chat",
            json={
                "query": "Look up information using the slow source.",
                "session_id": "resilience-http",
            },
        )

    expected = (
        "I could not complete the lookup. "
        + graph.FAILURE_TEXT[FailureKind.TIMEOUT]
    )

    assert response.status_code == 200
    assert response.json() == {"response": expected}
    assert isinstance(response.json()["response"], str)
    assert llm.seen_reply is not None
    assert llm.seen_reply.status == "error"