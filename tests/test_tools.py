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
@pytest.mark.parametrize("archived", [True, False, None])
@pytest.mark.parametrize("stars,tier,reach,visibility", [
    (5, "LOW", "a growing community", 42),
    (100, "MODERATE", "hundreds of developers", 42),
    (1_000, "MEDIUM", "thousands of developers", 44),
    (10_000, "HIGH", "tens of thousands of developers", 62),
    (60_000, "MASSIVE", "millions of developers", 82),
])
async def test_impact_estimator_reports_archived_status(
    mock_github, archived, stars, tier, reach, visibility,
):
    repo = {
        "stargazers_count": stars,
        "forks_count": 200,
        "subscribers_count": 1_000,
        "open_issues_count": 20,
        "description": "A useful library",
        "topics": ["python"],
    }
    if archived is not None:
        repo["archived"] = archived
    mock_github({"/repos/o/r": repo})

    result = await _call_tool_compat(
        build_server(),
        "opencollab_impact_estimator",
        {"params": {"owner": "o", "repo": "r"}},
    )
    parsed = json.loads(_extract_text(result))

    if archived:
        assert parsed.get("suggested_resume_line") is None
        assert parsed["note"] == "Archived — read-only, new contributions are not possible"
    else:
        if stars >= 1_000:
            expected_resume = f"Contributed to o/r ({stars:,}+ stars), reaching {reach}"
        else:
            expected_resume = "Open-source contributor to o/r — A useful library"
        assert parsed["suggested_resume_line"] == expected_resume
        assert "note" not in parsed

    assert parsed["archived"] is (archived is True)
    assert parsed["repo"] == "o/r"
    assert parsed["impact_tier"] == tier
    assert parsed["estimated_reach"] == reach
    assert parsed["stars"] == stars
    assert parsed["forks"] == 200
    assert parsed["watchers"] == 1_000
    assert parsed["open_issues"] == 20
    assert parsed["topics"] == ["python"]
    assert parsed["visibility_score"] == visibility


@pytest.mark.asyncio
async def test_repo_health_scores_when_community_profile_is_not_found(mock_github):
    """A missing community profile should not hide the rest of the health score."""
    mock_github({
        "/repos/o/r": {
            "pushed_at": "2026-09-25T00:00:00Z",
            "stargazers_count": 20,
            "open_issues_count": 7,
            "forks_count": 5,
            "description": "A small project",
            "topics": ["python"],
        },
        "/repos/o/r/pulls": [],
        # The missing community-profile route returns the fixture's default 404.
    })
    server = build_server()

    result = await _call_tool_compat(
        server,
        "opencollab_repo_health",
        {"params": {"owner": "o", "repo": "r"}},
    )

    parsed = json.loads(_extract_text(result))
    assert isinstance(parsed["health_score"], int)
    assert parsed["details"]["community_profile_available"] is False
    assert not any(parsed["details"]["community_files"].values())


@pytest.mark.asyncio
@pytest.mark.parametrize("archived", [True, False, None])
@pytest.mark.parametrize("merged", [False, True])
async def test_repo_health_reports_archived_status(mock_github, archived, merged):
    repo = {
        "stargazers_count": 1000,
        "forks_count": 100,
        "open_issues_count": 10,
        "description": "A popular project",
        "topics": ["python"],
    }
    if archived is not None:
        repo["archived"] = archived
    mock_github({
        "/repos/o/r": repo,
        "/repos/o/r/pulls": [{"merged_at": "2026-10-01T00:00:00Z"}] if merged else [],
        "/repos/o/r/community/profile": {
            "files": {key: {} for key in [
                "contributing", "code_of_conduct", "license", "readme", "issue_template",
            ]},
        },
    })
    result = await _call_tool_compat(
        build_server(),
        "opencollab_repo_health",
        {"params": {"owner": "o", "repo": "r"}},
    )
    parsed = json.loads(_extract_text(result))
    assert parsed["health_score"] == (80 if merged else 60)
    assert parsed["details"]["archived"] is (archived is True)
    if archived:
        assert parsed["verdict"] == "Archived — read-only, cannot accept contributions"
    elif merged:
        assert parsed["verdict"] == "Excellent — very contributor-friendly"
    else:
        assert parsed["verdict"] == "Good — solid project to contribute to"


@pytest.mark.asyncio
@pytest.mark.parametrize("has_issues", [True, False, None])
@pytest.mark.parametrize("open_count, issue_points", [(0, 0), (2, 5), (10, 10), (501, 5)])
async def test_repo_health_accounts_for_disabled_issues(
    mock_github, has_issues, open_count, issue_points,
):
    repo = {"stargazers_count": 10, "open_issues_count": open_count}
    if has_issues is not None:
        repo["has_issues"] = has_issues
    mock_github({
        "/repos/o/r": repo,
        "/repos/o/r/pulls": [],
        "/repos/o/r/community/profile": {"files": {}},
    })
    result = await _call_tool_compat(
        build_server(), "opencollab_repo_health",
        {"params": {"owner": "o", "repo": "r"}},
    )
    parsed = json.loads(_extract_text(result))
    enabled = has_issues is not False
    assert parsed["details"]["has_issues"] is enabled
    assert parsed["health_score"] == 5 + (issue_points if enabled else 0)
    assert parsed["details"]["open_issues"] == (open_count if enabled else 0)
    if enabled:
        assert "issues_note" not in parsed["details"]
    else:
        assert "Issues are disabled" in parsed["details"]["issues_note"]
        assert "README" in parsed["details"]["issues_note"]


