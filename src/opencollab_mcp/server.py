"""OpenCollab MCP Server — AI-powered open source contribution matchmaker.

Consolidated API: 22 internal helpers, 8 public tools.

Transports:
  stdio          (default, local) — for Claude Desktop, Cursor, etc.
  streamable-http (remote)         — for hosted deployments (MCP 2025-03-26+).
"""
from __future__ import annotations

import base64
import json
import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Any, Literal, Optional

from mcp.server.fastmcp import FastMCP
from pydantic import BaseModel, ConfigDict, Field

from .github_client import (
    StatsComputingError,
    github_get,
    github_search,
    handle_github_error,
)

logger = logging.getLogger(__name__)
mcp = FastMCP("opencollab_mcp")


# ========================== CONSTANTS ==========================

WEEKEND_LABELS = ["documentation", "docs", "typo", "test", "tests", "chore",
                  "style", "cleanup", "translation"]

BEGINNER_KEYWORDS = {"good first issue", "beginner", "easy", "starter",
                     "help wanted", "first-timers-only", "up-for-grabs",
                     "newcomer", "low-hanging-fruit"}

EASY_LABELS = {"good first issue", "beginner", "easy", "starter",
               "help wanted", "low-hanging-fruit", "trivial", "documentation"}

HARD_LABELS = {"critical", "complex", "breaking", "architecture",
               "security", "performance", "refactor"}

MENTOR_TOPICS = ("hacktoberfest", "gsoc", "outreachy", "mentorship",
                 "good-first-issue", "beginner-friendly", "first-timers-only")

DEP_FILES = ["package.json", "pyproject.toml", "requirements.txt",
             "go.mod", "Cargo.toml", "Gemfile", "setup.py", "setup.cfg"]


# ========================== UTILITIES ==========================

def _days_ago(iso_str: Optional[str]) -> Optional[int]:
    if not iso_str:
        return None
    try:
        dt = datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
        return (datetime.now(timezone.utc) - dt).days
    except Exception:
        return None


def _truncate(text: Optional[str], length: int = 120) -> str:
    if not text:
        return ""
    return text[:length] + ("…" if len(text) > length else "")


def _recent_date_str(days_back: int = 90) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=days_back)).strftime("%Y-%m-%d")


def _parse_issue_number(raw: str) -> int:
    """Accept '#123', '123', '  123  '."""
    cleaned = raw.strip().lstrip("#")
    return int(cleaned)


def _sanitize_language(lang: str) -> str:
    """Allow alphanumerics, +, #, -, and . for languages like C++, C#, F#, Objective-C."""
    allowed = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789+#-. ")
    return "".join(c for c in lang if c in allowed).strip()


# ========================== INPUT MODELS ==========================

class UsernameInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    username: str = Field(..., min_length=1, max_length=39, description="GitHub username")


class RepoInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    owner: str = Field(..., min_length=1, description="Repo owner, e.g. 'facebook'")
    repo: str = Field(..., min_length=1, description="Repo name, e.g. 'react'")


class IssueInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    owner: str = Field(..., min_length=1)
    repo: str = Field(..., min_length=1)
    issue_number: str = Field(..., description="Issue number, e.g. '123' or '#123'")


class LanguageInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    language: str = Field(..., min_length=1, description="e.g. 'Python', 'TypeScript'")


class CompareInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    owner_a: str = Field(..., min_length=1)
    repo_a: str = Field(..., min_length=1)
    owner_b: str = Field(..., min_length=1)
    repo_b: str = Field(..., min_length=1)


class OpportunityInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    language: str = Field(..., min_length=1, description="Programming language")
    mode: Literal["good_first_issue", "weekend", "trending", "similar", "mentor", "stale"] = Field(
        default="good_first_issue",
        description="What kind of opportunity to search for",
    )
    owner: Optional[str] = Field(None, description="Required for 'similar' and 'stale' modes")
    repo: Optional[str] = Field(None, description="Required for 'similar' and 'stale' modes")


class ExploreRepoInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    owner: str = Field(..., min_length=1)
    repo: str = Field(..., min_length=1)
    include: list[Literal["labels", "contributors", "recent_prs"]] = Field(
        default_factory=lambda: ["labels", "contributors", "recent_prs"],
    )


# ========================== PRIVATE HELPERS (the old 22 tools, reused) ==========================

async def _profile_data(username: str) -> dict:
    """Fetch profile + repos + events. Used by match_me, analyze, first_timer."""
    user = await github_get(f"/users/{username}")
    repos = await github_get(
        f"/users/{username}/repos",
        {"per_page": 100, "sort": "pushed", "type": "owner"},
    )
    events = await github_get(f"/users/{username}/events/public", {"per_page": 50})
    return {"user": user, "repos": repos, "events": events}


def _language_stats(repos: list[dict]) -> tuple[list[dict], list[str], set[str]]:
    lang_bytes: dict[str, int] = {}
    topics: set[str] = set()
    for r in repos:
        lang = r.get("language")
        if lang:
            lang_bytes[lang] = lang_bytes.get(lang, 0) + r.get("size", 0)
        for t in r.get("topics", []):
            topics.add(t)
    total = max(sum(lang_bytes.values()), 1)
    top = sorted(lang_bytes.items(), key=lambda x: x[1], reverse=True)
    languages = [{"name": n, "percentage": round(b / total * 100, 1)} for n, b in top[:8]]
    known = sorted({l for l in lang_bytes.keys()})
    return languages, known, topics


