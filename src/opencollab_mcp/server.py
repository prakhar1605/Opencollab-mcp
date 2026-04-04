"""OpenCollab MCP Server — AI-powered open source contribution matchmaker.

Helps developers find perfect open-source contribution opportunities
matched to their skills by analyzing GitHub profiles, searching issues,
and scoring repository health.

Supports both STDIO (local) and SSE (remote/deployed) transports.
Set TRANSPORT=sse and optionally PORT=8000 for remote deployment.
"""

import json
import os
from datetime import datetime, timezone, timedelta
from typing import Optional

from mcp.server.fastmcp import FastMCP
from pydantic import BaseModel, Field, ConfigDict

from .github_client import github_get, github_search, handle_github_error

mcp = FastMCP("opencollab_mcp")

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _days_ago(iso_str: str | None) -> int | None:
    if not iso_str:
        return None
    try:
        dt = datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
        return (datetime.now(timezone.utc) - dt).days
    except Exception:
        return None


def _truncate(text: str | None, length: int = 120) -> str:
    if not text:
        return ""
    return text[:length] + ("…" if len(text) > length else "")


def _recent_date_str(days_back: int = 90) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=days_back)).strftime("%Y-%m-%d")


# ---------------------------------------------------------------------------
# Tool 1 — analyze_profile
# ---------------------------------------------------------------------------

class AnalyzeProfileInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    username: str = Field(..., description="GitHub username to analyze", min_length=1, max_length=39)


@mcp.tool(name="opencollab_analyze_profile", annotations={"title": "Analyze developer GitHub profile", "readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": True})
async def opencollab_analyze_profile(params: AnalyzeProfileInput) -> str:
    """Analyze a GitHub user's profile to extract skills, languages, contribution patterns, and interests."""
    try:
        user = await github_get(f"/users/{params.username}")
        repos_raw = await github_get(f"/users/{params.username}/repos", {"per_page": 100, "sort": "pushed", "type": "owner"})
        events_raw = await github_get(f"/users/{params.username}/events/public", {"per_page": 50})
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
    languages = [{"name": n, "percentage": round(b / total * 100, 1)} for n, b in top_langs]

    event_types: dict[str, int] = {}
    for ev in events_raw:
        etype = ev.get("type", "Unknown")
        event_types[etype] = event_types.get(etype, 0) + 1

    notable = sorted(repos_raw, key=lambda r: r.get("stargazers_count", 0), reverse=True)[:5]
    highlights = [{"name": r.get("full_name", r.get("name", "")), "stars": r.get("stargazers_count", 0), "language": r.get("language"), "description": _truncate(r.get("description"), 100), "last_pushed_days_ago": _days_ago(r.get("pushed_at"))} for r in notable]

    profile = {
        "username": params.username, "name": user.get("name"), "bio": user.get("bio"),
        "public_repos": user.get("public_repos", 0), "followers": user.get("followers", 0),
        "following": user.get("following", 0), "account_age_days": _days_ago(user.get("created_at")),
        "top_languages": languages, "topics_of_interest": sorted(topics_set)[:20],
        "recent_activity_summary": event_types, "notable_repos": highlights,
    }
    return json.dumps(profile, indent=2)


# ---------------------------------------------------------------------------
# Tool 2 — find_issues (direct params — no Pydantic model)
# ---------------------------------------------------------------------------

@mcp.tool(name="opencollab_find_issues", annotations={"title": "Find good first issues matched to skills", "readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": True})
async def opencollab_find_issues(language: str, topic: str = "", max_results: int = 15) -> str:
    """Find beginner-friendly open-source issues matched to a developer's skills.

    Args:
        language: Programming language to filter by (e.g. 'Python', 'TypeScript', 'Rust')
        topic: Optional topic to narrow search (e.g. 'machine-learning', 'web', 'cli')
        max_results: Number of issues to return (1-30, default 15)
    """
    max_results = max(1, min(max_results, 30))
    since = _recent_date_str(90)
    query_parts = [f"language:{language}", 'label:"good first issue"', "state:open", f"created:>{since}", "is:public"]
    if topic:
        query_parts.insert(0, topic)
    try:
        result = await github_search("issues", " ".join(query_parts), {"sort": "created", "order": "desc", "per_page": max_results})
    except Exception as e:
        return handle_github_error(e)

    issues = []
    for item in result.get("items", []):
        repo_url = item.get("repository_url", "")
        repo_full_name = "/".join(repo_url.split("/")[-2:]) if repo_url else ""
        labels = [lb.get("name", "") for lb in item.get("labels", [])]
        issues.append({"title": item.get("title", ""), "url": item.get("html_url", ""), "repo": repo_full_name, "labels": labels, "comments": item.get("comments", 0), "created_days_ago": _days_ago(item.get("created_at")), "body_preview": _truncate(item.get("body"), 200)})
    return json.dumps({"total_found": result.get("total_count", 0), "issues": issues}, indent=2)