@pytest.mark.asyncio
async def test_repo_health_scores_when_community_profile_is_forbidden(mock_github):
    mock_github({
        "/repos/o/r": {},
        "/repos/o/r/pulls": [],
        "/repos/o/r/community/profile": (403, {"message": "Resource not accessible"}),
    })
    server = build_server()

    result = await _call_tool_compat(
        server,
        "opencollab_repo_health",
        {"params": {"owner": "o", "repo": "r"}},
    )

    parsed = json.loads(_extract_text(result))
    assert isinstance(parsed["health_score"], int)
    assert parsed["details"]["community_profile_available"] is False


@pytest.mark.asyncio
async def test_repo_health_score_calculation(mock_github):
    """Verify repo_health scoring on an active repo and an abandoned repo."""
    mock_github({
        "/repos/active/project": {
            "pushed_at": "2026-10-09T00:00:00Z",  # <= 7 days: +20
            "stargazers_count": 1500,  # >= 1000: +15
            "forks_count": 150,  # >= 100: +10
            "open_issues_count": 50,  # 5..500: +10
            "has_issues": True,
            "description": "An active open-source project",  # +2
            "topics": ["python", "ai"],  # +3
            "archived": False,
        },
        "/repos/active/project/pulls": [
            {"merged_at": "2026-10-08T00:00:00Z"},
            {"merged_at": "2026-10-07T00:00:00Z"},
        ],  # 2/2 merged = 100% (>= 60): +20
        "/repos/active/project/community/profile": {
            "files": {
                "contributing": {},
                "code_of_conduct": {},
                "license": {},
                "readme": {},
                "issue_template": {},
                "pull_request_template": {},
            },  # 6 * 4 = 24 capped at 20: +20
        },
        "/repos/abandoned/project": {
            "pushed_at": "2020-01-01T00:00:00Z",  # > 90 days: +0
            "stargazers_count": 2,  # < 10: +0
            "forks_count": 1,  # < 5: +0
            "open_issues_count": 0,  # 0: +0
            "has_issues": True,
            "description": None,  # +0
            "topics": [],  # +0
            "archived": False,
        },
        "/repos/abandoned/project/pulls": [
            {"merged_at": None},
        ],  # 0% merge rate: +0
        "/repos/abandoned/project/community/profile": {
            "files": {},  # 0 files: +0
        },
    })
    server = build_server()

    # Active repo: 20 (push) + 15 (stars) + 20 (merge) + 10 (issues) + 20 (files) + 2 (desc) + 3 (topics) + 10 (forks) = 100
    res_active = await _call_tool_compat(
        server,
        "opencollab_repo_health",
        {"params": {"owner": "active", "repo": "project"}},
    )
    parsed_active = json.loads(_extract_text(res_active))
    assert parsed_active["health_score"] == 100
    assert parsed_active["verdict"] == "Excellent — very contributor-friendly"

    # Abandoned repo: 0
    res_abandoned = await _call_tool_compat(
        server,
        "opencollab_repo_health",
        {"params": {"owner": "abandoned", "repo": "project"}},
    )
    parsed_abandoned = json.loads(_extract_text(res_abandoned))
    assert parsed_abandoned["health_score"] == 0
    assert parsed_abandoned["verdict"] == "Low — may be abandoned or hard to contribute to"


@pytest.mark.asyncio
@pytest.mark.parametrize("number", ["not-a-number", 0, -5])
@pytest.mark.parametrize("tool", [
    "opencollab_check_issue_availability", "opencollab_generate_pr_plan",
])
async def test_check_issue_availability_invalid_number(mock_github, number, tool):
    """The tool should return a friendly error JSON, not raise."""
    server = build_server()
    result = await _call_tool_compat(
        server,
        tool,
        {"params": {"owner": "x", "repo": "y", "issue_number": number}},
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


@pytest.mark.asyncio
async def test_generate_pr_plan_rejects_pull_request_number(mock_github):
    # The issues endpoint serves PRs too; they carry a `pull_request` key.
    # The other routes make the pre-fix code return a full plan, so this test
    # fails without the guard.
    mock_github({
        "/repos/o/r/issues/7": {
            "title": "Fix thing",
            "state": "open",
            "pull_request": {"url": "https://api.github.com/repos/o/r/pulls/7"},
        },
        "/repos/o/r/issues/7/comments": [],
        "/repos/o/r": {"language": "Python", "default_branch": "main"},
        "/repos/o/r/contents": [],
    })

    result = await _call_tool_compat(
        build_server(),
        "opencollab_generate_pr_plan",
        {"params": {"owner": "o", "repo": "r", "issue_number": "7"}},
    )

    parsed = json.loads(_extract_text(result))
    assert parsed == {"error": "#7 is a pull request, not an issue"}
