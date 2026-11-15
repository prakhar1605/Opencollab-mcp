"""Per-factor breakdown for `opencollab_repo_health` (#245).

`score_breakdown` must always carry all seven factors, each contribution must
match the tier the existing scoring logic picks, and the raw total must
reconcile with `health_score` under the `HEALTH_MAX_SCORE` cap.
"""

from __future__ import annotations

import json

import pytest

from opencollab_mcp.constants import (
    HEALTH_FORKS_HIGH,
    HEALTH_FORKS_LOW,
    HEALTH_FORKS_MEDIUM,
    HEALTH_MAX_COMMUNITY_FILES_POINTS,
    HEALTH_MAX_SCORE,
    HEALTH_MERGE_RATE_HIGH,
    HEALTH_MERGE_RATE_MEDIUM,
    HEALTH_OPEN_ISSUES_MAX,
    HEALTH_OPEN_ISSUES_MIN,
    HEALTH_POINTS_DESCRIPTION,
    HEALTH_POINTS_FORKS_HIGH,
    HEALTH_POINTS_FORKS_LOW,
    HEALTH_POINTS_FORKS_MEDIUM,
    HEALTH_POINTS_MERGE_RATE_HIGH,
    HEALTH_POINTS_MERGE_RATE_LOW,
    HEALTH_POINTS_MERGE_RATE_MEDIUM,
    HEALTH_POINTS_OPEN_ISSUES_ANY,
    HEALTH_POINTS_OPEN_ISSUES_OPTIMAL,
    HEALTH_POINTS_PER_COMMUNITY_FILE,
    HEALTH_POINTS_PUSH_ACTIVE,
    HEALTH_POINTS_PUSH_RECENT,
    HEALTH_POINTS_PUSH_STALE,
    HEALTH_POINTS_STARS_HIGH,
    HEALTH_POINTS_STARS_LOW,
    HEALTH_POINTS_STARS_MEDIUM,
    HEALTH_POINTS_TOPICS,
    HEALTH_PUSH_DAYS_ACTIVE,
    HEALTH_PUSH_DAYS_RECENT,
    HEALTH_PUSH_DAYS_STALE,
    HEALTH_STARS_HIGH,
    HEALTH_STARS_LOW,
    HEALTH_STARS_MEDIUM,
)
from opencollab_mcp.server import build_server
from opencollab_mcp.tools import evaluation

from .test_tools import _call_tool_compat, _days_ago_iso, _extract_text

BREAKDOWN_KEYS = {
    "activity",
    "stars",
    "merge_rate",
    "open_issues",
    "community_files",
    "metadata",
    "forks",
}

COMMUNITY_FILE_KEYS = [
    "contributing",
    "code_of_conduct",
    "license",
    "readme",
    "issue_template",
    "pull_request_template",
]


def _community(files: int) -> dict:
    return {"files": {key: {} for key in COMMUNITY_FILE_KEYS[:files]}}


def _pulls(merged: int, total: int) -> list[dict]:
    return [{"merged_at": "2026-01-01" if index < merged else None} for index in range(total)]


def _maxed_repo() -> dict:
    """Every factor at its highest tier: the raw total lands exactly on the cap."""
    return {
        "pushed_at": _days_ago_iso(HEALTH_PUSH_DAYS_RECENT),
        "stargazers_count": HEALTH_STARS_HIGH,
        "forks_count": HEALTH_FORKS_HIGH,
        "open_issues_count": HEALTH_OPEN_ISSUES_MIN,
        "description": "Fully configured project",
        "topics": ["python"],
    }


