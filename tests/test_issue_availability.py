"""opencollab_check_issue_availability must reflect the issue as it is now."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx
import pytest

from opencollab_mcp.server import build_server


def _days_ago_iso(days: int) -> str:
    """ISO timestamp `days` ago, so staleness tests don't go stale as time passes."""
    moment = datetime.now(timezone.utc) - timedelta(days=days)
    return moment.strftime("%Y-%m-%dT%H:%M:%SZ")


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
                        "body": "Closes #7",
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
    assert payload["linked_prs_source"] == "rest"
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
                        "body": "Fixes #7",
                        "pull_request": {"merged_at": None},
                        "user": {"login": "dev2"},
                    }
                },
            }
        ],
    })

    payload = await _check()

    assert payload["available"] is True
    assert payload["linked_prs_source"] == "rest"
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
                        "body": "Resolves #7",
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
    assert payload["linked_prs_source"] == "rest"
    assert len(payload["linked_prs"]) == 1
    assert payload["linked_prs"][0]["merged"] is False
    assert payload["linked_prs"][0]["pr_number"] == 11


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("pr_state", "merged_at"),
    [("open", None), ("closed", "2026-01-01T00:00:00Z")],
)
async def test_plain_mention_pr_keeps_issue_available_in_rest_path(
    mock_github, pr_state, merged_at
):
    mock_github({
        "/repos/o/r/issues/7": {"state": "open", "title": "Bug", "assignees": []},
        "/repos/o/r/issues/7/timeline": [
            {
                "event": "cross-referenced",
                "source": {
                    "issue": {
                        "number": 15,
                        "state": pr_state,
                        "title": "Refactor helper",
                        "body": "Related to #7 — prepares groundwork only.",
                        "pull_request": {"merged_at": merged_at},
                        "user": {"login": "helper-dev"},
                    }
                },
            }
        ],
    })

    payload = await _check()

    assert payload["available"] is True
    assert payload["linked_prs"] == []
    assert payload["linked_prs_source"] == "rest"
    assert len(payload["mentioned_in_prs"]) == 1
    assert payload["mentioned_in_prs"][0]["pr_number"] == 15
    assert "mentions this issue" in payload["reason"]


@pytest.mark.asyncio
async def test_graphql_sidebar_linked_pr_marks_unavailable_without_cross_reference(
    mock_github, monkeypatch
):
    monkeypatch.setenv("GITHUB_TOKEN", "ghp_test_token")
    mock_github({
        "/repos/o/r/issues/7": {"state": "open", "title": "Bug", "assignees": []},
        "/repos/o/r/issues/7/timeline": [],  # No text mention in PR body -> empty cross-refs
        "/graphql": {
            "data": {
                "repository": {
                    "issue": {
                        "closedByPullRequestsReferences": {
                            "nodes": [
                                None,  # Inaccessible private PR node from GitHub GraphQL
                                {
                                    "number": 42,
                                    "title": "Fix bug without body keyword",
                                    "state": "OPEN",
                                    "merged": False,
                                    "url": "https://github.com/o/r/pull/42",
                                    "author": {"login": "sidebar-dev"},
                                    "repository": {"nameWithOwner": "o/r"},
                                },
                            ]
                        }
                    }
                }
            }
        },
    })

    payload = await _check()

    assert payload["available"] is False
    assert payload["linked_prs_source"] == "graphql"
    assert payload["linked_prs_checked"] is True
    assert len(payload["linked_prs"]) == 1
    assert payload["linked_prs"][0] == {
        "pr_number": 42,
        "title": "Fix bug without body keyword",
        "state": "open",
        "author": "sidebar-dev",
        "merged": False,
    }


