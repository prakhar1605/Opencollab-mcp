# Changelog

All notable changes to this project will be documented here.
The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.5.0] - 2026-04-25

### Added
- 5-minute TTL cache on GitHub API responses (`cachetools.TTLCache`)
- Module-level shared `httpx.AsyncClient` for connection reuse
- Streamable HTTP transport support (MCP spec 2025-03-26+)
- `OPENCOLLAB_LOG_LEVEL` env var for runtime log control
- Input sanitization for language strings
- Proper rate-limit error messages with reset timestamps
- `tests/` directory with smoke tests
- GitHub Actions CI workflow
- `CONTRIBUTING.md`, `CODE_OF_CONDUCT.md`, `SECURITY.md`
- Issue and PR templates
- `.env.example`

### Changed
- **BREAKING:** Consolidated 22 tools → 8 tools. Old tool names removed.
  - `opencollab_match_me` (hero — analyze + find issues in one call)
  - `opencollab_repo_health` (health + impact + activity + deps + languages)
  - `opencollab_check_issue` (availability + complexity)
  - `opencollab_plan_pr` (full PR planning context)
  - `opencollab_find_opportunities` (issues/repos with `mode` filter)
  - `opencollab_compare_repos` (side-by-side)
  - `opencollab_explore_repo` (labels + contributors + recent PRs)
  - `opencollab_first_timer_score` (readiness rating)
- Rebalanced `first_timer_score` weights so max = 100 exactly
- Dockerfile now runs as non-root user
- README rewritten — outcome-focused tagline

### Fixed
- `repo_activity_pulse` no longer returns false "inactive" status when GitHub
  is still computing stats (handles 202 Accepted)
- `_parse_issue_number` now accepts `#123`, `123`, and whitespace
- `plan_pr` rejects pull requests passed as issue numbers
- Removed redundant Python-side filtering already done by GitHub API
- Removed `dist/` and `.DS_Store` from git tracking

### Removed
- 14 redundant tools (logic preserved as private helpers, exposed via the 8 consolidated tools)
- `dist/` build artifacts from git tracking
- Trailing whitespace in Dockerfile
- Pointless `ENV GITHUB_TOKEN=""` from Dockerfile

## [0.4.0] - 2026-03-10

### Added
- Initial release with 22 tools across discovery, scoring, profile, and PR planning categories.
