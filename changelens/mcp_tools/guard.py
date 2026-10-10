import logging
import re
import time

from mcp.shared.exceptions import McpError
from mcp.types import CallToolResult, EmbeddedResource, TextContent, TextResourceContents


MAX_TOOL_CHARS = 8000
ERROR_TEXT_CHARS = 500
NON_TEXT_PLACEHOLDER = "[non-text content omitted]"
CATEGORY_PATTERNS = [
    ("auth", r"\b401\b|\b403\b|unauthorized|forbidden|bad credentials"),
    ("not_found", r"\b404\b|not found|does not exist|could not resolve"),
    ("rate_limited", r"\b429\b|rate limit|too many requests"),
    ("invalid_arguments", r"validation error|invalid arguments|is not of type|required|missing"),
]


logger = logging.getLogger(__name__)


def flatten_content(blocks) -> str:
    parts = []
    for block in blocks:
        if isinstance(block, TextContent):
            parts.append(block.text)
        elif isinstance(block, EmbeddedResource) and isinstance(block.resource, TextResourceContents):
            parts.append(block.resource.text)
        else:
            parts.append(NON_TEXT_PLACEHOLDER)
    return "\n".join(parts)

def categorize(text: str) -> str:
    lowered = text.lower()
    for category, pattern in CATEGORY_PATTERNS:
        if re.search(pattern, lowered):
            return category
    return "tool_error"

async def guard(request, handler):
    started = time.monotonic()
    try:
        result = await handler(request)
    except McpError as error:
        if error.error.code == 408:
            raise
        result = CallToolResult(
            content = [TextContent(type="text",text = error.error.message)], isError = True)
    if not isinstance(result, CallToolResult):
        return result                    # ToolMessage or Command: leave alone
    text = flatten_content(result.content)
    chars = len(text)
    truncated = False
    category = "-"

    if result.isError:
        category = categorize(text)
        out = f"Tool error ({category}): {text[:ERROR_TEXT_CHARS] or 'no details'}"
        guarded = CallToolResult(
            content=[TextContent(type="text", text=out)],
            isError=True,
        )
    else:
        if chars > MAX_TOOL_CHARS:
            truncated = True
            text = text[:MAX_TOOL_CHARS] + (
                f"\n[truncated: showing {MAX_TOOL_CHARS} of {chars} characters]"
            )
        guarded = CallToolResult(
            content=[TextContent(type="text", text=text or "[empty result]")],
            isError=False,
        )

    logger.info(
        "mcp_guard server=%s tool=%s is_error=%s category=%s chars=%d truncated=%s seconds=%.2f",
        request.server_name,
        request.name,
        result.isError,
        category,
        chars,
        truncated,
        time.monotonic() - started,
    )
    return guarded