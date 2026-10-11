"""Evaluation & scoring tools."""

from __future__ import annotations

import asyncio
import json
from typing import Any

import httpx
from mcp.server.mcpserver import MCPServer

from ..constants import (
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
    HEALTH_VERDICT_EXCELLENT,
    HEALTH_VERDICT_FAIR,
    HEALTH_VERDICT_GOOD,
    IMPACT_HIGH_STARS,
    IMPACT_MASSIVE_STARS,
    IMPACT_MEDIUM_STARS,
    IMPACT_MODERATE_STARS,
)
from ..github_client import github_get, handle_github_error
from ..helpers import days_ago
from ..models import RepoInput


async def _community_profile_or_none(path: str) -> Any | None:
    """Return community metadata when available, without hiding rate limits."""
    try:
        return await github_get(f"{path}/community/profile")
    except httpx.HTTPStatusError as exc:
        status = exc.response.status_code
        rate_limited = status == 403 and exc.response.headers.get("x-ratelimit-remaining") == "0"
        if status == 404 or (status == 403 and not rate_limited):
            return None
        raise


def register(mcp: MCPServer) -> None:

    @mcp.tool(
        name="opencollab_repo_health",
        annotations={
            "title": "Score repository contributor-friendliness",
            "readOnlyHint": True, "destructiveHint": False,
            "idempotentHint": True, "openWorldHint": True,
        },
    )
    async def opencollab_repo_health(params: RepoInput) -> str:
        """Score a repository's health and contributor-friendliness (0-100).

        Checks activity recency, community size, PR merge patterns, open
        issues, and whether the repo has essential contributor files.
        Archived repositories receive a read-only verdict regardless of score.
        """
        path = f"/repos/{params.owner}/{params.repo}"
        try:
            repo, pulls, community = await asyncio.gather(
                github_get(path),
                github_get(f"{path}/pulls", {"state": "closed", "per_page": 30, "sort": "updated"}),
                _community_profile_or_none(path),
            )
        except Exception as e:
            return handle_github_error(e)

        score = 0
        details: dict[str, object] = {"archived": bool(repo.get("archived", False))}

        last_push_days = days_ago(repo.get("pushed_at"))
        if last_push_days is not None:
            if last_push_days <= HEALTH_PUSH_DAYS_RECENT:
                score += HEALTH_POINTS_PUSH_RECENT
            elif last_push_days <= HEALTH_PUSH_DAYS_ACTIVE:
                score += HEALTH_POINTS_PUSH_ACTIVE
            elif last_push_days <= HEALTH_PUSH_DAYS_STALE:
                score += HEALTH_POINTS_PUSH_STALE
        details["last_push_days_ago"] = last_push_days

        stars = repo.get("stargazers_count", 0)
        if stars >= HEALTH_STARS_HIGH:
            score += HEALTH_POINTS_STARS_HIGH
        elif stars >= HEALTH_STARS_MEDIUM:
            score += HEALTH_POINTS_STARS_MEDIUM
        elif stars >= HEALTH_STARS_LOW:
            score += HEALTH_POINTS_STARS_LOW
        details["stars"] = stars

        merged_count = sum(1 for p in pulls if p.get("merged_at"))
        total_closed = len(pulls)
        merge_rate = round(merged_count / max(total_closed, 1) * 100, 1)
        if merge_rate >= HEALTH_MERGE_RATE_HIGH:
            score += HEALTH_POINTS_MERGE_RATE_HIGH
        elif merge_rate >= HEALTH_MERGE_RATE_MEDIUM:
            score += HEALTH_POINTS_MERGE_RATE_MEDIUM
        elif merge_rate > 0:
            score += HEALTH_POINTS_MERGE_RATE_LOW
        details["pr_merge_rate_pct"] = merge_rate

        has_issues = bool(repo.get("has_issues", True))
        details["has_issues"] = has_issues
        # With Issues disabled, GitHub's combined count contains only PRs.
        open_issues = repo.get("open_issues_count", 0) if has_issues else 0
        if not has_issues:
            details["issues_note"] = (
                "Issues are disabled on GitHub — check the README for where this project tracks work"
            )
        if HEALTH_OPEN_ISSUES_MIN <= open_issues <= HEALTH_OPEN_ISSUES_MAX:
            score += HEALTH_POINTS_OPEN_ISSUES_OPTIMAL
        elif open_issues > 0:
            score += HEALTH_POINTS_OPEN_ISSUES_ANY
        details["open_issues"] = open_issues

        files_info = community.get("files", {}) if isinstance(community, dict) else {}
        details["community_profile_available"] = community is not None
        community_files = {
            "contributing": files_info.get("contributing") is not None,
            "code_of_conduct": files_info.get("code_of_conduct") is not None,
            "license": files_info.get("license") is not None,
            "readme": files_info.get("readme") is not None,
            "issue_template": files_info.get("issue_template") is not None,
            "pull_request_template": files_info.get("pull_request_template") is not None,
        }
        score += min(
            sum(community_files.values()) * HEALTH_POINTS_PER_COMMUNITY_FILE,
            HEALTH_MAX_COMMUNITY_FILES_POINTS,
        )
        details["community_files"] = community_files

        if repo.get("description"):
            score += HEALTH_POINTS_DESCRIPTION
        if repo.get("topics"):
            score += HEALTH_POINTS_TOPICS

        forks = repo.get("forks_count", 0)
        if forks >= HEALTH_FORKS_HIGH:
            score += HEALTH_POINTS_FORKS_HIGH
        elif forks >= HEALTH_FORKS_MEDIUM:
            score += HEALTH_POINTS_FORKS_MEDIUM
        elif forks >= HEALTH_FORKS_LOW:
            score += HEALTH_POINTS_FORKS_LOW
        score = min(score, HEALTH_MAX_SCORE)

        if details["archived"]:
            verdict = "Archived — read-only, cannot accept contributions"
        elif score >= HEALTH_VERDICT_EXCELLENT:
            verdict = "Excellent — very contributor-friendly"
        elif score >= HEALTH_VERDICT_GOOD:
            verdict = "Good — solid project to contribute to"
        elif score >= HEALTH_VERDICT_FAIR:
            verdict = "Fair — some friction expected"
        else:
            verdict = "Low — may be abandoned or hard to contribute to"

        return json.dumps({
            "repo": f"{params.owner}/{params.repo}",
            "health_score": score,
            "verdict": verdict,
            "details": details,
        }, indent=2)

    @mcp.tool(
        name="opencollab_impact_estimator",
        annotations={
            "title": "Estimate contribution impact for a repo",
            "readOnlyHint": True, "destructiveHint": False,
            "idempotentHint": True, "openWorldHint": True,
        },
    )
    async def opencollab_impact_estimator(params: RepoInput) -> str:
        """Estimate the impact of contributing to a specific repository.

        Produces an impact tier and a suggested resume line for active repositories.
        Archived repositories are flagged as read-only and receive no resume line.
        """
        path = f"/repos/{params.owner}/{params.repo}"
        try:
            repo = await github_get(path)
        except Exception as e:
            return handle_github_error(e)

        stars = repo.get("stargazers_count", 0)
        forks = repo.get("forks_count", 0)
        watchers = repo.get("subscribers_count", 0)
        open_issues = repo.get("open_issues_count", 0)
        description = repo.get("description") or ""
        archived = bool(repo.get("archived", False))

        if stars >= IMPACT_MASSIVE_STARS:
            tier, reach = "MASSIVE", "millions of developers"
        elif stars >= IMPACT_HIGH_STARS:
            tier, reach = "HIGH", "tens of thousands of developers"
        elif stars >= IMPACT_MEDIUM_STARS:
            tier, reach = "MEDIUM", "thousands of developers"
        elif stars >= IMPACT_MODERATE_STARS:
            tier, reach = "MODERATE", "hundreds of developers"
        else:
            tier, reach = "LOW", "a growing community"

        repo_name = f"{params.owner}/{params.repo}"
        if archived:
            resume_line = None
        elif stars >= IMPACT_MEDIUM_STARS:
            resume_line = f"Contributed to {repo_name} ({stars:,}+ stars), reaching {reach}"
        else:
            resume_line = f"Open-source contributor to {repo_name} — {description[:80]}"

        visibility = min(
            (min(stars // 500, 40) if stars >= 100 else 0)
            + (min(forks // 100, 20) if forks >= 50 else 0)
            + (min(watchers // 50, 20) if watchers >= 50 else 0)
            + (10 if open_issues >= 10 else 0)
            + (10 if repo.get("topics") else 0),
            100,
        )

        result = {
            "repo": repo_name,
            "archived": archived,
            "impact_tier": tier,
            "estimated_reach": reach,
            "stars": stars,
            "forks": forks,
            "watchers": watchers,
            "open_issues": open_issues,
            "visibility_score": visibility,
            "suggested_resume_line": resume_line,
            "topics": repo.get("topics", []),
        }
        if archived:
            result["note"] = "Archived — read-only, new contributions are not possible"
        return json.dumps(result, indent=2)
