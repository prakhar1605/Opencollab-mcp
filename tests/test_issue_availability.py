"""opencollab_check_issue_availability must reflect the issue as it is now."""

from __future__ import annotations

import json
from typing import Any

import pytest

from opencollab_mcp.server import build_server


async def _check(issue_number: str = "7") -> dict[str, Any]:
    result = build_server().call_tool(
        "opencollab_check_issue_availability",
        {"params": {"owner": "o", "repo": "r", "issue_number": issue_number}},
    )
    if hasattr(result, "__await__"):
        result = await result
    # mcp 1.x returns (content, structured) or a content list; 2.x returns a
    # CallToolResult with .content.
    if hasattr(result, "content"):
        result = result.content
    elif isinstance(result, tuple):
        result = result[0]
    text = result[0].text
    return json.loads(text)


@pytest.mark.asyncio
async def test_pull_request_is_not_reported_as_available(mock_github):
    # The issues endpoint serves PRs too; they carry a `pull_request` key.
    mock_github({
        "/repos/o/r/issues/7": {
            "state": "open", "title": "Fix thing", "assignees": [],
            "pull_request": {"url": "https://api.github.com/repos/o/r/pulls/7"},
        },
        "/repos/o/r/issues/7/timeline": [],
    })

    payload = await _check()

    assert payload["available"] is False
    assert "pull request" in payload["reason"]


@pytest.mark.asyncio
async def test_availability_is_not_served_from_cache(mock_github):
    mock_github({
        "/repos/o/r/issues/7": {"state": "open", "title": "Bug", "assignees": []},
        "/repos/o/r/issues/7/timeline": [],
    })
    assert (await _check())["available"] is True

    # Someone claims it between two calls in the same conversation.
    mock_github({
        "/repos/o/r/issues/7": {
            "state": "open", "title": "Bug", "assignees": [{"login": "fast-dev"}],
        },
    })
    payload = await _check()

    assert payload["available"] is False
    assert "fast-dev" in payload["reason"]


@pytest.mark.asyncio
async def test_merged_pull_request_marks_issue_unavailable(mock_github):
    mock_github({
        "/repos/o/r/issues/7": {"state": "open", "title": "Bug", "assignees": []},
        "/repos/o/r/issues/7/timeline": [
            {
                "event": "cross-referenced",
                "source": {
                    "issue": {
                        "number": 9,
                        "state": "closed",
                        "title": "Fix bug",
                        "pull_request": {"merged_at": "2026-01-01T00:00:00Z"},
                        "user": {"login": "dev1"},
                    }
                },
            }
        ],
    })

    payload = await _check()

    assert payload["available"] is False
    assert "already merged" in payload["reason"]
    assert len(payload["linked_prs"]) == 1
    assert payload["linked_prs"][0]["merged"] is True
    assert payload["linked_prs"][0]["pr_number"] == 9


@pytest.mark.asyncio
async def test_closed_unmerged_pull_request_leaves_issue_available(mock_github):
    mock_github({
        "/repos/o/r/issues/7": {"state": "open", "title": "Bug", "assignees": []},
        "/repos/o/r/issues/7/timeline": [
            {
                "event": "cross-referenced",
                "source": {
                    "issue": {
                        "number": 10,
                        "state": "closed",
                        "title": "Abandoned fix",
                        "pull_request": {"merged_at": None},
                        "user": {"login": "dev2"},
                    }
                },
            }
        ],
    })

    payload = await _check()

    assert payload["available"] is True
    assert len(payload["linked_prs"]) == 1
    assert payload["linked_prs"][0]["merged"] is False
    assert payload["linked_prs"][0]["pr_number"] == 10


@pytest.mark.asyncio
async def test_open_pull_request_marks_issue_unavailable_and_records_merged_false(mock_github):
    mock_github({
        "/repos/o/r/issues/7": {"state": "open", "title": "Bug", "assignees": []},
        "/repos/o/r/issues/7/timeline": [
            {
                "event": "cross-referenced",
                "source": {
                    "issue": {
                        "number": 11,
                        "state": "open",
                        "title": "WIP PR",
                        "pull_request": {},
                        "user": {"login": "dev3"},
                    }
                },
            }
        ],
    })

    payload = await _check()

    assert payload["available"] is False
    assert "open PR" in payload["reason"]
    assert len(payload["linked_prs"]) == 1
    assert payload["linked_prs"][0]["merged"] is False
    assert payload["linked_prs"][0]["pr_number"] == 11

