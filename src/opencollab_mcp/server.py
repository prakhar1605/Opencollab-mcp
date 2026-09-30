"""OpenCollab MCP Server — AI-powered open source contribution matchmaker.

Slim entry point. All 6 tools live in src/opencollab_mcp/tools/, organized
by category to match the three sections in the README.

Supports STDIO (local), streamable-HTTP, and legacy SSE (remote) transports.
Set TRANSPORT and optionally HOST / PORT for remote deployment.
"""

from __future__ import annotations

import logging
import os

from mcp.server.mcpserver import MCPServer
from starlette.requests import Request
from starlette.responses import PlainTextResponse

from .constants import __version__
from .tools import discovery, evaluation, issues


def _configure_logging() -> None:
    level_name = os.environ.get("OPENCOLLAB_LOG_LEVEL", "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )


def build_server() -> MCPServer:
    """Build and register all 6 tools onto an MCPServer instance."""
    mcp = MCPServer("opencollab_mcp", version=__version__)
    discovery.register(mcp)
    evaluation.register(mcp)
    issues.register(mcp)

    @mcp.custom_route("/health", methods=["GET"], include_in_schema=False)
    async def health_check(_: Request) -> PlainTextResponse:
        return PlainTextResponse("ok")

    return mcp


# Module-level instance (used by tests and `mcp dev` integrations).
mcp = build_server()


def main() -> None:
    _configure_logging()
    transport = os.environ.get("TRANSPORT", "stdio").lower()
    logger = logging.getLogger("opencollab_mcp")

    if transport in ("streamable-http", "http"):
        # Default 0.0.0.0 keeps existing Docker / remote deployments unchanged.
        # Set HOST=127.0.0.1 to bind only to loopback on a local machine.
        host = os.environ.get("HOST", "0.0.0.0")
        port = int(os.environ.get("PORT", "8000"))
        logger.info("Starting OpenCollab MCP on streamable-http (%s:%d)", host, port)
        mcp.run(transport="streamable-http", host=host, port=port)
    elif transport == "sse":
        # Legacy SSE transport — kept for backwards compatibility.
        host = os.environ.get("HOST", "0.0.0.0")
        port = int(os.environ.get("PORT", "8000"))
        logger.info("Starting OpenCollab MCP on SSE (%s:%d)", host, port)
        mcp.run(transport="sse", host=host, port=port)
    else:
        logger.info("Starting OpenCollab MCP on stdio")
        mcp.run()


if __name__ == "__main__":
    main()
