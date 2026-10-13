"""Closed issue guidance distinguishes completed work from declined work."""

import pytest

from .test_issue_availability import _check


@pytest.mark.asyncio
@pytest.mark.parametrize("state_reason, expected", [
    ("completed", "Issue is closed — already fixed"),
    ("not_planned", "Issue is closed as not planned — maintainers don't intend to change this"),
    ("duplicate", "Issue is closed as a duplicate"),
    (None, "Issue is closed"),
    ("future_reason", "Issue is closed"),
])
async def test_closed_issue_explains_state_reason(mock_github, state_reason, expected):
    issue = {"state": "closed", "title": "Example issue"}
    if state_reason is not None:
        issue["state_reason"] = state_reason
    mock_github({"/repos/o/r/issues/7": issue})
    result = await _check()
    assert result["available"] is False
    assert result["reason"] == expected
    assert result["state_reason"] == state_reason
    assert result["issue_title"] == "Example issue"


@pytest.mark.asyncio
async def test_open_issue_is_still_available(mock_github):
    mock_github({
        "/repos/o/r/issues/7": {"state": "open", "state_reason": "reopened"},
        "/repos/o/r/issues/7/timeline": [],
    })
    assert (await _check())["available"] is True