@pytest.mark.asyncio
async def test_graphql_path_separates_mentions_from_closing_prs(mock_github, monkeypatch):
    monkeypatch.setenv("GITHUB_TOKEN", "ghp_test_token")
    mock_github({
        "/repos/o/r/issues/7": {"state": "open", "title": "Bug", "assignees": []},
        "/repos/o/r/issues/7/timeline": [
            {
                "event": "cross-referenced",
                "source": {
                    "issue": {
                        "number": 50,
                        "state": "open",
                        "title": "Docs note",
                        "body": "See also #7",
                        "pull_request": {},
                        "user": {"login": "doc-dev"},
                    }
                },
            }
        ],
        "/graphql": {
            "data": {
                "repository": {
                    "issue": {
                        "closedByPullRequestsReferences": {"nodes": []}
                    }
                }
            }
        },
    })

    payload = await _check()

    assert payload["available"] is True
    assert payload["linked_prs_source"] == "graphql"
    assert payload["linked_prs"] == []
    assert len(payload["mentioned_in_prs"]) == 1
    assert payload["mentioned_in_prs"][0]["pr_number"] == 50
    assert "mentions this issue" in payload["reason"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "graphql_spec",
    [
        (401, {"message": "Bad credentials"}),
        (403, {"message": "API rate limit exceeded"}),
        {"errors": [{"type": "NOT_FOUND", "message": "Could not resolve to an Issue"}]},
        {"errors": [{"type": "RATE_LIMITED", "message": "API rate limit exceeded"}]},
    ],
)
async def test_graphql_errors_fall_back_cleanly_to_rest_timeline(
    mock_github, monkeypatch, graphql_spec
):
    monkeypatch.setenv("GITHUB_TOKEN", "ghp_limited_or_bad")
    mock_github({
        "/repos/o/r/issues/7": {"state": "open", "title": "Bug", "assignees": []},
        "/graphql": graphql_spec,
        "/repos/o/r/issues/7/timeline": [
            {
                "event": "cross-referenced",
                "source": {
                    "issue": {
                        "number": 88,
                        "state": "open",
                        "title": "Fix bug",
                        "body": "Fixes #7",
                        "pull_request": {},
                        "user": {"login": "fallback-dev"},
                    }
                },
            }
        ],
    })

    payload = await _check()

    assert payload["available"] is False
    assert payload["linked_prs_source"] == "rest"
    assert payload["linked_prs_checked"] is True
    assert payload["linked_prs"][0]["pr_number"] == 88


@pytest.mark.asyncio
async def test_graphql_merged_pr_and_ghost_author_handled(mock_github, monkeypatch):
    monkeypatch.setenv("GITHUB_TOKEN", "ghp_test_token")
    node = {
        "number": 61,
        "title": "Fix race condition",
        "state": "MERGED",
        "merged": True,
        "url": "https://github.com/o/r/pull/61",
        "author": None,  # Deleted / ghost GitHub account
        "repository": {"nameWithOwner": "o/r"},
    }
    mock_github({
        "/repos/o/r/issues/7": {"state": "open", "title": "Bug", "assignees": []},
        "/repos/o/r/issues/7/timeline": [],
        "/graphql": {
            "data": {
                "repository": {
                    "issue": {
                        "closedByPullRequestsReferences": {
                            "nodes": [node, node]  # Duplicate refs deduplicated
                        }
                    }
                }
            }
        },
    })

    payload = await _check()

    assert payload["available"] is False
    assert "already merged" in payload["reason"]
    assert payload["linked_prs_source"] == "graphql"
    assert payload["linked_prs"] == [
        {
            "pr_number": 61,
            "title": "Fix race condition",
            "state": "closed",
            "author": "unknown",
            "merged": True,
        }
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "malformed_data",
    [
        {"data": {}},
        {"data": {"repository": {"issue": None}}},
        {"data": {"repository": {"issue": {"closedByPullRequestsReferences": None}}}},
    ],
)
async def test_malformed_graphql_data_falls_back_to_rest_and_reports_total_outage(
    mock_github, monkeypatch, malformed_data
):
    monkeypatch.setenv("GITHUB_TOKEN", "ghp_test_token")
    mock_github({
        "/repos/o/r/issues/7": {"state": "open", "title": "Bug", "assignees": []},
        "/graphql": malformed_data,
        "/repos/o/r/issues/7/timeline": (500, {}),
    })

    payload = await _check()

    assert payload["available"] is True
    assert payload["linked_prs_source"] == "rest"
    assert payload["linked_prs_checked"] is False
    assert "could not be checked" in payload["reason"]


@pytest.mark.asyncio
async def test_rest_timeline_deduplicates_events_and_handles_cross_repo_mentions(mock_github):
    pr_event = {
        "event": "cross-referenced",
        "source": {
            "issue": {
                "number": 7,
                "state": "open",
                "title": "Downstream fix",
                "body": "See upstream o/r#7. Closes #7",
                "repository_url": "https://api.github.com/repos/downstream/app",
                "pull_request": {},
                "user": {"login": "downstream-dev"},
            }
        },
    }
    mock_github({
        "/repos/o/r/issues/7": _labelled_issue("needs-triage"),
        # Same PR cross-referenced twice + non-PR cross-reference event
        "/repos/o/r/issues/7/timeline": [
            {"event": "labeled"},
            {"event": "cross-referenced", "source": {"issue": {"number": 3, "state": "open"}}},
            pr_event,
            pr_event,
        ],
    })

    payload = await _check()

    assert payload["available"] is True
    assert payload["linked_prs"] == []
    assert len(payload["mentioned_in_prs"]) == 1
    assert payload["mentioned_in_prs"][0]["pr_number"] == 7
    assert "ask a maintainer" in payload["reason"]
    assert "mentions this issue" in payload["reason"]



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