async def _health(
    mock_github,
    repo: dict,
    *,
    pulls: list[dict] | None = None,
    community: dict | None = None,
    max_score: int = HEALTH_MAX_SCORE,
) -> dict:
    mock_github({
        "/repos/o/r": repo,
        "/repos/o/r/pulls": pulls or [],
        "/repos/o/r/community/profile": _community(0) if community is None else community,
    })
    result = await _call_tool_compat(
        build_server(),
        "opencollab_repo_health",
        {"params": {"owner": "o", "repo": "r"}},
    )
    payload = json.loads(_extract_text(result))

    # Invariants that hold for every response, capped or not.
    breakdown = payload["score_breakdown"]
    assert set(breakdown) == BREAKDOWN_KEYS
    assert all(isinstance(points, int) and points >= 0 for points in breakdown.values())
    raw_total = sum(breakdown.values())
    assert payload["health_score"] == min(raw_total, max_score)
    assert payload["capped"] is (raw_total > max_score)
    return payload


async def test_breakdown_lists_all_seven_factors(mock_github):
    payload = await _health(
        mock_github,
        _maxed_repo(),
        pulls=_pulls(merged=1, total=1),
        community=_community(6),
    )

    assert payload["repo"] == "o/r"
    assert payload["score_breakdown"] == {
        "activity": HEALTH_POINTS_PUSH_RECENT,
        "stars": HEALTH_POINTS_STARS_HIGH,
        "merge_rate": HEALTH_POINTS_MERGE_RATE_HIGH,
        "open_issues": HEALTH_POINTS_OPEN_ISSUES_OPTIMAL,
        "community_files": HEALTH_MAX_COMMUNITY_FILES_POINTS,
        "metadata": HEALTH_POINTS_DESCRIPTION + HEALTH_POINTS_TOPICS,
        "forks": HEALTH_POINTS_FORKS_HIGH,
    }
    assert sum(payload["score_breakdown"].values()) == HEALTH_MAX_SCORE
    assert payload["health_score"] == HEALTH_MAX_SCORE
    assert payload["capped"] is False


async def _assert_single_factor(mock_github, repo, key, points, pulls=None):
    payload = await _health(mock_github, repo, pulls=pulls)
    breakdown = payload["score_breakdown"]
    assert breakdown[key] == points
    assert sum(breakdown.values()) == points, breakdown
    assert payload["health_score"] == points


@pytest.mark.parametrize("days_ago, points", [
    (HEALTH_PUSH_DAYS_RECENT, HEALTH_POINTS_PUSH_RECENT),
    (HEALTH_PUSH_DAYS_RECENT + 1, HEALTH_POINTS_PUSH_ACTIVE),
    (HEALTH_PUSH_DAYS_ACTIVE, HEALTH_POINTS_PUSH_ACTIVE),
    (HEALTH_PUSH_DAYS_ACTIVE + 1, HEALTH_POINTS_PUSH_STALE),
    (HEALTH_PUSH_DAYS_STALE, HEALTH_POINTS_PUSH_STALE),
    (HEALTH_PUSH_DAYS_STALE + 1, 0),
])
async def test_activity_tiers(mock_github, days_ago, points):
    await _assert_single_factor(mock_github, {"pushed_at": _days_ago_iso(days_ago)}, "activity", points)


@pytest.mark.parametrize("stars, points", [
    (HEALTH_STARS_HIGH, HEALTH_POINTS_STARS_HIGH),
    (HEALTH_STARS_HIGH - 1, HEALTH_POINTS_STARS_MEDIUM),
    (HEALTH_STARS_MEDIUM, HEALTH_POINTS_STARS_MEDIUM),
    (HEALTH_STARS_MEDIUM - 1, HEALTH_POINTS_STARS_LOW),
    (HEALTH_STARS_LOW, HEALTH_POINTS_STARS_LOW),
    (HEALTH_STARS_LOW - 1, 0),
])
async def test_star_tiers(mock_github, stars, points):
    await _assert_single_factor(mock_github, {"stargazers_count": stars}, "stars", points)


@pytest.mark.parametrize("merged, total, points", [
    (100, 100, HEALTH_POINTS_MERGE_RATE_HIGH),
    (HEALTH_MERGE_RATE_HIGH, 100, HEALTH_POINTS_MERGE_RATE_HIGH),
    (HEALTH_MERGE_RATE_HIGH - 1, 100, HEALTH_POINTS_MERGE_RATE_MEDIUM),
    (HEALTH_MERGE_RATE_MEDIUM, 100, HEALTH_POINTS_MERGE_RATE_MEDIUM),
    (HEALTH_MERGE_RATE_MEDIUM - 1, 100, HEALTH_POINTS_MERGE_RATE_LOW),
    (0, 10, 0),
])
async def test_merge_rate_tiers(mock_github, merged, total, points):
    await _assert_single_factor(
        mock_github, {}, "merge_rate", points, pulls=_pulls(merged=merged, total=total),
    )


