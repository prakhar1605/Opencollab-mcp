"""OpenCollab MCP Server — AI-powered open source contribution matchmaker.

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


# ========================== INPUT MODELS ==========================

class AnalyzeProfileInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    username: str = Field(..., description="GitHub username to analyze", min_length=1, max_length=39)

class FindIssuesInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    language: str = Field(..., description="Programming language to filter by (e.g. 'Python', 'TypeScript')", min_length=1)
    topic: str = Field(default="", description="Optional topic to narrow search (e.g. 'machine-learning', 'web')")
    max_results: int = Field(default=15, description="Number of issues to return (1-30)", ge=1, le=30)

class RepoInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    owner: str = Field(..., description="Repository owner (e.g. 'facebook')", min_length=1)
    repo: str = Field(..., description="Repository name (e.g. 'react')", min_length=1)

class PRPlanInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    owner: str = Field(..., description="Repository owner", min_length=1)
    repo: str = Field(..., description="Repository name", min_length=1)
    issue_number: int = Field(..., description="Issue number to plan a PR for", ge=1)

class TrendingReposInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    language: str = Field(default="", description="Filter by programming language. Leave empty for all.")
    max_results: int = Field(default=10, description="Number of repos to return (1-25)", ge=1, le=25)

class MatchMeInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    username: str = Field(..., description="GitHub username to analyze and match", min_length=1, max_length=39)
    max_issues: int = Field(default=10, description="Number of matched issues to return (1-20)", ge=1, le=20)

class CompareReposInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    owner_a: str = Field(..., description="First repo owner", min_length=1)
    repo_a: str = Field(..., description="First repo name", min_length=1)
    owner_b: str = Field(..., description="Second repo owner", min_length=1)
    repo_b: str = Field(..., description="Second repo name", min_length=1)

class CheckIssueInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    owner: str = Field(..., description="Repository owner", min_length=1)
    repo: str = Field(..., description="Repository name", min_length=1)
    issue_number: int = Field(..., description="Issue number to check", ge=1)

class LeaderboardInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    owner: str = Field(..., description="Repository owner", min_length=1)
    repo: str = Field(..., description="Repository name", min_length=1)
    top_n: int = Field(default=10, description="Number of top contributors (1-25)", ge=1, le=25)

class StaleIssueInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    owner: str = Field(..., description="Repository owner", min_length=1)
    repo: str = Field(..., description="Repository name", min_length=1)
    max_results: int = Field(default=10, description="Number of issues to return (1-20)", ge=1, le=20)


# ========================== TOOL 1: analyze_profile ==========================

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
        et = ev.get("type", "Unknown")
        event_types[et] = event_types.get(et, 0) + 1
    notable = sorted(repos_raw, key=lambda r: r.get("stargazers_count", 0), reverse=True)[:5]
    highlights = [{"name": r.get("full_name", ""), "stars": r.get("stargazers_count", 0), "language": r.get("language"), "description": _truncate(r.get("description"), 100)} for r in notable]
    return json.dumps({"username": params.username, "name": user.get("name"), "bio": user.get("bio"), "public_repos": user.get("public_repos", 0), "followers": user.get("followers", 0), "account_age_days": _days_ago(user.get("created_at")), "top_languages": languages, "topics_of_interest": sorted(topics_set)[:20], "recent_activity_summary": event_types, "notable_repos": highlights}, indent=2)


# ========================== TOOL 2: find_issues ==========================

@mcp.tool(name="opencollab_find_issues", annotations={"title": "Find good first issues matched to skills", "readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": True})
async def opencollab_find_issues(params: FindIssuesInput) -> str:
    """Find beginner-friendly open-source issues matched to a developer's skills."""
    since = _recent_date_str(90)
    query_parts = [f"language:{params.language}", 'label:"good first issue"', "state:open", f"created:>{since}", "is:public"]
    if params.topic:
        query_parts.insert(0, params.topic)
    try:
        result = await github_search("issues", " ".join(query_parts), {"sort": "created", "order": "desc", "per_page": params.max_results})
    except Exception as e:
        return handle_github_error(e)
    issues = []
    for item in result.get("items", []):
        repo_url = item.get("repository_url", "")
        repo_name = "/".join(repo_url.split("/")[-2:]) if repo_url else ""
        issues.append({"title": item.get("title", ""), "url": item.get("html_url", ""), "repo": repo_name, "labels": [lb.get("name", "") for lb in item.get("labels", [])], "comments": item.get("comments", 0), "created_days_ago": _days_ago(item.get("created_at")), "body_preview": _truncate(item.get("body"), 200)})
    return json.dumps({"total_found": result.get("total_count", 0), "issues": issues}, indent=2)


