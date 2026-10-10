
"""Unit tests for changelens.mcp_tools.guard.

FAKE: handlers, sessions and tool results are fake (no network).
RECORDED: the category table loads real error texts saved in docs/evidence/g0.
SYNTHETIC: auth and rate-limit texts, because none were recorded.
"""
import json
import logging
from pathlib import Path

import pytest
from langchain_core.messages import ToolMessage
from langchain_mcp_adapters.interceptors import MCPToolCallRequest
from langchain_mcp_adapters.tools import convert_mcp_tool_to_langchain_tool
from mcp.shared.exceptions import McpError
from mcp.types import (
    AudioContent,
    BlobResourceContents,
    CallToolResult,
    EmbeddedResource,
    ErrorData,
    ImageContent,
    TextContent,
    TextResourceContents,
)
from mcp.types import Tool as MCPTool

from changelens.graph import message_text
from changelens.mcp_tools.guard import (
    ERROR_TEXT_CHARS,
    MAX_TOOL_CHARS,
    NON_TEXT_PLACEHOLDER,
    categorize,
    flatten_content,
    guard,
)

EVIDENCE = Path(__file__).resolve().parents[1] / "docs" / "evidence" / "g0"


def recorded_error_text(relative_path: str) -> str:
    """Return the error text from a recorded M0 probe file (real data, not a mock)."""
    data = json.loads((EVIDENCE / relative_path).read_text(encoding="utf-8"))
    if "error" in data:  # the Tavily file records a raised McpError as a string
        return data["error"].removeprefix("McpError: ")
    return data["content"][0]["text"]


def make_result(text: str, is_error: bool = False) -> CallToolResult:
    return CallToolResult(content=[TextContent(type="text", text=text)], isError=is_error)


def make_request(args: dict | None = None) -> MCPToolCallRequest:
    return MCPToolCallRequest(
        name="get_file_contents",
        args=args or {},
        server_name="github",
        headers=None,
        runtime=None,
    )


def fake_handler(result):  # FAKE handler: returns a fixed result
    async def handler(request):
        return result

    return handler


def raising_handler(error: BaseException):  # FAKE handler: always raises
    async def handler(request):
        raise error

    return handler


def result_text(result: CallToolResult) -> str:
    return result.content[0].text


# ---------- guard: success path ----------

async def test_short_text_passes_unchanged():
    out = await guard(make_request(), fake_handler(make_result("hello")))
    assert out.isError is False
    assert result_text(out) == "hello"


async def test_text_exactly_at_limit_is_not_truncated():
    text = "x" * MAX_TOOL_CHARS
    out = await guard(make_request(), fake_handler(make_result(text)))
    assert result_text(out) == text


async def test_long_text_is_cut_with_visible_marker():
    out = await guard(make_request(), fake_handler(make_result("x" * 20000)))
    marker = f"\n[truncated: showing {MAX_TOOL_CHARS} of 20000 characters]"
    assert out.isError is False
    assert result_text(out) == "x" * MAX_TOOL_CHARS + marker
    assert "showing 8000 of 20000 characters" in result_text(out)


async def test_empty_success_gets_placeholder():
    out = await guard(make_request(), fake_handler(make_result("")))
    assert out.isError is False
    assert result_text(out) == "[empty result]"


async def test_structured_content_is_dropped():
    raw = CallToolResult(
        content=[TextContent(type="text", text="data")],
        structuredContent={"big": "payload"},
        isError=False,
    )
    out = await guard(make_request(), fake_handler(raw))
    assert out.structuredContent is None


# ---------- guard: error path ----------

async def test_error_result_is_labelled_and_stays_an_error():
    raw = make_result("The file does not exist in the repository.", is_error=True)
    out = await guard(make_request(), fake_handler(raw))
    assert out.isError is True
    assert result_text(out).startswith("Tool error (not_found):")


async def test_error_text_is_capped():
    out = await guard(make_request(), fake_handler(make_result("x" * 2000, is_error=True)))
    assert result_text(out) == f"Tool error (tool_error): {'x' * ERROR_TEXT_CHARS}"


async def test_empty_error_text_gets_placeholder():
    out = await guard(make_request(), fake_handler(make_result("", is_error=True)))
    assert result_text(out) == "Tool error (tool_error): no details"


# ---------- guard: exceptions and pass-through ----------

async def test_transport_error_propagates():
    with pytest.raises(RuntimeError):
        await guard(make_request(), raising_handler(RuntimeError("connection refused")))


async def test_non_call_tool_result_passes_through_unchanged():
    message = ToolMessage(content="already a message", tool_call_id="1")
    out = await guard(make_request(), fake_handler(message))
    assert out is message


async def test_mcp_error_becomes_invalid_arguments_result():
    message = recorded_error_text("tavily/call_bad_args_exception.json")
    error = McpError(ErrorData(code=-32603, message=message))  # code is FAKE; any non-408 works
    out = await guard(make_request(), raising_handler(error))
    assert out.isError is True
    assert result_text(out).startswith("Tool error (invalid_arguments):")