# ---------------------------------------------------------------------------
# Tool 3 — repo_health
# ---------------------------------------------------------------------------

class RepoHealthInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    owner: str = Field(..., description="Repository owner (e.g. 'facebook')", min_length=1)
    repo: str = Field(..., description="Repository name (e.g. 'react')", min_length=1)

@mcp.tool(name="opencollab_repo_health", annotations={"title": "Score repository contributor-friendliness", "readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": True})
async def opencollab_repo_health(params: RepoHealthInput) -> str:
    """Score a repository's health and contributor-friendliness (0-100)."""
    path = f"/repos/{params.owner}/{params.repo}"
    try:
        repo = await github_get(path)
        pulls = await github_get(f"{path}/pulls", {"state": "closed", "per_page": 30, "sort": "updated"})
        community = await github_get(f"{path}/community/profile")
    except Exception as e:
        return handle_github_error(e)

    score = 0
    details: dict[str, object] = {}

    last_push_days = _days_ago(repo.get("pushed_at"))
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
    details["recent_closed_prs"] = total_closed
    open_issues = repo.get("open_issues_count", 0)
    if 5 <= open_issues <= 500: score += 10
    elif open_issues > 0: score += 5
    details["open_issues"] = open_issues
    files = community.get("files", {})
    community_items = {"contributing": files.get("contributing") is not None, "code_of_conduct": files.get("code_of_conduct") is not None, "license": files.get("license") is not None, "readme": files.get("readme") is not None, "issue_template": files.get("issue_template") is not None, "pull_request_template": files.get("pull_request_template") is not None}
    score += min(sum(community_items.values()) * 4, 20)
    details["community_files"] = community_items
    if repo.get("description"): score += 2
    if repo.get("topics"): score += 3
    details["has_description"] = bool(repo.get("description"))
    details["topics"] = repo.get("topics", [])
    forks = repo.get("forks_count", 0)
    if forks >= 100: score += 10
    elif forks >= 20: score += 6
    elif forks >= 5: score += 3
    details["forks"] = forks
    score = min(score, 100)
    if score >= 75: verdict = "Excellent — very contributor-friendly"
    elif score >= 50: verdict = "Good — solid project to contribute to"
    elif score >= 30: verdict = "Fair — some friction expected"
    else: verdict = "Low — may be abandoned or hard to contribute to"
    return json.dumps({"repo": f"{params.owner}/{params.repo}", "health_score": score, "verdict": verdict, "details": details}, indent=2)


# ---------------------------------------------------------------------------
# Tool 4 — contribution_readiness
# ---------------------------------------------------------------------------

class ContribReadinessInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    owner: str = Field(..., description="Repository owner", min_length=1)
    repo: str = Field(..., description="Repository name", min_length=1)

