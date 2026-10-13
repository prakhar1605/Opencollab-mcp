"""Bot automation should not skew contributor-facing merge statistics."""

import json

import pytest

from opencollab_mcp.server import build_server

from .test_tools import _call_tool_compat, _extract_text


@pytest.mark.asyncio
@pytest.mark.parametrize("bot_merged", [True, False])
async def test_health_merge_rate_excludes_bot_authors(mock_github, bot_merged):
    pulls = [
        {"user": {"login": "robotics-fan", "type": "User"}, "merged_at": "2026-01-01"},
        {"user": {"login": "contributor", "type": "User"}, "merged_at": None},
    ] + [
        {"user": user, "merged_at": "2026-01-01" if bot_merged else None}
        for user in [
            {"login": "automation", "type": "Bot"},
            {"login": "renovate[bot]", "type": "User"},
            {"login": "dependabot[bot]", "type": "Bot"},
        ]
    ]
    mock_github({
        "/repos/o/r": {},
        "/repos/o/r/pulls": pulls,
        "/repos/o/r/community/profile": {},
    })
    result = await _call_tool_compat(build_server(), "opencollab_repo_health", {
        "params": {"owner": "o", "repo": "r"},
    })
    payload = json.loads(_extract_text(result))
    assert payload["details"]["pr_merge_rate_pct"] == 50.0
    assert payload["details"]["bot_prs_excluded"] == 3
    # With an otherwise empty repo, only the 50% merge-rate tier earns points.
    assert payload["health_score"] == 12


@pytest.mark.asyncio
async def test_all_bot_sample_does_not_award_merge_points(mock_github):
    mock_github({
        "/repos/o/r": {},
        "/repos/o/r/pulls": [{"user": {"type": "Bot"}, "merged_at": "2026-01-01"}],
        "/repos/o/r/community/profile": {},
    })
    result = await _call_tool_compat(build_server(), "opencollab_repo_health", {
        "params": {"owner": "o", "repo": "r"},
    })
    payload = json.loads(_extract_text(result))
    assert payload["details"]["bot_prs_excluded"] == 1
    assert payload["details"]["pr_merge_rate_pct"] == 0
    assert payload["health_score"] == 0
