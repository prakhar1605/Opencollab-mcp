"""Issue intelligence tools."""

from __future__ import annotations

import asyncio
import json
from datetime import datetime

from mcp.server.fastmcp import FastMCP

from ..constants import (
    BEGINNER_LABEL_KEYWORDS,
    COMPLEXITY_ADVANCED,
    COMPLEXITY_BEGINNER,
    COMPLEXITY_INTERMEDIATE,
    EASY_ISSUE_LABELS,
    HARD_ISSUE_LABELS,
)
from ..github_client import github_get, handle_github_error
from ..helpers import days_ago, decode_base64_content, parse_issue_number, truncate
from ..models import IssueInput, RepoInput


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
        name="opencollab_issue_complexity",
        annotations={
            "title": "Estimate complexity of a specific issue",
            "readOnlyHint": True, "destructiveHint": False,
            "idempotentHint": True, "openWorldHint": True,
        },
    )
    async def opencollab_issue_complexity(params: IssueInput) -> str:
        """Estimate the complexity of a specific GitHub issue.

        Analyzes issue body length, number of comments, labels, and
        discussion depth to produce a complexity rating (1-10).
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

        body = issue.get("body") or ""
        body_len = len(body)
        comments_count = issue.get("comments", 0)
        labels = [lb.get("name", "").lower() for lb in issue.get("labels", [])]
        label_set = set(labels)
        has_easy = bool(label_set & EASY_ISSUE_LABELS)
        has_hard = bool(label_set & HARD_ISSUE_LABELS)

        score = 0
        if body_len > 2000: score += 3
        elif body_len > 500: score += 2
        elif body_len > 100: score += 1

        if comments_count > 10: score += 3
        elif comments_count > 5: score += 2
        elif comments_count > 2: score += 1

        if has_hard: score += 3
        if has_easy: score -= 2

        checklist_items = body.count("- [ ]") + body.count("- [x]")
        if checklist_items > 5: score += 2
        elif checklist_items > 0: score += 1

        code_blocks = body.count("```") // 2
        if code_blocks > 2: score += 2
        elif code_blocks > 0: score += 1

        score = max(1, min(score, 10))
        if score <= COMPLEXITY_BEGINNER:
            level = "Beginner — good for first-time contributors"
        elif score <= COMPLEXITY_INTERMEDIATE:
            level = "Intermediate — some experience helpful"
        elif score <= COMPLEXITY_ADVANCED:
            level = "Advanced — requires deep understanding of the codebase"
        else:
            level = "Expert — significant effort and expertise needed"

        return json.dumps({
            "repo": f"{params.owner}/{params.repo}",
            "issue_number": issue_num,
            "title": issue.get("title", ""),
            "complexity_score": score,
            "complexity_level": level,
            "signals": {
                "body_length": body_len,
                "comments": comments_count,
                "checklist_items": checklist_items,
                "code_blocks_in_body": code_blocks,
                "has_beginner_label": has_easy,
                "has_hard_label": has_hard,
                "labels": labels,
            },
            "body_preview": truncate(body, 300),
        }, indent=2)

    @mcp.tool(
        name="opencollab_stale_issue_finder",
        annotations={
            "title": "Find old unclaimed issues — hidden easy wins",
            "readOnlyHint": True, "destructiveHint": False,
            "idempotentHint": True, "openWorldHint": True,
        },
    )
    async def opencollab_stale_issue_finder(params: RepoInput) -> str:
        """Find old, unclaimed issues in a repo that no one is working on
        — hidden easy wins. Returns issues older than 30 days with no
        assignees.
        """
        try:
            issues_raw = await github_get(
                f"/repos/{params.owner}/{params.repo}/issues",
                {"state": "open", "sort": "created", "direction": "asc",
                 "per_page": 50, "assignee": "none"},
            )
        except Exception as e:
            return handle_github_error(e)

        stale = []
        for issue in issues_raw:
            if issue.get("pull_request") or issue.get("assignees"):
                continue
            d = days_ago(issue.get("created_at"))
            if d is not None and d >= 30:
                stale.append({
                    "title": issue.get("title", ""),
                    "url": issue.get("html_url", ""),
                    "labels": [lb.get("name", "") for lb in issue.get("labels", [])],
                    "comments": issue.get("comments", 0),
                    "days_old": d,
                    "body_preview": truncate(issue.get("body"), 150),
                })
            if len(stale) >= 10:
                break
        return json.dumps({
            "repo": f"{params.owner}/{params.repo}",
            "stale_unclaimed_issues": stale,
            "count": len(stale),
        }, indent=2)

    @mcp.tool(
        name="opencollab_label_explorer",
        annotations={
            "title": "Explore all labels in a repo",
            "readOnlyHint": True, "destructiveHint": False,
            "idempotentHint": True, "openWorldHint": True,
        },
    )
    async def opencollab_label_explorer(params: RepoInput) -> str:
        """List all labels in a repository with their descriptions and colors.

        Helps contributors discover which labels mark beginner-friendly
        issues, bugs, features, documentation tasks, and more.
        """
        try:
            labels_raw = await github_get(
                f"/repos/{params.owner}/{params.repo}/labels",
                {"per_page": 100},
            )
        except Exception as e:
            return handle_github_error(e)

        labels = []
        beginner_labels = []
        for lb in labels_raw:
            name = lb.get("name", "")
            entry = {
                "name": name,
                "description": lb.get("description") or "",
                "color": lb.get("color", ""),
            }
            labels.append(entry)
            name_lower = name.lower()
            if name_lower in BEGINNER_LABEL_KEYWORDS or any(
                kw in name_lower for kw in BEGINNER_LABEL_KEYWORDS
            ):
                beginner_labels.append(name)
        return json.dumps({
            "repo": f"{params.owner}/{params.repo}",
            "total_labels": len(labels),
            "beginner_friendly_labels": beginner_labels,
            "all_labels": labels,
        }, indent=2)

    @mcp.tool(
        name="opencollab_recent_prs",
        annotations={
            "title": "Show recent merged PRs in a repo",
            "readOnlyHint": True, "destructiveHint": False,
            "idempotentHint": True, "openWorldHint": True,
        },
    )
    async def opencollab_recent_prs(params: RepoInput) -> str:
        """Show recently merged pull requests in a repository.

        Helps contributors see what kind of PRs get accepted, how fast
        they're merged, and who the active reviewers are.
        """
        try:
            pulls = await github_get(
                f"/repos/{params.owner}/{params.repo}/pulls",
                {"state": "closed", "sort": "updated", "direction": "desc",
                 "per_page": 30},
            )
        except Exception as e:
            return handle_github_error(e)

        merged = []
        for pr in pulls:
            if not pr.get("merged_at"):
                continue
            created = pr.get("created_at", "")
            merged_at = pr.get("merged_at", "")
            time_to_merge_days = None
            if created and merged_at:
                try:
                    c = datetime.fromisoformat(created.replace("Z", "+00:00"))
                    m = datetime.fromisoformat(merged_at.replace("Z", "+00:00"))
                    time_to_merge_days = (m - c).days
                except Exception:
                    pass
            merged.append({
                "title": pr.get("title", ""),
                "url": pr.get("html_url", ""),
                "author": pr.get("user", {}).get("login", "unknown"),
                "merged_days_ago": days_ago(merged_at),
                "days_to_merge": time_to_merge_days,
                "additions": pr.get("additions", 0),
                "deletions": pr.get("deletions", 0),
                "labels": [lb.get("name", "") for lb in pr.get("labels", [])],
            })
            if len(merged) >= 10:
                break

        merge_times = [p["days_to_merge"] for p in merged if p["days_to_merge"] is not None]
        avg_merge_time = round(sum(merge_times) / len(merge_times), 1) if merge_times else None

        return json.dumps({
            "repo": f"{params.owner}/{params.repo}",
            "recent_merged_prs": merged,
            "average_days_to_merge": avg_merge_time,
            "count": len(merged),
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