@mcp.tool(name="opencollab_contribution_readiness", annotations={"title": "Check repo setup difficulty for contributors", "readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": True})
async def opencollab_contribution_readiness(params: ContribReadinessInput) -> str:
    """Check how easy it is to set up and contribute to a repository."""
    path = f"/repos/{params.owner}/{params.repo}"
    try:
        repo = await github_get(path)
        contents = await github_get(f"{path}/contents")
    except Exception as e:
        return handle_github_error(e)

    filenames = [f.get("name", "").lower() for f in contents if isinstance(f, dict)]
    checks = {
        "has_readme": any(n.startswith("readme") for n in filenames),
        "has_contributing": any("contributing" in n for n in filenames),
        "has_license": any(n.startswith("license") or n.startswith("licence") for n in filenames),
        "has_dockerfile": "dockerfile" in filenames or "docker-compose.yml" in filenames,
        "has_ci": any(n in filenames for n in [".github", ".circleci", ".travis.yml", "jenkinsfile", ".gitlab-ci.yml"]),
        "has_tests_dir": any(n in ("tests", "test", "spec", "__tests__") for n in filenames),
        "has_package_config": any(n in filenames for n in ["package.json", "pyproject.toml", "setup.py", "setup.cfg", "cargo.toml", "go.mod", "gemfile", "pom.xml", "build.gradle"]),
        "has_code_of_conduct": any("code_of_conduct" in n for n in filenames),
        "has_changelog": any(n.startswith("changelog") or n.startswith("changes") for n in filenames),
    }
    passed = sum(checks.values())
    total = len(checks)
    if passed >= 8: difficulty = "Easy — well-documented, CI ready, contributor-friendly"
    elif passed >= 5: difficulty = "Moderate — some docs present, may need setup effort"
    elif passed >= 3: difficulty = "Hard — minimal docs, expect to figure things out yourself"
    else: difficulty = "Very hard — barely any contributor infrastructure"
    try:
        github_dir = await github_get(f"{path}/contents/.github")
        gh_files = [f.get("name", "").lower() for f in github_dir if isinstance(f, dict)]
        checks["has_issue_templates"] = any("issue" in n for n in gh_files)
        checks["has_pr_template"] = any("pull" in n for n in gh_files)
    except Exception:
        checks["has_issue_templates"] = False
        checks["has_pr_template"] = False
    return json.dumps({"repo": f"{params.owner}/{params.repo}", "difficulty": difficulty, "score": f"{passed}/{total}", "checks": checks, "primary_language": repo.get("language"), "default_branch": repo.get("default_branch", "main")}, indent=2)


# ---------------------------------------------------------------------------
# Tool 5 — generate_pr_plan (direct params — no Pydantic model)
# ---------------------------------------------------------------------------

@mcp.tool(name="opencollab_generate_pr_plan", annotations={"title": "Gather issue context for AI-assisted PR planning", "readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": True})
async def opencollab_generate_pr_plan(owner: str, repo: str, issue_number: int) -> str:
    """Gather full context about a GitHub issue so the AI can draft a PR plan.

    Args:
        owner: Repository owner (e.g. 'langchain-ai')
        repo: Repository name (e.g. 'langchain')
        issue_number: Issue number to plan a PR for (e.g. 123)
    """
    path = f"/repos/{owner}/{repo}"
    try:
        issue = await github_get(f"{path}/issues/{issue_number}")
        comments_raw = await github_get(f"{path}/issues/{issue_number}/comments", {"per_page": 20})
        repo_info = await github_get(path)
    except Exception as e:
        return handle_github_error(e)
    contributing_text = ""
    try:
        contrib = await github_get(f"{path}/contents/CONTRIBUTING.md")
        if contrib.get("encoding") == "base64":
            import base64
            contributing_text = base64.b64decode(contrib.get("content", "")).decode("utf-8", errors="replace")[:2000]
    except Exception:
        pass
    dir_listing = []
    try:
        root_contents = await github_get(f"{path}/contents")
        dir_listing = [{"name": f.get("name"), "type": f.get("type")} for f in root_contents if isinstance(f, dict)][:40]
    except Exception:
        pass
    comments = [{"author": c.get("user", {}).get("login", "unknown"), "body": _truncate(c.get("body"), 300), "created_days_ago": _days_ago(c.get("created_at"))} for c in comments_raw]
    labels = [lb.get("name", "") for lb in issue.get("labels", [])]
    context = {"repo": f"{owner}/{repo}", "primary_language": repo_info.get("language"), "default_branch": repo_info.get("default_branch", "main"),
        "issue": {"number": issue_number, "title": issue.get("title", ""), "body": _truncate(issue.get("body"), 1500), "labels": labels, "state": issue.get("state"), "author": issue.get("user", {}).get("login", "unknown"), "created_days_ago": _days_ago(issue.get("created_at")), "comments_count": issue.get("comments", 0)},
        "comments": comments, "contributing_guidelines_preview": _truncate(contributing_text, 1000) if contributing_text else "Not found", "repo_root_files": dir_listing}
    return json.dumps(context, indent=2)


# ---------------------------------------------------------------------------
# Tool 6 — trending_repos
# ---------------------------------------------------------------------------

class TrendingReposInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    language: str = Field(default="", description="Filter by programming language (e.g. 'Python', 'Go'). Leave empty for all.")
    max_results: int = Field(default=10, description="Number of repos to return (1-25)", ge=1, le=25)

