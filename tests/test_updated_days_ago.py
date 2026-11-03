"""Deterministic activity-age coverage for find_issues (#178)."""

import json
from datetime import datetime, timezone

import pytest

from opencollab_mcp import helpers
from opencollab_mcp.server import build_server
from tests.test_tools import _call_tool_compat, _extract_text


@pytest.mark.parametrize(
    "timestamp, expected",
    [
        ("2026-01-08T12:00:00Z", 2),
        (None, None),
    ],
)
async def test_find_issues_updated_days_ago(monkeypatch, mock_github, timestamp, expected):
    class FixedDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            return cls(2026, 1, 10, 12, tzinfo=timezone.utc)

    monkeypatch.setattr(helpers, "datetime", FixedDatetime)
    item = {"title": "synthetic", "created_at": "2026-01-01T12:00:00Z"}
    if timestamp is not None:
        item["updated_at"] = timestamp
    mock_github({"/search/issues": {"total_count": 1, "items": [item]}})
    result = await _call_tool_compat(
        build_server(),
        "opencollab_find_issues",
        {"params": {"language": "Python"}},
    )
    issue = json.loads(_extract_text(result))["issues"][0]
    assert issue["updated_days_ago"] == expected
    assert issue["created_days_ago"] == 9
