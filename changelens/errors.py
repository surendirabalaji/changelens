from enum import Enum

import httpx
from anyio import BrokenResourceError, ClosedResourceError, EndOfStream
from langchain_core.tools import ToolException
from mcp.shared.exceptions import McpError
from mcp.types import CONNECTION_CLOSED
from pydantic import ValidationError


def describe(error: BaseException) -> str:
    """Flatten exception groups into one short line per error."""
    if isinstance(error, BaseExceptionGroup):
        return " | ".join(describe(sub) for sub in error.exceptions)

    message = str(error)[:200]
    return (
        f"{type(error).__name__}: {message}"
        if message
        else type(error).__name__
    )


class FailureKind(str, Enum):
    TRANSPORT = "transport"
    TIMEOUT = "timeout"
    AUTH = "auth"
    NOT_FOUND = "not_found"
    RATE_LIMITED = "rate_limited"
    INVALID_ARGUMENTS = "invalid_arguments"
    TOOL_ERROR = "tool_error"
    MALFORMED = "malformed"


TRANSIENT_KINDS = frozenset({
    FailureKind.TRANSPORT,
    FailureKind.TIMEOUT,
    FailureKind.RATE_LIMITED,
})


def classify(error: BaseException) -> FailureKind:
    """Map an exception to a kind; groups use their first member."""
    if isinstance(error, BaseExceptionGroup):
        return classify(error.exceptions[0])

    # Local argument and tool errors do not imply connectivity failures.
    if isinstance(error, ValidationError):
        return FailureKind.INVALID_ARGUMENTS

    if isinstance(error, ToolException):
        return FailureKind.TOOL_ERROR

    # Check timeouts before broader network types:
    # TimeoutError subclasses OSError, and HTTPX timeouts
    # subclass httpx.TransportError.
    if isinstance(error, (TimeoutError, httpx.TimeoutException)):
        return FailureKind.TIMEOUT

    if isinstance(error, httpx.HTTPStatusError):
        status = error.response.status_code

        if status in (401, 403):
            return FailureKind.AUTH
        if status == 404:
            return FailureKind.NOT_FOUND
        if status == 408:
            return FailureKind.TIMEOUT
        if status == 429:
            return FailureKind.RATE_LIMITED
        if 500 <= status < 600:
            return FailureKind.TRANSPORT

        return FailureKind.TOOL_ERROR

    if isinstance(error, McpError):
        if error.error.code == CONNECTION_CLOSED:
            return FailureKind.TRANSPORT
        if error.error.code == 408:
            return FailureKind.TIMEOUT
        return FailureKind.TOOL_ERROR

    # Include stream closures, which are not necessarily OSError
    # or HTTPX exceptions.
    if isinstance(
        error,
        (
            httpx.TransportError,
            OSError,
            ClosedResourceError,
            BrokenResourceError,
            EndOfStream,
        ),
    ):
        return FailureKind.TRANSPORT
    
    return FailureKind.TOOL_ERROR