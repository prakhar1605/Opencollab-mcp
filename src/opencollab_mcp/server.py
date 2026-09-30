"""OpenCollab MCP Server — AI-powered open source contribution matchmaker.

Slim entry point. All 6 tools live in src/opencollab_mcp/tools/, organized
by category to match the three sections in the README.

Supports STDIO (local), streamable-HTTP, and legacy SSE (remote) transports.
Set TRANSPORT and optionally PORT=8000 for remote deployment.
"""

from __future__ import annotations

import argparse
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


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        prog="opencollab-mcp",
        description="OpenCollab MCP Server — AI-powered open source contribution matchmaker.",
    )
    parser.add_argument(
        "-V",
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
    )
    parser.parse_known_args(argv)

    _configure_logging()
    transport = os.environ.get("TRANSPORT", "stdio").lower()
    logger = logging.getLogger("opencollab_mcp")

    if transport in ("streamable-http", "http"):
        port = int(os.environ.get("PORT", "8000"))
        logger.info("Starting OpenCollab MCP on streamable-http (port %d)", port)
        mcp.run(transport="streamable-http", host="0.0.0.0", port=port)
    elif transport == "sse":
        # Legacy SSE transport — kept for backwards compatibility.
        port = int(os.environ.get("PORT", "8000"))
        logger.info("Starting OpenCollab MCP on SSE (port %d)", port)
        mcp.run(transport="sse", host="0.0.0.0", port=port)
    else:
        logger.info("Starting OpenCollab MCP on stdio")
        mcp.run()


if __name__ == "__main__":
    main()