# ========================== TOOL 3: repo_health ==========================

@mcp.tool(name="opencollab_repo_health", annotations={"title": "Score repository contributor-friendliness", "readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": True})
async def opencollab_repo_health(params: RepoInput) -> str:
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
    lpd = _days_ago(repo.get("pushed_at"))
    if lpd is not None:
        if lpd <= 7: score += 20
        elif lpd <= 30: score += 15
        elif lpd <= 90: score += 8
    details["last_push_days_ago"] = lpd
    stars = repo.get("stargazers_count", 0)
    if stars >= 1000: score += 15
    elif stars >= 100: score += 10
    elif stars >= 10: score += 5
    details["stars"] = stars
    mc = sum(1 for p in pulls if p.get("merged_at"))
    tc = len(pulls)
    mr = round(mc / max(tc, 1) * 100, 1)
    if mr >= 60: score += 20
    elif mr >= 30: score += 12
    elif mr > 0: score += 5
    details["pr_merge_rate_pct"] = mr
    oi = repo.get("open_issues_count", 0)
    if 5 <= oi <= 500: score += 10
    elif oi > 0: score += 5
    details["open_issues"] = oi
    fi = community.get("files", {})
    ci = {"contributing": fi.get("contributing") is not None, "code_of_conduct": fi.get("code_of_conduct") is not None, "license": fi.get("license") is not None, "readme": fi.get("readme") is not None, "issue_template": fi.get("issue_template") is not None, "pull_request_template": fi.get("pull_request_template") is not None}
    score += min(sum(ci.values()) * 4, 20)
    details["community_files"] = ci
    if repo.get("description"): score += 2
    if repo.get("topics"): score += 3
    forks = repo.get("forks_count", 0)
    if forks >= 100: score += 10
    elif forks >= 20: score += 6
    elif forks >= 5: score += 3
    score = min(score, 100)
    if score >= 75: v = "Excellent — very contributor-friendly"
    elif score >= 50: v = "Good — solid project to contribute to"
    elif score >= 30: v = "Fair — some friction expected"
    else: v = "Low — may be abandoned or hard to contribute to"
    return json.dumps({"repo": f"{params.owner}/{params.repo}", "health_score": score, "verdict": v, "details": details}, indent=2)


# ========================== TOOL 4: contribution_readiness ==========================

@mcp.tool(name="opencollab_contribution_readiness", annotations={"title": "Check repo setup difficulty for contributors", "readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": True})
async def opencollab_contribution_readiness(params: RepoInput) -> str:
    """Check how easy it is to set up and contribute to a repository."""
    path = f"/repos/{params.owner}/{params.repo}"
    try:
        repo = await github_get(path)
        contents = await github_get(f"{path}/contents")
    except Exception as e:
        return handle_github_error(e)
    fn = [f.get("name", "").lower() for f in contents if isinstance(f, dict)]
    checks = {"has_readme": any(n.startswith("readme") for n in fn), "has_contributing": any("contributing" in n for n in fn), "has_license": any(n.startswith("license") for n in fn), "has_dockerfile": "dockerfile" in fn or "docker-compose.yml" in fn, "has_ci": any(n in fn for n in [".github", ".circleci", ".travis.yml"]), "has_tests_dir": any(n in ("tests", "test", "spec", "__tests__") for n in fn), "has_package_config": any(n in fn for n in ["package.json", "pyproject.toml", "setup.py", "cargo.toml", "go.mod"]), "has_code_of_conduct": any("code_of_conduct" in n for n in fn), "has_changelog": any(n.startswith("changelog") for n in fn)}
    p = sum(checks.values())
    t = len(checks)
    if p >= 8: d = "Easy — well-documented, CI ready, contributor-friendly"
    elif p >= 5: d = "Moderate — some docs present, may need setup effort"
    elif p >= 3: d = "Hard — minimal docs, figure things out yourself"
    else: d = "Very hard — barely any contributor infrastructure"
    try:
        gd = await github_get(f"{path}/contents/.github")
        gf = [f.get("name", "").lower() for f in gd if isinstance(f, dict)]
        checks["has_issue_templates"] = any("issue" in n for n in gf)
        checks["has_pr_template"] = any("pull" in n for n in gf)
    except Exception:
        checks["has_issue_templates"] = False
        checks["has_pr_template"] = False
    return json.dumps({"repo": f"{params.owner}/{params.repo}", "difficulty": d, "score": f"{p}/{t}", "checks": checks, "primary_language": repo.get("language"), "default_branch": repo.get("default_branch", "main")}, indent=2)


