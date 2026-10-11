"""Unit tests for graph nodes.

FAKE: runtime, tools and LLM. No network.
"""

import time
from types import SimpleNamespace

import pytest
from langchain_core.messages import (
    AIMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)

from changelens.config import Settings
from changelens.context import TurnContext
from changelens.graph import (
    FINAL_ANSWER_REQUEST,
    NO_ANSWER_TEXT,
    agent,
    budget_spent,
    ingest,
    render,
    route_after_agent,
    run_tools,
)
from changelens.mcp_tools.breaker import CircuitBreaker


SETTINGS = Settings(
    _env_file=None,
    max_tool_rounds=3,
    tool_loop_stop_s=30.0,
    mcp_retry_jitter_s=0.0,
)

FOOTER = (
    "Note: I could not reach public GitHub repositories for this request, "
    "so it is not used in this answer."
)


@pytest.fixture(autouse=True)
def fixed_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "changelens.graph.get_settings",
        lambda: SETTINGS,
    )


@pytest.fixture(autouse=True)
def isolated_breaker(monkeypatch: pytest.MonkeyPatch) -> None:
    breaker = CircuitBreaker(2, 30.0)
    monkeypatch.setattr(
        "changelens.graph.get_breaker",
        lambda: breaker,
    )


def fake_runtime(**context_fields) -> SimpleNamespace:
    fields = {
        "tools": [],
        "started_at": time.monotonic(),
        **context_fields,
    }

    # Some agent tests use object() as a placeholder tool.
    # Preserve explicitly supplied maps, including empty maps.
    fields.setdefault(
        "tool_servers",
        {
            tool.name: "test_server"
            for tool in fields["tools"]
            if hasattr(tool, "name")
        },
    )

    return SimpleNamespace(context=TurnContext(**fields))


def tool_call(name: str, call_id: str) -> dict:
    return {
        "name": name,
        "args": {},
        "id": call_id,
        "type": "tool_call",
    }


# ---------- ingest ----------


async def test_ingest_first_turn_has_no_repairs_and_resets_counter():
    out = await ingest({"query": "  next  "})

    assert len(out["messages"]) == 1
    assert isinstance(out["messages"][0], HumanMessage)
    assert out["messages"][0].content == "next"
    assert out["tool_rounds"] == 0


async def test_ingest_adds_error_reply_for_unanswered_tool_call():
    history = [
        HumanMessage(content="hi"),
        AIMessage(content="", tool_calls=[tool_call("x", "c1")]),
    ]

    out = await ingest({
        "query": "next",
        "messages": history,
        "tool_rounds": 3,
    })

    repair, new_message = out["messages"]

    assert isinstance(repair, ToolMessage)
    assert repair.tool_call_id == "c1"
    assert repair.status == "error"
    assert isinstance(new_message, HumanMessage)
    assert new_message.content == "next"
    assert out["tool_rounds"] == 0


async def test_ingest_does_not_repair_a_plain_reply():
    history = [
        HumanMessage(content="hi"),
        AIMessage(content="hello"),
    ]

    out = await ingest({"query": "next", "messages": history})

    assert len(out["messages"]) == 1


async def test_ingest_does_not_repair_when_the_call_was_answered():
    history = [
        HumanMessage(content="hi"),
        AIMessage(content="", tool_calls=[tool_call("x", "c1")]),
        ToolMessage(content="done", tool_call_id="c1"),
    ]

    out = await ingest({"query": "next", "messages": history})

    assert len(out["messages"]) == 1


# ---------- route_after_agent ----------


def test_route_goes_to_tools_when_the_model_asked_for_a_tool():
    state = {
        "messages": [
            AIMessage(content="", tool_calls=[tool_call("x", "c1")])
        ]
    }

    assert route_after_agent(state) == "tools"


def test_route_goes_to_render_for_plain_text():
    state = {"messages": [AIMessage(content="done")]}
    assert route_after_agent(state) == "render"


def test_route_goes_to_render_when_last_message_is_not_from_the_model():
    state = {"messages": [HumanMessage(content="hi")]}
    assert route_after_agent(state) == "render"


# ---------- budget_spent ----------


def test_budget_not_spent_at_start():
    assert budget_spent({"tool_rounds": 0}, fake_runtime()) is False


def test_budget_spent_after_max_rounds():
    assert budget_spent({"tool_rounds": 3}, fake_runtime()) is True


def test_budget_spent_when_time_limit_passed():
    runtime = fake_runtime(started_at=time.monotonic() - 31)

    assert budget_spent({"tool_rounds": 0}, runtime) is True


