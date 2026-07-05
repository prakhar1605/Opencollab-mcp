"""OpenCollab MCP — AI-powered open source contribution matchmaker."""

__version__ = "0.6.1"

from .server import build_server, main, mcp

__all__ = ["build_server", "main", "mcp", "__version__"]
