"""Discovery & matching tools."""

from __future__ import annotations

import asyncio
import json

from mcp.server.fastmcp import FastMCP

from ..constants import (
    MENTOR_REPOS_DAYS,
    QUICK_WEEKEND_LABELS,
    RECENT_ISSUES_DAYS,
    RECENT_TRENDING_DAYS,
    WEEKEND_ISSUES_DAYS,
)
from ..github_client import github_get, github_search, handle_github_error
from ..helpers import days_ago, recent_date_str, truncate
from ..models import LanguageInput, RepoInput, UsernameInput


def register(mcp: FastMCP) -> None:

    @mcp.tool(
        name="opencollab_find_issues",
        annotations={
            "title": "Find good first issues matched to skills",
            "readOnlyHint": True, "destructiveHint": False,
            "idempotentHint": True, "openWorldHint": True,
        },
    )
    async def opencollab_find_issues(params: LanguageInput) -> str:
        """Find beginner-friendly open-source issues labelled 'good first
        issue' for a given programming language. Returns up to 15 recently
        created issues from public repos.
        """
        since = recent_date_str(RECENT_ISSUES_DAYS)
        query_parts = [
            f"language:{params.language}",
            'label:"good first issue"',
            "state:open",
            f"created:>{since}",
            "is:public",
        ]
        try:
            result = await github_search(
                "issues",
                " ".join(query_parts),
                {"sort": "created", "order": "desc", "per_page": 15},
            )
        except Exception as e:
            return handle_github_error(e)

        # TODO: exclude_topics not applied here — issue payloads don't include topics.
        # Would require an extra repo lookup per issue (rate-limit concern). Deferred to follow-up PR.

        issues = []
        for item in result.get("items", []):
            repo_url = item.get("repository_url", "")
            repo_name = "/".join(repo_url.split("/")[-2:]) if repo_url else ""
            issues.append({
                "title": item.get("title", ""),
                "url": item.get("html_url", ""),
                "repo": repo_name,
                "labels": [lb.get("name", "") for lb in item.get("labels", [])],
                "comments": item.get("comments", 0),
                "created_days_ago": days_ago(item.get("created_at")),
                "body_preview": truncate(item.get("body"), 200),
            })
        return json.dumps({
            "total_found": result.get("total_count", 0),
            "language": params.language,
            "issues": issues,
        }, indent=2)

    @mcp.tool(
        name="opencollab_trending_repos",
        annotations={
            "title": "Find trending repos seeking contributors",
            "readOnlyHint": True, "destructiveHint": False,
            "idempotentHint": True, "openWorldHint": True,
        },
    )
    async def opencollab_trending_repos(params: LanguageInput) -> str:
        """Find trending repositories that are actively seeking contributors.

        Searches for recently created repos with good-first-issue labels,
        sorted by stars.
        """
        since = recent_date_str(RECENT_TRENDING_DAYS)
        qp = [
            f"created:>{since}",
            "good-first-issues:>0",
            "is:public",
            "archived:false",
            f"language:{params.language}",
        ]
        try:
            result = await github_search(
                "repositories",
                " ".join(qp),
                {"sort": "stars", "order": "desc", "per_page": 10},
            )
        except Exception as e:
            return handle_github_error(e)

        repos = [
            {
                "name": r.get("full_name", ""),
                "description": truncate(r.get("description"), 150),
                "stars": r.get("stargazers_count", 0),
                "forks": r.get("forks_count", 0),
                "language": r.get("language"),
                "open_issues": r.get("open_issues_count", 0),
                "topics": r.get("topics", [])[:8],
                "url": r.get("html_url", ""),
                "created_days_ago": days_ago(r.get("created_at")),
                "last_push_days_ago": days_ago(r.get("pushed_at")),
            }
            for r in result.get("items", [])
        ]

        normalized_exclude = [t.lower().strip() for t in (params.exclude_topics or [])]
        if normalized_exclude:
            repos = [
                r for r in repos
                if not any(topic in normalized_exclude for topic in r.get("topics", []))
            ]

        return json.dumps({
            "total_found": result.get("total_count", 0),
            "repos": repos,
        }, indent=2)

    @mcp.tool(
        name="opencollab_similar_repos",
        annotations={
            "title": "Find similar repos to contribute to",
            "readOnlyHint": True, "destructiveHint": False,
            "idempotentHint": True, "openWorldHint": True,
        },
    )
    async def opencollab_similar_repos(params: RepoInput) -> str:
        """Find repositories similar to a given one based on topics and language.

        If you like contributing to repo X, this finds other repos in the
        same domain that are also welcoming to contributors.
        """
        path = f"/repos/{params.owner}/{params.repo}"
        try:
            repo = await github_get(path)
        except Exception as e:
            return handle_github_error(e)

        lang = repo.get("language") or ""
        topics = repo.get("topics") or []
        desc_words = (repo.get("description") or "").split()[:3]
        query_parts = []
        if topics:
            query_parts.append(f"topic:{topics[0]}")
        if lang:
            query_parts.append(f"language:{lang}")
        if desc_words:
            query_parts.append(" ".join(desc_words))
        query_parts.append("good-first-issues:>0")
        query_parts.append("archived:false")

        try:
            result = await github_search(
                "repositories",
                " ".join(query_parts),
                {"sort": "stars", "order": "desc", "per_page": 12},
            )
        except Exception as e:
            return handle_github_error(e)

        similar = []
        for r in result.get("items", []):
            if r.get("full_name") == f"{params.owner}/{params.repo}":
                continue
            similar.append({
                "name": r.get("full_name", ""),
                "description": truncate(r.get("description"), 150),
                "stars": r.get("stargazers_count", 0),
                "language": r.get("language"),
                "topics": r.get("topics", [])[:6],
                "open_issues": r.get("open_issues_count", 0),
                "url": r.get("html_url", ""),
                "last_push_days_ago": days_ago(r.get("pushed_at")),
            })
        return json.dumps({
            "source_repo": f"{params.owner}/{params.repo}",
            "similar_repos": similar[:10],
            "count": len(similar[:10]),
        }, indent=2)

    @mcp.tool(
        name="opencollab_find_mentor_repos",
        annotations={
            "title": "Find repos with mentorship programs for beginners",
            "readOnlyHint": True, "destructiveHint": False,
            "idempotentHint": True, "openWorldHint": True,
        },
    )
    async def opencollab_find_mentor_repos(params: LanguageInput) -> str:
        """Find repositories that actively mentor newcomers.

        Searches for repos with mentorship topics and programs like GSoC,
        Outreachy, or Hacktoberfest. Note: Hacktoberfest topics peak in
        October; mentorship/gsoc topics return fewer repos year-round.
        """
        since = recent_date_str(MENTOR_REPOS_DAYS)
        queries = [
            f"language:{params.language} topic:hacktoberfest good-first-issues:>3 pushed:>{since}",
            f"language:{params.language} topic:gsoc good-first-issues:>1 pushed:>{since}",
            f"language:{params.language} topic:mentorship good-first-issues:>1 pushed:>{since}",
        ]
        seen: set[str] = set()
        repos: list[dict] = []
        # Run all three searches in parallel — they're independent.
        results = await asyncio.gather(
            *(github_search("repositories", q, {"sort": "stars", "order": "desc", "per_page": 8})
              for q in queries),
            return_exceptions=True,
        )
        for result in results:
            if isinstance(result, Exception):
                continue
            for r in result.get("items", []):
                name = r.get("full_name", "")
                if name in seen:
                    continue
                seen.add(name)
                topics = r.get("topics", [])
                mentor_signals = [
                    t for t in topics
                    if t in ("hacktoberfest", "gsoc", "outreachy", "mentorship",
                             "good-first-issue", "beginner-friendly", "first-timers-only")
                ]
                repos.append({
                    "name": name,
                    "description": truncate(r.get("description"), 150),
                    "stars": r.get("stargazers_count", 0),
                    "language": r.get("language"),
                    "mentor_signals": mentor_signals,
                    "topics": topics[:8],
                    "url": r.get("html_url", ""),
                    "open_issues": r.get("open_issues_count", 0),
                    "last_push_days_ago": days_ago(r.get("pushed_at")),
                })
        repos.sort(key=lambda x: len(x.get("mentor_signals", [])), reverse=True)

        normalized_exclude = [t.lower().strip() for t in (params.exclude_topics or [])]
        if normalized_exclude:
            repos = [
                r for r in repos
                if not any(topic in normalized_exclude for topic in r.get("topics", []))
            ]

        return json.dumps({
            "language": params.language,
            "mentor_repos": repos[:15],
            "count": len(repos[:15]),
        }, indent=2)

    @mcp.tool(
        name="opencollab_weekend_issues",
        annotations={
            "title": "Find quick issues for a weekend contribution",
            "readOnlyHint": True, "destructiveHint": False,
            "idempotentHint": True, "openWorldHint": True,
        },
    )
    async def opencollab_weekend_issues(params: LanguageInput) -> str:
        """Find small, quick issues perfect for a weekend or 1-2 hour
        contribution. Searches for issues labelled documentation, typo,
        test, chore, or other low-effort tags in addition to good-first-issue.
        """
        since = recent_date_str(WEEKEND_ISSUES_DAYS)

        async def _search_label(label: str):
            return await github_search(
                "issues",
                f'language:{params.language} label:"{label}" state:open '
                f'created:>{since} is:public',
                {"sort": "created", "order": "desc", "per_page": 5},
            )

        # Parallel fan-out across the first 5 quick labels.
        results = await asyncio.gather(
            *(_search_label(label) for label in QUICK_WEEKEND_LABELS[:5]),
            return_exceptions=True,
        )

        # TODO: exclude_topics not applied here — issue payloads don't include topics.
        # Would require an extra repo lookup per issue (rate-limit concern). Deferred to follow-up PR.

        all_issues: list[dict] = []
        seen_urls: set[str] = set()
        for result in results:
            if isinstance(result, Exception):
                continue
            for item in result.get("items", []):
                url = item.get("html_url", "")
                if url in seen_urls:
                    continue
                seen_urls.add(url)
                repo_url = item.get("repository_url", "")
                repo_name = "/".join(repo_url.split("/")[-2:]) if repo_url else ""
                body = item.get("body") or ""
                is_quick = len(body) < 500 and item.get("comments", 0) <= 3
                if is_quick:
                    all_issues.append({
                        "title": item.get("title", ""),
                        "url": url,
                        "repo": repo_name,
                        "labels": [lb.get("name", "") for lb in item.get("labels", [])],
                        "comments": item.get("comments", 0),
                        "body_preview": truncate(body, 150),
                        "estimated_effort": "1-2 hours",
                    })
        all_issues.sort(key=lambda x: x.get("comments", 0))
        return json.dumps({
            "language": params.language,
            "weekend_issues": all_issues[:12],
            "count": len(all_issues[:12]),
            "tip": "These are small issues (short description, few comments) — perfect for a quick weekend contribution",
        }, indent=2)

    @mcp.tool(
        name="opencollab_match_me",
        annotations={
            "title": "Analyze profile and find matched issues in one step",
            "readOnlyHint": True, "destructiveHint": False,
            "idempotentHint": True, "openWorldHint": True,
        },
    )
    async def opencollab_match_me(params: UsernameInput) -> str:
        """All-in-one: analyze a GitHub profile and instantly find issues
        matched to that user's top skills.

        Detects the user's primary language and returns 10 matching
        good-first-issues.
        """
        try:
            # User and repos can be fetched in parallel.
            user, repos_raw = await asyncio.gather(
                github_get(f"/users/{params.username}"),
                github_get(
                    f"/users/{params.username}/repos",
                    {"per_page": 100, "sort": "pushed", "type": "owner"},
                ),
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
        top_langs = sorted(lang_bytes.items(), key=lambda x: x[1], reverse=True)[:3]
        languages = [
            {"name": n, "percentage": round(b / total * 100, 1)}
            for n, b in top_langs
        ]
        primary_lang = top_langs[0][0] if top_langs else "Python"
        since = recent_date_str(RECENT_ISSUES_DAYS)
        try:
            result = await github_search(
                "issues",
                f'language:{primary_lang} label:"good first issue" state:open '
                f'created:>{since} is:public',
                {"sort": "created", "order": "desc", "per_page": 10},
            )
        except Exception as e:
            return handle_github_error(e)

        issues = [
            {
                "title": it.get("title", ""),
                "url": it.get("html_url", ""),
                "repo": "/".join(it.get("repository_url", "").split("/")[-2:]),
                "labels": [lb.get("name", "") for lb in it.get("labels", [])],
                "comments": it.get("comments", 0),
                "body_preview": truncate(it.get("body"), 150),
            }
            for it in result.get("items", [])
        ]
        return json.dumps({
            "username": params.username,
            "name": user.get("name"),
            "top_languages": languages,
            "topics": sorted(topics_set)[:10],
            "matched_language": primary_lang,
            "matched_issues": issues,
        }, indent=2)
