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
    """Return how many days ago an ISO-8601 timestamp was."""
    if not iso_str:
        return None
    try:
        dt = datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
        return (datetime.now(timezone.utc) - dt).days
    except Exception:
        return None


def _truncate(text: str | None, length: int = 120) -> str:
    """Truncate text to *length* chars with ellipsis."""
    if not text:
        return ""
    return text[:length] + ("…" if len(text) > length else "")


def _recent_date_str(days_back: int = 90) -> str:
    """Return an ISO date string N days ago (for dynamic search filters)."""
    return (datetime.now(timezone.utc) - timedelta(days=days_back)).strftime("%Y-%m-%d")


# ---------------------------------------------------------------------------
# Tool 1 — analyze_profile
# ---------------------------------------------------------------------------

class AnalyzeProfileInput(BaseModel):
    """Input for analyzing a GitHub developer profile."""
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    username: str = Field(..., description="GitHub username to analyze (e.g. 'torvalds', 'gaearon')", min_length=1, max_length=39)


@mcp.tool(
    name="opencollab_analyze_profile",
    annotations={
        "title": "Analyze developer GitHub profile",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
async def opencollab_analyze_profile(params: AnalyzeProfileInput) -> str:
    """Analyze a GitHub user's profile to extract skills, languages, contribution patterns, and interests.

    Returns a structured skill profile including top languages, starred topics,
    contribution frequency, and repository highlights — used as input for
    finding matching contribution opportunities.
    """
    try:
        user = await github_get(f"/users/{params.username}")
        repos_raw = await github_get(
            f"/users/{params.username}/repos",
            {"per_page": 100, "sort": "pushed", "type": "owner"},
        )
        events_raw = await github_get(
            f"/users/{params.username}/events/public", {"per_page": 50}
        )
    except Exception as e:
        return handle_github_error(e)

    # Aggregate languages
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
        {"name": name, "percentage": round(b / total * 100, 1)}
        for name, b in top_langs
    ]

    # Recent activity types
    event_types: dict[str, int] = {}
    for ev in events_raw:
        etype = ev.get("type", "Unknown")
        event_types[etype] = event_types.get(etype, 0) + 1

    # Notable repos
    notable = sorted(
        repos_raw, key=lambda r: r.get("stargazers_count", 0), reverse=True
    )[:5]
    highlights = [
        {
            "name": r.get("full_name", r.get("name", "")),
            "stars": r.get("stargazers_count", 0),
            "language": r.get("language"),
            "description": _truncate(r.get("description"), 100),
            "last_pushed_days_ago": _days_ago(r.get("pushed_at")),
        }
        for r in notable
    ]

    profile = {
        "username": params.username,
        "name": user.get("name"),
        "bio": user.get("bio"),
        "public_repos": user.get("public_repos", 0),
        "followers": user.get("followers", 0),
        "following": user.get("following", 0),
        "account_age_days": _days_ago(user.get("created_at")),
        "top_languages": languages,
        "topics_of_interest": sorted(topics_set)[:20],
        "recent_activity_summary": event_types,
        "notable_repos": highlights,
    }
    return json.dumps(profile, indent=2)


# ---------------------------------------------------------------------------
# Tool 2 — find_issues
# ---------------------------------------------------------------------------


@mcp.tool(
    name="opencollab_find_issues",
    annotations={
        "title": "Find good first issues matched to skills",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
async def opencollab_find_issues(
    language: str,
    topic: str = "",
    max_results: int = 15,
) -> str:
    """Find beginner-friendly open-source issues matched to a developer's skills.

    Searches GitHub for issues labelled 'good first issue' or 'help wanted'
    in the specified language/topic, filtered to recently active repos.
    Returns structured issue data including repo health signals.

    Args:
        language: Primary programming language to filter by (e.g. 'Python', 'TypeScript', 'Rust')
        topic: Optional topic/domain to narrow search (e.g. 'machine-learning', 'web', 'cli')
        max_results: Number of issues to return (1-30, default 15)
    """
    max_results = max(1, min(max_results, 30))
    since = _recent_date_str(90)
    query_parts = [
        f"language:{language}",
        "label:\"good first issue\"",
        "state:open",
        f"created:>{since}",
        "is:public",
    ]
    if topic:
        query_parts.insert(0, topic)

    query = " ".join(query_parts)

    try:
        result = await github_search(
            "issues", query, {"sort": "created", "order": "desc", "per_page": max_results}
        )
    except Exception as e:
        return handle_github_error(e)

    issues = []
    for item in result.get("items", []):
        repo_url = item.get("repository_url", "")
        repo_full_name = "/".join(repo_url.split("/")[-2:]) if repo_url else ""

        labels = [lb.get("name", "") for lb in item.get("labels", [])]

        issues.append({
            "title": item.get("title", ""),
            "url": item.get("html_url", ""),
            "repo": repo_full_name,
            "labels": labels,
            "comments": item.get("comments", 0),
            "created_days_ago": _days_ago(item.get("created_at")),
            "body_preview": _truncate(item.get("body"), 200),
        })

    return json.dumps(
        {"total_found": result.get("total_count", 0), "issues": issues},
        indent=2,
    )


# ---------------------------------------------------------------------------
# Tool 3 — repo_health
# ---------------------------------------------------------------------------

class RepoHealthInput(BaseModel):
    """Input for checking repository health."""
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    owner: str = Field(..., description="Repository owner (e.g. 'facebook')", min_length=1)
    repo: str = Field(..., description="Repository name (e.g. 'react')", min_length=1)


@mcp.tool(
    name="opencollab_repo_health",
    annotations={
        "title": "Score repository contributor-friendliness",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
async def opencollab_repo_health(params: RepoHealthInput) -> str:
    """Score a repository's health and contributor-friendliness (0-100).

    Checks activity recency, community size, PR merge patterns, open issue
    count, and whether the repo has essential contributor files
    (CONTRIBUTING.md, CODE_OF_CONDUCT.md, issue templates, etc.).
    """
    path = f"/repos/{params.owner}/{params.repo}"
    try:
        repo = await github_get(path)
        pulls = await github_get(f"{path}/pulls", {"state": "closed", "per_page": 30, "sort": "updated"})
        community = await github_get(f"{path}/community/profile")
    except Exception as e:
        return handle_github_error(e)

    score = 0
    details: dict[str, object] = {}

    # 1. Recent activity (0-20)
    last_push_days = _days_ago(repo.get("pushed_at"))
    if last_push_days is not None:
        if last_push_days <= 7:
            score += 20
        elif last_push_days <= 30:
            score += 15
        elif last_push_days <= 90:
            score += 8
    details["last_push_days_ago"] = last_push_days

    # 2. Stars & community (0-15)
    stars = repo.get("stargazers_count", 0)
    if stars >= 1000:
        score += 15
    elif stars >= 100:
        score += 10
    elif stars >= 10:
        score += 5
    details["stars"] = stars

    # 3. PR merge rate (0-20)
    merged_count = sum(1 for p in pulls if p.get("merged_at"))
    total_closed = len(pulls)
    merge_rate = round(merged_count / max(total_closed, 1) * 100, 1)
    if merge_rate >= 60:
        score += 20
    elif merge_rate >= 30:
        score += 12
    elif merge_rate > 0:
        score += 5
    details["pr_merge_rate_pct"] = merge_rate
    details["recent_closed_prs"] = total_closed

    # 4. Open issues (healthy range) (0-10)
    open_issues = repo.get("open_issues_count", 0)
    if 5 <= open_issues <= 500:
        score += 10
    elif open_issues > 0:
        score += 5
    details["open_issues"] = open_issues

    # 5. Community profile files (0-20)
    files = community.get("files", {})
    community_items = {
        "contributing": files.get("contributing") is not None,
        "code_of_conduct": files.get("code_of_conduct") is not None,
        "license": files.get("license") is not None,
        "readme": files.get("readme") is not None,
        "issue_template": files.get("issue_template") is not None,
        "pull_request_template": files.get("pull_request_template") is not None,
    }
    comm_score = sum(community_items.values())
    score += min(comm_score * 4, 20)
    details["community_files"] = community_items

    # 6. Has description & topics (0-5)
    if repo.get("description"):
        score += 2
    if repo.get("topics"):
        score += 3
    details["has_description"] = bool(repo.get("description"))
    details["topics"] = repo.get("topics", [])

    # 7. Forks — shows people are contributing (0-10)
    forks = repo.get("forks_count", 0)
    if forks >= 100:
        score += 10
    elif forks >= 20:
        score += 6
    elif forks >= 5:
        score += 3
    details["forks"] = forks

    score = min(score, 100)

    if score >= 75:
        verdict = "Excellent — very contributor-friendly"
    elif score >= 50:
        verdict = "Good — solid project to contribute to"
    elif score >= 30:
        verdict = "Fair — some friction expected"
    else:
        verdict = "Low — may be abandoned or hard to contribute to"

    return json.dumps(
        {
            "repo": f"{params.owner}/{params.repo}",
            "health_score": score,
            "verdict": verdict,
            "details": details,
        },
        indent=2,
    )


# ---------------------------------------------------------------------------
# Tool 4 — contribution_readiness
# ---------------------------------------------------------------------------

class ContribReadinessInput(BaseModel):
    """Input for checking contribution readiness of a repo."""
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    owner: str = Field(..., description="Repository owner", min_length=1)
    repo: str = Field(..., description="Repository name", min_length=1)


@mcp.tool(
    name="opencollab_contribution_readiness",
    annotations={
        "title": "Check repo setup difficulty for contributors",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
async def opencollab_contribution_readiness(params: ContribReadinessInput) -> str:
    """Check how easy it is to set up and contribute to a repository.

    Looks for Dockerfile, CI configs, documentation, contributing guide,
    development setup instructions, and issue/PR templates. Returns a
    readiness checklist with a difficulty rating.
    """
    path = f"/repos/{params.owner}/{params.repo}"
    try:
        repo = await github_get(path)
        # Check root contents for key files
        contents = await github_get(f"{path}/contents")
    except Exception as e:
        return handle_github_error(e)

    filenames = [f.get("name", "").lower() for f in contents if isinstance(f, dict)]

    checks = {
        "has_readme": any(n.startswith("readme") for n in filenames),
        "has_contributing": any("contributing" in n for n in filenames),
        "has_license": any(n.startswith("license") or n.startswith("licence") for n in filenames),
        "has_dockerfile": "dockerfile" in filenames or "docker-compose.yml" in filenames or "docker-compose.yaml" in filenames,
        "has_ci": any(n in filenames for n in [".github", ".circleci", ".travis.yml", "jenkinsfile", ".gitlab-ci.yml"]),
        "has_tests_dir": any(n in ("tests", "test", "spec", "__tests__") for n in filenames),
        "has_package_config": any(
            n in filenames
            for n in [
                "package.json", "pyproject.toml", "setup.py", "setup.cfg",
                "cargo.toml", "go.mod", "gemfile", "pom.xml", "build.gradle",
            ]
        ),
        "has_code_of_conduct": any("code_of_conduct" in n for n in filenames),
        "has_changelog": any(n.startswith("changelog") or n.startswith("changes") for n in filenames),
    }

    passed = sum(checks.values())
    total = len(checks)

    if passed >= 8:
        difficulty = "Easy — well-documented, CI ready, contributor-friendly"
    elif passed >= 5:
        difficulty = "Moderate — some docs present, may need setup effort"
    elif passed >= 3:
        difficulty = "Hard — minimal docs, expect to figure things out yourself"
    else:
        difficulty = "Very hard — barely any contributor infrastructure"

    # Check for GitHub-specific contributor helpers
    try:
        github_dir = await github_get(f"{path}/contents/.github")
        gh_files = [f.get("name", "").lower() for f in github_dir if isinstance(f, dict)]
        checks["has_issue_templates"] = any("issue" in n for n in gh_files)
        checks["has_pr_template"] = any("pull" in n for n in gh_files)
    except Exception:
        checks["has_issue_templates"] = False
        checks["has_pr_template"] = False

    return json.dumps(
        {
            "repo": f"{params.owner}/{params.repo}",
            "difficulty": difficulty,
            "score": f"{passed}/{total}",
            "checks": checks,
            "primary_language": repo.get("language"),
            "default_branch": repo.get("default_branch", "main"),
        },
        indent=2,
    )


# ---------------------------------------------------------------------------
# Tool 5 — generate_pr_plan
# ---------------------------------------------------------------------------


@mcp.tool(
    name="opencollab_generate_pr_plan",
    annotations={
        "title": "Gather issue context for AI-assisted PR planning",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
async def opencollab_generate_pr_plan(
    owner: str,
    repo: str,
    issue_number: int,
) -> str:
    """Gather full context about a GitHub issue so the AI can draft a PR plan.

    Fetches the issue body, comments, labels, linked PRs, repo language,
    contributing guidelines, and directory structure to provide the AI
    with everything needed to suggest a concrete implementation approach.

    Args:
        owner: Repository owner (e.g. 'langchain-ai')
        repo: Repository name (e.g. 'langchain')
        issue_number: Issue number to plan a PR for (e.g. 123)
    """
    path = f"/repos/{owner}/{repo}"
    try:
        issue = await github_get(f"{path}/issues/{issue_number}")
        comments_raw = await github_get(
            f"{path}/issues/{issue_number}/comments", {"per_page": 20}
        )
        repo_info = await github_get(path)
    except Exception as e:
        return handle_github_error(e)

    # Try to get contributing guidelines
    contributing_text = ""
    try:
        contrib = await github_get(f"{path}/contents/CONTRIBUTING.md")
        if contrib.get("encoding") == "base64":
            import base64
            contributing_text = base64.b64decode(contrib.get("content", "")).decode("utf-8", errors="replace")[:2000]
    except Exception:
        pass

    # Get top-level directory listing
    dir_listing = []
    try:
        root_contents = await github_get(f"{path}/contents")
        dir_listing = [
            {"name": f.get("name"), "type": f.get("type")}
            for f in root_contents
            if isinstance(f, dict)
        ][:40]
    except Exception:
        pass

    comments = [
        {
            "author": c.get("user", {}).get("login", "unknown"),
            "body": _truncate(c.get("body"), 300),
            "created_days_ago": _days_ago(c.get("created_at")),
        }
        for c in comments_raw
    ]

    labels = [lb.get("name", "") for lb in issue.get("labels", [])]

    context = {
        "repo": f"{owner}/{repo}",
        "primary_language": repo_info.get("language"),
        "default_branch": repo_info.get("default_branch", "main"),
        "issue": {
            "number": issue_number,
            "title": issue.get("title", ""),
            "body": _truncate(issue.get("body"), 1500),
            "labels": labels,
            "state": issue.get("state"),
            "author": issue.get("user", {}).get("login", "unknown"),
            "created_days_ago": _days_ago(issue.get("created_at")),
            "comments_count": issue.get("comments", 0),
        },
        "comments": comments,
        "contributing_guidelines_preview": _truncate(contributing_text, 1000) if contributing_text else "Not found",
        "repo_root_files": dir_listing,
    }

    return json.dumps(context, indent=2)


# ---------------------------------------------------------------------------
# Tool 6 — trending_repos
# ---------------------------------------------------------------------------

class TrendingReposInput(BaseModel):
    """Input for finding trending repos seeking contributors."""
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    language: str = Field(
        default="",
        description="Filter by programming language (e.g. 'Python', 'Go'). Leave empty for all languages.",
    )
    max_results: int = Field(
        default=10,
        description="Number of repos to return (1-25)",
        ge=1,
        le=25,
    )


@mcp.tool(
    name="opencollab_trending_repos",
    annotations={
        "title": "Find trending repos seeking contributors",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
async def opencollab_trending_repos(params: TrendingReposInput) -> str:
    """Find trending repositories that are actively seeking contributors.

    Searches for recently created or recently popular repos that have
    'good first issue' or 'help wanted' issues open, sorted by stars.
    Great for discovering new projects to contribute to.
    """
    since = _recent_date_str(60)
    query_parts = [
        f"created:>{since}",
        "good-first-issues:>0",
        "is:public",
        "archived:false",
    ]
    if params.language:
        query_parts.append(f"language:{params.language}")

    query = " ".join(query_parts)

    try:
        result = await github_search(
            "repositories",
            query,
            {"sort": "stars", "order": "desc", "per_page": params.max_results},
        )
    except Exception as e:
        return handle_github_error(e)

    repos = []
    for r in result.get("items", []):
        repos.append({
            "name": r.get("full_name", ""),
            "description": _truncate(r.get("description"), 150),
            "stars": r.get("stargazers_count", 0),
            "forks": r.get("forks_count", 0),
            "language": r.get("language"),
            "open_issues": r.get("open_issues_count", 0),
            "topics": r.get("topics", [])[:8],
            "url": r.get("html_url", ""),
            "created_days_ago": _days_ago(r.get("created_at")),
            "last_push_days_ago": _days_ago(r.get("pushed_at")),
        })

    return json.dumps(
        {"total_found": result.get("total_count", 0), "repos": repos},
        indent=2,
    )


# ---------------------------------------------------------------------------
# Tool 7 — impact_estimator
# ---------------------------------------------------------------------------

class ImpactEstimatorInput(BaseModel):
    """Input for estimating contribution impact."""
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    owner: str = Field(..., description="Repository owner", min_length=1)
    repo: str = Field(..., description="Repository name", min_length=1)


@mcp.tool(
    name="opencollab_impact_estimator",
    annotations={
        "title": "Estimate contribution impact for a repo",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
async def opencollab_impact_estimator(params: ImpactEstimatorInput) -> str:
    """Estimate the impact of contributing to a specific repository.

    Analyses stars, forks, dependent projects, community size, and
    repo prominence to produce an impact tier (MASSIVE / HIGH / MEDIUM / LOW)
    plus a suggested resume line the contributor could use.
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

    # Determine impact tier
    if stars >= 50000:
        tier = "MASSIVE"
        reach = "millions of developers"
    elif stars >= 10000:
        tier = "HIGH"
        reach = "tens of thousands of developers"
    elif stars >= 1000:
        tier = "MEDIUM"
        reach = "thousands of developers"
    elif stars >= 100:
        tier = "MODERATE"
        reach = "hundreds of developers"
    else:
        tier = "LOW"
        reach = "a growing community"

    # Generate suggested resume line
    repo_name = f"{params.owner}/{params.repo}"
    if stars >= 1000:
        resume_line = f"Contributed to {repo_name} ({stars:,}+ stars), a widely-used project reaching {reach}"
    else:
        resume_line = f"Open-source contributor to {repo_name} — {description[:80]}"

    # Visibility score (0-100)
    vis = 0
    if stars >= 100:
        vis += min(stars // 500, 40)
    if forks >= 50:
        vis += min(forks // 100, 20)
    if watchers >= 50:
        vis += min(watchers // 50, 20)
    if open_issues >= 10:
        vis += 10
    if repo.get("topics"):
        vis += 10
    vis = min(vis, 100)

    return json.dumps(
        {
            "repo": repo_name,
            "impact_tier": tier,
            "estimated_reach": reach,
            "stars": stars,
            "forks": forks,
            "watchers": watchers,
            "open_issues": open_issues,
            "visibility_score": vis,
            "suggested_resume_line": resume_line,
            "topics": repo.get("topics", []),
        },
        indent=2,
    )


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main():
    """Run the MCP server.

    By default uses STDIO transport (for local MCP clients like Claude Desktop).
    Set TRANSPORT=sse and PORT=8000 environment variables for remote deployment.
    """
    transport = os.environ.get("TRANSPORT", "stdio").lower()

    if transport == "sse":
        port = int(os.environ.get("PORT", "8000"))
        mcp.run(transport="sse", host="0.0.0.0", port=port)
    else:
        mcp.run()


if __name__ == "__main__":
    main()
