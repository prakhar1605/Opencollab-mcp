"""Issue intelligence tools."""

from __future__ import annotations

import asyncio
import json
from typing import Any

import httpx
from mcp.server.mcpserver import MCPServer

from ..constants import (
    ASSIGNED_ISSUE_STALE_DAYS,
    BLOCKING_ISSUE_LABELS,
    LINKED_PRS_GRAPHQL_LIMIT,
    PR_PLAN_ISSUE_BODY_LIMIT,
    TIMELINE_MAX_PAGES,
    WARNING_ISSUE_LABELS,
)
from ..github_client import (
    GitHubGraphQLError,
    github_get,
    github_get_all,
    github_graphql,
    handle_github_error,
    has_github_token,
)
from ..helpers import (
    days_ago,
    decode_base64_content,
    extract_issue_repo,
    parse_issue_number,
    pr_closes_issue,
    truncate,
)
from ..models import IssueInput

_CLOSING_PRS_QUERY = f"""
query($owner: String!, $repo: String!, $number: Int!) {{
  repository(owner: $owner, name: $repo) {{
    issue(number: $number) {{
      closedByPullRequestsReferences(first: {LINKED_PRS_GRAPHQL_LIMIT}, includeClosedPrs: true) {{
        nodes {{
          number
          title
          state
          merged
          url
          author {{ login }}
          repository {{ nameWithOwner }}
        }}
      }}
    }}
  }}
}}
"""


def _extract_graphql_closing_prs(
    data: dict[str, Any], default_repo_key: str
) -> list[tuple[tuple[str, int | None], dict[str, Any]]]:
    """Parse `closedByPullRequestsReferences.nodes` into normalized PR dicts.

    Raises `ValueError` if the GraphQL payload lacks the expected repository or
    issue structure so callers cleanly fall back to REST.
    """
    repo_obj = data.get("repository")
    if not isinstance(repo_obj, dict):
        raise ValueError("Missing repository in GraphQL response")
    issue_obj = repo_obj.get("issue")
    if not isinstance(issue_obj, dict):
        raise ValueError("Missing issue in GraphQL response")
    refs = issue_obj.get("closedByPullRequestsReferences")
    if not isinstance(refs, dict) or not isinstance(refs.get("nodes"), list):
        raise ValueError("Missing closedByPullRequestsReferences nodes")

    results: list[tuple[tuple[str, int | None], dict[str, Any]]] = []
    seen: set[tuple[str, int | None]] = set()
    for node in refs["nodes"]:
        if not isinstance(node, dict):
            continue
        pr_number = node.get("number")
        repo_info = node.get("repository")
        repo_name = (
            repo_info.get("nameWithOwner", "")
            if isinstance(repo_info, dict)
            else ""
        )
        repo_key = (repo_name or default_repo_key).lower()
        dedup_key = (repo_key, pr_number)
        if dedup_key in seen:
            continue
        seen.add(dedup_key)

        raw_state = str(node.get("state") or "unknown").lower()
        merged = bool(node.get("merged")) or raw_state == "merged"
        state = (
            "open"
            if raw_state == "open"
            else ("closed" if raw_state in ("closed", "merged") else raw_state)
        )
        author_obj = node.get("author")
        author = (
            author_obj.get("login") or "unknown"
            if isinstance(author_obj, dict)
            else "unknown"
        )
        results.append(
            (
                dedup_key,
                {
                    "pr_number": pr_number,
                    "title": node.get("title", ""),
                    "state": state,
                    "author": author,
                    "merged": merged,
                },
            )
        )
    return results


