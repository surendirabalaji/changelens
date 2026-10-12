import logging
import re
import time

from mcp.shared.exceptions import McpError
from mcp.types import (
    CallToolResult,
    EmbeddedResource,
    TextContent,
    TextResourceContents,
)
from pydantic import ValidationError

from changelens.errors import TRANSIENT_KINDS, FailureKind, classify


MAX_TOOL_CHARS = 8000
ERROR_TEXT_CHARS = 500
NON_TEXT_PLACEHOLDER = "[non-text content omitted]"

CATEGORY_PATTERNS = [
    (
        FailureKind.AUTH.value,
        r"\b401\b|\b403\b|unauthorized|forbidden|bad credentials",
    ),
    (
        FailureKind.NOT_FOUND.value,
        r"\b404\b|not found|does not exist|could not resolve",
    ),
    (
        FailureKind.RATE_LIMITED.value,
        r"\b429\b|rate limit|too many requests",
    ),
    (
        FailureKind.INVALID_ARGUMENTS.value,
        r"validation error|invalid arguments|is not of type|required|missing",
    ),
]

logger = logging.getLogger(__name__)


def looks_malformed(result: CallToolResult) -> str | None:
    """Return a fixed reason for unusable successful responses."""
    if result.isError:
        return None

    # Empty output is valid.
    if not result.content:
        return None

    for block in result.content:
        if isinstance(block, TextContent):
            return None

        if (
            isinstance(block, EmbeddedResource)
            and isinstance(block.resource, TextResourceContents)
        ):
            return None

    # An empty dictionary still counts as present structured content.
    if result.structuredContent is not None:
        return None

    return "only non-text content"


def flatten_content(blocks) -> str:
    parts = []

    for block in blocks:
        if isinstance(block, TextContent):
            parts.append(block.text)
        elif (
            isinstance(block, EmbeddedResource)
            and isinstance(block.resource, TextResourceContents)
        ):
            parts.append(block.resource.text)
        else:
            parts.append(NON_TEXT_PLACEHOLDER)

    return "\n".join(parts)


def categorize(text: str) -> str:
    lowered = text.lower()

    for category, pattern in CATEGORY_PATTERNS:
        if re.search(pattern, lowered):
            return category

    return FailureKind.TOOL_ERROR.value


def _malformed_result(
    request,
    reason: str,
    started: float,
    chars: int = 0,
) -> CallToolResult:
    # Log only a fixed reason and length, never rejected server content
    # or validation exception details.
    logger.warning(
        "mcp_guard server=%s tool=%s category=%s "
        "reason=%s chars=%d seconds=%.2f",
        request.server_name,
        request.name,
        FailureKind.MALFORMED.value,
        reason,
        chars,
        time.monotonic() - started,
    )

    # The server answered, but its response is unusable.
    # graph.py treats MALFORMED as non-transient, resets the breaker,
    # and returns an error ToolMessage without retrying.
    return CallToolResult(
        content=[
            TextContent(
                type="text",
                text=f"Tool error ({FailureKind.MALFORMED.value}): {reason}",
            )
        ],
        isError=True,
    )


async def guard(request, handler):
    started = time.monotonic()

    try:
        result = await handler(request)

    except ValidationError:
        # Response-side validation happens inside the MCP handler.
        return _malformed_result(
            request,
            reason="response failed validation",
            started=started,
        )

    except RuntimeError as error:
        message = str(error)

        if message.startswith("Invalid structured content"):
            return _malformed_result(
                request,
                reason="invalid structured content",
                started=started,
            )

        if message.startswith("Invalid schema"):
            return _malformed_result(
                request,
                reason="invalid output schema",
                started=started,
            )

        # Unrelated runtime errors are handled by the caller.
        raise

    except McpError as error:
        # Preserve transport closures and timeouts as exceptions so
        # graph.py can update the breaker and decide whether to retry.
        if classify(error) in TRANSIENT_KINDS:
            raise

        result = CallToolResult(
            content=[
                TextContent(
                    type="text",
                    text=error.error.message,
                )
            ],
            isError=True,
        )

    if not isinstance(result, CallToolResult):
        # ToolMessage or Command: leave unchanged.
        return result

    # Inspect the raw MCP result before flattening removes its shape.
    reason = looks_malformed(result)
    if reason is not None:
        return _malformed_result(
            request,
            reason=reason,
            started=started,
            chars=len(flatten_content(result.content)),
        )

    text = flatten_content(result.content)
    chars = len(text)
    truncated = False
    category = "-"

    if result.isError:
        category = categorize(text)
        out = (
            f"Tool error ({category}): "
            f"{text[:ERROR_TEXT_CHARS] or 'no details'}"
        )

        guarded = CallToolResult(
            content=[TextContent(type="text", text=out)],
            isError=True,
        )

    else:
        if chars > MAX_TOOL_CHARS:
            truncated = True
            text = text[:MAX_TOOL_CHARS] + (
                f"\n[truncated: showing {MAX_TOOL_CHARS} "
                f"of {chars} characters]"
            )

        guarded = CallToolResult(
            content=[
                TextContent(
                    type="text",
                    text=text or "[empty result]",
                )
            ],
            isError=False,
            structuredContent=result.structuredContent,
        )

    logger.info(
        "mcp_guard server=%s tool=%s is_error=%s category=%s "
        "chars=%d truncated=%s seconds=%.2f",
        request.server_name,
        request.name,
        result.isError,
        category,
        chars,
        truncated,
        time.monotonic() - started,
    )

    return guarded