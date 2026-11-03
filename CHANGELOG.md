# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

Changes merged since v0.6.1.

### Added
- Optional `exclude_repos` filter for `find_issues`, with up to 10 validated `owner/name` entries ([#175](https://github.com/prakhar1605/Opencollab-mcp/issues/175)).
- Optional `sort` parameter for `find_issues` (`newest` [default], `recently_updated`, `least_discussed`) mapped to GitHub search sorting ([#177](https://github.com/prakhar1605/Opencollab-mcp/issues/177)).
- `find_issues` reports nullable `updated_days_ago` using the existing timestamp helper.
- Pure `parse_github_url` helper for repository, issue and pull request URLs, with validation and no network calls ([#185](https://github.com/prakhar1605/Opencollab-mcp/issues/185)).
- `--version` and `-V` command-line flags ([#51](https://github.com/prakhar1605/Opencollab-mcp/pull/51))
- `/health` endpoint, plus cache TTL and eviction tests ([#44](https://github.com/prakhar1605/Opencollab-mcp/pull/44))
- Difficulty option for `opencollab_match_me`, matching `find_issues` ([#39](https://github.com/prakhar1605/Opencollab-mcp/pull/39))
- Difficulty filter for issue discovery ([#27](https://github.com/prakhar1605/Opencollab-mcp/pull/27))

### Changed
- CI test job now also runs on `windows-latest` and `macos-latest` (Python 3.12 only); Ubuntu still covers Python 3.10-3.13 ([#183](https://github.com/prakhar1605/Opencollab-mcp/issues/183))
- `opencollab_impact_estimator` now returns MCP structured output (`structuredContent` plus a published `outputSchema`) while keeping the JSON text content; GitHub errors are now returned as tool errors (`isError`) ([#141](https://github.com/prakhar1605/Opencollab-mcp/issues/141))
- Migrated to the MCP 2.x server API, replacing the temporary `mcp<2` pin ([#30](https://github.com/prakhar1605/Opencollab-mcp/pull/30), [#28](https://github.com/prakhar1605/Opencollab-mcp/pull/28))
- Reuse one `httpx.AsyncClient` instead of creating one per request ([#24](https://github.com/prakhar1605/Opencollab-mcp/pull/24))
- Version is now derived from package metadata instead of being copied ([#23](https://github.com/prakhar1605/Opencollab-mcp/pull/23))
- `opencollab_match_me` now says so when it falls back to Python ([#25](https://github.com/prakhar1605/Opencollab-mcp/pull/25))
- Contributing guidelines are also looked up in `.github/` and `docs/` ([#38](https://github.com/prakhar1605/Opencollab-mcp/pull/38))

### Fixed
- Version drift test reads package sources as UTF-8 so it passes on Windows locales that are not UTF-8 by default ([#183](https://github.com/prakhar1605/Opencollab-mcp/issues/183))
- `opencollab_match_me` now reports a partial repository scan with `repos_analyzed`, `repos_total` and a note when the profile has more repositories than the returned page ([#180](https://github.com/prakhar1605/Opencollab-mcp/issues/180))
- `opencollab_check_issue_availability` now paginates issue timelines via shared `github_get_all` `Link: rel="next"` pagination (up to 5 pages / 500 events) instead of truncating silently at 100 events, reporting `timeline_truncated: true` and softening `reason` when the cap is hit ([#203](https://github.com/prakhar1605/Opencollab-mcp/issues/203))
- `opencollab_check_issue_availability` now distinguishes closing PRs from plain issue mentions: uses GraphQL `closedByPullRequestsReferences` when authenticated, falls back to closing-keyword parsing on REST timeline events when unauthenticated or when GraphQL fails, reports non-closing mentions separately in `mentioned_in_prs` without blocking availability, and exposes `linked_prs_source` ([#204](https://github.com/prakhar1605/Opencollab-mcp/issues/204))
- Docker health check now uses the configured `PORT` instead of always 8000 ([#73](https://github.com/prakhar1605/Opencollab-mcp/pull/73))
- `check_issue_availability` now reports timeline failures and reads 100 events ([#43](https://github.com/prakhar1605/Opencollab-mcp/pull/43))
- Issues are marked unavailable when a linked PR was already merged ([#40](https://github.com/prakhar1605/Opencollab-mcp/pull/40))
- `repo_health` keeps working without community profile data ([#37](https://github.com/prakhar1605/Opencollab-mcp/pull/37))
- Stale availability checks, fork-skewed matching and unvalidated path input ([#36](https://github.com/prakhar1605/Opencollab-mcp/pull/36))
- A rate-limited 403 is now told apart from a denied one ([#26](https://github.com/prakhar1605/Opencollab-mcp/pull/26))
- Language is quoted and pull requests are excluded in both search queries ([#22](https://github.com/prakhar1605/Opencollab-mcp/pull/22))
