"""GitHub API client for OpenCollab MCP."""

import os
import json
from typing import Any, Optional
import httpx

GITHUB_API_BASE = "https://api.github.com"
DEFAULT_TIMEOUT = 30.0


def _get_headers() -> dict[str, str]:
    """Build auth headers from environment."""
    token = os.environ.get("GITHUB_TOKEN", "")
    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "opencollab-mcp/0.2.0",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


async def github_get(path: str, params: Optional[dict[str, Any]] = None) -> Any:
    """Make an authenticated GET request to GitHub API."""
    async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT) as client:
        resp = await client.get(
            f"{GITHUB_API_BASE}{path}",
            headers=_get_headers(),
            params=params or {},
        )
        resp.raise_for_status()
        return resp.json()


async def github_search(endpoint: str, query: str, params: Optional[dict[str, Any]] = None) -> Any:
    """Search GitHub (issues, repos, etc.)."""
    merged = {"q": query, "per_page": 30, **(params or {})}
    return await github_get(f"/search/{endpoint}", merged)


def handle_github_error(e: Exception) -> str:
    """Return a human-friendly error string for GitHub API failures."""
    if isinstance(e, httpx.HTTPStatusError):
        code = e.response.status_code
        if code == 401:
            return "Error: GitHub authentication failed. Check your GITHUB_TOKEN environment variable."
        if code == 403:
            remaining = e.response.headers.get("x-ratelimit-remaining", "?")
            return f"Error: GitHub API rate limit or permission issue (remaining: {remaining}). Try again later or use a token with more scopes."
        if code == 404:
            return "Error: Resource not found on GitHub. Double-check the username or repo name."
        if code == 422:
            return f"Error: GitHub rejected the request — {e.response.text[:200]}"
        return f"Error: GitHub API returned status {code}."
    if isinstance(e, httpx.TimeoutException):
        return "Error: GitHub API request timed out. Please try again."
    return f"Error: Unexpected failure — {type(e).__name__}: {e}"