def test_budget_without_context_counts_only_rounds():
    runtime = SimpleNamespace(context=None)

    assert budget_spent({"tool_rounds": 0}, runtime) is False
    assert budget_spent({"tool_rounds": 3}, runtime) is True


# ---------- render ----------


async def test_render_returns_the_model_text():
    state = {
        "messages": [AIMessage(content="ok")],
        "tool_rounds": 0,
    }

    out = await render(state, fake_runtime())

    assert out == {"response": "ok"}


async def test_render_strips_citation_markers():
    state = {
        "messages": [AIMessage(content="ok【0†L1-L3】")],
        "tool_rounds": 0,
    }

    assert (await render(state, fake_runtime()))["response"] == "ok"


async def test_render_removes_the_space_before_a_citation_marker():
    state = {
        "messages": [AIMessage(content="each 【0†L1】.")],
        "tool_rounds": 0,
    }

    assert (await render(state, fake_runtime()))["response"] == "each."


async def test_render_rejects_a_reply_that_is_only_a_marker():
    state = {
        "messages": [AIMessage(content="【0†L1-L3】")],
        "tool_rounds": 0,
    }

    with pytest.raises(ValueError):
        await render(state, fake_runtime())


async def test_render_adds_a_note_when_the_reply_was_cut_off():
    message = AIMessage(
        content="partial",
        response_metadata={"finish_reason": "length"},
    )

    out = await render(
        {"messages": [message], "tool_rounds": 0},
        fake_runtime(),
    )

    assert out["response"].endswith(
        "[The answer was cut off because it reached the length limit.]"
    )


async def test_render_adds_no_cut_off_note_for_a_normal_stop():
    message = AIMessage(
        content="whole",
        response_metadata={"finish_reason": "stop"},
    )

    out = await render(
        {"messages": [message], "tool_rounds": 0},
        fake_runtime(),
    )

    assert out["response"] == "whole"


async def test_render_adds_footer_only_when_tools_were_used():
    runtime = fake_runtime(unavailable=("github",))

    with_tools = await render(
        {"messages": [AIMessage(content="ok")], "tool_rounds": 1},
        runtime,
    )
    without_tools = await render(
        {"messages": [AIMessage(content="ok")], "tool_rounds": 0},
        runtime,
    )

    assert with_tools["response"] == f"ok\n\n{FOOTER}"
    assert without_tools["response"] == "ok"


async def test_render_adds_no_footer_when_every_source_was_available():
    out = await render(
        {"messages": [AIMessage(content="ok")], "tool_rounds": 2},
        fake_runtime(),
    )

    assert out["response"] == "ok"


# ---------- run_tools ----------


class FakeTool:
    """FAKE tool: returns a prepared result or raises, without network."""

    def __init__(
        self,
        name: str,
        result=None,
        error: Exception | None = None,
    ):
        self.name = name
        self.result = result
        self.error = error
        self.calls = 0

    async def ainvoke(self, call):
        self.calls += 1

        if self.error is not None:
            raise self.error

        return self.result


def tools_state(*calls: dict, rounds: int = 0) -> dict:
    return {
        "messages": [
            AIMessage(content="", tool_calls=list(calls))
        ],
        "tool_rounds": rounds,
    }


async def test_run_tools_answers_every_call_exactly_once():
    good = FakeTool(
        "good_tool",
        result=ToolMessage(
            content=[{"type": "text", "text": "result"}],
            tool_call_id="1",
            status="success",
        ),
    )
    broken = FakeTool(
        "broken_tool",
        error=RuntimeError("secret detail"),
    )

    runtime = fake_runtime(tools=[good, broken])
    state = tools_state(
        tool_call("good_tool", "1"),
        tool_call("missing_tool", "2"),
        tool_call("broken_tool", "3"),
    )

    out = await run_tools(state, runtime)
    replies = out["messages"]

    assert [reply.tool_call_id for reply in replies] == ["1", "2", "3"]
    assert [reply.status for reply in replies] == [
        "success",
        "error",
        "error",
    ]
    assert replies[0].content == "result"
    assert "secret detail" not in replies[2].content
    assert good.calls == 1
    assert broken.calls == 1
    assert out["tool_rounds"] == 1


async def test_run_tools_runs_nothing_when_the_budget_is_spent(
    monkeypatch,
):
    monkeypatch.setattr(
        "changelens.graph.budget_spent",
        lambda state, runtime: True,
    )

    tool = FakeTool(
        "good_tool",
        result=ToolMessage(content="x", tool_call_id="1"),
    )

    out = await run_tools(
        tools_state(tool_call("good_tool", "1")),
        fake_runtime(tools=[tool]),
    )

    reply = out["messages"][0]

    assert tool.calls == 0
    assert reply.status == "error"
    assert reply.tool_call_id == "1"
    assert "budget" not in reply.content.lower()
    assert "not run" in reply.content.lower()


