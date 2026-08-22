"""OpenCollab MCP — AI-powered open source contribution matchmaker."""

from .constants import __version__
from .server import build_server, main, mcp

__all__ = ["build_server", "main", "mcp", "__version__"]
