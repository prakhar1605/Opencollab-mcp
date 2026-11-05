"""OpenCollab MCP Server — AI-powered open source contribution matchmaker.

Slim entry point. All 6 tools live in src/opencollab_mcp/tools/, organized
by category to match the three sections in the README.

Supports STDIO (local), streamable-HTTP, and legacy SSE (remote) transports.
Set TRANSPORT and optionally PORT=8000 for remote deployment, or pass
--transport / --port on the command line (flags win over env vars).
"""

from __future__ import annotations

import argparse
import logging
import os
import sys

from mcp.server.mcpserver import MCPServer
from starlette.requests import Request
from starlette.responses import PlainTextResponse

from .constants import __version__
from .tools import discovery, evaluation, issues


def _configure_logging() -> None:
    level_name = os.environ.get("OPENCOLLAB_LOG_LEVEL", "INFO").upper()
    level = logging.getLevelName(level_name)
    known = isinstance(level, int)
    logging.basicConfig(
        level=level if known else logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )
    if not known:
        logging.getLogger("opencollab_mcp").warning(
            "Unknown OPENCOLLAB_LOG_LEVEL %r; valid levels are "
            "DEBUG, INFO, WARNING, ERROR, CRITICAL. Using INFO.",
            level_name,
        )


def _read_port(raw: str | None = None) -> int:
    """Validate a port value from a --port flag or the PORT env var.

    When raw is None, the PORT env var (default 8000) is used. Exits with
    the same error whether the bad value came from the flag or the env var.
    """
    if raw is None:
        raw = os.environ.get("PORT", "8000")
    try:
        port = int(raw)
    except ValueError:
        port = 0
    if not 1 <= port <= 65535:
        sys.exit(f"Error: PORT must be a number between 1 and 65535, got {raw!r}")
    return port


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
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "command-line flags override the matching environment variables:\n"
            "  --transport beats TRANSPORT, --port beats PORT.\n"
            "environment variables:\n"
            "  GITHUB_TOKEN         GitHub token (optional; recommended for a higher rate limit)\n"
            "  GH_TOKEN             fallback when GITHUB_TOKEN is unset or empty\n"
            "  TRANSPORT            stdio (default), streamable-http (alias: http), or sse\n"
            "  PORT                 port for HTTP transports (default 8000)\n"
            "  OPENCOLLAB_LOG_LEVEL DEBUG, INFO (default), WARNING, ERROR, CRITICAL"
        ),
    )
    parser.add_argument(
        "-V",
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
    )
    parser.add_argument(
        "--transport",
        choices=["stdio", "streamable-http", "http", "sse"],
        type=str.lower,
        default=None,
        metavar="{stdio,streamable-http,http,sse}",
        help="transport to use; overrides TRANSPORT (default: stdio)",
    )
    parser.add_argument(
        "--port",
        default=None,
        metavar="N",
        help="port for HTTP transports; overrides PORT (default: 8000)",
    )
    args, unknown_args = parser.parse_known_args(argv)

    _configure_logging()
    # Precedence: flag > environment variable > default.
    if args.transport is not None:
        transport = args.transport
    else:
        transport = os.environ.get("TRANSPORT", "stdio").lower()
    if transport not in ("stdio", "streamable-http", "http", "sse"):
        sys.exit(
            "Error: TRANSPORT must be one of stdio, streamable-http, http, sse; "
            f"got {transport!r}"
        )
    logger = logging.getLogger("opencollab_mcp")
    if unknown_args:
        logger.warning(
            "Ignoring unknown arguments: %s. Configure the server with environment "
            "variables (TRANSPORT, PORT); see the README.",
            " ".join(unknown_args),
        )

    if transport in ("streamable-http", "http"):
        port = _read_port(args.port)
        logger.info("Starting OpenCollab MCP on streamable-http (port %d)", port)
        mcp.run(transport="streamable-http", host="0.0.0.0", port=port)
    elif transport == "sse":
        # Legacy SSE transport — kept for backwards compatibility.
        port = _read_port(args.port)
        logger.info("Starting OpenCollab MCP on SSE (port %d)", port)
        mcp.run(transport="sse", host="0.0.0.0", port=port)
    else:
        logger.info("Starting OpenCollab MCP on stdio")
        mcp.run()


if __name__ == "__main__":
    main()