async def test_mcp_timeout_error_propagates():
    error = McpError(ErrorData(code=408, message="Timed out while waiting for response"))
    with pytest.raises(McpError):
        await guard(make_request(), raising_handler(error))


# ---------- guard: logging ----------

async def test_log_line_has_no_arguments_or_result_text(caplog):
    caplog.set_level(logging.INFO, logger="changelens.mcp_tools.guard")
    request = make_request(args={"token": "s3cret"})
    await guard(request, fake_handler(make_result("private-text")))
    records = [r for r in caplog.records if r.name == "changelens.mcp_tools.guard"]
    assert len(records) == 1
    assert "server=github" in caplog.text
    assert "tool=get_file_contents" in caplog.text
    assert "s3cret" not in caplog.text
    assert "private-text" not in caplog.text


# ---------- flatten_content ----------

def test_flatten_text_blocks_are_joined_with_newlines():
    blocks = [TextContent(type="text", text="a"), TextContent(type="text", text="b")]
    assert flatten_content(blocks) == "a\nb"


def test_flatten_embedded_text_resource_gives_its_text():
    block = EmbeddedResource(
        type="resource",
        resource=TextResourceContents(uri="file:///a.txt", text="hi"),
    )
    assert flatten_content([block]) == "hi"


def test_flatten_blob_image_and_audio_give_placeholder():
    blocks = [
        EmbeddedResource(
            type="resource",
            resource=BlobResourceContents(uri="file:///b.bin", blob="AAAA"),
        ),
        ImageContent(type="image", data="AAAA", mimeType="image/png"),
        AudioContent(type="audio", data="AAAA", mimeType="audio/wav"),
    ]
    assert flatten_content(blocks) == "\n".join([NON_TEXT_PLACEHOLDER] * 3)


# ---------- categorize ----------

RECORDED_CASES = [
    ("github/call_not_found.json", "not_found"),
    # The file name says "pat" but the recorded text is a 404. GitHub also returns
    # 404 for repositories you cannot see, so "not_found" can mean "no access".
    ("github/pat_negative.json", "not_found"),
    ("github/call_bad_args.json", "invalid_arguments"),
    ("context7/call_bad_args.json", "invalid_arguments"),
    ("tavily/call_bad_args_exception.json", "invalid_arguments"),
]


@pytest.mark.parametrize("relative_path, expected", RECORDED_CASES)
def test_category_of_recorded_real_error_texts(relative_path, expected):
    assert categorize(recorded_error_text(relative_path)) == expected


SYNTHETIC_CASES = [  # SYNTHETIC strings: no real auth or rate-limit text was recorded
    ("401 Unauthorized", "auth"),
    ("Bad credentials", "auth"),
    ("HTTP 403 Forbidden", "auth"),
    ("API rate limit exceeded (429)", "rate_limited"),
    ("Too many requests, slow down", "rate_limited"),
    ("something broke", "tool_error"),
    ("NOT FOUND", "not_found"),  # matching ignores case
]


@pytest.mark.parametrize("text, expected", SYNTHETIC_CASES)
def test_category_of_synthetic_texts(text, expected):
    assert categorize(text) == expected


def test_status_code_must_be_a_whole_number():
    assert categorize("order 14043 failed") == "tool_error"


# ---------- guard through the real adapter (fake session) ----------

class FakeSession:  # FAKE MCP session: returns a fixed CallToolResult
    def __init__(self, result: CallToolResult):
        self.result = result

    async def call_tool(self, name, arguments=None, progress_callback=None, **kwargs):
        return self.result


def make_adapter_tool(result: CallToolResult):
    mcp_tool = MCPTool(
        name="get_file_contents",
        description="fake tool",
        inputSchema={"type": "object", "properties": {}},
    )
    return convert_mcp_tool_to_langchain_tool(
        FakeSession(result), mcp_tool, tool_interceptors=[guard], server_name="github"
    )


async def test_adapter_returns_labelled_error_message():
    tool = make_adapter_tool(make_result("repo does not exist (404)", is_error=True))
    message = await tool.ainvoke(
        {"type": "tool_call", "name": "get_file_contents", "args": {}, "id": "t1"}
    )
    assert isinstance(message, ToolMessage)
    assert message.status == "error"
    assert message.tool_call_id == "t1"
    assert message_text(message.content).startswith("Tool error (not_found):")


async def test_adapter_returns_truncated_success_message():
    tool = make_adapter_tool(make_result("x" * 20000))
    message = await tool.ainvoke(
        {"type": "tool_call", "name": "get_file_contents", "args": {}, "id": "t2"}
    )
    text = message_text(message.content)
    assert message.status == "success"
    assert text.endswith("[truncated: showing 8000 of 20000 characters]")