"""Smoke tests for tool registration and end-to-end JSON shape.

These don't deeply test scoring — they verify that:
  1. All 6 tools register on the server.
  2. The tools return well-formed JSON, not exceptions, for happy-path inputs.
"""

from __future__ import annotations

import json

import pytest

from opencollab_mcp.server import build_server
from opencollab_mcp.tools import discovery

EXPECTED_TOOL_NAMES = {
    # Discovery (2)
    "opencollab_find_issues",
    "opencollab_match_me",
    # Evaluation (2)
    "opencollab_repo_health",
    "opencollab_impact_estimator",
    # Issues (2)
    "opencollab_check_issue_availability",
    "opencollab_generate_pr_plan",
}


async def _list_tools_compat(server):
    """FastMCP's list_tools() may be sync or async depending on SDK version."""
    result = server.list_tools()
    if hasattr(result, "__await__"):
        result = await result
    return result


async def _call_tool_compat(server, name: str, arguments: dict):
    """FastMCP's call_tool() may be sync or async depending on SDK version."""
    result = server.call_tool(name, arguments)
    if hasattr(result, "__await__"):
        result = await result
    return result


def _extract_text(result) -> str:
    """Pull JSON text out of a FastMCP tool result, regardless of return shape."""
    if isinstance(result, tuple):
        result = result[0]
    if isinstance(result, list) and result:
        first = result[0]
        if hasattr(first, "text"):
            return first.text
        if isinstance(first, dict) and "text" in first:
            return first["text"]
    if hasattr(result, "text"):
        return result.text
    return str(result)


@pytest.mark.asyncio
async def test_all_tools_registered():
    server = build_server()
    tools = await _list_tools_compat(server)
    registered = {t.name for t in tools}
    missing = EXPECTED_TOOL_NAMES - registered
    assert not missing, f"missing tools: {missing}"
    assert len(EXPECTED_TOOL_NAMES) == 6


@pytest.mark.asyncio
async def test_impact_estimator_low_stars(mock_github):
    """Smoke-test the impact tier scoring on a tiny repo."""
    mock_github({
        "/repos/me/tinylib": {
            "stargazers_count": 5,
            "forks_count": 0,
            "subscribers_count": 0,
            "open_issues_count": 0,
            "description": "A tiny library",
            "topics": [],
        }
    })
    server = build_server()
    result = await _call_tool_compat(
        server,
        "opencollab_impact_estimator",
        {"params": {"owner": "me", "repo": "tinylib"}},
    )
    parsed = json.loads(_extract_text(result))
    assert parsed["impact_tier"] == "LOW"
    assert parsed["stars"] == 5


@pytest.mark.asyncio
async def test_impact_estimator_massive_stars(mock_github):
    mock_github({
        "/repos/big/famous": {
            "stargazers_count": 75_000,
            "forks_count": 5_000,
            "subscribers_count": 1_000,
            "open_issues_count": 200,
            "description": "Huge project",
            "topics": ["popular"],
        }
    })
    server = build_server()
    result = await _call_tool_compat(
        server,
        "opencollab_impact_estimator",
        {"params": {"owner": "big", "repo": "famous"}},
    )
    parsed = json.loads(_extract_text(result))
    assert parsed["impact_tier"] == "MASSIVE"


@pytest.mark.asyncio
async def test_check_issue_availability_invalid_number(mock_github):
    """The tool should return a friendly error JSON, not raise."""
    server = build_server()
    result = await _call_tool_compat(
        server,
        "opencollab_check_issue_availability",
        {"params": {"owner": "x", "repo": "y", "issue_number": "not-a-number"}},
    )
    parsed = json.loads(_extract_text(result))
    assert "error" in parsed
    assert "Invalid issue_number" in parsed["error"]
@pytest.mark.asyncio
async def test_find_issues_intermediate_uses_help_wanted(monkeypatch):
    captured_query = ""

    async def fake_github_search(endpoint, query, params=None):
        nonlocal captured_query
        captured_query = query
        return {"total_count": 0, "items": []}

    monkeypatch.setattr(discovery, "github_search", fake_github_search)

    server = build_server()
    await _call_tool_compat(
        server,
        "opencollab_find_issues",
        {"params": {"language": "Python", "difficulty": "intermediate"}},
    )

    assert 'label:"help wanted"' in captured_query
    assert 'label:"good first issue"' not in captured_query
