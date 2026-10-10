"""Unit tests for the HTTP contract. The graph and the MCP session are FAKE (no network)."""
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from changelens import api
from changelens.config import Settings

FALLBACK = "I could not process that request. Please try again."


class Closer:  # FAKE MCP session: records whether the stack closed it
    def __init__(self):
        self.closed = False

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc_info):
        self.closed = True


class FakeGraph:  # FAKE graph: returns a fixed answer, or raises
    def __init__(self, error: Exception | None = None):
        self.error = error
        self.calls: list[dict] = []

    async def ainvoke(self, payload, config=None, context=None):
        self.calls.append({"payload": payload, "config": config, "context": context})
        if self.error is not None:
            raise self.error
        return {"response": "fake answer"}


@pytest.fixture
def closer() -> Closer:
    return Closer()


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch, closer: Closer) -> TestClient:
    async def fake_open_tools(stack):
        await stack.enter_async_context(closer)
        return SimpleNamespace(tools=[], available=("context7",), unavailable=("github",))

    monkeypatch.setattr(api, "open_tools", fake_open_tools)
    monkeypatch.setattr(api, "get_settings", lambda: Settings(_env_file=None))
    monkeypatch.setattr(api, "graph", FakeGraph())
    return TestClient(api.app)


def post_chat(client: TestClient, **body):
    return client.post("/chat", json=body)


def test_health_returns_ok(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_chat_returns_only_the_response_key(client):
    response = post_chat(client, query="hi", session_id="a")
    assert response.status_code == 200
    assert response.json() == {"response": "fake answer"}


def test_chat_passes_session_id_limits_and_context_to_the_graph(client):
    post_chat(client, query="hi", session_id="session-1")
    call = api.graph.calls[0]
    assert call["payload"] == {"query": "hi"}
    assert call["config"]["configurable"]["thread_id"] == "session-1"
    assert call["config"]["recursion_limit"] == 2 * 3 + 10  # max_tool_rounds default is 3
    assert call["context"].sources == ("context7",)
    assert call["context"].unavailable == ("github",)


@pytest.mark.parametrize(
    "body",
    [
        {"query": "hi", "session_id": "a", "extra": 1},
        {"query": "hi"},
        {"session_id": "a"},
        {"query": 5, "session_id": "a"},
    ],
)
def test_invalid_body_gets_422_with_only_the_response_key(client, body):
    response = post_chat(client, **body)
    assert response.status_code == 422
    assert list(response.json()) == ["response"]


def test_non_json_body_gets_422_with_only_the_response_key(client):
    response = client.post(
        "/chat", content="not json", headers={"Content-Type": "application/json"}
    )
    assert response.status_code == 422
    assert list(response.json()) == ["response"]


def test_invalid_body_does_not_echo_user_input(client):
    response = post_chat(client, query="hi", session_id="a", extra="SECRET-INPUT")
    assert "SECRET-INPUT" not in response.text


def test_graph_failure_returns_200_with_the_fixed_fallback(client, monkeypatch):
    monkeypatch.setattr(api, "graph", FakeGraph(error=RuntimeError("secret detail")))
    response = post_chat(client, query="hi", session_id="a")
    assert response.status_code == 200
    assert response.json() == {"response": FALLBACK}
    assert "secret detail" not in response.text


def test_mcp_sessions_are_closed_after_success(client, closer):
    post_chat(client, query="hi", session_id="a")
    assert closer.closed is True


def test_mcp_sessions_are_closed_after_a_graph_failure(client, closer, monkeypatch):
    monkeypatch.setattr(api, "graph", FakeGraph(error=RuntimeError("boom")))
    post_chat(client, query="hi", session_id="a")
    assert closer.closed is True
