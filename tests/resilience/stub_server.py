"""TEST-ONLY, not an integration."""

import argparse
import asyncio
import base64
import os

import uvicorn
from mcp.server.fastmcp import FastMCP
from mcp.types import CallToolResult, ImageContent


PNG_DATA = (
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwC"
    "AAAAC0lEQVR42mP8/x8AAwMCAO+jRZkAAAAASUVORK5CYII="
)


class HttpFault:
    """Reject HTTP requests but preserve the MCP application lifespan."""

    def __init__(self, app, status: int) -> None:
        self.app = app
        self.status = status

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        await send({
            "type": "http.response.start",
            "status": self.status,
            "headers": [(b"content-type", b"text/plain")],
        })
        await send({
            "type": "http.response.body",
            "body": b"Injected test HTTP failure",
        })


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--http-fault", type=int, choices=[401, 503])
    args = parser.parse_args()

    mcp = FastMCP(
        "resilience-stub",
        host="127.0.0.1",
        port=args.port,
    )

    @mcp.tool()
    async def stub_ok() -> str:
        """Return a predictable successful result."""
        return "Stub lookup succeeded."

    @mcp.tool()
    async def stub_slow() -> str:
        """Exceed the test's call timeout."""
        await asyncio.sleep(30)
        return "Slow lookup completed."

    @mcp.tool()
    async def stub_tool_error() -> str:
        """Produce a normal tool execution error."""
        raise RuntimeError("Deliberate stub failure")

    @mcp.tool()
    async def stub_malformed() -> CallToolResult:
        """Return image-only content without structured content."""
        # Decode once to check that the test payload is valid base64.
        base64.b64decode(PNG_DATA, validate=True)

        return CallToolResult(
            content=[
                ImageContent(
                    type="image",
                    data=PNG_DATA,
                    mimeType="image/png",
                )
            ],
            isError=False,
        )

    @mcp.tool()
    async def stub_die() -> str:
        """Kill this server process during a call."""
        os._exit(1)

    app = mcp.streamable_http_app()

    if args.http_fault is not None:
        app = HttpFault(app, args.http_fault)

    uvicorn.run(
        app,
        host="127.0.0.1",
        port=args.port,
    )


if __name__ == "__main__":
    main()