@mcp.tool(name="opencollab_trending_repos", annotations={"title": "Find trending repos seeking contributors", "readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": True})
async def opencollab_trending_repos(params: TrendingReposInput) -> str:
    """Find trending repositories that are actively seeking contributors."""
    since = _recent_date_str(60)
    query_parts = [f"created:>{since}", "good-first-issues:>0", "is:public", "archived:false"]
    if params.language:
        query_parts.append(f"language:{params.language}")
    try:
        result = await github_search("repositories", " ".join(query_parts), {"sort": "stars", "order": "desc", "per_page": params.max_results})
    except Exception as e:
        return handle_github_error(e)
    repos = []
    for r in result.get("items", []):
        repos.append({"name": r.get("full_name", ""), "description": _truncate(r.get("description"), 150), "stars": r.get("stargazers_count", 0), "forks": r.get("forks_count", 0), "language": r.get("language"), "open_issues": r.get("open_issues_count", 0), "topics": r.get("topics", [])[:8], "url": r.get("html_url", ""), "created_days_ago": _days_ago(r.get("created_at")), "last_push_days_ago": _days_ago(r.get("pushed_at"))})
    return json.dumps({"total_found": result.get("total_count", 0), "repos": repos}, indent=2)


# ---------------------------------------------------------------------------
# Tool 7 — impact_estimator
# ---------------------------------------------------------------------------

class ImpactEstimatorInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    owner: str = Field(..., description="Repository owner", min_length=1)
    repo: str = Field(..., description="Repository name", min_length=1)

