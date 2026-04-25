"""Smoke tests for tool registration and end-to-end JSON shape.

These don't deeply test scoring — they verify that:
  1. All 22 tools register on the server.
  2. The tools return well-formed JSON, not exceptions, for happy-path inputs.
"""

from __future__ import annotations

import json
import pytest

from opencollab_mcp.server import build_server
from opencollab_mcp.tools import discovery, evaluation, issues, profile
from opencollab_mcp.models import RepoInput, UsernameInput, IssueInput, LanguageInput


EXPECTED_TOOL_NAMES = {
    # Discovery (6)
    "opencollab_find_issues",
    "opencollab_trending_repos",
    "opencollab_similar_repos",
    "opencollab_find_mentor_repos",
    "opencollab_weekend_issues",
    "opencollab_match_me",
    # Evaluation (7)
    "opencollab_repo_health",
    "opencollab_contribution_readiness",
    "opencollab_impact_estimator",
    "opencollab_repo_activity_pulse",
    "opencollab_compare_repos",
    "opencollab_repo_languages",
    "opencollab_dependency_check",
    # Issues (6)
    "opencollab_check_issue_availability",
    "opencollab_issue_complexity",
    "opencollab_stale_issue_finder",
    "opencollab_label_explorer",
    "opencollab_recent_prs",
    "opencollab_generate_pr_plan",
    # Profile (3)
    "opencollab_analyze_profile",
    "opencollab_first_timer_score",
    "opencollab_contributor_leaderboard",
}


@pytest.mark.asyncio
async def test_all_22_tools_registered():
    server = build_server()
    registered = {t.name for t in await server.list_tools()}
    missing = EXPECTED_TOOL_NAMES - registered
    extra = registered - EXPECTED_TOOL_NAMES
    assert not missing, f"missing tools: {missing}"
    assert len(EXPECTED_TOOL_NAMES) == 22


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
    # Pull the registered tool out of the server and call it.
    server = build_server()
    tools = await server.list_tools()
    impact_tool = next(t for t in tools if t.name == "opencollab_impact_estimator")
    result = await server.call_tool(
        impact_tool.name, {"params": {"owner": "me", "repo": "tinylib"}}
    )
    # FastMCP returns a list of content items; first is the JSON text.
    text = result[0].text if hasattr(result[0], "text") else result[0]["text"]
    parsed = json.loads(text)
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
    tools = await server.list_tools()
    impact_tool = next(t for t in tools if t.name == "opencollab_impact_estimator")
    result = await server.call_tool(
        impact_tool.name, {"params": {"owner": "big", "repo": "famous"}}
    )
    text = result[0].text if hasattr(result[0], "text") else result[0]["text"]
    parsed = json.loads(text)
    assert parsed["impact_tier"] == "MASSIVE"


@pytest.mark.asyncio
async def test_check_issue_availability_invalid_number(mock_github):
    """The tool should return a friendly error JSON, not raise."""
    server = build_server()
    tools = await server.list_tools()
    tool = next(t for t in tools if t.name == "opencollab_check_issue_availability")
    result = await server.call_tool(
        tool.name,
        {"params": {"owner": "x", "repo": "y", "issue_number": "not-a-number"}},
    )
    text = result[0].text if hasattr(result[0], "text") else result[0]["text"]
    parsed = json.loads(text)
    assert "error" in parsed
    assert "Invalid issue_number" in parsed["error"]
