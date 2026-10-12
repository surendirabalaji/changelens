import pytest
from mcp.shared.exceptions import McpError
from mcp.types import ErrorData

from changelens.errors import TRANSIENT_KINDS, FailureKind, classify


@pytest.mark.parametrize(
    "error, expected",
    [
        pytest.param(TimeoutError(), FailureKind.TIMEOUT, id="timeout-error"),
        pytest.param(ConnectionRefusedError(), FailureKind.TRANSPORT, id="connection-refused"),
        pytest.param(
            McpError(ErrorData(code=408, message="t")),
            FailureKind.TIMEOUT,
            id="mcp-408",
        ),
        pytest.param(
            McpError(ErrorData(code=-32602, message="t")),
            FailureKind.TOOL_ERROR,
            id="mcp-other-code",
        ),
        pytest.param(
            ExceptionGroup("x", [ConnectionRefusedError()]),
            FailureKind.TRANSPORT,
            id="group-wrapping-connection-refused",
        ),
    ],
)
def test_classify(error, expected):
    assert classify(error) == expected


def test_timeout_is_transient():
    assert FailureKind.TIMEOUT in TRANSIENT_KINDS


def test_not_found_is_not_transient():
    assert FailureKind.NOT_FOUND not in TRANSIENT_KINDS