@pytest.mark.asyncio
async def test_recently_updated_assigned_issue_has_no_stale_warning(mock_github):
    mock_github({
        "/repos/o/r/issues/7": {
            "state": "open",
            "title": "Bug",
            "assignees": [{"login": "fast-dev"}],
            "updated_at": _days_ago_iso(1),
        },
    })

    payload = await _check()

    assert payload["available"] is False
    assert "fast-dev" in payload["reason"]
    assert "no activity for" not in payload["reason"]


@pytest.mark.asyncio
async def test_stale_assigned_issue_includes_activity_warning(mock_github):
    mock_github({
        "/repos/o/r/issues/7": {
            "state": "open",
            "title": "Bug",
            "assignees": [{"login": "fast-dev"}],
            "updated_at": "2026-07-01T00:00:00Z",
        },
    })

    payload = await _check()

    assert payload["available"] is False
    assert "fast-dev" in payload["reason"]
    assert "no activity for" in payload["reason"]
    assert payload["last_activity_days_ago"] >= 60


@pytest.mark.asyncio
async def test_assigned_issue_without_updated_at_has_no_stale_warning(mock_github):
    mock_github({
        "/repos/o/r/issues/7": {
            "state": "open",
            "title": "Bug",
            "assignees": [{"login": "fast-dev"}],
        },
    })

    payload = await _check()

    assert payload["available"] is False
    assert "fast-dev" in payload["reason"]
    assert "no activity for" not in payload["reason"]
    assert payload["last_activity_days_ago"] is None


