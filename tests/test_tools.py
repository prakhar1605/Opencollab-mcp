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
    """MCPServer's list_tools() may be sync or async across SDK versions."""
    result = server.list_tools()
    if hasattr(result, "__await__"):
        result = await result
    return result


async def _call_tool_compat(server, name: str, arguments: dict):
    """MCPServer's call_tool() may be sync or async across SDK versions."""
    result = server.call_tool(name, arguments)
    if hasattr(result, "__await__"):
        result = await result
    return result


def _extract_text(result) -> str:
    """Pull JSON text from the MCP 2.x CallToolResult envelope."""
    return result.content[0].text


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

@pytest.mark.asyncio
async def test_generate_pr_plan_finds_contributing_in_dot_github(mock_github):
    mock_github({
        "/repos/o/r/issues/7": {
            "title": "Test issue",
            "body": "Test body",
            "labels": [],
            "state": "open",
            "user": {"login": "tester"},
            "comments": 0,
        },
        "/repos/o/r/issues/7/comments": [],
        "/repos/o/r": {
            "language": "Python",
            "default_branch": "main",
        },
        "/repos/o/r/contents": [],
        "/repos/o/r/contents/.github/CONTRIBUTING.md": {
            "encoding": "base64",
            "content": "VGVzdCBndWlkZWxpbmVz",
        },
    })
    server = build_server()

    result = await _call_tool_compat(
        server,
        "opencollab_generate_pr_plan",
        {"params": {"owner": "o", "repo": "r", "issue_number": "7"}},
    )

    parsed = json.loads(_extract_text(result))
    assert parsed["contributing_guidelines_preview"] == "Test guidelines"
