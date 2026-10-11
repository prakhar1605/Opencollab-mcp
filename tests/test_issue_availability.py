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



@pytest.mark.asyncio
async def test_timeline_failure_is_reported_not_hidden(mock_github):
    mock_github({
        "/repos/o/r/issues/7": {"state": "open", "title": "Bug", "assignees": []},
        "/repos/o/r/issues/7/timeline": (500, {}),
    })

    payload = await _check()

    assert payload["linked_prs_checked"] is False
    assert payload["linked_prs"] == []
    assert "no open PRs" not in payload["reason"]
    assert "could not be checked" in payload["reason"]


@pytest.mark.asyncio
async def test_timeline_success_marks_linked_prs_checked(mock_github):
    mock_github({
        "/repos/o/r/issues/7": {"state": "open", "title": "Bug", "assignees": []},
        "/repos/o/r/issues/7/timeline": [],
    })

    payload = await _check()

    assert payload["available"] is True
    assert payload["linked_prs_checked"] is True


@pytest.mark.asyncio
@pytest.mark.parametrize("lock_reason", ["resolved", None])
async def test_locked_issue_is_not_available(mock_github, lock_reason):
    mock_github({
        "/repos/o/r/issues/7": {
            "state": "open", "title": "Locked bug", "assignees": [],
            "locked": True, "active_lock_reason": lock_reason,
        },
        "/repos/o/r/issues/7/timeline": [],
    })

    payload = await _check()

    assert payload["available"] is False
    assert "locked" in payload["reason"]
    assert payload["issue_title"] == "Locked bug"
    if lock_reason:
        assert payload["active_lock_reason"] == lock_reason


@pytest.mark.asyncio
async def test_unlocked_issue_with_old_lock_reason_is_available(mock_github):
    mock_github({
        "/repos/o/r/issues/7": {
            "state": "open", "title": "Bug", "assignees": [],
            "locked": False, "active_lock_reason": "resolved",
        },
        "/repos/o/r/issues/7/timeline": [],
    })

    assert (await _check())["available"] is True


def _labelled_issue(*names: str) -> dict[str, Any]:
    return {
        "state": "open", "title": "Bug", "assignees": [],
        "labels": [{"name": n} for n in names],
    }


@pytest.mark.asyncio
@pytest.mark.parametrize("label", ["wontfix", "Duplicate", "invalid"])
async def test_blocking_label_marks_issue_unavailable(mock_github, label):
    mock_github({
        "/repos/o/r/issues/7": _labelled_issue("bug", label),
        "/repos/o/r/issues/7/timeline": [],
    })

    payload = await _check()

    assert payload["available"] is False
    assert label in payload["reason"]


@pytest.mark.asyncio
@pytest.mark.parametrize("label", ["needs-triage", "Needs Discussion", "on hold", "blocked"])
async def test_warning_label_keeps_issue_available_with_warning(mock_github, label):
    mock_github({
        "/repos/o/r/issues/7": _labelled_issue("good first issue", label),
        "/repos/o/r/issues/7/timeline": [],
    })

    payload = await _check()

    assert payload["available"] is True
    assert "ask a maintainer" in payload["reason"]
    assert payload["warning_labels"] == [label]


@pytest.mark.asyncio
async def test_plain_good_first_issue_has_no_warning(mock_github):
    mock_github({
        "/repos/o/r/issues/7": _labelled_issue("good first issue"),
        "/repos/o/r/issues/7/timeline": [],
    })

    payload = await _check()

    assert payload["available"] is True
    assert payload["reason"] == "No assignees, no open PRs — go for it!"
    assert "warning_labels" not in payload
