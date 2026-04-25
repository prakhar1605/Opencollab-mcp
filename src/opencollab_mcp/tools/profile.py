"""Profile & readiness tools."""

from __future__ import annotations

import json

from mcp.server.fastmcp import FastMCP

from ..constants import READINESS_ALMOST, READINESS_GETTING_STARTED, READINESS_READY
from ..github_client import github_get, handle_github_error
from ..helpers import days_ago, truncate
from ..models import RepoInput, UsernameInput


def register(mcp: FastMCP) -> None:

    @mcp.tool(
        name="opencollab_analyze_profile",
        annotations={
            "title": "Analyze developer GitHub profile",
            "readOnlyHint": True, "destructiveHint": False,
            "idempotentHint": True, "openWorldHint": True,
        },
    )
    async def opencollab_analyze_profile(params: UsernameInput) -> str:
        """Analyze a GitHub user's profile to extract skills, languages,
        contribution patterns, and interests.

        Returns a structured skill profile including top languages, starred
        topics, contribution frequency, and repository highlights.
        """
        try:
            user = await github_get(f"/users/{params.username}")
            repos_raw = await github_get(
                f"/users/{params.username}/repos",
                {"per_page": 100, "sort": "pushed", "type": "owner"},
            )
            events_raw = await github_get(
                f"/users/{params.username}/events/public",
                {"per_page": 50},
            )
        except Exception as e:
            return handle_github_error(e)

        lang_bytes: dict[str, int] = {}
        topics_set: set[str] = set()
        for repo in repos_raw:
            lang = repo.get("language")
            if lang:
                lang_bytes[lang] = lang_bytes.get(lang, 0) + repo.get("size", 0)
            for t in repo.get("topics", []):
                topics_set.add(t)

        total = max(sum(lang_bytes.values()), 1)
        top_langs = sorted(lang_bytes.items(), key=lambda x: x[1], reverse=True)[:8]
        languages = [
            {"name": name, "percentage": round(byte_count / total * 100, 1)}
            for name, byte_count in top_langs
        ]

        event_types: dict[str, int] = {}
        for ev in events_raw:
            et = ev.get("type", "Unknown")
            event_types[et] = event_types.get(et, 0) + 1

        notable = sorted(
            repos_raw, key=lambda r: r.get("stargazers_count", 0), reverse=True
        )[:5]
        highlights = [
            {
                "name": r.get("full_name", ""),
                "stars": r.get("stargazers_count", 0),
                "language": r.get("language"),
                "description": truncate(r.get("description"), 100),
            }
            for r in notable
        ]

        return json.dumps({
            "username": params.username,
            "name": user.get("name"),
            "bio": user.get("bio"),
            "public_repos": user.get("public_repos", 0),
            "followers": user.get("followers", 0),
            "account_age_days": days_ago(user.get("created_at")),
            "top_languages": languages,
            "topics_of_interest": sorted(topics_set)[:20],
            "recent_activity_summary": event_types,
            "notable_repos": highlights,
        }, indent=2)

    @mcp.tool(
        name="opencollab_first_timer_score",
        annotations={
            "title": "Rate how ready a user is for open source",
            "readOnlyHint": True, "destructiveHint": False,
            "idempotentHint": True, "openWorldHint": True,
        },
    )
    async def opencollab_first_timer_score(params: UsernameInput) -> str:
        """Rate how ready a GitHub user is for open source contributions.

        Scores profile completeness, coding activity, language diversity,
        and gives personalized tips on what to improve before contributing.
        """
        try:
            user = await github_get(f"/users/{params.username}")
            repos_raw = await github_get(
                f"/users/{params.username}/repos",
                {"per_page": 100, "sort": "pushed", "type": "owner"},
            )
            events_raw = await github_get(
                f"/users/{params.username}/events/public",
                {"per_page": 30},
            )
        except Exception as e:
            return handle_github_error(e)

        score = 0
        tips: list[str] = []

        if user.get("bio"):
            score += 10
        else:
            tips.append("Add a bio to your GitHub profile — maintainers check contributor profiles")

        public_repos = user.get("public_repos", 0)
        if public_repos >= 5:
            score += 15
        elif public_repos >= 1:
            score += 8
            tips.append("Create more public repos to show your work")
        else:
            tips.append("Push at least 1-2 projects to GitHub to build credibility")

        languages_known = {r.get("language") for r in repos_raw if r.get("language")}
        if len(languages_known) >= 3:
            score += 15
        elif len(languages_known) >= 1:
            score += 8
            tips.append("Try projects in more languages to expand your contribution options")
        else:
            tips.append("Your repos don't show any programming language — push some code")

        repos_with_description = sum(1 for r in repos_raw if r.get("description"))
        if repos_with_description >= 3:
            score += 10
        else:
            tips.append("Add descriptions to your repos — shows you care about documentation")

        recent_events = len(events_raw)
        if recent_events >= 20:
            score += 15
        elif recent_events >= 5:
            score += 8
        else:
            tips.append("Be more active on GitHub — push code, open issues, star repos")

        fork_count = sum(1 for r in repos_raw if r.get("fork"))
        if fork_count >= 2:
            score += 10
            tips.append("You've forked repos — great! Now open PRs on them")
        elif fork_count >= 1:
            score += 5
        else:
            tips.append("Fork a project you use and try making a small improvement")

        stars_received = sum(r.get("stargazers_count", 0) for r in repos_raw)
        if stars_received >= 10:
            score += 10
        elif stars_received >= 1:
            score += 5

        account_age = days_ago(user.get("created_at"))
        if account_age and account_age >= 365:
            score += 5

        has_pr_events = any(e.get("type") == "PullRequestEvent" for e in events_raw)
        if has_pr_events:
            score += 10
        else:
            tips.append("You haven't opened any PRs yet — start with a documentation fix!")

        score = min(score, 100)
        if score >= READINESS_READY:
            level = "Ready — you can confidently contribute to most projects"
        elif score >= READINESS_ALMOST:
            level = "Almost there — a few improvements and you're set"
        elif score >= READINESS_GETTING_STARTED:
            level = "Getting started — build up your profile first"
        else:
            level = "Beginner — focus on learning and building projects before contributing"

        return json.dumps({
            "username": params.username,
            "readiness_score": score,
            "readiness_level": level,
            "languages_known": sorted(languages_known),
            "public_repos": public_repos,
            "account_age_days": account_age,
            "has_opened_prs": has_pr_events,
            "tips_to_improve": tips,
        }, indent=2)

    @mcp.tool(
        name="opencollab_contributor_leaderboard",
        annotations={
            "title": "Show top contributors of a repo",
            "readOnlyHint": True, "destructiveHint": False,
            "idempotentHint": True, "openWorldHint": True,
        },
    )
    async def opencollab_contributor_leaderboard(params: RepoInput) -> str:
        """Get the top contributors of a repository with their commit counts
        and profiles. Returns the top 10 contributors ranked by commits.
        """
        try:
            contributors = await github_get(
                f"/repos/{params.owner}/{params.repo}/contributors",
                {"per_page": 10},
            )
        except Exception as e:
            return handle_github_error(e)

        if not isinstance(contributors, list):
            # GitHub returned 202 (still computing) — handle gracefully.
            return json.dumps({
                "repo": f"{params.owner}/{params.repo}",
                "message": "Contributor stats are still being computed by GitHub. Try again in 30 seconds.",
            }, indent=2)

        leaderboard = [
            {
                "rank": i,
                "username": c.get("login", ""),
                "contributions": c.get("contributions", 0),
                "profile_url": c.get("html_url", ""),
                "avatar_url": c.get("avatar_url", ""),
            }
            for i, c in enumerate(contributors[:10], 1)
        ]
        return json.dumps({
            "repo": f"{params.owner}/{params.repo}",
            "top_contributors": leaderboard,
            "total_contributions_shown": sum(c.get("contributions", 0) for c in contributors[:10]),
        }, indent=2)
