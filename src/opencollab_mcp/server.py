"""OpenCollab MCP Server — AI-powered open source contribution matchmaker.

Helps developers find perfect open-source contribution opportunities
matched to their skills by analyzing GitHub profiles, searching issues,
and scoring repository health.
"""

import json
import math
from datetime import datetime, timezone
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

    Args:
        params (AnalyzeProfileInput): Contains the GitHub username.

    Returns:
        str: JSON-formatted developer skill profile.
    """
    try:
        user = await github_get(f"/users/{params.username}")
        repos_raw = await github_get(f"/users/{params.username}/repos", {"per_page": 100, "sort": "pushed", "type": "owner"})
        events_raw = await github_get(f"/users/{params.username}/events/public", {"per_page": 50})
    except Exception as e:
        return handle_github_error(e)

    # Aggregate languages
    lang_bytes: dict[str, int] = {}
    topics_set: set[str] = set()
    for repo in repos_raw:
        lang = repo.get("language")
        if lang:
            lang_bytes[lang] = lang_bytes.get(lang, 0) + (repo.get("size", 0))
        for t in repo.get("topics", []):
            topics_set.add(t)

    top_langs = sorted(lang_bytes.items(), key=lambda x: x[1], reverse=True)[:10]

    # Contribution events breakdown
    pr_events = [e for e in events_raw if e.get("type") == "PullRequestEvent"]
    push_events = [e for e in events_raw if e.get("type") == "PushEvent"]
    issue_events = [e for e in events_raw if e.get("type") == "IssuesEvent"]

    # Top repos
    top_repos = sorted(repos_raw, key=lambda r: r.get("stargazers_count", 0), reverse=True)[:5]

    profile = {
        "username": user.get("login"),
        "name": user.get("name"),
        "bio": user.get("bio"),
        "public_repos": user.get("public_repos", 0),
        "followers": user.get("followers", 0),
        "account_age_days": _days_ago(user.get("created_at")),
        "top_languages": [{"language": l, "relative_size": s} for l, s in top_langs],
        "topics_of_interest": sorted(topics_set)[:25],
        "recent_activity": {
            "pull_requests": len(pr_events),
            "pushes": len(push_events),
            "issues_opened": len(issue_events),
        },
        "top_repos": [
            {
                "name": r.get("full_name"),
                "stars": r.get("stargazers_count", 0),
                "language": r.get("language"),
                "description": _truncate(r.get("description")),
            }
            for r in top_repos
        ],
    }
    return json.dumps(profile, indent=2)


# ---------------------------------------------------------------------------
# Tool 2 — find_matching_issues
# ---------------------------------------------------------------------------

class FindIssuesInput(BaseModel):
    """Input for searching contribution-friendly issues."""
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    languages: list[str] = Field(
        default_factory=list,
        description="Programming languages to filter by (e.g. ['python', 'typescript'])",
        max_length=5,
    )
    topics: list[str] = Field(
        default_factory=list,
        description="Topics/domains to search in (e.g. ['machine-learning', 'react', 'cli'])",
        max_length=5,
    )
    difficulty: str = Field(
        default="beginner",
        description="Difficulty level: 'beginner' (good first issue), 'intermediate' (help wanted), or 'any'",
    )
    min_stars: int = Field(default=50, description="Minimum repo stars to filter out toy projects", ge=0)
    max_results: int = Field(default=10, description="Number of issues to return", ge=1, le=25)


@mcp.tool(
    name="opencollab_find_issues",
    annotations={
        "title": "Find matching open-source issues",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": False,
        "openWorldHint": True,
    },
)
async def opencollab_find_issues(params: FindIssuesInput) -> str:
    """Search GitHub for open issues labeled 'good first issue' or 'help wanted' that match the developer's skills.

    Filters by language, topic, difficulty label, and minimum repo popularity
    to surface high-quality contribution opportunities.

    Args:
        params (FindIssuesInput): Search filters including languages, topics, difficulty, and minimum stars.

    Returns:
        str: JSON array of matched issues with repo context.
    """
    label_map = {
        "beginner": "good first issue",
        "intermediate": "help wanted",
    }
    label = label_map.get(params.difficulty)

    # Build search query
    parts = ["state:open"]
    if label:
        parts.append(f'label:"{label}"')
    for lang in params.languages[:3]:
        parts.append(f"language:{lang}")
    for topic in params.topics[:2]:
        parts.append(f"topic:{topic}" if params.topics else "")
    parts = [p for p in parts if p]
    query = " ".join(parts)

    try:
        data = await github_search("issues", query, {
            "sort": "created",
            "order": "desc",
            "per_page": min(params.max_results * 2, 50),
        })
    except Exception as e:
        return handle_github_error(e)

    results = []
    for item in data.get("items", []):
        repo_url = item.get("repository_url", "")
        repo_full = "/".join(repo_url.split("/")[-2:]) if repo_url else ""

        # Quick star check via repo data embedded in issue (if available)
        repo_data = item.get("repository", {})
        stars = repo_data.get("stargazers_count") if repo_data else None

        results.append({
            "title": item.get("title"),
            "html_url": item.get("html_url"),
            "repo": repo_full,
            "stars": stars,
            "labels": [l.get("name") for l in item.get("labels", [])],
            "created": item.get("created_at"),
            "days_open": _days_ago(item.get("created_at")),
            "comments": item.get("comments", 0),
            "body_preview": _truncate(item.get("body"), 200),
        })

    # Filter by min stars if we got star data
    if params.min_stars > 0:
        results = [r for r in results if r["stars"] is None or r["stars"] >= params.min_stars]

    results = results[: params.max_results]

    return json.dumps({
        "query_used": query,
        "total_available": data.get("total_count", 0),
        "returned": len(results),
        "issues": results,
    }, indent=2)


# ---------------------------------------------------------------------------
# Tool 3 — repo_health
# ---------------------------------------------------------------------------

class RepoHealthInput(BaseModel):
    """Input for checking repository contribution-friendliness."""
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    repo: str = Field(..., description="Full repo name as 'owner/repo' (e.g. 'langchain-ai/langchain')", min_length=3)


@mcp.tool(
    name="opencollab_repo_health",
    annotations={
        "title": "Check repo contribution-friendliness",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
async def opencollab_repo_health(params: RepoHealthInput) -> str:
    """Evaluate how contributor-friendly a GitHub repository is.

    Checks maintainer activity, issue response times, PR merge rates,
    presence of CONTRIBUTING.md, and more. Returns a health score from 0-100.

    Args:
        params (RepoHealthInput): The full 'owner/repo' name.

    Returns:
        str: JSON health report with scores and details.
    """
    repo = params.repo.strip("/")
    try:
        repo_data = await github_get(f"/repos/{repo}")
        pulls = await github_get(f"/repos/{repo}/pulls", {"state": "all", "per_page": 30, "sort": "updated"})
        issues = await github_get(f"/repos/{repo}/issues", {"state": "all", "per_page": 30, "sort": "updated"})
        contributors = await github_get(f"/repos/{repo}/contributors", {"per_page": 10})
    except Exception as e:
        return handle_github_error(e)

    # Check for CONTRIBUTING.md
    has_contributing = False
    try:
        await github_get(f"/repos/{repo}/contents/CONTRIBUTING.md")
        has_contributing = True
    except Exception:
        pass

    # Compute metrics
    last_push_days = _days_ago(repo_data.get("pushed_at")) or 999
    open_issues = repo_data.get("open_issues_count", 0)
    stars = repo_data.get("stargazers_count", 0)
    forks = repo_data.get("forks_count", 0)

    # PR merge rate
    merged_prs = [p for p in pulls if p.get("merged_at")]
    merge_rate = (len(merged_prs) / max(len(pulls), 1)) * 100

    # Average days to close an issue (from the sample)
    closed_issues = [i for i in issues if i.get("state") == "closed" and i.get("closed_at")]
    avg_close_days = None
    if closed_issues:
        close_times = []
        for ci in closed_issues[:20]:
            created = _days_ago(ci.get("created_at"))
            closed = _days_ago(ci.get("closed_at"))
            if created is not None and closed is not None:
                close_times.append(max(created - closed, 0))
        if close_times:
            avg_close_days = round(sum(close_times) / len(close_times), 1)

    bus_factor = len(contributors)

    # Compute health score (0-100)
    score = 50  # base
    if last_push_days <= 7:
        score += 15
    elif last_push_days <= 30:
        score += 8
    elif last_push_days > 180:
        score -= 20

    if has_contributing:
        score += 10
    if merge_rate > 50:
        score += 10
    elif merge_rate < 10:
        score -= 10
    if bus_factor >= 5:
        score += 5
    elif bus_factor <= 1:
        score -= 10
    if avg_close_days is not None and avg_close_days < 14:
        score += 10

    score = max(0, min(100, score))

    report = {
        "repo": repo,
        "health_score": score,
        "stars": stars,
        "forks": forks,
        "open_issues": open_issues,
        "last_push_days_ago": last_push_days,
        "pr_merge_rate_percent": round(merge_rate, 1),
        "avg_issue_close_days": avg_close_days,
        "bus_factor_top_contributors": bus_factor,
        "has_contributing_md": has_contributing,
        "license": (repo_data.get("license") or {}).get("spdx_id"),
        "language": repo_data.get("language"),
        "topics": repo_data.get("topics", []),
        "description": _truncate(repo_data.get("description"), 200),
        "verdict": (
            "Excellent — very active, contributor-friendly repo"
            if score >= 80
            else "Good — reasonably active, worth contributing"
            if score >= 60
            else "Fair — some concerns, check recent activity"
            if score >= 40
            else "Risky — may be unmaintained or unresponsive"
        ),
    }
    return json.dumps(report, indent=2)


# ---------------------------------------------------------------------------
# Tool 4 — contribution_readiness
# ---------------------------------------------------------------------------

class ContribReadyInput(BaseModel):
    """Input for checking how easy a repo is to set up for contributing."""
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    repo: str = Field(..., description="Full repo name as 'owner/repo'", min_length=3)


@mcp.tool(
    name="opencollab_contribution_readiness",
    annotations={
        "title": "Assess contribution setup difficulty",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
async def opencollab_contribution_readiness(params: ContribReadyInput) -> str:
    """Check how easy it is to start contributing to a repo.

    Looks for Dockerfile, CI config, test suite, README quality,
    CONTRIBUTING.md, and issue templates. Returns a readiness score 1-10.

    Args:
        params (ContribReadyInput): The full 'owner/repo' name.

    Returns:
        str: JSON readiness report with checklist and score.
    """
    repo = params.repo.strip("/")
    checks: dict[str, bool] = {}

    # Check key files
    file_checks = {
        "has_readme": "README.md",
        "has_contributing": "CONTRIBUTING.md",
        "has_license": "LICENSE",
        "has_dockerfile": "Dockerfile",
        "has_code_of_conduct": "CODE_OF_CONDUCT.md",
    }

    for key, filepath in file_checks.items():
        try:
            await github_get(f"/repos/{repo}/contents/{filepath}")
            checks[key] = True
        except Exception:
            checks[key] = False

    # Check for CI (look for common CI config files)
    ci_files = [".github/workflows", ".circleci", ".travis.yml", "Jenkinsfile"]
    checks["has_ci"] = False
    for ci in ci_files:
        try:
            await github_get(f"/repos/{repo}/contents/{ci}")
            checks["has_ci"] = True
            break
        except Exception:
            continue

    # Check for issue templates
    checks["has_issue_templates"] = False
    try:
        await github_get(f"/repos/{repo}/contents/.github/ISSUE_TEMPLATE")
        checks["has_issue_templates"] = True
    except Exception:
        pass

    # Score 1-10
    score = 3  # base
    if checks.get("has_readme"):
        score += 1
    if checks.get("has_contributing"):
        score += 2
    if checks.get("has_ci"):
        score += 1
    if checks.get("has_dockerfile"):
        score += 1
    if checks.get("has_license"):
        score += 0.5
    if checks.get("has_issue_templates"):
        score += 0.5
    if checks.get("has_code_of_conduct"):
        score += 0.5
    score = min(10, round(score))

    return json.dumps({
        "repo": repo,
        "readiness_score": score,
        "checklist": checks,
        "verdict": (
            "Very easy to start contributing — great docs and tooling"
            if score >= 8
            else "Fairly straightforward to contribute"
            if score >= 6
            else "May require some effort to set up locally"
            if score >= 4
            else "Sparse contributor documentation — expect friction"
        ),
    }, indent=2)


# ---------------------------------------------------------------------------
# Tool 5 — generate_pr_plan
# ---------------------------------------------------------------------------

class PRPlanInput(BaseModel):
    """Input for generating a step-by-step PR plan from an issue."""
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    issue_url: str = Field(
        ...,
        description="Full GitHub issue URL (e.g. 'https://github.com/org/repo/issues/123')",
        min_length=10,
    )


@mcp.tool(
    name="opencollab_generate_pr_plan",
    annotations={
        "title": "Generate a PR plan for an issue",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
async def opencollab_generate_pr_plan(params: PRPlanInput) -> str:
    """Fetch a GitHub issue and return its full context so the AI can generate a step-by-step pull request plan.

    Gathers the issue body, labels, comments, and repo metadata (languages,
    structure) so the LLM has everything it needs to draft a contribution plan.

    Args:
        params (PRPlanInput): The full GitHub issue URL.

    Returns:
        str: JSON context bundle for the AI to generate a PR plan from.
    """
    # Parse URL -> owner/repo and issue number
    url = params.issue_url.rstrip("/")
    parts = url.replace("https://github.com/", "").split("/")
    if len(parts) < 4 or parts[2] != "issues":
        return json.dumps({"error": "Invalid issue URL. Expected format: https://github.com/owner/repo/issues/123"})

    owner, repo_name, _, issue_num = parts[0], parts[1], parts[2], parts[3]
    full_repo = f"{owner}/{repo_name}"

    try:
        issue = await github_get(f"/repos/{full_repo}/issues/{issue_num}")
        comments_raw = await github_get(f"/repos/{full_repo}/issues/{issue_num}/comments", {"per_page": 10})
        repo_data = await github_get(f"/repos/{full_repo}")
        languages = await github_get(f"/repos/{full_repo}/languages")
    except Exception as e:
        return handle_github_error(e)

    return json.dumps({
        "issue": {
            "title": issue.get("title"),
            "body": issue.get("body", "")[:3000],
            "labels": [l.get("name") for l in issue.get("labels", [])],
            "state": issue.get("state"),
            "author": issue.get("user", {}).get("login"),
            "created": issue.get("created_at"),
            "comments_count": issue.get("comments", 0),
        },
        "comments": [
            {
                "author": c.get("user", {}).get("login"),
                "body": _truncate(c.get("body"), 500),
                "created": c.get("created_at"),
            }
            for c in comments_raw[:5]
        ],
        "repo": {
            "full_name": full_repo,
            "description": _truncate(repo_data.get("description"), 200),
            "default_branch": repo_data.get("default_branch"),
            "languages": languages,
            "topics": repo_data.get("topics", []),
        },
        "hint": "Use this context to generate a step-by-step PR plan: fork, branch naming, files to modify, tests to write, and PR description template.",
    }, indent=2)


# ---------------------------------------------------------------------------
# Tool 6 — trending_repos
# ---------------------------------------------------------------------------

class TrendingInput(BaseModel):
    """Input for finding trending repos that need contributors."""
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    language: Optional[str] = Field(default=None, description="Filter by programming language (e.g. 'python')")
    topic: Optional[str] = Field(default=None, description="Filter by topic (e.g. 'machine-learning')")
    max_results: int = Field(default=10, description="Number of repos to return", ge=1, le=20)


@mcp.tool(
    name="opencollab_trending_repos",
    annotations={
        "title": "Find trending repos needing contributors",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": False,
        "openWorldHint": True,
    },
)
async def opencollab_trending_repos(params: TrendingInput) -> str:
    """Find trending GitHub repos that have recent 'good first issue' or 'help wanted' labels.

    Surfaces active, popular repos that are explicitly looking for contributors,
    sorted by recent activity and star count.

    Args:
        params (TrendingInput): Language, topic, and result count filters.

    Returns:
        str: JSON array of trending repos with contributor-relevant metadata.
    """
    parts = ["good-first-issues:>2", "stars:>100", "pushed:>2025-01-01"]
    if params.language:
        parts.append(f"language:{params.language}")
    if params.topic:
        parts.append(f"topic:{params.topic}")
    query = " ".join(parts)

    try:
        data = await github_search("repositories", query, {
            "sort": "updated",
            "order": "desc",
            "per_page": params.max_results,
        })
    except Exception as e:
        return handle_github_error(e)

    repos = []
    for r in data.get("items", [])[:params.max_results]:
        repos.append({
            "full_name": r.get("full_name"),
            "description": _truncate(r.get("description"), 150),
            "stars": r.get("stargazers_count", 0),
            "forks": r.get("forks_count", 0),
            "open_issues": r.get("open_issues_count", 0),
            "language": r.get("language"),
            "topics": r.get("topics", [])[:8],
            "last_push_days_ago": _days_ago(r.get("pushed_at")),
            "html_url": r.get("html_url"),
        })

    return json.dumps({
        "query_used": query,
        "total_matching": data.get("total_count", 0),
        "returned": len(repos),
        "repos": repos,
    }, indent=2)


# ---------------------------------------------------------------------------
# Tool 7 — impact_estimator
# ---------------------------------------------------------------------------

class ImpactInput(BaseModel):
    """Input for estimating the impact of solving an issue."""
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    repo: str = Field(..., description="Full repo name as 'owner/repo'", min_length=3)


@mcp.tool(
    name="opencollab_impact_estimator",
    annotations={
        "title": "Estimate contribution impact",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
async def opencollab_impact_estimator(params: ImpactInput) -> str:
    """Estimate the impact of contributing to a repository.

    Calculates reach based on stars, forks, dependent packages,
    and recent download/clone activity. Useful for prioritizing which
    contributions will look best on a resume.

    Args:
        params (ImpactInput): The full 'owner/repo' name.

    Returns:
        str: JSON impact assessment with reach metrics.
    """
    repo = params.repo.strip("/")
    try:
        repo_data = await github_get(f"/repos/{repo}")
    except Exception as e:
        return handle_github_error(e)

    # Try to get dependents count (not always available)
    network_count = repo_data.get("network_count", 0)
    subscribers = repo_data.get("subscribers_count", 0)
    stars = repo_data.get("stargazers_count", 0)
    forks = repo_data.get("forks_count", 0)

    # Rough impact tier
    total_reach = stars + (forks * 3) + (subscribers * 2) + network_count
    if total_reach > 50000:
        tier = "massive"
        resume_line = f"Contributed to a project used by tens of thousands of developers ({stars:,} stars)"
    elif total_reach > 10000:
        tier = "high"
        resume_line = f"Contributed to a widely-used open source project ({stars:,} stars)"
    elif total_reach > 1000:
        tier = "medium"
        resume_line = f"Contributed to an active open source project ({stars:,} stars)"
    else:
        tier = "growing"
        resume_line = f"Early contributor to a growing open source project ({stars:,} stars)"

    return json.dumps({
        "repo": repo,
        "stars": stars,
        "forks": forks,
        "watchers": subscribers,
        "network_count": network_count,
        "estimated_reach": total_reach,
        "impact_tier": tier,
        "suggested_resume_line": resume_line,
        "language": repo_data.get("language"),
        "topics": repo_data.get("topics", []),
    }, indent=2)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    """Run the OpenCollab MCP server."""
    mcp.run()


if __name__ == "__main__":
    main()