@mcp.tool(name="opencollab_impact_estimator", annotations={"title": "Estimate contribution impact for a repo", "readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": True})
async def opencollab_impact_estimator(params: ImpactEstimatorInput) -> str:
    """Estimate the impact of contributing to a specific repository."""
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
    if stars >= 50000: tier, reach = "MASSIVE", "millions of developers"
    elif stars >= 10000: tier, reach = "HIGH", "tens of thousands of developers"
    elif stars >= 1000: tier, reach = "MEDIUM", "thousands of developers"
    elif stars >= 100: tier, reach = "MODERATE", "hundreds of developers"
    else: tier, reach = "LOW", "a growing community"
    repo_name = f"{params.owner}/{params.repo}"
    resume_line = f"Contributed to {repo_name} ({stars:,}+ stars), a widely-used project reaching {reach}" if stars >= 1000 else f"Open-source contributor to {repo_name} — {description[:80]}"
    vis = 0
    if stars >= 100: vis += min(stars // 500, 40)
    if forks >= 50: vis += min(forks // 100, 20)
    if watchers >= 50: vis += min(watchers // 50, 20)
    if open_issues >= 10: vis += 10
    if repo.get("topics"): vis += 10
    vis = min(vis, 100)
    return json.dumps({"repo": repo_name, "impact_tier": tier, "estimated_reach": reach, "stars": stars, "forks": forks, "watchers": watchers, "open_issues": open_issues, "visibility_score": vis, "suggested_resume_line": resume_line, "topics": repo.get("topics", [])}, indent=2)


# ===========================================================================
# NEW TOOLS 8-12
# ===========================================================================

# ---------------------------------------------------------------------------
# Tool 8 — match_me (all-in-one: profile + matched issues)
# ---------------------------------------------------------------------------

@mcp.tool(name="opencollab_match_me", annotations={"title": "Analyze profile and find matched issues in one step", "readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": True})
async def opencollab_match_me(username: str, max_issues: int = 10) -> str:
    """All-in-one: analyze a GitHub profile and instantly find issues matched to that user's top skills.

    Args:
        username: GitHub username to analyze and match
        max_issues: Number of matched issues to return (1-20, default 10)
    """
    max_issues = max(1, min(max_issues, 20))
    try:
        user = await github_get(f"/users/{username}")
        repos_raw = await github_get(f"/users/{username}/repos", {"per_page": 100, "sort": "pushed", "type": "owner"})
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
    languages = [{"name": n, "percentage": round(b / total * 100, 1)} for n, b in top_langs]

    # Search issues for the user's top language
    primary_lang = top_langs[0][0] if top_langs else "Python"
    since = _recent_date_str(90)
    query = f"language:{primary_lang} label:\"good first issue\" state:open created:>{since} is:public"
    try:
        result = await github_search("issues", query, {"sort": "created", "order": "desc", "per_page": max_issues})
    except Exception as e:
        return handle_github_error(e)

    issues = []
    for item in result.get("items", []):
        repo_url = item.get("repository_url", "")
        repo_full_name = "/".join(repo_url.split("/")[-2:]) if repo_url else ""
        issues.append({"title": item.get("title", ""), "url": item.get("html_url", ""), "repo": repo_full_name, "labels": [lb.get("name", "") for lb in item.get("labels", [])], "comments": item.get("comments", 0), "body_preview": _truncate(item.get("body"), 150)})

    return json.dumps({"username": username, "name": user.get("name"), "top_languages": languages, "topics": sorted(topics_set)[:10], "matched_language": primary_lang, "matched_issues": issues}, indent=2)


# ---------------------------------------------------------------------------
# Tool 9 — compare_repos
# ---------------------------------------------------------------------------

@mcp.tool(name="opencollab_compare_repos", annotations={"title": "Compare two repos for contributor-friendliness", "readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": True})
async def opencollab_compare_repos(owner_a: str, repo_a: str, owner_b: str, repo_b: str) -> str:
    """Compare two GitHub repositories side-by-side for contributor-friendliness.

    Args:
        owner_a: First repo owner (e.g. 'langchain-ai')
        repo_a: First repo name (e.g. 'langchain')
        owner_b: Second repo owner (e.g. 'run-llama')
        repo_b: Second repo name (e.g. 'llama_index')
    """
    async def _score_repo(owner: str, repo: str) -> dict:
        path = f"/repos/{owner}/{repo}"
        try:
            r = await github_get(path)
            pulls = await github_get(f"{path}/pulls", {"state": "closed", "per_page": 20, "sort": "updated"})
        except Exception as e:
            return {"repo": f"{owner}/{repo}", "error": handle_github_error(e)}
        merged = sum(1 for p in pulls if p.get("merged_at"))
        merge_rate = round(merged / max(len(pulls), 1) * 100, 1)
        return {
            "repo": f"{owner}/{repo}", "stars": r.get("stargazers_count", 0), "forks": r.get("forks_count", 0),
            "open_issues": r.get("open_issues_count", 0), "language": r.get("language"),
            "last_push_days_ago": _days_ago(r.get("pushed_at")), "pr_merge_rate_pct": merge_rate,
            "has_contributing": bool(r.get("description")), "topics": r.get("topics", [])[:6],
        }
    a = await _score_repo(owner_a, repo_a)
    b = await _score_repo(owner_b, repo_b)
    winner = "tie"
    if not a.get("error") and not b.get("error"):
        score_a = (a.get("stars", 0) > 100) + (a.get("pr_merge_rate_pct", 0) > 50) + (a.get("last_push_days_ago", 999) < 14) + (a.get("open_issues", 0) > 5)
        score_b = (b.get("stars", 0) > 100) + (b.get("pr_merge_rate_pct", 0) > 50) + (b.get("last_push_days_ago", 999) < 14) + (b.get("open_issues", 0) > 5)
        if score_a > score_b: winner = f"{owner_a}/{repo_a}"
        elif score_b > score_a: winner = f"{owner_b}/{repo_b}"
    return json.dumps({"repo_a": a, "repo_b": b, "recommended": winner}, indent=2)


# ---------------------------------------------------------------------------
# Tool 10 — check_issue_availability
# ---------------------------------------------------------------------------

@mcp.tool(name="opencollab_check_issue_availability", annotations={"title": "Check if an issue is still available to work on", "readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": True})
async def opencollab_check_issue_availability(owner: str, repo: str, issue_number: int) -> str:
    """Check if a GitHub issue is still available — no one has claimed it or opened a PR for it.

    Args:
        owner: Repository owner
        repo: Repository name
        issue_number: Issue number to check
    """
    path = f"/repos/{owner}/{repo}"
    try:
        issue = await github_get(f"{path}/issues/{issue_number}")
    except Exception as e:
        return handle_github_error(e)

    if issue.get("state") != "open":
        return json.dumps({"available": False, "reason": f"Issue is {issue.get('state', 'unknown')}", "issue_title": issue.get("title", "")}, indent=2)

    assignees = [a.get("login", "") for a in issue.get("assignees", [])]
    if assignees:
        return json.dumps({"available": False, "reason": f"Already assigned to: {', '.join(assignees)}", "issue_title": issue.get("title", "")}, indent=2)

    # Check for linked PRs
    linked_prs = []
    try:
        timeline = await github_get(f"{path}/issues/{issue_number}/timeline", {"per_page": 50})
        for event in timeline:
            if event.get("event") == "cross-referenced":
                source = event.get("source", {}).get("issue", {})
                if source.get("pull_request"):
                    pr_state = source.get("state", "unknown")
                    linked_prs.append({"pr_number": source.get("number"), "title": source.get("title", ""), "state": pr_state, "author": source.get("user", {}).get("login", "unknown")})
    except Exception:
        pass

    if any(pr.get("state") == "open" for pr in linked_prs):
        return json.dumps({"available": False, "reason": "An open PR already exists for this issue", "linked_prs": linked_prs, "issue_title": issue.get("title", "")}, indent=2)

    return json.dumps({"available": True, "reason": "No assignees, no open PRs — go for it!", "issue_title": issue.get("title", ""), "labels": [lb.get("name", "") for lb in issue.get("labels", [])], "comments": issue.get("comments", 0), "linked_prs": linked_prs, "created_days_ago": _days_ago(issue.get("created_at"))}, indent=2)


# ---------------------------------------------------------------------------
# Tool 11 — contributor_leaderboard
# ---------------------------------------------------------------------------

@mcp.tool(name="opencollab_contributor_leaderboard", annotations={"title": "Show top contributors of a repo", "readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": True})
async def opencollab_contributor_leaderboard(owner: str, repo: str, top_n: int = 10) -> str:
    """Get the top contributors of a repository with their commit counts and profiles.

    Args:
        owner: Repository owner
        repo: Repository name
        top_n: Number of top contributors to show (1-25, default 10)
    """
    top_n = max(1, min(top_n, 25))
    try:
        contributors = await github_get(f"/repos/{owner}/{repo}/contributors", {"per_page": top_n})
    except Exception as e:
        return handle_github_error(e)
    leaderboard = []
    for i, c in enumerate(contributors[:top_n], 1):
        leaderboard.append({"rank": i, "username": c.get("login", ""), "contributions": c.get("contributions", 0), "profile_url": c.get("html_url", ""), "avatar_url": c.get("avatar_url", "")})
    total_contributions = sum(c.get("contributions", 0) for c in contributors[:top_n])
    return json.dumps({"repo": f"{owner}/{repo}", "top_contributors": leaderboard, "total_contributions_shown": total_contributions}, indent=2)


# ---------------------------------------------------------------------------
# Tool 12 — stale_issue_finder
# ---------------------------------------------------------------------------

@mcp.tool(name="opencollab_stale_issue_finder", annotations={"title": "Find old unclaimed issues that are likely easy wins", "readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": True})
async def opencollab_stale_issue_finder(owner: str, repo: str, max_results: int = 10) -> str:
    """Find old, unclaimed issues in a repo that no one is working on — hidden easy wins.

    Args:
        owner: Repository owner
        repo: Repository name
        max_results: Number of issues to return (1-20, default 10)
    """
    max_results = max(1, min(max_results, 20))
    try:
        issues_raw = await github_get(f"/repos/{owner}/{repo}/issues", {"state": "open", "sort": "created", "direction": "asc", "per_page": 50, "assignee": "none"})
    except Exception as e:
        return handle_github_error(e)

    stale = []
    for issue in issues_raw:
        if issue.get("pull_request"):
            continue
        if issue.get("assignees"):
            continue
        days_old = _days_ago(issue.get("created_at"))
        if days_old is not None and days_old >= 30:
            labels = [lb.get("name", "") for lb in issue.get("labels", [])]
            stale.append({"title": issue.get("title", ""), "url": issue.get("html_url", ""), "labels": labels, "comments": issue.get("comments", 0), "days_old": days_old, "body_preview": _truncate(issue.get("body"), 150)})
        if len(stale) >= max_results:
            break
    return json.dumps({"repo": f"{owner}/{repo}", "stale_unclaimed_issues": stale, "count": len(stale)}, indent=2)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    """Run the MCP server."""
    transport = os.environ.get("TRANSPORT", "stdio").lower()
    if transport == "sse":
        port = int(os.environ.get("PORT", "8000"))
        mcp.run(transport="sse", host="0.0.0.0", port=port)
    else:
        mcp.run()


if __name__ == "__main__":
    main()
