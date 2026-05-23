"""Evaluation & scoring tools."""

from __future__ import annotations

import asyncio
import json

from mcp.server.fastmcp import FastMCP

from ..constants import (
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


def register(mcp: FastMCP) -> None:

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
        """
        path = f"/repos/{params.owner}/{params.repo}"
        try:
            repo, pulls, community = await asyncio.gather(
                github_get(path),
                github_get(f"{path}/pulls", {"state": "closed", "per_page": 30, "sort": "updated"}),
                github_get(f"{path}/community/profile"),
            )
        except Exception as e:
            return handle_github_error(e)

        score = 0
        details: dict[str, object] = {}

        last_push_days = days_ago(repo.get("pushed_at"))
        if last_push_days is not None:
            if last_push_days <= 7: score += 20
            elif last_push_days <= 30: score += 15
            elif last_push_days <= 90: score += 8
        details["last_push_days_ago"] = last_push_days

        stars = repo.get("stargazers_count", 0)
        if stars >= 1000: score += 15
        elif stars >= 100: score += 10
        elif stars >= 10: score += 5
        details["stars"] = stars

        merged_count = sum(1 for p in pulls if p.get("merged_at"))
        total_closed = len(pulls)
        merge_rate = round(merged_count / max(total_closed, 1) * 100, 1)
        if merge_rate >= 60: score += 20
        elif merge_rate >= 30: score += 12
        elif merge_rate > 0: score += 5
        details["pr_merge_rate_pct"] = merge_rate

        open_issues = repo.get("open_issues_count", 0)
        if 5 <= open_issues <= 500: score += 10
        elif open_issues > 0: score += 5
        details["open_issues"] = open_issues

        files_info = community.get("files", {}) if isinstance(community, dict) else {}
        community_files = {
            "contributing": files_info.get("contributing") is not None,
            "code_of_conduct": files_info.get("code_of_conduct") is not None,
            "license": files_info.get("license") is not None,
            "readme": files_info.get("readme") is not None,
            "issue_template": files_info.get("issue_template") is not None,
            "pull_request_template": files_info.get("pull_request_template") is not None,
        }
        score += min(sum(community_files.values()) * 4, 20)
        details["community_files"] = community_files

        if repo.get("description"): score += 2
        if repo.get("topics"): score += 3

        forks = repo.get("forks_count", 0)
        if forks >= 100: score += 10
        elif forks >= 20: score += 6
        elif forks >= 5: score += 3
        score = min(score, 100)

        if score >= HEALTH_VERDICT_EXCELLENT:
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

        Produces an impact tier (MASSIVE/HIGH/MEDIUM/LOW) and a suggested
        resume line.
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
        if stars >= IMPACT_MEDIUM_STARS:
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

        return json.dumps({
            "repo": repo_name,
            "impact_tier": tier,
            "estimated_reach": reach,
            "stars": stars,
            "forks": forks,
            "watchers": watchers,
            "open_issues": open_issues,
            "visibility_score": visibility,
            "suggested_resume_line": resume_line,
            "topics": repo.get("topics", []),
        }, indent=2)
