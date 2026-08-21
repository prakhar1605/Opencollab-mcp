"""Discovery & matching tools."""

from __future__ import annotations

import asyncio
import json

from mcp.server.fastmcp import FastMCP

from ..constants import RECENT_ISSUES_DAYS
from ..github_client import github_get, github_search, handle_github_error
from ..helpers import days_ago, recent_date_str, truncate
from ..models import LanguageInput, UsernameInput


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
            # The language is quoted so multi-word values survive: bare
            # `language:Jupyter Notebook` is parsed by GitHub as
            # `language:Jupyter` plus a free-text `Notebook`.
            f'language:"{params.language}"',
            'label:"good first issue"',
            "state:open",
            # /search/issues returns pull requests too, and a PR carrying the
            # label would otherwise look like an issue to pick up.
            "is:issue",
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
                f'language:"{primary_lang}" label:"good first issue" state:open '
                f'is:issue created:>{since} is:public',
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
