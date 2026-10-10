

from contextlib import AsyncExitStack
from dataclasses import dataclass
import logging
import time

from langchain_core.tools import BaseTool
from langchain_mcp_adapters.client import MultiServerMCPClient

from changelens.config import get_settings
from changelens.errors import describe
from changelens.mcp_tools.connections import ALLOWED_TOOLS, build_connections
from changelens.mcp_tools.loader import load_allowed_tools

logger = logging.getLogger(__name__)

@dataclass(frozen=True)
class OpenTools:
    tools: list[BaseTool]
    available: tuple[str,...]
    unavailable: tuple[str,...]



async def open_tools(stack: AsyncExitStack) -> OpenTools:
    start = time.monotonic()
    connections = build_connections(get_settings())
    client = MultiServerMCPClient(connections)

    tools: list[BaseTool] = []
    available: list[str] = []
    unavailable: list[str] = []

    # Track which server provided each tool.
    tool_servers: list[tuple[str, BaseTool]] = []

    for server in ALLOWED_TOOLS:
        if server not in connections:
            logger.warning("MCP server %s not configured", server)
            unavailable.append(server)
            continue

        started = time.monotonic()

        try:
            session = await stack.enter_async_context(
                client.session(server)
            )
            server_tools = await load_allowed_tools(session, server)

        except Exception as error:
            logger.warning(
                "MCP server %s unavailable (%s)",
                server,
                describe(error),
            )
            unavailable.append(server)
            continue

        if not server_tools:
            logger.warning("MCP server %s has no allowed tools", server)
            unavailable.append(server)
            continue

        available.append(server)

        for tool in server_tools:
            tool_servers.append((server, tool))

        logger.info(
            "MCP server %s loaded %d tools in %.2fs",
            server,
            len(server_tools),
            time.monotonic() - started,
        )

    # Remove duplicate tool names, keeping the first occurrence.
    seen: dict[str, str] = {}

    for server, tool in tool_servers:
        if tool.name in seen:
            logger.warning(
                "Duplicate MCP tool %s from servers %s and %s; keeping %s",
                tool.name,
                seen[tool.name],
                server,
                seen[tool.name],
            )
            continue

        seen[tool.name] = server
        tools.append(tool)

    logger.info(
        "MCP tools initialized in %.2fs: "
        "%d tools, available=%s, unavailable=%s",
        time.monotonic() - start,
        len(tools),
        available,
        unavailable,
    )

    return OpenTools(
        tools=tools,
        available=tuple(available),
        unavailable=tuple(unavailable),
    )