def _extract_timeline_prs(
    timeline: list[Any], *, owner: str, repo: str, issue_num: int
) -> list[tuple[tuple[str, int | None], bool, dict[str, Any]]]:
    """Extract `(dedup_key, closes_issue, pr_dict)` entries from REST timeline events.

    GitHub's REST timeline schema (`#/components/schemas/timeline-cross-referenced-event`)
    embeds the full `#/components/schemas/issue` object at `source.issue`, which
    already includes `title`, `body`, `repository_url`, `html_url`, `user`, and
    `pull_request` — so no extra per-PR HTTP request is needed.
    """
    default_repo_key = f"{owner}/{repo}".lower()
    entries: dict[tuple[str, int | None], tuple[bool, dict[str, Any]]] = {}

    for event in timeline:
        if not isinstance(event, dict) or event.get("event") != "cross-referenced":
            continue
        source = event.get("source")
        issue_obj = source.get("issue") if isinstance(source, dict) else None
        if not isinstance(issue_obj, dict):
            continue
        pr_info = issue_obj.get("pull_request")
        if pr_info is None:
            continue

        pr_repo = extract_issue_repo(issue_obj)
        repo_key = (
            f"{pr_repo[0]}/{pr_repo[1]}".lower() if pr_repo else default_repo_key
        )
        pr_number = issue_obj.get("number")
        dedup_key = (repo_key, pr_number)

        merged = bool(pr_info.get("merged_at")) if isinstance(pr_info, dict) else False
        closes = pr_closes_issue(
            issue_obj.get("title"),
            issue_obj.get("body"),
            owner=owner,
            repo=repo,
            issue_number=issue_num,
            pr_repo=pr_repo,
        )
        pr_entry = {
            "pr_number": pr_number,
            "title": issue_obj.get("title", ""),
            "state": issue_obj.get("state", "unknown"),
            "author": (
                issue_obj.get("user", {}).get("login", "unknown")
                if isinstance(issue_obj.get("user"), dict)
                else "unknown"
            ),
            "merged": merged,
        }
        if dedup_key in entries:
            prev_closes, _ = entries[dedup_key]
            entries[dedup_key] = (prev_closes or closes, pr_entry)
        else:
            entries[dedup_key] = (closes, pr_entry)

    return [(key, closes, pr_entry) for key, (closes, pr_entry) in entries.items()]


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
            state_reason = issue.get("state_reason")
            reason = f"Issue is {issue.get('state', 'unknown')}"
            if issue.get("state") == "closed":
                reason = {
                    "completed": "Issue is closed — already fixed",
                    "not_planned": "Issue is closed as not planned — maintainers don't intend to change this",
                    "duplicate": "Issue is closed as a duplicate",
                }.get(state_reason, reason)
            return json.dumps({
                "available": False,
                "reason": reason,
                "state_reason": state_reason,
                "issue_title": issue.get("title", ""),
            }, indent=2)

        assignees = [a.get("login", "") for a in issue.get("assignees", [])]
        if assignees:
            last_activity_days = days_ago(issue.get("updated_at"))
            reason = f"Already assigned to: {', '.join(assignees)}"

            if (
                last_activity_days is not None
                and last_activity_days >= ASSIGNED_ISSUE_STALE_DAYS
            ):
                reason += (
                    f", but no activity for {last_activity_days} days — "
                    "consider politely asking whether it is still being worked on"
        )

            return json.dumps({
                "available": False,
                "reason": reason,
                "issue_title": issue.get("title", ""),
                "last_activity_days_ago": last_activity_days,
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

        linked_prs: list[dict[str, Any]] = []
        mentioned_in_prs: list[dict[str, Any]] = []
        linked_prs_checked = True
        linked_prs_source = "rest"
        timeline_truncated = False
        default_repo_key = f"{params.owner}/{params.repo}".lower()

        if has_github_token():
            graphql_res, timeline_res = await asyncio.gather(
                github_graphql(
                    _CLOSING_PRS_QUERY,
                    {
                        "owner": params.owner,
                        "repo": params.repo,
                        "number": issue_num,
                    },
                ),
                github_get_all(
                    f"{path}/issues/{issue_num}/timeline",
                    {"per_page": 100},
                    max_pages=TIMELINE_MAX_PAGES,
                    use_cache=False,
                ),
                return_exceptions=True,
            )

            graphql_prs: list[tuple[tuple[str, int | None], dict[str, Any]]] | None = None
            if not isinstance(graphql_res, BaseException):
                try:
                    graphql_prs = _extract_graphql_closing_prs(
                        graphql_res, default_repo_key
                    )
                except ValueError:
                    graphql_prs = None
            elif isinstance(graphql_res, GitHubGraphQLError | httpx.HTTPError):
                # Log clean diagnostic via handle_github_error before falling back.
                handle_github_error(graphql_res)

            timeline_events: list[Any] | None = None
            if isinstance(timeline_res, tuple):
                timeline_events, timeline_truncated = timeline_res

            if graphql_prs is not None:
                linked_prs_source = "graphql"
                linked_keys = {key for key, _ in graphql_prs}
                linked_prs = [pr for _, pr in graphql_prs]
                if timeline_events is not None:
                    for key, _, pr in _extract_timeline_prs(
                        timeline_events,
                        owner=params.owner,
                        repo=params.repo,
                        issue_num=issue_num,
                    ):
                        if key not in linked_keys:
                            mentioned_in_prs.append(pr)
            elif timeline_events is not None:
                for _, closes, pr in _extract_timeline_prs(
                    timeline_events,
                    owner=params.owner,
                    repo=params.repo,
                    issue_num=issue_num,
                ):
                    if closes:
                        linked_prs.append(pr)
                    else:
                        mentioned_in_prs.append(pr)
            else:
                linked_prs_checked = False
        else:
            try:
                timeline, timeline_truncated = await github_get_all(
                    f"{path}/issues/{issue_num}/timeline",
                    {"per_page": 100},
                    max_pages=TIMELINE_MAX_PAGES,
                    use_cache=False,
                )
                for _, closes, pr in _extract_timeline_prs(
                    timeline,
                    owner=params.owner,
                    repo=params.repo,
                    issue_num=issue_num,
                ):
                    if closes:
                        linked_prs.append(pr)
                    else:
                        mentioned_in_prs.append(pr)
            except Exception:
                # Without the timeline we can't tell whether a PR is already open,
                # so say so instead of reporting "no open PRs".
                linked_prs_checked = False

        if any(pr.get("state") == "open" for pr in linked_prs):
            payload = {
                "available": False,
                "reason": "An open PR already exists for this issue",
                "linked_prs": linked_prs,
                "mentioned_in_prs": mentioned_in_prs,
                "linked_prs_checked": linked_prs_checked,
                "linked_prs_source": linked_prs_source,
                "issue_title": issue.get("title", ""),
            }
            if timeline_truncated:
                payload["timeline_truncated"] = True
            return json.dumps(payload, indent=2)

        if any(pr.get("merged") for pr in linked_prs):
            payload = {
                "available": False,
                "reason": "A linked PR was already merged — the issue may already be fixed",
                "linked_prs": linked_prs,
                "mentioned_in_prs": mentioned_in_prs,
                "linked_prs_checked": linked_prs_checked,
                "linked_prs_source": linked_prs_source,
                "issue_title": issue.get("title", ""),
            }
            if timeline_truncated:
                payload["timeline_truncated"] = True
            return json.dumps(payload, indent=2)

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
            if mentioned_in_prs:
                reason += " (a PR also mentions this issue — take a look before starting)"
            if not linked_prs_checked:
                reason += " (linked PRs could not be checked either)"
            elif timeline_truncated:
                reason += " (timeline was truncated — look for a recent open PR before starting)"
        elif mentioned_in_prs:
            reason = (
                "No assignees or closing PRs, though a PR mentions this issue — "
                "take a look before starting"
            )
            if timeline_truncated:
                reason += " (timeline was also truncated — check for recent PRs)"
        elif not linked_prs_checked:
            reason = (
                "No assignees, but linked PRs could not be checked "
                "(timeline request failed) — look for an open PR before starting"
            )
        elif timeline_truncated:
            reason = (
                f"No assignees or closing PRs found in the first "
                f"{TIMELINE_MAX_PAGES * 100} timeline events (timeline truncated) "
                f"— look for a recent open PR before starting"
            )
        else:
            reason = "No assignees, no open PRs — go for it!"
        payload = {
            "available": True,
            "reason": reason,
            "issue_title": issue.get("title", ""),
            "labels": labels,
            "comments": issue.get("comments", 0),
            "linked_prs": linked_prs,
            "mentioned_in_prs": mentioned_in_prs,
            "linked_prs_checked": linked_prs_checked,
            "linked_prs_source": linked_prs_source,
            "created_days_ago": days_ago(issue.get("created_at")),
        }
        if timeline_truncated:
            payload["timeline_truncated"] = True
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

        Fetches issue body, comments, labels, contributing guidelines, PR template, and
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

        async def _try_pr_template() -> str:
            locations = [
                ".github/PULL_REQUEST_TEMPLATE.md",
                ".github/pull_request_template.md",
                "PULL_REQUEST_TEMPLATE.md",
                "docs/PULL_REQUEST_TEMPLATE.md",
            ]
            for location in locations:
                try:
                    template = await github_get(f"{path}/contents/{location}")
                    text = decode_base64_content(template)
                    if text:
                        return text
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
            issue, comments_raw, repo_info, contrib_text, dir_listing, template_text = await asyncio.gather(
                github_get(f"{path}/issues/{issue_num}"),
                github_get(f"{path}/issues/{issue_num}/comments", {"per_page": 20}),
                github_get(path),
                _try_contributing(),
                _try_root_dir(),
                _try_pr_template(),
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
            if c.get("user", {}).get("type") != "Bot"
            and not c.get("user", {}).get("login", "").endswith("[bot]")
        ]
        labels = [lb.get("name", "") for lb in issue.get("labels", [])]
        body = issue.get("body") or ""
        return json.dumps({
            "repo": f"{params.owner}/{params.repo}",
            "primary_language": repo_info.get("language"),
            "default_branch": repo_info.get("default_branch", "main"),
            "issue": {
                "number": issue_num,
                "title": issue.get("title", ""),
                "body": truncate(body, PR_PLAN_ISSUE_BODY_LIMIT),
                "body_truncated": len(body) > PR_PLAN_ISSUE_BODY_LIMIT,
                "body_length": len(body),
                "labels": labels,
                "state": issue.get("state"),
                "author": issue.get("user", {}).get("login", "unknown"),
                "created_days_ago": days_ago(issue.get("created_at")),
                "comments_count": issue.get("comments", 0),
            },
            "comments": comments,
            "bot_comments_skipped": len(comments_raw) - len(comments),
            "contributing_guidelines_preview": truncate(contrib_text, 1000) if contrib_text else "Not found",
            "pr_template_preview": truncate(template_text, 1000) if template_text else None,
            "repo_root_files": dir_listing,
        }, indent=2)