# ========================== TOOL 5: generate_pr_plan ==========================

@mcp.tool(name="opencollab_generate_pr_plan", annotations={"title": "Gather issue context for AI-assisted PR planning", "readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": True})
async def opencollab_generate_pr_plan(params: PRPlanInput) -> str:
    """Gather full context about a GitHub issue so the AI can draft a PR plan."""
    path = f"/repos/{params.owner}/{params.repo}"
    try:
        issue = await github_get(f"{path}/issues/{params.issue_number}")
        comments_raw = await github_get(f"{path}/issues/{params.issue_number}/comments", {"per_page": 20})
        repo_info = await github_get(path)
    except Exception as e:
        return handle_github_error(e)
    ct = ""
    try:
        contrib = await github_get(f"{path}/contents/CONTRIBUTING.md")
        if contrib.get("encoding") == "base64":
            import base64
            ct = base64.b64decode(contrib.get("content", "")).decode("utf-8", errors="replace")[:2000]
    except Exception:
        pass
    dl = []
    try:
        rc = await github_get(f"{path}/contents")
        dl = [{"name": f.get("name"), "type": f.get("type")} for f in rc if isinstance(f, dict)][:40]
    except Exception:
        pass
    comments = [{"author": c.get("user", {}).get("login", "unknown"), "body": _truncate(c.get("body"), 300), "created_days_ago": _days_ago(c.get("created_at"))} for c in comments_raw]
    labels = [lb.get("name", "") for lb in issue.get("labels", [])]
    return json.dumps({"repo": f"{params.owner}/{params.repo}", "primary_language": repo_info.get("language"), "default_branch": repo_info.get("default_branch", "main"), "issue": {"number": params.issue_number, "title": issue.get("title", ""), "body": _truncate(issue.get("body"), 1500), "labels": labels, "state": issue.get("state"), "author": issue.get("user", {}).get("login", "unknown"), "created_days_ago": _days_ago(issue.get("created_at")), "comments_count": issue.get("comments", 0)}, "comments": comments, "contributing_guidelines_preview": _truncate(ct, 1000) if ct else "Not found", "repo_root_files": dl}, indent=2)


# ========================== TOOL 6: trending_repos ==========================

@mcp.tool(name="opencollab_trending_repos", annotations={"title": "Find trending repos seeking contributors", "readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": True})
async def opencollab_trending_repos(params: TrendingReposInput) -> str:
    """Find trending repositories that are actively seeking contributors."""
    since = _recent_date_str(60)
    qp = [f"created:>{since}", "good-first-issues:>0", "is:public", "archived:false"]
    if params.language:
        qp.append(f"language:{params.language}")
    try:
        result = await github_search("repositories", " ".join(qp), {"sort": "stars", "order": "desc", "per_page": params.max_results})
    except Exception as e:
        return handle_github_error(e)
    repos = [{"name": r.get("full_name", ""), "description": _truncate(r.get("description"), 150), "stars": r.get("stargazers_count", 0), "forks": r.get("forks_count", 0), "language": r.get("language"), "open_issues": r.get("open_issues_count", 0), "topics": r.get("topics", [])[:8], "url": r.get("html_url", ""), "created_days_ago": _days_ago(r.get("created_at")), "last_push_days_ago": _days_ago(r.get("pushed_at"))} for r in result.get("items", [])]
    return json.dumps({"total_found": result.get("total_count", 0), "repos": repos}, indent=2)


# ========================== TOOL 7: impact_estimator ==========================

