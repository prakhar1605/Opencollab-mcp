"""Issue intelligence tools."""

from __future__ import annotations

import asyncio
import json

from mcp.server.fastmcp import FastMCP

from ..github_client import github_get, handle_github_error
from ..helpers import days_ago, decode_base64_content, parse_issue_number, truncate
from ..models import IssueInput


def _bad_issue_number(raw: str, err: Exception) -> str:
    return json.dumps({"error": f"Invalid issue_number {raw!r}: {err}"}, indent=2)


def register(mcp: FastMCP) -> None:

    @mcp.tool(
        name="opencollab_check_issue_availability",
        annotations={
            "title": "Check if an issue is still available to work on",
            "readOnlyHint": True, "destructiveHint": False,
            "idempotentHint": True, "openWorldHint": True,
        },
    )
    async def opencollab_check_issue_availability(params: IssueInput) -> str:
        """Check if a GitHub issue is still available — no one has claimed
        it or opened a PR for it. Checks assignees and linked pull requests.
        """
        try:
            issue_num = parse_issue_number(params.issue_number)
        except ValueError as e:
            return _bad_issue_number(params.issue_number, e)

        path = f"/repos/{params.owner}/{params.repo}"
        try:
            issue = await github_get(f"{path}/issues/{issue_num}")
        except Exception as e:
            return handle_github_error(e)

        if issue.get("state") != "open":
            return json.dumps({
                "available": False,
                "reason": f"Issue is {issue.get('state', 'unknown')}",
                "issue_title": issue.get("title", ""),
            }, indent=2)

        assignees = [a.get("login", "") for a in issue.get("assignees", [])]
        if assignees:
            return json.dumps({
                "available": False,
                "reason": f"Already assigned to: {', '.join(assignees)}",
                "issue_title": issue.get("title", ""),
            }, indent=2)

        linked_prs: list[dict] = []
        try:
            timeline = await github_get(
                f"{path}/issues/{issue_num}/timeline",
                {"per_page": 50},
            )
            for event in timeline:
                if event.get("event") == "cross-referenced":
                    source = event.get("source", {}).get("issue", {})
                    if source.get("pull_request"):
                        linked_prs.append({
                            "pr_number": source.get("number"),
                            "title": source.get("title", ""),
                            "state": source.get("state", "unknown"),
                            "author": source.get("user", {}).get("login", "unknown"),
                        })
        except Exception:
            pass

        if any(pr.get("state") == "open" for pr in linked_prs):
            return json.dumps({
                "available": False,
                "reason": "An open PR already exists for this issue",
                "linked_prs": linked_prs,
                "issue_title": issue.get("title", ""),
            }, indent=2)

        return json.dumps({
            "available": True,
            "reason": "No assignees, no open PRs — go for it!",
            "issue_title": issue.get("title", ""),
            "labels": [lb.get("name", "") for lb in issue.get("labels", [])],
            "comments": issue.get("comments", 0),
            "linked_prs": linked_prs,
            "created_days_ago": days_ago(issue.get("created_at")),
        }, indent=2)

    @mcp.tool(
        name="opencollab_generate_pr_plan",
        annotations={
            "title": "Gather issue context for AI-assisted PR planning",
            "readOnlyHint": True, "destructiveHint": False,
            "idempotentHint": True, "openWorldHint": True,
        },
    )
    async def opencollab_generate_pr_plan(params: IssueInput) -> str:
        """Gather full context about a GitHub issue so the AI can draft a PR plan.

        Fetches issue body, comments, labels, contributing guidelines, and
        repo directory structure for comprehensive PR planning.
        """
        try:
            issue_num = parse_issue_number(params.issue_number)
        except ValueError as e:
            return _bad_issue_number(params.issue_number, e)

        path = f"/repos/{params.owner}/{params.repo}"

        async def _try_contributing() -> str:
            try:
                contrib = await github_get(f"{path}/contents/CONTRIBUTING.md")
                return decode_base64_content(contrib)[:2000]
            except Exception:
                return ""

        async def _try_root_dir() -> list[dict]:
            try:
                rc = await github_get(f"{path}/contents")
                return [
                    {"name": f.get("name"), "type": f.get("type")}
                    for f in rc if isinstance(f, dict)
                ][:40]
            except Exception:
                return []

        try:
            issue, comments_raw, repo_info, contrib_text, dir_listing = await asyncio.gather(
                github_get(f"{path}/issues/{issue_num}"),
                github_get(f"{path}/issues/{issue_num}/comments", {"per_page": 20}),
                github_get(path),
                _try_contributing(),
                _try_root_dir(),
            )
        except Exception as e:
            return handle_github_error(e)

        comments = [
            {
                "author": c.get("user", {}).get("login", "unknown"),
                "body": truncate(c.get("body"), 300),
                "created_days_ago": days_ago(c.get("created_at")),
            }
            for c in comments_raw
        ]
        labels = [lb.get("name", "") for lb in issue.get("labels", [])]
        return json.dumps({
            "repo": f"{params.owner}/{params.repo}",
            "primary_language": repo_info.get("language"),
            "default_branch": repo_info.get("default_branch", "main"),
            "issue": {
                "number": issue_num,
                "title": issue.get("title", ""),
                "body": truncate(issue.get("body"), 1500),
                "labels": labels,
                "state": issue.get("state"),
                "author": issue.get("user", {}).get("login", "unknown"),
                "created_days_ago": days_ago(issue.get("created_at")),
                "comments_count": issue.get("comments", 0),
            },
            "comments": comments,
            "contributing_guidelines_preview": truncate(contrib_text, 1000) if contrib_text else "Not found",
            "repo_root_files": dir_listing,
        }, indent=2)
