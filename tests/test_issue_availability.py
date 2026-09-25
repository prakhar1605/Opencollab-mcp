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
    text = result[0][0].text if isinstance(result, tuple) else result[0].text
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