@pytest.mark.asyncio
async def test_open_linked_pr_on_page_2_of_timeline_marks_issue_unavailable(mock_github):
    def _timeline_handler(request: httpx.Request) -> httpx.Response:
        page = int(request.url.params.get("page", "1"))
        if page == 1:
            return httpx.Response(
                200,
                json=[{"event": "labeled"} for _ in range(100)],
                headers={
                    "Link": (
                        '<https://api.github.com/repos/o/r/issues/7/timeline'
                        '?per_page=100&page=2>; rel="next"'
                    )
                },
            )
        return httpx.Response(
            200,
            json=[
                {
                    "event": "cross-referenced",
                    "source": {
                        "issue": {
                            "number": 212,
                            "state": "open",
                            "title": "Fix long-running bug",
                            "body": "Fixes #7",
                            "pull_request": {},
                            "user": {"login": "recent-dev"},
                        }
                    },
                }
            ],
        )

    mock_github({
        "/repos/o/r/issues/7": {"state": "open", "title": "Popular bug", "assignees": []},
        "/repos/o/r/issues/7/timeline": _timeline_handler,
    })

    payload = await _check()

    assert payload["available"] is False
    assert "open PR" in payload["reason"]
    assert payload["linked_prs"][0]["pr_number"] == 212
    assert payload["linked_prs_checked"] is True


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("labels", "page1_events"),
    [
        ([], [{"event": "labeled"}]),
        (["needs-triage"], [{"event": "labeled"}]),
        (
            [],
            [
                {
                    "event": "cross-referenced",
                    "source": {
                        "issue": {
                            "number": 30,
                            "state": "open",
                            "title": "Docs note",
                            "body": "Related to #7",
                            "pull_request": {},
                            "user": {"login": "doc-dev"},
                        }
                    },
                }
            ],
        ),
    ],
)
async def test_timeline_hitting_max_pages_reports_truncation_and_softens_reason(
    mock_github, labels, page1_events
):
    calls = {"n": 0}

    def _long_timeline(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        page = int(request.url.params.get("page", "1"))
        return httpx.Response(
            200,
            json=page1_events if page == 1 else [{"event": "commented"}],
            headers={
                "Link": (
                    f'<https://api.github.com/repos/o/r/issues/7/timeline'
                    f'?per_page=100&page={page + 1}>; rel="next"'
                )
            },
        )

    mock_github({
        "/repos/o/r/issues/7": _labelled_issue(*labels),
        "/repos/o/r/issues/7/timeline": _long_timeline,
    })

    payload = await _check()

    assert calls["n"] == 5
    assert payload["available"] is True
    assert payload["timeline_truncated"] is True
    assert "go for it" not in payload["reason"].lower()
    assert "no open prs" not in payload["reason"].lower()


@pytest.mark.asyncio
async def test_timeline_failure_on_page_2_reports_linked_prs_unchecked(mock_github):
    calls = {"n": 0}

    def _flaky_page2(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        page = int(request.url.params.get("page", "1"))
        if page == 1:
            return httpx.Response(
                200,
                json=[{"event": "labeled"}],
                headers={
                    "Link": (
                        '<https://api.github.com/repos/o/r/issues/7/timeline'
                        '?per_page=100&page=2>; rel="next"'
                    )
                },
            )
        return httpx.Response(500, json={"message": "Internal Server Error"})

    mock_github({
        "/repos/o/r/issues/7": {"state": "open", "title": "Bug", "assignees": []},
        "/repos/o/r/issues/7/timeline": _flaky_page2,
    })

    payload = await _check()

    assert calls["n"] == 2
    assert payload["available"] is True
    assert payload["linked_prs_checked"] is False
    assert payload["linked_prs"] == []
    assert "no open PRs" not in payload["reason"]
    assert "could not be checked" in payload["reason"]


@pytest.mark.asyncio
async def test_single_page_timeline_makes_one_request_and_omits_truncation_flag(mock_github):
    calls = {"n": 0}

    def _one_page(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(200, json=[])

    mock_github({
        "/repos/o/r/issues/7": {"state": "open", "title": "Bug", "assignees": []},
        "/repos/o/r/issues/7/timeline": _one_page,
    })

    payload = await _check()

    assert calls["n"] == 1
    assert payload["available"] is True
    assert "timeline_truncated" not in payload


@pytest.mark.asyncio
async def test_graphql_mentions_on_page_2_and_merged_pr_with_truncated_timeline(
    mock_github, monkeypatch
):
    # 1. GraphQL mode reads page 2 of timeline so late non-closing mentions still surface.
    monkeypatch.setenv("GITHUB_TOKEN", "ghp_test_token")

    def _two_page_mention(request: httpx.Request) -> httpx.Response:
        page = int(request.url.params.get("page", "1"))
        if page == 1:
            return httpx.Response(
                200,
                json=[{"event": "labeled"}],
                headers={
                    "Link": (
                        '<https://api.github.com/repos/o/r/issues/7/timeline'
                        '?per_page=100&page=2>; rel="next"'
                    )
                },
            )
        return httpx.Response(
            200,
            json=[
                {
                    "event": "cross-referenced",
                    "source": {
                        "issue": {
                            "number": 99,
                            "state": "open",
                            "title": "Follow-up note",
                            "body": "See also #7",
                            "pull_request": {},
                            "user": {"login": "page2-author"},
                        }
                    },
                }
            ],
        )

    mock_github({
        "/repos/o/r/issues/7": {"state": "open", "title": "Bug", "assignees": []},
        "/repos/o/r/issues/7/timeline": _two_page_mention,
        "/graphql": {
            "data": {
                "repository": {
                    "issue": {"closedByPullRequestsReferences": {"nodes": []}}
                }
            }
        },
    })
    gql_payload = await _check()
    assert gql_payload["available"] is True
    assert [p["pr_number"] for p in gql_payload["mentioned_in_prs"]] == [99]

    # 2. Merged/open closing PR on page 5 of a 6+ page timeline preserves timeline_truncated=True.
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)

    def _merged_on_page_5(request: httpx.Request) -> httpx.Response:
        page = int(request.url.params.get("page", "1"))
        events = (
            [
                {
                    "event": "cross-referenced",
                    "source": {
                        "issue": {
                            "number": 500,
                            "state": "closed",
                            "title": "Fix bug",
                            "body": "Fixes #7",
                            "pull_request": {"merged_at": "2026-10-20T00:00:00Z"},
                            "user": {"login": "merger"},
                        }
                    },
                }
            ]
            if page == 5
            else [{"event": "commented"}]
        )
        return httpx.Response(
            200,
            json=events,
            headers={
                "Link": (
                    f'<https://api.github.com/repos/o/r/issues/7/timeline'
                    f'?per_page=100&page={page + 1}>; rel="next"'
                )
            },
        )

    mock_github({
        "/repos/o/r/issues/7": {"state": "open", "title": "Bug", "assignees": []},
        "/repos/o/r/issues/7/timeline": _merged_on_page_5,
    })
    merged_payload = await _check()
    assert merged_payload["available"] is False
    assert "already merged" in merged_payload["reason"]
    assert merged_payload["timeline_truncated"] is True