async def _repo_bundle(owner: str, repo: str) -> dict:
    """Fetch repo + pulls + community + languages in parallel-ish fashion.
    Returns a dict of all data used by scoring/health/impact tools.
    """
    import asyncio
    path = f"/repos/{owner}/{repo}"
    repo_data, pulls, community, languages = await asyncio.gather(
        github_get(path),
        github_get(f"{path}/pulls", {"state": "closed", "per_page": 30, "sort": "updated"}),
        github_get(f"{path}/community/profile"),
        github_get(f"{path}/languages"),
        return_exceptions=True,
    )
    return {
        "repo": repo_data if not isinstance(repo_data, Exception) else {},
        "pulls": pulls if not isinstance(pulls, Exception) else [],
        "community": community if not isinstance(community, Exception) else {},
        "languages": languages if not isinstance(languages, Exception) else {},
    }


def _score_health(bundle: dict) -> dict:
    """Compute health score + details from a repo bundle."""
    repo = bundle["repo"]
    pulls = bundle["pulls"]
    community = bundle["community"]

    score = 0
    details: dict[str, Any] = {}

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

    merged = sum(1 for p in pulls if p.get("merged_at"))
    total = len(pulls)
    mr = round(merged / max(total, 1) * 100, 1)
    if mr >= 60: score += 20
    elif mr >= 30: score += 12
    elif mr > 0: score += 5
    details["pr_merge_rate_pct"] = mr

    oi = repo.get("open_issues_count", 0)
    if 5 <= oi <= 500: score += 10
    elif oi > 0: score += 5
    details["open_issues"] = oi

    files = community.get("files", {}) or {}
    community_files = {
        "contributing": files.get("contributing") is not None,
        "code_of_conduct": files.get("code_of_conduct") is not None,
        "license": files.get("license") is not None,
        "readme": files.get("readme") is not None,
        "issue_template": files.get("issue_template") is not None,
        "pull_request_template": files.get("pull_request_template") is not None,
    }
    score += min(sum(community_files.values()) * 4, 20)
    details["community_files"] = community_files

    if repo.get("description"): score += 2
    if repo.get("topics"): score += 3

    forks = repo.get("forks_count", 0)
    if forks >= 100: score += 10
    elif forks >= 20: score += 6
    elif forks >= 5: score += 3

    score = min(score, 100)
    if score >= 75: verdict = "Excellent — very contributor-friendly"
    elif score >= 50: verdict = "Good — solid project to contribute to"
    elif score >= 30: verdict = "Fair — some friction expected"
    else: verdict = "Low — may be abandoned or hard to contribute to"

    return {"health_score": score, "verdict": verdict, "details": details}