@pytest.mark.parametrize("open_issues, points", [
    (0, 0),
    (HEALTH_OPEN_ISSUES_MIN - 1, HEALTH_POINTS_OPEN_ISSUES_ANY),
    (HEALTH_OPEN_ISSUES_MIN, HEALTH_POINTS_OPEN_ISSUES_OPTIMAL),
    (HEALTH_OPEN_ISSUES_MAX, HEALTH_POINTS_OPEN_ISSUES_OPTIMAL),
    (HEALTH_OPEN_ISSUES_MAX + 1, HEALTH_POINTS_OPEN_ISSUES_ANY),
])
async def test_open_issue_volume_tiers(mock_github, open_issues, points):
    await _assert_single_factor(
        mock_github, {"open_issues_count": open_issues}, "open_issues", points,
    )


@pytest.mark.parametrize("files", [0, 4, 5, 6])
async def test_community_file_points_stay_under_existing_maximum(mock_github, files):
    # 6 files would be 24 points; the existing per-category maximum is 20.
    expected = min(files * HEALTH_POINTS_PER_COMMUNITY_FILE, HEALTH_MAX_COMMUNITY_FILES_POINTS)
    payload = await _health(mock_github, {}, community=_community(files))
    assert payload["score_breakdown"]["community_files"] == expected
    assert payload["health_score"] == expected


@pytest.mark.parametrize("description, topics, points", [
    (False, False, 0),
    (True, False, HEALTH_POINTS_DESCRIPTION),
    (False, True, HEALTH_POINTS_TOPICS),
    (True, True, HEALTH_POINTS_DESCRIPTION + HEALTH_POINTS_TOPICS),
])
async def test_metadata_points_are_independent(mock_github, description, topics, points):
    repo = {
        "description": "A project" if description else None,
        "topics": ["python"] if topics else [],
    }
    await _assert_single_factor(mock_github, repo, "metadata", points)


@pytest.mark.parametrize("forks, points", [
    (HEALTH_FORKS_HIGH, HEALTH_POINTS_FORKS_HIGH),
    (HEALTH_FORKS_HIGH - 1, HEALTH_POINTS_FORKS_MEDIUM),
    (HEALTH_FORKS_MEDIUM, HEALTH_POINTS_FORKS_MEDIUM),
    (HEALTH_FORKS_MEDIUM - 1, HEALTH_POINTS_FORKS_LOW),
    (HEALTH_FORKS_LOW, HEALTH_POINTS_FORKS_LOW),
    (HEALTH_FORKS_LOW - 1, 0),
])
async def test_fork_tiers(mock_github, forks, points):
    await _assert_single_factor(mock_github, {"forks_count": forks}, "forks", points)


async def test_breakdown_above_cap_keeps_raw_total_and_flags_capped(mock_github, monkeypatch):
    # The shipped constants top out at exactly HEALTH_MAX_SCORE, so a lower cap
    # is the only way to exercise >cap without changing production thresholds.
    monkeypatch.setattr(evaluation, "HEALTH_MAX_SCORE", 50)
    payload = await _health(
        mock_github,
        _maxed_repo(),
        pulls=_pulls(merged=1, total=1),
        community=_community(6),
        max_score=50,
    )

    raw_total = sum(payload["score_breakdown"].values())
    assert raw_total == HEALTH_MAX_SCORE  # raw total is not squeezed to the cap
    assert raw_total > 50
    assert payload["health_score"] == 50
    assert payload["capped"] is True
    # The verdict still comes from the capped score, not the raw total.
    assert payload["verdict"] == "Good — solid project to contribute to"
