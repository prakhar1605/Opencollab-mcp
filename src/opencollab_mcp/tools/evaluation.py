"""Evaluation & scoring tools."""

from __future__ import annotations

import asyncio
import json

from mcp.server.fastmcp import FastMCP

from ..github_client import github_get, handle_github_error
from ..helpers import days_ago, decode_base64_content
from ..models import RepoInput, CompareInput
from ..constants import (
    HEALTH_VERDICT_EXCELLENT,
    HEALTH_VERDICT_GOOD,
    HEALTH_VERDICT_FAIR,
    IMPACT_MASSIVE_STARS,
    IMPACT_HIGH_STARS,
    IMPACT_MEDIUM_STARS,
    IMPACT_MODERATE_STARS,
    DEPENDENCY_FILES,
)


def register(mcp: FastMCP) -> None:

    @mcp.tool(
        name="opencollab_repo_health",
        annotations={
            "title": "Score repository contributor-friendliness",
            "readOnlyHint": True, "destructiveHint": False,
            "idempotentHint": True, "openWorldHint": True,
        },
    )
    async def opencollab_repo_health(params: RepoInput) -> str:
        """Score a repository's health and contributor-friendliness (0-100).

        Checks activity recency, community size, PR merge patterns, open
        issues, and whether the repo has essential contributor files.
        """
        path = f"/repos/{params.owner}/{params.repo}"
        try:
            repo, pulls, community = await asyncio.gather(
                github_get(path),
                github_get(f"{path}/pulls", {"state": "closed", "per_page": 30, "sort": "updated"}),
                github_get(f"{path}/community/profile"),
            )
        except Exception as e:
            return handle_github_error(e)

        score = 0
        details: dict[str, object] = {}

        last_push_days = days_ago(repo.get("pushed_at"))
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

        open_issues = repo.get("open_issues_count", 0)
        if 5 <= open_issues <= 500: score += 10
        elif open_issues > 0: score += 5
        details["open_issues"] = open_issues

        files_info = community.get("files", {}) if isinstance(community, dict) else {}
        community_files = {
            "contributing": files_info.get("contributing") is not None,
            "code_of_conduct": files_info.get("code_of_conduct") is not None,
            "license": files_info.get("license") is not None,
            "readme": files_info.get("readme") is not None,
            "issue_template": files_info.get("issue_template") is not None,
            "pull_request_template": files_info.get("pull_request_template") is not None,
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

        if score >= HEALTH_VERDICT_EXCELLENT:
            verdict = "Excellent — very contributor-friendly"
        elif score >= HEALTH_VERDICT_GOOD:
            verdict = "Good — solid project to contribute to"
        elif score >= HEALTH_VERDICT_FAIR:
            verdict = "Fair — some friction expected"
        else:
            verdict = "Low — may be abandoned or hard to contribute to"

        return json.dumps({
            "repo": f"{params.owner}/{params.repo}",
            "health_score": score,
            "verdict": verdict,
            "details": details,
        }, indent=2)

    @mcp.tool(
        name="opencollab_contribution_readiness",
        annotations={
            "title": "Check repo setup difficulty for contributors",
            "readOnlyHint": True, "destructiveHint": False,
            "idempotentHint": True, "openWorldHint": True,
        },
    )
    async def opencollab_contribution_readiness(params: RepoInput) -> str:
        """Check how easy it is to set up and contribute to a repository.

        Looks for Dockerfile, CI configs, documentation, contributing
        guide, and issue/PR templates. Returns a readiness checklist with
        difficulty rating.
        """
        path = f"/repos/{params.owner}/{params.repo}"
        try:
            repo, contents = await asyncio.gather(
                github_get(path),
                github_get(f"{path}/contents"),
            )
        except Exception as e:
            return handle_github_error(e)

        # Build a (name, type) map so we can distinguish files vs dirs.
        entries = {
            f.get("name", "").lower(): f.get("type")
            for f in contents if isinstance(f, dict)
        }

        # CI detection: check for actual CI config locations, not just
        # presence of a `.github` directory (which usually only means
        # issue templates).
        has_ci = False
        # File-based CI configs first (cheap).
        if any(name in entries for name in (".travis.yml", ".circleci", "azure-pipelines.yml", "jenkinsfile")):
            has_ci = True
        # GitHub Actions: only counts if .github/workflows actually exists.
        if not has_ci and ".github" in entries and entries[".github"] == "dir":
            try:
                gh_dir = await github_get(f"{path}/contents/.github")
                if any(
                    isinstance(f, dict) and f.get("name", "").lower() == "workflows"
                    and f.get("type") == "dir"
                    for f in gh_dir
                ):
                    has_ci = True
            except Exception:
                pass

        checks = {
            "has_readme": any(n.startswith("readme") for n in entries),
            "has_contributing": any("contributing" in n for n in entries),
            "has_license": any(n.startswith("license") for n in entries),
            "has_dockerfile": "dockerfile" in entries or "docker-compose.yml" in entries,
            "has_ci": has_ci,
            "has_tests_dir": any(n in entries for n in ("tests", "test", "spec", "__tests__")),
            "has_package_config": any(
                n in entries for n in
                ("package.json", "pyproject.toml", "setup.py", "cargo.toml", "go.mod")
            ),
            "has_code_of_conduct": any("code_of_conduct" in n for n in entries),
            "has_changelog": any(n.startswith("changelog") for n in entries),
        }
        passed = sum(checks.values())
        total = len(checks)
        if passed >= 8:
            difficulty = "Easy — well-documented, CI ready, contributor-friendly"
        elif passed >= 5:
            difficulty = "Moderate — some docs present, may need setup effort"
        elif passed >= 3:
            difficulty = "Hard — minimal docs, figure things out yourself"
        else:
            difficulty = "Very hard — barely any contributor infrastructure"

        # Issue/PR templates from .github/
        try:
            gh_dir = await github_get(f"{path}/contents/.github")
            gh_files = [f.get("name", "").lower() for f in gh_dir if isinstance(f, dict)]
            checks["has_issue_templates"] = any("issue" in n for n in gh_files)
            checks["has_pr_template"] = any("pull" in n for n in gh_files)
        except Exception:
            checks["has_issue_templates"] = False
            checks["has_pr_template"] = False

        return json.dumps({
            "repo": f"{params.owner}/{params.repo}",
            "difficulty": difficulty,
            "score": f"{passed}/{total}",
            "checks": checks,
            "primary_language": repo.get("language"),
            "default_branch": repo.get("default_branch", "main"),
        }, indent=2)

    @mcp.tool(
        name="opencollab_impact_estimator",
        annotations={
            "title": "Estimate contribution impact for a repo",
            "readOnlyHint": True, "destructiveHint": False,
            "idempotentHint": True, "openWorldHint": True,
        },
    )
    async def opencollab_impact_estimator(params: RepoInput) -> str:
        """Estimate the impact of contributing to a specific repository.

        Produces an impact tier (MASSIVE/HIGH/MEDIUM/LOW) and a suggested
        resume line.
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

        if stars >= IMPACT_MASSIVE_STARS:
            tier, reach = "MASSIVE", "millions of developers"
        elif stars >= IMPACT_HIGH_STARS:
            tier, reach = "HIGH", "tens of thousands of developers"
        elif stars >= IMPACT_MEDIUM_STARS:
            tier, reach = "MEDIUM", "thousands of developers"
        elif stars >= IMPACT_MODERATE_STARS:
            tier, reach = "MODERATE", "hundreds of developers"
        else:
            tier, reach = "LOW", "a growing community"

        repo_name = f"{params.owner}/{params.repo}"
        if stars >= IMPACT_MEDIUM_STARS:
            resume_line = f"Contributed to {repo_name} ({stars:,}+ stars), reaching {reach}"
        else:
            resume_line = f"Open-source contributor to {repo_name} — {description[:80]}"

        visibility = min(
            (min(stars // 500, 40) if stars >= 100 else 0)
            + (min(forks // 100, 20) if forks >= 50 else 0)
            + (min(watchers // 50, 20) if watchers >= 50 else 0)
            + (10 if open_issues >= 10 else 0)
            + (10 if repo.get("topics") else 0),
            100,
        )

        return json.dumps({
            "repo": repo_name,
            "impact_tier": tier,
            "estimated_reach": reach,
            "stars": stars,
            "forks": forks,
            "watchers": watchers,
            "open_issues": open_issues,
            "visibility_score": visibility,
            "suggested_resume_line": resume_line,
            "topics": repo.get("topics", []),
        }, indent=2)

    @mcp.tool(
        name="opencollab_repo_activity_pulse",
        annotations={
            "title": "Get repo activity pulse for last 30 days",
            "readOnlyHint": True, "destructiveHint": False,
            "idempotentHint": True, "openWorldHint": True,
        },
    )
    async def opencollab_repo_activity_pulse(params: RepoInput) -> str:
        """Get an activity pulse for a repo over the last 30 days.

        Shows commit frequency, PR activity, and whether the project is
        gaining or losing momentum.
        """
        path = f"/repos/{params.owner}/{params.repo}"
        try:
            repo, commit_activity, participation = await asyncio.gather(
                github_get(path),
                github_get(f"{path}/stats/commit_activity"),
                github_get(f"{path}/stats/participation"),
            )
        except Exception as e:
            return handle_github_error(e)

        # GitHub returns 202 with empty body while it computes stats — our
        # github_get normalizes that to {}. Handle both shapes.
        if not isinstance(commit_activity, list) or not commit_activity:
            return json.dumps({
                "repo": f"{params.owner}/{params.repo}",
                "message": "Activity stats are still being computed by GitHub. Try again in 30 seconds.",
                "stars": repo.get("stargazers_count", 0),
                "open_issues": repo.get("open_issues_count", 0),
                "last_push_days_ago": days_ago(repo.get("pushed_at")),
            }, indent=2)

        recent_4 = commit_activity[-4:] if len(commit_activity) >= 4 else commit_activity
        weekly_commits = [w.get("total", 0) for w in recent_4]
        total_30d = sum(weekly_commits)

        prev_4 = commit_activity[-8:-4] if len(commit_activity) >= 8 else []
        prev_total = sum(w.get("total", 0) for w in prev_4)

        if prev_total > 0:
            momentum_pct = round((total_30d - prev_total) / prev_total * 100, 1)
        elif total_30d > 0:
            momentum_pct = 100.0
        else:
            momentum_pct = 0.0

        if momentum_pct > 20:
            momentum = "Growing — more active than last month"
        elif momentum_pct > -20 and total_30d > 0:
            momentum = "Stable — consistent activity"
        elif total_30d == 0:
            momentum = "Inactive — no commits in 30 days"
        else:
            momentum = "Declining — less active than last month"

        owner_commits: list[int] = []
        all_commits: list[int] = []
        if isinstance(participation, dict):
            owner_commits = (participation.get("owner") or [])[-4:]
            all_commits = (participation.get("all") or [])[-4:]

        return json.dumps({
            "repo": f"{params.owner}/{params.repo}",
            "last_30_days": {
                "total_commits": total_30d,
                "weekly_breakdown": weekly_commits,
                "owner_weekly_commits": owner_commits,
                "all_weekly_commits": all_commits,
            },
            "momentum": momentum,
            "momentum_change_pct": momentum_pct,
            "stars": repo.get("stargazers_count", 0),
            "open_issues": repo.get("open_issues_count", 0),
            "last_push_days_ago": days_ago(repo.get("pushed_at")),
        }, indent=2)

    @mcp.tool(
        name="opencollab_compare_repos",
        annotations={
            "title": "Compare two repos for contributor-friendliness",
            "readOnlyHint": True, "destructiveHint": False,
            "idempotentHint": True, "openWorldHint": True,
        },
    )
    async def opencollab_compare_repos(params: CompareInput) -> str:
        """Compare two GitHub repositories side-by-side for
        contributor-friendliness.

        Returns stars, PR merge rate, activity, and a recommendation on
        which to contribute to.
        """
        async def _score(owner: str, repo: str) -> dict:
            try:
                r, pulls = await asyncio.gather(
                    github_get(f"/repos/{owner}/{repo}"),
                    github_get(
                        f"/repos/{owner}/{repo}/pulls",
                        {"state": "closed", "per_page": 20, "sort": "updated"},
                    ),
                )
            except Exception as e:
                return {"repo": f"{owner}/{repo}", "error": handle_github_error(e)}

            merge_rate = round(
                sum(1 for p in pulls if p.get("merged_at"))
                / max(len(pulls), 1) * 100,
                1,
            )
            return {
                "repo": f"{owner}/{repo}",
                "stars": r.get("stargazers_count", 0),
                "forks": r.get("forks_count", 0),
                "open_issues": r.get("open_issues_count", 0),
                "language": r.get("language"),
                "last_push_days_ago": days_ago(r.get("pushed_at")),
                "pr_merge_rate_pct": merge_rate,
                "topics": r.get("topics", [])[:6],
            }

        a, b = await asyncio.gather(
            _score(params.owner_a, params.repo_a),
            _score(params.owner_b, params.repo_b),
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
            if sa > sb:
                winner = f"{params.owner_a}/{params.repo_a}"
            elif sb > sa:
                winner = f"{params.owner_b}/{params.repo_b}"
        return json.dumps({"repo_a": a, "repo_b": b, "recommended": winner}, indent=2)

    @mcp.tool(
        name="opencollab_repo_languages",
        annotations={
            "title": "Get detailed language breakdown of a repo",
            "readOnlyHint": True, "destructiveHint": False,
            "idempotentHint": True, "openWorldHint": True,
        },
    )
    async def opencollab_repo_languages(params: RepoInput) -> str:
        """Get a detailed language breakdown for a repository.

        Shows percentage of each programming language used in the codebase.
        Helps you decide if you have the right skills before contributing.
        """
        try:
            languages = await github_get(
                f"/repos/{params.owner}/{params.repo}/languages"
            )
        except Exception as e:
            return handle_github_error(e)

        total_bytes = max(sum(languages.values()), 1)
        breakdown = [
            {
                "language": lang,
                "bytes": byte_count,
                "percentage": round(byte_count / total_bytes * 100, 1),
            }
            for lang, byte_count in sorted(
                languages.items(), key=lambda x: x[1], reverse=True
            )
        ]
        primary = breakdown[0]["language"] if breakdown else "Unknown"
        skills_needed = [lang_info["language"] for lang_info in breakdown if lang_info["percentage"] >= 5]
        return json.dumps({
            "repo": f"{params.owner}/{params.repo}",
            "primary_language": primary,
            "skills_needed": skills_needed,
            "total_languages": len(breakdown),
            "breakdown": breakdown,
        }, indent=2)

    @mcp.tool(
        name="opencollab_dependency_check",
        annotations={
            "title": "Check repo tech stack and dependencies",
            "readOnlyHint": True, "destructiveHint": False,
            "idempotentHint": True, "openWorldHint": True,
        },
    )
    async def opencollab_dependency_check(params: RepoInput) -> str:
        """Inspect a repo's tech stack by reading its dependency files.

        Checks package.json, pyproject.toml, requirements.txt, go.mod,
        Cargo.toml, and Gemfile to show what libraries and frameworks the
        project uses.
        """
        path = f"/repos/{params.owner}/{params.repo}"

        async def _try_fetch(filename: str) -> tuple[str, str | None]:
            try:
                content = await github_get(f"{path}/contents/{filename}")
                raw = decode_base64_content(content)
                return filename, raw[:3000] if raw else None
            except Exception:
                return filename, None

        # Fan-out: try every dependency file in parallel.
        results = await asyncio.gather(
            *(_try_fetch(df) for df in DEPENDENCY_FILES)
        )
        found = {fn: raw for fn, raw in results if raw}

        if not found:
            return json.dumps({
                "repo": f"{params.owner}/{params.repo}",
                "dependencies_found": False,
                "message": "No standard dependency files found in repo root",
            }, indent=2)

        deps_summary: dict = {}
        for filename, raw in found.items():
            if filename == "package.json":
                try:
                    pkg = json.loads(raw)
                    deps_summary["npm_dependencies"] = list((pkg.get("dependencies") or {}).keys())[:20]
                    deps_summary["npm_dev_dependencies"] = list((pkg.get("devDependencies") or {}).keys())[:15]
                except Exception:
                    deps_summary["package.json"] = "present but could not parse"
            elif filename == "requirements.txt":
                lines = [
                    line.strip().split("==")[0].split(">=")[0].split("[")[0]
                    for line in raw.splitlines()
                    if line.strip() and not line.startswith("#")
                ]
                deps_summary["python_requirements"] = lines[:25]
            elif filename == "pyproject.toml":
                deps_summary["pyproject.toml_preview"] = raw[:500]
            else:
                deps_summary[f"{filename}_preview"] = raw[:400]

        return json.dumps({
            "repo": f"{params.owner}/{params.repo}",
            "dependency_files": list(found.keys()),
            "parsed": deps_summary,
        }, indent=2)
