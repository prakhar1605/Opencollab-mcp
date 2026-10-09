"""Issue intelligence tools."""

from __future__ import annotations

import asyncio
import json

from mcp.server.mcpserver import MCPServer

from ..constants import BLOCKING_ISSUE_LABELS, WARNING_ISSUE_LABELS
from ..github_client import github_get, handle_github_error
from ..helpers import days_ago, decode_base64_content, parse_issue_number, truncate
from ..models import IssueInput


def _bad_issue_number(raw: str, err: Exception) -> str:
    return json.dumps({"error": f"Invalid issue_number {raw!r}: {err}"}, indent=2)


def _normalize_label(name: str) -> str:
    return " ".join(name.lower().replace("-", " ").replace("_", " ").split())


def register(mcp: MCPServer) -> None:

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
        it or opened a PR for it. Checks assignees, linked pull requests and
        labels such as `wontfix` or `needs-triage`.
        """
        try:
            issue_num = parse_issue_number(params.issue_number)
        except ValueError as e:
            return _bad_issue_number(params.issue_number, e)

        path = f"/repos/{params.owner}/{params.repo}"
        try:
            # Availability is exactly the thing that changes between calls —
            # someone gets assigned, a PR gets opened — so a cached copy up to
            # five minutes old would report an issue as free after it was taken.
            issue = await github_get(f"{path}/issues/{issue_num}", use_cache=False)
        except Exception as e:
            return handle_github_error(e)

        # The issues endpoint also serves pull requests, which are not
        # something to pick up and work on.
        if issue.get("pull_request"):
            return json.dumps({
                "available": False,
                "reason": f"#{issue_num} is a pull request, not an issue",
                "issue_title": issue.get("title", ""),
            }, indent=2)

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

        if issue.get("locked"):
            payload = {
                "available": False,
                "reason": "Issue is locked — only maintainers can comment",
                "issue_title": issue.get("title", ""),
            }
            if issue.get("active_lock_reason"):
                payload["active_lock_reason"] = issue["active_lock_reason"]
            return json.dumps(payload, indent=2)

        linked_prs: list[dict] = []
        linked_prs_checked = True
        try:
            timeline = await github_get(
                f"{path}/issues/{issue_num}/timeline",
                {"per_page": 100},
                use_cache=False,
            )
            for event in timeline:
                if event.get("event") == "cross-referenced":
                    source = event.get("source", {})
                    issue_obj = source.get("issue", {}) if isinstance(source, dict) else {}
                    pr_info = issue_obj.get("pull_request") if isinstance(issue_obj, dict) else None
                    if pr_info is not None:
                        merged = bool(pr_info.get("merged_at")) if isinstance(pr_info, dict) else False
                        linked_prs.append({
                            "pr_number": issue_obj.get("number"),
                            "title": issue_obj.get("title", ""),
                            "state": issue_obj.get("state", "unknown"),
                            "author": (
                                issue_obj.get("user", {}).get("login", "unknown")
                                if isinstance(issue_obj.get("user"), dict)
                                else "unknown"
                            ),
                            "merged": merged,
                        })
        except Exception:
            # Without the timeline we can't tell whether a PR is already open,
            # so say so instead of reporting "no open PRs".
            linked_prs_checked = False

        if any(pr.get("state") == "open" for pr in linked_prs):
            return json.dumps({
                "available": False,
                "reason": "An open PR already exists for this issue",
                "linked_prs": linked_prs,
                "linked_prs_checked": linked_prs_checked,
                "issue_title": issue.get("title", ""),
            }, indent=2)

        if any(pr.get("merged") for pr in linked_prs):
            return json.dumps({
                "available": False,
                "reason": "A linked PR was already merged — the issue may already be fixed",
                "linked_prs": linked_prs,
                "linked_prs_checked": linked_prs_checked,
                "issue_title": issue.get("title", ""),
            }, indent=2)

        labels = [lb.get("name", "") for lb in issue.get("labels", [])]
        blocking = [lb for lb in labels if _normalize_label(lb) in BLOCKING_ISSUE_LABELS]
        if blocking:
            return json.dumps({
                "available": False,
                "reason": f"Labelled {blocking[0]!r} — maintainers don't plan to take a fix",
                "issue_title": issue.get("title", ""),
                "labels": labels,
            }, indent=2)
        warning_labels = [lb for lb in labels if _normalize_label(lb) in WARNING_ISSUE_LABELS]

        if warning_labels:
            reason = f"Labelled {warning_labels[0]!r} — ask a maintainer before starting"
            if not linked_prs_checked:
                reason += " (linked PRs could not be checked either)"
        elif linked_prs_checked:
            reason = "No assignees, no open PRs — go for it!"
        else:
            reason = (
                "No assignees, but linked PRs could not be checked "
                "(timeline request failed) — look for an open PR before starting"
            )
        payload = {
            "available": True,
            "reason": reason,
            "issue_title": issue.get("title", ""),
            "labels": labels,
            "comments": issue.get("comments", 0),
            "linked_prs": linked_prs,
            "linked_prs_checked": linked_prs_checked,
            "created_days_ago": days_ago(issue.get("created_at")),
        }
        if warning_labels:
            payload["warning_labels"] = warning_labels
        return json.dumps(payload, indent=2)

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
            locations = [
                "CONTRIBUTING.md",
                ".github/CONTRIBUTING.md",
                "docs/CONTRIBUTING.md",
            ]
            for location in locations:
                try:
                    contrib = await github_get(f"{path}/contents/{location}")
                    return decode_base64_content(contrib)[:2000]
                except Exception:
                    continue
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

        # The issues endpoint also serves pull requests; reject them, as
        # opencollab_check_issue_availability does.
        if issue.get("pull_request"):
            return json.dumps(
                {"error": f"#{issue_num} is a pull request, not an issue"}, indent=2
            )

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
