"""OpenCollab MCP Server — AI-powered open source contribution matchmaker.

Slim entry point. All 6 tools live in src/opencollab_mcp/tools/, organized
by category to match the three sections in the README.

Supports both STDIO (local) and streamable-HTTP (remote) transports.
Set TRANSPORT=streamable-http and optionally PORT=8000 for remote deployment.
"""

from __future__ import annotations

import logging
import os

from mcp.server.fastmcp import FastMCP

from .tools import discovery, evaluation, issues


def _configure_logging() -> None:
    level_name = os.environ.get("OPENCOLLAB_LOG_LEVEL", "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )


def build_server() -> FastMCP:
    """Build and register all 6 tools onto a FastMCP instance."""
    mcp = FastMCP("opencollab_mcp")
    discovery.register(mcp)
    evaluation.register(mcp)
    issues.register(mcp)
    return mcp


# Module-level instance (used by tests and `mcp dev` integrations).
mcp = build_server()


def main() -> None:
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
