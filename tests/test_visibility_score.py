"""Pin the impact estimator visibility score for a known input.

This ensures future changes to the scoring constants are deliberate
rather than accidental.
"""

from __future__ import annotations

import json

import pytest

from opencollab_mcp.server import build_server
from tests.test_tools import _call_tool_compat, _extract_text


@pytest.mark.asyncio
async def test_impact_estimator_visibility_score_is_pinned(mock_github):
    """Known inputs produce an exactly calculated visibility score."""
    # stars=600 (>=100), forks=150 (>=50), watchers=60 (>=50), open_issues=12 (>=10), topics present
    # Expected:
    # stars: min(600 // 500, 40) = 1
    # forks: min(150 // 100, 20) = 1
    # watchers: min(60 // 50, 20) = 1
    # open_issues: 10
    # topics: 10
    # total: 23
    mock_github({
        "/repos/test/repo": {
            "stargazers_count": 600,
            "forks_count": 150,
            "subscribers_count": 60,
            "open_issues_count": 12,
            "description": "Test repository",
            "topics": ["python", "testing"],
        }
    })
    server = build_server()
    result = await _call_tool_compat(
        server,
        "opencollab_impact_estimator",
        {"params": {"owner": "test", "repo": "repo"}},
    )
    parsed = json.loads(_extract_text(result))
    assert parsed["visibility_score"] == 23
    assert parsed["stars"] == 600
    assert parsed["forks"] == 150
    assert parsed["watchers"] == 60
    assert parsed["open_issues"] == 12