def _score_impact(repo: dict) -> dict:
    s = repo.get("stargazers_count", 0)
    f = repo.get("forks_count", 0)
    w = repo.get("subscribers_count", 0)
    oi = repo.get("open_issues_count", 0)

    if s >= 50000: tier, reach = "MASSIVE", "millions of developers"
    elif s >= 10000: tier, reach = "HIGH", "tens of thousands of developers"
    elif s >= 1000: tier, reach = "MEDIUM", "thousands of developers"
    elif s >= 100: tier, reach = "MODERATE", "hundreds of developers"
    else: tier, reach = "LOW", "a growing community"

    full = repo.get("full_name", "")
    desc = repo.get("description") or ""
    resume_line = (
        f"Contributed to {full} ({s:,}+ stars), reaching {reach}"
        if s >= 1000
        else f"Open-source contributor to {full} — {desc[:80]}"
    )

    visibility = min(
        (min(s // 500, 40) if s >= 100 else 0)
        + (min(f // 100, 20) if f >= 50 else 0)
        + (min(w // 50, 20) if w >= 50 else 0)
        + (10 if oi >= 10 else 0)
        + (10 if repo.get("topics") else 0),
        100,
    )
    return {
        "impact_tier": tier,
        "estimated_reach": reach,
        "visibility_score": visibility,
        "suggested_resume_line": resume_line,
    }


async def _activity_pulse(owner: str, repo: str) -> dict:
    """Last-30-day momentum. Handles 202 Accepted gracefully."""
    path = f"/repos/{owner}/{repo}"
    try:
        commit_activity = await github_get(f"{path}/stats/commit_activity")
    except StatsComputingError:
        return {"status": "computing", "message": "GitHub is still computing stats. Try again shortly."}
    except Exception as e:
        return {"status": "error", "message": handle_github_error(e)}

    if not isinstance(commit_activity, list) or len(commit_activity) < 4:
        return {"status": "insufficient_data", "message": "Not enough history to compute momentum."}

    last_4 = [w.get("total", 0) for w in commit_activity[-4:]]
    prev_4 = [w.get("total", 0) for w in commit_activity[-8:-4]] if len(commit_activity) >= 8 else []
    total_30d = sum(last_4)
    prev_total = sum(prev_4)

    if prev_total > 0:
        momentum_pct = round((total_30d - prev_total) / prev_total * 100, 1)
    elif total_30d > 0:
        momentum_pct = 100.0
    else:
        momentum_pct = 0.0

    if total_30d == 0:
        momentum = "Inactive — no commits in 30 days"
    elif momentum_pct > 20:
        momentum = "Growing — more active than last month"
    elif momentum_pct > -20:
        momentum = "Stable — consistent activity"
    else:
        momentum = "Declining — less active than last month"

    return {
        "status": "ok",
        "total_commits_30d": total_30d,
        "weekly_breakdown": last_4,
        "momentum": momentum,
        "momentum_change_pct": momentum_pct,
    }


async def _dependencies(owner: str, repo: str) -> dict:
    """Find dependency files in repo root and parse what we can."""
    path = f"/repos/{owner}/{repo}"
    found: dict[str, str] = {}
    for df in DEP_FILES:
        try:
            content = await github_get(f"{path}/contents/{df}")
            if content.get("encoding") == "base64":
                raw = base64.b64decode(content.get("content", "")).decode("utf-8", errors="replace")
                found[df] = raw
        except Exception:
            continue

    if not found:
        return {"dependencies_found": False}

    parsed: dict[str, Any] = {}
    for filename, raw in found.items():
        if filename == "package.json":
            try:
                pkg = json.loads(raw)
                parsed["npm_dependencies"] = list((pkg.get("dependencies") or {}).keys())[:20]
                parsed["npm_dev_dependencies"] = list((pkg.get("devDependencies") or {}).keys())[:15]
            except Exception:
                parsed["package.json"] = "present but could not parse"
        elif filename == "requirements.txt":
            lines = [
                l.strip().split("==")[0].split(">=")[0].split("[")[0]
                for l in raw.splitlines()
                if l.strip() and not l.startswith("#")
            ]
            parsed["python_requirements"] = lines[:25]
        else:
            parsed[f"{filename}_preview"] = raw[:400]
    return {"dependencies_found": True, "dependency_files": list(found.keys()), "parsed": parsed}


async def _top_contributors(owner: str, repo: str, limit: int = 10) -> list[dict]:
    try:
        contributors = await github_get(
            f"/repos/{owner}/{repo}/contributors", {"per_page": limit}
        )
    except Exception:
        return []
    return [
        {
            "rank": i,
            "username": c.get("login", ""),
            "contributions": c.get("contributions", 0),
            "profile_url": c.get("html_url", ""),
        }
        for i, c in enumerate(contributors[:limit], 1)
    ]


async def _recent_merged_prs(owner: str, repo: str, limit: int = 10) -> dict:
    try:
        pulls = await github_get(
            f"/repos/{owner}/{repo}/pulls",
            {"state": "closed", "sort": "updated", "direction": "desc", "per_page": 30},
        )
    except Exception as e:
        return {"error": handle_github_error(e)}

    merged: list[dict] = []
    for pr in pulls:
        if not pr.get("merged_at"):
            continue
        created = pr.get("created_at", "")
        merged_at = pr.get("merged_at", "")
        days_to_merge = None
        if created and merged_at:
            try:
                c = datetime.fromisoformat(created.replace("Z", "+00:00"))
                m = datetime.fromisoformat(merged_at.replace("Z", "+00:00"))
                days_to_merge = (m - c).days
            except Exception:
                pass
        merged.append({
            "title": pr.get("title", ""),
            "url": pr.get("html_url", ""),
            "author": pr.get("user", {}).get("login", "unknown"),
            "merged_days_ago": _days_ago(merged_at),
            "days_to_merge": days_to_merge,
            "labels": [lb.get("name", "") for lb in pr.get("labels", [])],
        })
        if len(merged) >= limit:
            break

    times = [p["days_to_merge"] for p in merged if p["days_to_merge"] is not None]
    avg = round(sum(times) / len(times), 1) if times else None
    return {"recent_merged_prs": merged, "average_days_to_merge": avg}


async def _labels(owner: str, repo: str) -> dict:
    try:
        labels_raw = await github_get(
            f"/repos/{owner}/{repo}/labels", {"per_page": 100}
        )
    except Exception:
        return {"total_labels": 0, "beginner_friendly_labels": [], "all_labels": []}

    all_labels: list[dict] = []
    beginner: list[str] = []
    for lb in labels_raw:
        name = lb.get("name", "")
        all_labels.append({
            "name": name,
            "description": lb.get("description") or "",
            "color": lb.get("color", ""),
        })
        nlower = name.lower()
        if nlower in BEGINNER_KEYWORDS or any(kw in nlower for kw in BEGINNER_KEYWORDS):
            beginner.append(name)

    return {
        "total_labels": len(all_labels),
        "beginner_friendly_labels": beginner,
        "all_labels": all_labels,
    }


async def _find_issues(language: str, days_back: int = 90, limit: int = 15) -> dict:
    since = _recent_date_str(days_back)
    q = f'language:{language} label:"good first issue" state:open created:>{since} is:public'
    result = await github_search("issues", q, {"sort": "created", "order": "desc", "per_page": limit})
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
            "created_days_ago": _days_ago(item.get("created_at")),
            "body_preview": _truncate(item.get("body"), 200),
        })
    return {"total_found": result.get("total_count", 0), "issues": issues}


async def _weekend_issues(language: str) -> dict:
    since = _recent_date_str(60)
    all_issues: list[dict] = []
    seen: set[str] = set()
    for label in WEEKEND_LABELS[:5]:
        try:
            result = await github_search(
                "issues",
                f'language:{language} label:"{label}" state:open created:>{since} is:public',
                {"sort": "created", "order": "desc", "per_page": 5},
            )
        except Exception:
            continue
        for item in result.get("items", []):
            url = item.get("html_url", "")
            if url in seen:
                continue
            seen.add(url)
            body = item.get("body") or ""
            if len(body) >= 500 or item.get("comments", 0) > 3:
                continue
            repo_url = item.get("repository_url", "")
            repo_name = "/".join(repo_url.split("/")[-2:]) if repo_url else ""
            all_issues.append({
                "title": item.get("title", ""),
                "url": url,
                "repo": repo_name,
                "labels": [lb.get("name", "") for lb in item.get("labels", [])],
                "comments": item.get("comments", 0),
                "body_preview": _truncate(body, 150),
                "estimated_effort": "1-2 hours",
            })
    all_issues.sort(key=lambda x: x.get("comments", 0))
    return {"weekend_issues": all_issues[:12]}


async def _trending_repos(language: str) -> dict:
    since = _recent_date_str(60)
    q = f"created:>{since} good-first-issues:>0 is:public archived:false language:{language}"
    result = await github_search("repositories", q, {"sort": "stars", "order": "desc", "per_page": 10})
    repos = [{
        "name": r.get("full_name", ""),
        "description": _truncate(r.get("description"), 150),
        "stars": r.get("stargazers_count", 0),
        "forks": r.get("forks_count", 0),
        "language": r.get("language"),
        "open_issues": r.get("open_issues_count", 0),
        "topics": r.get("topics", [])[:8],
        "url": r.get("html_url", ""),
        "last_push_days_ago": _days_ago(r.get("pushed_at")),
    } for r in result.get("items", [])]
    return {"trending_repos": repos}


async def _mentor_repos(language: str) -> dict:
    since = _recent_date_str(180)
    queries = [
        f"language:{language} topic:hacktoberfest good-first-issues:>3 pushed:>{since}",
        f"language:{language} topic:gsoc good-first-issues:>1 pushed:>{since}",
        f"language:{language} topic:mentorship good-first-issues:>1 pushed:>{since}",
    ]
    seen: set[str] = set()
    repos: list[dict] = []
    for q in queries:
        try:
            result = await github_search("repositories", q, {"sort": "stars", "order": "desc", "per_page": 8})
        except Exception:
            continue
        for r in result.get("items", []):
            name = r.get("full_name", "")
            if name in seen:
                continue
            seen.add(name)
            topics = r.get("topics", [])
            signals = [t for t in topics if t in MENTOR_TOPICS]
            repos.append({
                "name": name,
                "description": _truncate(r.get("description"), 150),
                "stars": r.get("stargazers_count", 0),
                "language": r.get("language"),
                "mentor_signals": signals,
                "url": r.get("html_url", ""),
            })
    repos.sort(key=lambda x: len(x.get("mentor_signals", [])), reverse=True)
    return {"mentor_repos": repos[:15]}


async def _similar_repos(owner: str, repo: str) -> dict:
    try:
        repo_data = await github_get(f"/repos/{owner}/{repo}")
    except Exception as e:
        return {"error": handle_github_error(e)}
    lang = repo_data.get("language") or ""
    topics = repo_data.get("topics") or []
    parts = []
    if topics: parts.append(f"topic:{topics[0]}")
    if lang: parts.append(f"language:{lang}")
    parts.append("good-first-issues:>0")
    parts.append("archived:false")
    try:
        result = await github_search("repositories", " ".join(parts), {"sort": "stars", "order": "desc", "per_page": 12})
    except Exception as e:
        return {"error": handle_github_error(e)}
    similar = []
    for r in result.get("items", []):
        if r.get("full_name") == f"{owner}/{repo}":
            continue
        similar.append({
            "name": r.get("full_name", ""),
            "description": _truncate(r.get("description"), 150),
            "stars": r.get("stargazers_count", 0),
            "language": r.get("language"),
            "topics": r.get("topics", [])[:6],
            "open_issues": r.get("open_issues_count", 0),
            "url": r.get("html_url", ""),
        })
    return {"source_repo": f"{owner}/{repo}", "similar_repos": similar[:10]}


async def _stale_issues(owner: str, repo: str) -> dict:
    try:
        issues_raw = await github_get(
            f"/repos/{owner}/{repo}/issues",
            {"state": "open", "sort": "created", "direction": "asc", "per_page": 50, "assignee": "none"},
        )
    except Exception as e:
        return {"error": handle_github_error(e)}
    stale: list[dict] = []
    for issue in issues_raw:
        if issue.get("pull_request"):
            continue
        days_old = _days_ago(issue.get("created_at"))
        if days_old is not None and days_old >= 30:
            stale.append({
                "title": issue.get("title", ""),
                "url": issue.get("html_url", ""),
                "labels": [lb.get("name", "") for lb in issue.get("labels", [])],
                "comments": issue.get("comments", 0),
                "days_old": days_old,
                "body_preview": _truncate(issue.get("body"), 150),
            })
        if len(stale) >= 10:
            break
    return {"repo": f"{owner}/{repo}", "stale_unclaimed_issues": stale}


def _score_complexity(issue: dict) -> dict:
    body = issue.get("body") or ""
    body_len = len(body)
    comments = issue.get("comments", 0)
    labels = [lb.get("name", "").lower() for lb in issue.get("labels", [])]
    has_easy = bool(set(labels) & EASY_LABELS)
    has_hard = bool(set(labels) & HARD_LABELS)

    score = 0
    if body_len > 2000: score += 3
    elif body_len > 500: score += 2
    elif body_len > 100: score += 1

    if comments > 10: score += 3
    elif comments > 5: score += 2
    elif comments > 2: score += 1

    if has_hard: score += 3
    if has_easy: score -= 2

    checklist = body.count("- [ ]") + body.count("- [x]")
    if checklist > 5: score += 2
    elif checklist > 0: score += 1

    code_blocks = body.count("```")
    if code_blocks > 4: score += 2
    elif code_blocks > 0: score += 1

    score = max(1, min(score, 10))
    if score <= 3: level = "Beginner — good for first-time contributors"
    elif score <= 5: level = "Intermediate — some experience helpful"
    elif score <= 7: level = "Advanced — requires deep understanding of the codebase"
    else: level = "Expert — significant effort and expertise needed"

    return {
        "complexity_score": score,
        "complexity_level": level,
        "signals": {
            "body_length": body_len,
            "comments": comments,
            "checklist_items": checklist,
            "has_beginner_label": has_easy,
            "has_hard_label": has_hard,
        },
    }


async def _check_availability(owner: str, repo: str, issue_num: int) -> dict:
    path = f"/repos/{owner}/{repo}"
    issue = await github_get(f"{path}/issues/{issue_num}")

    if issue.get("state") != "open":
        return {
            "available": False,
            "reason": f"Issue is {issue.get('state', 'unknown')}",
            "issue": issue,
        }

    assignees = [a.get("login", "") for a in issue.get("assignees", [])]
    if assignees:
        return {
            "available": False,
            "reason": f"Already assigned to: {', '.join(assignees)}",
            "issue": issue,
        }

    linked_prs: list[dict] = []
    try:
        timeline = await github_get(f"{path}/issues/{issue_num}/timeline", {"per_page": 50})
        for event in timeline:
            if event.get("event") == "cross-referenced":
                src = event.get("source", {}).get("issue", {})
                if src.get("pull_request"):
                    linked_prs.append({
                        "pr_number": src.get("number"),
                        "title": src.get("title", ""),
                        "state": src.get("state", "unknown"),
                        "author": src.get("user", {}).get("login", "unknown"),
                    })
    except Exception:
        pass

    if any(pr.get("state") == "open" for pr in linked_prs):
        return {
            "available": False,
            "reason": "An open PR already exists for this issue",
            "linked_prs": linked_prs,
            "issue": issue,
        }

    return {
        "available": True,
        "reason": "No assignees, no open PRs — go for it!",
        "linked_prs": linked_prs,
        "issue": issue,
    }


# ========================== PUBLIC TOOLS (8) ==========================

@mcp.tool(
    name="opencollab_match_me",
    annotations={
        "title": "Profile → skills → matched good-first-issues (hero tool)",
        "readOnlyHint": True, "destructiveHint": False,
        "idempotentHint": True, "openWorldHint": True,
    },
)
async def opencollab_match_me(params: UsernameInput) -> str:
    """All-in-one: analyze a GitHub profile and instantly return issues matched
    to the user's top language. Includes readiness signals so you know whether
    to start with docs or jump into a feature.

    Use this as the default entry point when someone says "find me an issue".
    """
    try:
        data = await _profile_data(params.username)
    except Exception as e:
        return handle_github_error(e)

    user = data["user"]
    repos = data["repos"]
    events = data["events"]
    languages, known, topics = _language_stats(repos)
    primary = languages[0]["name"] if languages else "Python"

    try:
        issues_payload = await _find_issues(primary, days_back=90, limit=10)
    except Exception as e:
        return handle_github_error(e)

    has_prs = any(e.get("type") == "PullRequestEvent" for e in events)

    return json.dumps({
        "username": params.username,
        "name": user.get("name"),
        "bio": user.get("bio"),
        "public_repos": user.get("public_repos", 0),
        "top_languages": languages[:3],
        "topics": sorted(topics)[:10],
        "matched_language": primary,
        "has_opened_prs_before": has_prs,
        "matched_issues": issues_payload["issues"],
    }, indent=2)


@mcp.tool(
    name="opencollab_repo_health",
    annotations={
        "title": "Full repo health: score + activity + impact + deps",
        "readOnlyHint": True, "destructiveHint": False,
        "idempotentHint": True, "openWorldHint": True,
    },
)
async def opencollab_repo_health(params: RepoInput) -> str:
    """One-shot repo evaluation: contributor-friendliness score, 30-day momentum,
    impact tier + resume line, language breakdown, and dependency summary.

    Use this to answer: "Is this repo worth contributing to?"
    """
    try:
        bundle = await _repo_bundle(params.owner, params.repo)
    except Exception as e:
        return handle_github_error(e)

    repo = bundle["repo"]
    if not repo:
        return json.dumps({"error": "Repo not found or inaccessible"}, indent=2)

    health = _score_health(bundle)
    impact = _score_impact({**repo, "full_name": f"{params.owner}/{params.repo}"})
    pulse = await _activity_pulse(params.owner, params.repo)
    deps = await _dependencies(params.owner, params.repo)

    languages = bundle["languages"]
    total_bytes = max(sum(languages.values()), 1) if isinstance(languages, dict) else 1
    lang_breakdown = (
        [
            {"language": lang, "percentage": round(b / total_bytes * 100, 1)}
            for lang, b in sorted(languages.items(), key=lambda x: x[1], reverse=True)
        ]
        if isinstance(languages, dict)
        else []
    )

    return json.dumps({
        "repo": f"{params.owner}/{params.repo}",
        "health": health,
        "impact": impact,
        "activity_30d": pulse,
        "languages": lang_breakdown,
        "dependencies": deps,
        "primary_language": repo.get("language"),
        "default_branch": repo.get("default_branch", "main"),
    }, indent=2)


@mcp.tool(
    name="opencollab_check_issue",
    annotations={
        "title": "Issue availability + complexity in one call",
        "readOnlyHint": True, "destructiveHint": False,
        "idempotentHint": True, "openWorldHint": True,
    },
)
async def opencollab_check_issue(params: IssueInput) -> str:
    """Check if a specific issue is still available AND rate its complexity.

    Returns: availability (assignees, linked PRs), complexity 1-10,
    label signals, and body preview. Use before picking an issue.
    """
    try:
        issue_num = _parse_issue_number(params.issue_number)
    except ValueError:
        return json.dumps({"error": f"Could not parse issue number: '{params.issue_number}'"}, indent=2)

    try:
        availability = await _check_availability(params.owner, params.repo, issue_num)
    except Exception as e:
        return handle_github_error(e)

    issue = availability.pop("issue", {})
    complexity = _score_complexity(issue)

    return json.dumps({
        "repo": f"{params.owner}/{params.repo}",
        "issue_number": issue_num,
        "title": issue.get("title", ""),
        "available": availability["available"],
        "availability_reason": availability["reason"],
        "linked_prs": availability.get("linked_prs", []),
        "complexity": complexity,
        "labels": [lb.get("name", "") for lb in issue.get("labels", [])],
        "comments": issue.get("comments", 0),
        "created_days_ago": _days_ago(issue.get("created_at")),
        "body_preview": _truncate(issue.get("body"), 300),
        "is_pull_request": issue.get("pull_request") is not None,
    }, indent=2)


@mcp.tool(
    name="opencollab_plan_pr",
    annotations={
        "title": "Gather full context to plan a PR for an issue",
        "readOnlyHint": True, "destructiveHint": False,
        "idempotentHint": True, "openWorldHint": True,
    },
)
async def opencollab_plan_pr(params: IssueInput) -> str:
    """Gather full context about an issue so the AI can draft a PR plan.

    Fetches: issue body, comments, labels, CONTRIBUTING.md, repo root
    structure, default branch, primary language. Hands Claude everything
    needed to propose the actual code changes.
    """
    try:
        issue_num = _parse_issue_number(params.issue_number)
    except ValueError:
        return json.dumps({"error": f"Could not parse issue number: '{params.issue_number}'"}, indent=2)

    path = f"/repos/{params.owner}/{params.repo}"
    try:
        issue = await github_get(f"{path}/issues/{issue_num}")
        comments_raw = await github_get(f"{path}/issues/{issue_num}/comments", {"per_page": 20})
        repo_info = await github_get(path)
    except Exception as e:
        return handle_github_error(e)

    if issue.get("pull_request"):
        return json.dumps({
            "error": f"#{issue_num} is a pull request, not an issue. Use the PR URL directly.",
        }, indent=2)

    contributing = ""
    try:
        contrib = await github_get(f"{path}/contents/CONTRIBUTING.md")
        if contrib.get("encoding") == "base64":
            contributing = base64.b64decode(contrib.get("content", "")).decode("utf-8", errors="replace")[:2000]
    except Exception:
        pass

    root_files: list[dict] = []
    try:
        rc = await github_get(f"{path}/contents")
        root_files = [{"name": f.get("name"), "type": f.get("type")} for f in rc if isinstance(f, dict)][:40]
    except Exception:
        pass

    comments = [{
        "author": c.get("user", {}).get("login", "unknown"),
        "body": _truncate(c.get("body"), 300),
        "created_days_ago": _days_ago(c.get("created_at")),
    } for c in comments_raw]

    return json.dumps({
        "repo": f"{params.owner}/{params.repo}",
        "primary_language": repo_info.get("language"),
        "default_branch": repo_info.get("default_branch", "main"),
        "issue": {
            "number": issue_num,
            "title": issue.get("title", ""),
            "body": _truncate(issue.get("body"), 1500),
            "labels": [lb.get("name", "") for lb in issue.get("labels", [])],
            "state": issue.get("state"),
            "author": issue.get("user", {}).get("login", "unknown"),
            "created_days_ago": _days_ago(issue.get("created_at")),
            "comments_count": issue.get("comments", 0),
        },
        "comments": comments,
        "contributing_guidelines_preview": _truncate(contributing, 1000) if contributing else "Not found",
        "repo_root_files": root_files,
    }, indent=2)


@mcp.tool(
    name="opencollab_find_opportunities",
    annotations={
        "title": "Find issues/repos by mode: good_first_issue | weekend | trending | similar | mentor | stale",
        "readOnlyHint": True, "destructiveHint": False,
        "idempotentHint": True, "openWorldHint": True,
    },
)
async def opencollab_find_opportunities(params: OpportunityInput) -> str:
    """One flexible search tool. Set `mode` to pick the flavor:

    - good_first_issue: recent "good first issue" labelled issues for `language`
    - weekend:          1-2 hour issues (docs, typos, tests) for `language`
    - trending:         trending repos in `language` seeking contributors
    - similar:          repos similar to `owner/repo` (needs owner+repo)
    - mentor:           GSoC/Hacktoberfest/Outreachy repos in `language`
    - stale:            old unclaimed issues in `owner/repo` (needs owner+repo)
    """
    lang = _sanitize_language(params.language)
    if not lang:
        return json.dumps({"error": "Invalid language"}, indent=2)

    try:
        if params.mode == "good_first_issue":
            result = await _find_issues(lang)
        elif params.mode == "weekend":
            result = await _weekend_issues(lang)
        elif params.mode == "trending":
            result = await _trending_repos(lang)
        elif params.mode == "mentor":
            result = await _mentor_repos(lang)
        elif params.mode == "similar":
            if not params.owner or not params.repo:
                return json.dumps({"error": "mode='similar' requires owner and repo"}, indent=2)
            result = await _similar_repos(params.owner, params.repo)
        elif params.mode == "stale":
            if not params.owner or not params.repo:
                return json.dumps({"error": "mode='stale' requires owner and repo"}, indent=2)
            result = await _stale_issues(params.owner, params.repo)
        else:
            return json.dumps({"error": f"Unknown mode: {params.mode}"}, indent=2)
    except Exception as e:
        return handle_github_error(e)

    return json.dumps({"mode": params.mode, "language": lang, **result}, indent=2)


@mcp.tool(
    name="opencollab_compare_repos",
    annotations={
        "title": "Compare two repos for contributor-friendliness",
        "readOnlyHint": True, "destructiveHint": False,
        "idempotentHint": True, "openWorldHint": True,
    },
)
async def opencollab_compare_repos(params: CompareInput) -> str:
    """Side-by-side comparison of two repos: stars, PR merge rate, activity,
    and a recommendation on which to contribute to.
    """
    import asyncio

    async def _snapshot(owner: str, repo: str) -> dict:
        try:
            r = await github_get(f"/repos/{owner}/{repo}")
            pulls = await github_get(
                f"/repos/{owner}/{repo}/pulls",
                {"state": "closed", "per_page": 20, "sort": "updated"},
            )
        except Exception as e:
            return {"repo": f"{owner}/{repo}", "error": handle_github_error(e)}
        mr = round(
            sum(1 for p in pulls if p.get("merged_at")) / max(len(pulls), 1) * 100, 1
        )
        return {
            "repo": f"{owner}/{repo}",
            "stars": r.get("stargazers_count", 0),
            "forks": r.get("forks_count", 0),
            "open_issues": r.get("open_issues_count", 0),
            "language": r.get("language"),
            "last_push_days_ago": _days_ago(r.get("pushed_at")),
            "pr_merge_rate_pct": mr,
            "topics": r.get("topics", [])[:6],
        }

    a, b = await asyncio.gather(
        _snapshot(params.owner_a, params.repo_a),
        _snapshot(params.owner_b, params.repo_b),
    )

    winner = "tie"
    if not a.get("error") and not b.get("error"):
        sa = (
            (a.get("stars", 0) > 100)
            + (a.get("pr_merge_rate_pct", 0) > 50)
            + ((a.get("last_push_days_ago") or 999) < 14)
            + (a.get("open_issues", 0) > 5)
        )
        sb = (
            (b.get("stars", 0) > 100)
            + (b.get("pr_merge_rate_pct", 0) > 50)
            + ((b.get("last_push_days_ago") or 999) < 14)
            + (b.get("open_issues", 0) > 5)
        )
        if sa > sb: winner = a["repo"]
        elif sb > sa: winner = b["repo"]

    return json.dumps({"repo_a": a, "repo_b": b, "recommended": winner}, indent=2)


@mcp.tool(
    name="opencollab_explore_repo",
    annotations={
        "title": "Explore a repo: labels + contributors + recent merged PRs",
        "readOnlyHint": True, "destructiveHint": False,
        "idempotentHint": True, "openWorldHint": True,
    },
)
async def opencollab_explore_repo(params: ExploreRepoInput) -> str:
    """Deep-dive on a repo's contribution ecosystem.

    Returns (configurable via `include`):
    - labels: all labels + which are beginner-friendly
    - contributors: top 10 with commit counts
    - recent_prs: recently merged PRs + average merge time
    """
    import asyncio

    tasks = {}
    if "labels" in params.include:
        tasks["labels"] = _labels(params.owner, params.repo)
    if "contributors" in params.include:
        tasks["contributors"] = _top_contributors(params.owner, params.repo)
    if "recent_prs" in params.include:
        tasks["recent_prs"] = _recent_merged_prs(params.owner, params.repo)

    results = await asyncio.gather(*tasks.values(), return_exceptions=True)
    out: dict[str, Any] = {"repo": f"{params.owner}/{params.repo}"}
    for key, result in zip(tasks.keys(), results):
        if isinstance(result, Exception):
            out[key] = {"error": handle_github_error(result)}
        else:
            out[key] = result

    return json.dumps(out, indent=2)


@mcp.tool(
    name="opencollab_first_timer_score",
    annotations={
        "title": "Rate open-source readiness for a GitHub user",
        "readOnlyHint": True, "destructiveHint": False,
        "idempotentHint": True, "openWorldHint": True,
    },
)
async def opencollab_first_timer_score(params: UsernameInput) -> str:
    """Rate how ready a GitHub user is to contribute to open source.

    Scores profile completeness, coding activity, language breadth,
    and existing PR history. Returns 0-100 with personalized tips.
    """
    try:
        data = await _profile_data(params.username)
    except Exception as e:
        return handle_github_error(e)

    user = data["user"]
    repos = data["repos"]
    events = data["events"]
    _, known, _ = _language_stats(repos)

    score = 0
    tips: list[str] = []

    # Profile (max 10)
    if user.get("bio"): score += 10
    else: tips.append("Add a bio to your GitHub profile — maintainers check contributor profiles")

    # Repos (max 15)
    nrepos = user.get("public_repos", 0)
    if nrepos >= 5: score += 15
    elif nrepos >= 1:
        score += 8
        tips.append("Create more public repos to show your work")
    else:
        tips.append("Push at least 1-2 projects to GitHub to build credibility")

    # Language breadth (max 15)
    if len(known) >= 3: score += 15
    elif len(known) >= 1:
        score += 8
        tips.append("Try projects in more languages to expand your contribution options")
    else:
        tips.append("Your repos don't show any programming language — push some code")


    # Repo descriptions (max 10)
    desc_count = sum(1 for r in repos if r.get("description"))
    if desc_count >= 3: score += 10
    else: tips.append("Add descriptions to your repos — shows you care about documentation")

    # Recent activity (max 15)
    if len(events) >= 20: score += 15
    elif len(events) >= 5: score += 8
    else: tips.append("Be more active on GitHub — push code, open issues, star repos")

    # Forks (max 10)
    forks = sum(1 for r in repos if r.get("fork"))
    if forks >= 2:
        score += 10
        tips.append("You've forked repos — great! Now open PRs on them")
    elif forks >= 1: score += 5
    else: tips.append("Fork a project you use and try making a small improvement")

    # Stars received (max 10)
    stars = sum(r.get("stargazers_count", 0) for r in repos)
    if stars >= 10: score += 10
    elif stars >= 1: score += 5

    # PR history (max 15)
    has_prs = any(e.get("type") == "PullRequestEvent" for e in events)
    if has_prs: score += 15
    else: tips.append("You haven't opened any PRs yet — start with a documentation fix!")

    # Cap at 100 (weights sum to 100 exactly)
    score = min(score, 100)

    if score >= 80: level = "Ready — you can confidently contribute to most projects"
    elif score >= 60: level = "Almost there — a few improvements and you're set"
    elif score >= 40: level = "Getting started — build up your profile first"
    else: level = "Beginner — focus on learning and building projects before contributing"

    return json.dumps({
        "username": params.username,
        "readiness_score": score,
        "readiness_level": level,
        "languages_known": known,
        "public_repos": nrepos,
        "has_opened_prs": has_prs,
        "account_age_days": _days_ago(user.get("created_at")),
        "tips_to_improve": tips,
    }, indent=2)


# ========================== ENTRY POINT ==========================

def main() -> None:
    level = os.environ.get("OPENCOLLAB_LOG_LEVEL", "INFO").upper()
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    transport = os.environ.get("TRANSPORT", "stdio").lower()

    if transport in ("streamable-http", "http"):
        # MCP spec 2025-03-26+ — replaces the deprecated SSE transport.
        port = int(os.environ.get("PORT", "8000"))
        logger.info("Starting OpenCollab MCP on Streamable HTTP :%d", port)
        mcp.run(transport="streamable-http", host="0.0.0.0", port=port)
    elif transport == "sse":
        # Deprecated, kept for backward compatibility only.
        logger.warning("SSE transport is deprecated. Prefer 'streamable-http'.")
        port = int(os.environ.get("PORT", "8000"))
        mcp.run(transport="sse", host="0.0.0.0", port=port)
    else:
        logger.info("Starting OpenCollab MCP on stdio")
        mcp.run()


if __name__ == "__main__":
    main()