@mcp.tool(name="opencollab_impact_estimator", annotations={"title": "Estimate contribution impact for a repo", "readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": True})
async def opencollab_impact_estimator(params: RepoInput) -> str:
    """Estimate the impact of contributing to a specific repository."""
    path = f"/repos/{params.owner}/{params.repo}"
    try:
        repo = await github_get(path)
    except Exception as e:
        return handle_github_error(e)
    s = repo.get("stargazers_count", 0)
    f = repo.get("forks_count", 0)
    w = repo.get("subscribers_count", 0)
    oi = repo.get("open_issues_count", 0)
    desc = repo.get("description") or ""
    if s >= 50000: tier, reach = "MASSIVE", "millions of developers"
    elif s >= 10000: tier, reach = "HIGH", "tens of thousands of developers"
    elif s >= 1000: tier, reach = "MEDIUM", "thousands of developers"
    elif s >= 100: tier, reach = "MODERATE", "hundreds of developers"
    else: tier, reach = "LOW", "a growing community"
    rn = f"{params.owner}/{params.repo}"
    rl = f"Contributed to {rn} ({s:,}+ stars), reaching {reach}" if s >= 1000 else f"Open-source contributor to {rn} — {desc[:80]}"
    vis = min((min(s // 500, 40) if s >= 100 else 0) + (min(f // 100, 20) if f >= 50 else 0) + (min(w // 50, 20) if w >= 50 else 0) + (10 if oi >= 10 else 0) + (10 if repo.get("topics") else 0), 100)
    return json.dumps({"repo": rn, "impact_tier": tier, "estimated_reach": reach, "stars": s, "forks": f, "watchers": w, "open_issues": oi, "visibility_score": vis, "suggested_resume_line": rl, "topics": repo.get("topics", [])}, indent=2)


# ========================== TOOL 8: match_me ==========================

@mcp.tool(name="opencollab_match_me", annotations={"title": "Analyze profile and find matched issues in one step", "readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": True})
async def opencollab_match_me(params: MatchMeInput) -> str:
    """All-in-one: analyze a GitHub profile and instantly find issues matched to that user's top skills."""
    try:
        user = await github_get(f"/users/{params.username}")
        repos_raw = await github_get(f"/users/{params.username}/repos", {"per_page": 100, "sort": "pushed", "type": "owner"})
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
    primary_lang = top_langs[0][0] if top_langs else "Python"
    since = _recent_date_str(90)
    try:
        result = await github_search("issues", f'language:{primary_lang} label:"good first issue" state:open created:>{since} is:public', {"sort": "created", "order": "desc", "per_page": params.max_issues})
    except Exception as e:
        return handle_github_error(e)
    issues = [{"title": it.get("title", ""), "url": it.get("html_url", ""), "repo": "/".join(it.get("repository_url", "").split("/")[-2:]), "labels": [lb.get("name", "") for lb in it.get("labels", [])], "comments": it.get("comments", 0), "body_preview": _truncate(it.get("body"), 150)} for it in result.get("items", [])]
    return json.dumps({"username": params.username, "name": user.get("name"), "top_languages": languages, "topics": sorted(topics_set)[:10], "matched_language": primary_lang, "matched_issues": issues}, indent=2)


# ========================== TOOL 9: compare_repos ==========================

@mcp.tool(name="opencollab_compare_repos", annotations={"title": "Compare two repos for contributor-friendliness", "readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": True})
async def opencollab_compare_repos(params: CompareReposInput) -> str:
    """Compare two GitHub repositories side-by-side for contributor-friendliness."""
    async def _score(owner: str, repo: str) -> dict:
        try:
            r = await github_get(f"/repos/{owner}/{repo}")
            pulls = await github_get(f"/repos/{owner}/{repo}/pulls", {"state": "closed", "per_page": 20, "sort": "updated"})
        except Exception as e:
            return {"repo": f"{owner}/{repo}", "error": handle_github_error(e)}
        mr = round(sum(1 for p in pulls if p.get("merged_at")) / max(len(pulls), 1) * 100, 1)
        return {"repo": f"{owner}/{repo}", "stars": r.get("stargazers_count", 0), "forks": r.get("forks_count", 0), "open_issues": r.get("open_issues_count", 0), "language": r.get("language"), "last_push_days_ago": _days_ago(r.get("pushed_at")), "pr_merge_rate_pct": mr, "topics": r.get("topics", [])[:6]}
    a = await _score(params.owner_a, params.repo_a)
    b = await _score(params.owner_b, params.repo_b)
    winner = "tie"
    if not a.get("error") and not b.get("error"):
        sa = (a.get("stars", 0) > 100) + (a.get("pr_merge_rate_pct", 0) > 50) + ((a.get("last_push_days_ago") or 999) < 14) + (a.get("open_issues", 0) > 5)
        sb = (b.get("stars", 0) > 100) + (b.get("pr_merge_rate_pct", 0) > 50) + ((b.get("last_push_days_ago") or 999) < 14) + (b.get("open_issues", 0) > 5)
        if sa > sb: winner = f"{params.owner_a}/{params.repo_a}"
        elif sb > sa: winner = f"{params.owner_b}/{params.repo_b}"
    return json.dumps({"repo_a": a, "repo_b": b, "recommended": winner}, indent=2)


# ========================== TOOL 10: check_issue_availability ==========================

@mcp.tool(name="opencollab_check_issue_availability", annotations={"title": "Check if an issue is still available to work on", "readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": True})
async def opencollab_check_issue_availability(params: CheckIssueInput) -> str:
    """Check if a GitHub issue is still available — no one has claimed it or opened a PR for it."""
    path = f"/repos/{params.owner}/{params.repo}"
    try:
        issue = await github_get(f"{path}/issues/{params.issue_number}")
    except Exception as e:
        return handle_github_error(e)
    if issue.get("state") != "open":
        return json.dumps({"available": False, "reason": f"Issue is {issue.get('state', 'unknown')}", "issue_title": issue.get("title", "")}, indent=2)
    assignees = [a.get("login", "") for a in issue.get("assignees", [])]
    if assignees:
        return json.dumps({"available": False, "reason": f"Already assigned to: {', '.join(assignees)}", "issue_title": issue.get("title", "")}, indent=2)
    linked_prs = []
    try:
        timeline = await github_get(f"{path}/issues/{params.issue_number}/timeline", {"per_page": 50})
        for event in timeline:
            if event.get("event") == "cross-referenced":
                source = event.get("source", {}).get("issue", {})
                if source.get("pull_request"):
                    linked_prs.append({"pr_number": source.get("number"), "title": source.get("title", ""), "state": source.get("state", "unknown"), "author": source.get("user", {}).get("login", "unknown")})
    except Exception:
        pass
    if any(pr.get("state") == "open" for pr in linked_prs):
        return json.dumps({"available": False, "reason": "An open PR already exists for this issue", "linked_prs": linked_prs, "issue_title": issue.get("title", "")}, indent=2)
    return json.dumps({"available": True, "reason": "No assignees, no open PRs — go for it!", "issue_title": issue.get("title", ""), "labels": [lb.get("name", "") for lb in issue.get("labels", [])], "comments": issue.get("comments", 0), "linked_prs": linked_prs, "created_days_ago": _days_ago(issue.get("created_at"))}, indent=2)


# ========================== TOOL 11: contributor_leaderboard ==========================

@mcp.tool(name="opencollab_contributor_leaderboard", annotations={"title": "Show top contributors of a repo", "readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": True})
async def opencollab_contributor_leaderboard(params: LeaderboardInput) -> str:
    """Get the top contributors of a repository with their commit counts and profiles."""
    try:
        contributors = await github_get(f"/repos/{params.owner}/{params.repo}/contributors", {"per_page": params.top_n})
    except Exception as e:
        return handle_github_error(e)
    lb = [{"rank": i, "username": c.get("login", ""), "contributions": c.get("contributions", 0), "profile_url": c.get("html_url", ""), "avatar_url": c.get("avatar_url", "")} for i, c in enumerate(contributors[:params.top_n], 1)]
    return json.dumps({"repo": f"{params.owner}/{params.repo}", "top_contributors": lb, "total_contributions_shown": sum(c.get("contributions", 0) for c in contributors[:params.top_n])}, indent=2)


# ========================== TOOL 12: stale_issue_finder ==========================

@mcp.tool(name="opencollab_stale_issue_finder", annotations={"title": "Find old unclaimed issues — hidden easy wins", "readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": True})
async def opencollab_stale_issue_finder(params: StaleIssueInput) -> str:
    """Find old, unclaimed issues in a repo that no one is working on — hidden easy wins."""
    try:
        issues_raw = await github_get(f"/repos/{params.owner}/{params.repo}/issues", {"state": "open", "sort": "created", "direction": "asc", "per_page": 50, "assignee": "none"})
    except Exception as e:
        return handle_github_error(e)
    stale = []
    for issue in issues_raw:
        if issue.get("pull_request") or issue.get("assignees"):
            continue
        days_old = _days_ago(issue.get("created_at"))
        if days_old is not None and days_old >= 30:
            stale.append({"title": issue.get("title", ""), "url": issue.get("html_url", ""), "labels": [lb.get("name", "") for lb in issue.get("labels", [])], "comments": issue.get("comments", 0), "days_old": days_old, "body_preview": _truncate(issue.get("body"), 150)})
        if len(stale) >= params.max_results:
            break
    return json.dumps({"repo": f"{params.owner}/{params.repo}", "stale_unclaimed_issues": stale, "count": len(stale)}, indent=2)


# ========================== ENTRY POINT ==========================

def main():
    transport = os.environ.get("TRANSPORT", "stdio").lower()
    if transport == "sse":
        mcp.run(transport="sse", host="0.0.0.0", port=int(os.environ.get("PORT", "8000")))
    else:
        mcp.run()

if __name__ == "__main__":
    main()
