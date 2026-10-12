import asyncio
from contextlib import AsyncExitStack
from dataclasses import dataclass, field
import logging
import random
import time

from langchain_core.tools import BaseTool
from langchain_mcp_adapters.client import MultiServerMCPClient

from changelens.config import get_settings
from changelens.errors import TRANSIENT_KINDS, FailureKind, classify, describe
from changelens.mcp_tools.breaker import CircuitBreaker, get_breaker
from changelens.mcp_tools.connections import ALLOWED_TOOLS, build_connections
from changelens.mcp_tools.loader import load_allowed_tools

logger = logging.getLogger(__name__)

_MIN_ATTEMPT_BUDGET_S = 0.1
_MIN_RETRY_BUDGET_S = 2.0


@dataclass(frozen=True)
class OpenTools:
    tools: list[BaseTool]
    available: tuple[str, ...]
    unavailable: tuple[str, ...]
    tool_servers: dict[str, str] = field(default_factory=dict)


async def _connect_once(
    client: MultiServerMCPClient,
    stack: AsyncExitStack,
    server: str,
    deadline_s: float,
) -> list[BaseTool]:
    async def _attempt() -> list[BaseTool]:
        session = await stack.enter_async_context(client.session(server))
        return await load_allowed_tools(session, server)

    return await asyncio.wait_for(_attempt(), timeout=deadline_s)


async def _connect_with_retry(
    client: MultiServerMCPClient,
    stack: AsyncExitStack,
    server: str,
    breaker: CircuitBreaker,
    budget_end: float,
) -> list[BaseTool] | None:
    """Make at most two attempts within this server's allocated budget."""
    settings = get_settings()

    for attempt in range(2):
        remaining = budget_end - time.monotonic()
        minimum_s = (
            _MIN_ATTEMPT_BUDGET_S
            if attempt == 0
            else _MIN_RETRY_BUDGET_S
        )

        if remaining < minimum_s:
            logger.warning(
                "MCP server %s attempt %d skipped: insufficient budget",
                server,
                attempt + 1,
            )
            return None

        if not breaker.allow(server):
            logger.warning(
                "MCP server %s skipped: circuit open or probe in flight",
                server,
            )
            return None

        timeout_s = min(settings.mcp_connect_deadline_s, remaining)
        budget_limited = timeout_s < settings.mcp_connect_deadline_s

        try:
            server_tools = await _connect_once(
                client=client,
                stack=stack,
                server=server,
                deadline_s=timeout_s,
            )
        except asyncio.CancelledError:
            breaker.release_probe(server)
            raise
        except Exception as error:
            kind = classify(error)

            if budget_limited and kind == FailureKind.TIMEOUT:
                # Policy: a timeout under a shortened budget is inconclusive.
                # Preserve failure history and release any reserved probe.
                breaker.release_probe(server)
                logger.warning(
                    "MCP server %s timed out with a reduced %.2fs budget; "
                    "not counted as a breaker failure",
                    server,
                    timeout_s,
                )
                return None

            breaker.record_failure(server, kind)

            logger.warning(
                "MCP server %s attempt %d failed (%s)",
                server,
                attempt + 1,
                describe(error),
            )

            if kind not in TRANSIENT_KINDS or attempt == 1:
                return None
        else:
            breaker.record_success(server)
            return server_tools

        delay_s = random.uniform(0, settings.mcp_retry_jitter_s)
        remaining = budget_end - time.monotonic()

        # Reserve enough time for a useful retry after backoff.
        if remaining - delay_s < _MIN_RETRY_BUDGET_S:
            logger.warning(
                "MCP server %s retry skipped: less than %.1fs available "
                "after backoff",
                server,
                _MIN_RETRY_BUDGET_S,
            )
            return None

        await asyncio.sleep(delay_s)

    return None

async def open_tools(stack: AsyncExitStack) -> OpenTools:
    start = time.monotonic()
    settings = get_settings()

    # Connections are sequential and share one overall budget.
    # Each configured server gets remaining_budget / servers_left for
    # its entire cycle, including attempts and retry jitter. Unused time
    # carries forward. Each attempt also has its own timeout cap.
    # Timeout cancellation cleanup can take additional time.
    budget_end = start + settings.mcp_open_budget_s

    connections = build_connections(settings)
    client = MultiServerMCPClient(connections)
    breaker = get_breaker()

    tools: list[BaseTool] = []
    available: list[str] = []
    unavailable: list[str] = []
    tool_servers: list[tuple[str, BaseTool]] = []

    servers_left = sum(
        server in connections
        for server in ALLOWED_TOOLS
    )

    for server in ALLOWED_TOOLS:
        if server not in connections:
            logger.warning(
                "MCP server %s not configured; skipping",
                server,
            )
            unavailable.append(server)
            continue

        now = time.monotonic()
        remaining = budget_end - now

        if remaining <= _MIN_ATTEMPT_BUDGET_S:
            servers_left -= 1
            logger.warning(
                "MCP server %s skipped: overall connection budget exhausted",
                server,
            )
            unavailable.append(server)
            continue

        # Allocate once per server, not once per attempt.
        share_s = remaining / servers_left
        server_budget_end = min(budget_end, now + share_s)
        servers_left -= 1

        started = now

        # This helper owns all breaker checks and outcome updates.
        server_tools = await _connect_with_retry(
            client=client,
            stack=stack,
            server=server,
            breaker=breaker,
            budget_end=server_budget_end,
        )

        if server_tools is None:
            unavailable.append(server)
            continue

        if not server_tools:
            logger.warning(
                "MCP server %s offered no allowlisted tools",
                server,
            )
            unavailable.append(server)
            continue

        available.append(server)
        tool_servers.extend((server, tool) for tool in server_tools)

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
        tool_servers = seen,
        available=tuple(available),
        unavailable=tuple(unavailable),
    )