async def test_run_tools_counts_rounds_from_the_saved_state():
    out = await run_tools(
        tools_state(tool_call("missing_tool", "1"), rounds=2),
        fake_runtime(),
    )

    assert out["tool_rounds"] == 3


async def test_run_tools_does_not_execute_tool_without_server_mapping():
    tool = FakeTool(
        "unmapped_tool",
        result=ToolMessage(content="x", tool_call_id="1"),
    )

    out = await run_tools(
        tools_state(tool_call("unmapped_tool", "1")),
        fake_runtime(tools=[tool], tool_servers={}),
    )

    assert tool.calls == 0
    assert len(out["messages"]) == 1
    assert out["messages"][0].tool_call_id == "1"
    assert out["messages"][0].status == "error"
    assert out["messages"][0].content == (
        "Unknown tool. It was not executed."
    )


# ---------- agent ----------


class FakeLLM:
    """FAKE model: returns prepared replies in order."""

    def __init__(self, *replies: AIMessage):
        self.replies = list(replies)
        self.calls: list[list] = []
        self.bind_calls = 0

    def bind_tools(self, tools):
        self.bind_calls += 1
        return self

    async def ainvoke(self, messages):
        self.calls.append(messages)
        return self.replies.pop(0)


def patch_llm(
    monkeypatch: pytest.MonkeyPatch,
    llm: FakeLLM,
) -> None:
    monkeypatch.setattr(
        "changelens.graph.get_llm",
        lambda: llm,
    )


def agent_state(rounds: int = 0) -> dict:
    return {
        "messages": [HumanMessage(content="hi")],
        "tool_rounds": rounds,
    }


async def test_agent_without_tools_says_so_in_the_system_message(
    monkeypatch,
):
    llm = FakeLLM(AIMessage(content="hello"))
    patch_llm(monkeypatch, llm)

    out = await agent(agent_state(), fake_runtime())
    system = llm.calls[0][0]

    assert isinstance(system, SystemMessage)
    assert "No lookup tools are available" in system.content
    assert "{" not in system.content
    assert llm.bind_calls == 0
    assert out["messages"][0].content == "hello"


async def test_agent_with_tools_names_sources_and_unavailable_sources(
    monkeypatch,
):
    llm = FakeLLM(AIMessage(content="hello"))
    patch_llm(monkeypatch, llm)

    runtime = fake_runtime(
        tools=[object()],
        sources=("tavily", "context7"),
        unavailable=("github",),
    )

    await agent(agent_state(), runtime)
    system = llm.calls[0][0].content

    assert "web search" in system
    assert "library documentation" in system
    assert "public GitHub repositories" in system
    assert "{" not in system
    assert llm.bind_calls == 1


async def test_agent_does_not_bind_tools_once_the_budget_is_spent(
    monkeypatch,
):
    llm = FakeLLM(AIMessage(content="answer"))
    patch_llm(monkeypatch, llm)

    await agent(
        agent_state(rounds=3),
        fake_runtime(tools=[object()], sources=("tavily",)),
    )

    assert llm.bind_calls == 0
    assert "You cannot look anything more up" in llm.calls[0][0].content


async def test_agent_asks_again_when_an_unbound_model_requests_tools(
    monkeypatch,
):
    llm = FakeLLM(
        AIMessage(
            content="",
            tool_calls=[tool_call("query-docs", "c1")],
        ),
        AIMessage(content="Final answer"),
    )
    patch_llm(monkeypatch, llm)

    out = await agent(
        agent_state(rounds=3),
        fake_runtime(tools=[object()], sources=("tavily",)),
    )

    message = out["messages"][0]

    assert message.content == "Final answer"
    assert message.tool_calls == []
    assert len(llm.calls) == 2

    retry_request = llm.calls[1][-1]

    assert isinstance(retry_request, HumanMessage)
    assert retry_request.content == FINAL_ANSWER_REQUEST


async def test_agent_falls_back_when_the_retry_also_gives_no_text(
    monkeypatch,
):
    llm = FakeLLM(
        AIMessage(
            content="",
            tool_calls=[tool_call("query-docs", "c1")],
        ),
        AIMessage(content=""),
    )
    patch_llm(monkeypatch, llm)

    out = await agent(agent_state(), fake_runtime())

    assert out["messages"][0].content == NO_ANSWER_TEXT