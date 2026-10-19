# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.7.0] - 2026-10-08

Changes merged since v0.6.1. This is the first release published to PyPI since
0.5.0: 0.6.0 and 0.6.1 exist in the repository history but were never
tagged or published, so 0.7.0 also brings their changes to `pip` / `uvx` users. In
particular it fixes the startup crash of 0.5.0 under `mcp` 2.x ([#79](https://github.com/prakhar1605/Opencollab-mcp/issues/79)).

### Added
- Pull request template ([#199](https://github.com/prakhar1605/Opencollab-mcp/pull/199))
- Claude Code install instructions (`claude mcp add`) in the README ([#192](https://github.com/prakhar1605/Opencollab-mcp/pull/192))
- A test that checks all six tools are registered with read-only annotations ([#193](https://github.com/prakhar1605/Opencollab-mcp/pull/193))
- Contributors section in the README ([#187](https://github.com/prakhar1605/Opencollab-mcp/pull/187)) and an `.editorconfig` ([#188](https://github.com/prakhar1605/Opencollab-mcp/pull/188))
- `language` accepts up to three comma-separated languages for `opencollab_find_issues`; the response adds a `languages` list ([#165](https://github.com/prakhar1605/Opencollab-mcp/pull/165))
- A workflow publishes the Docker image to GitHub Container Registry on `v*` tags ([#164](https://github.com/prakhar1605/Opencollab-mcp/pull/164))
- `opencollab_generate_pr_plan` includes the repository's PR template ([#150](https://github.com/prakhar1605/Opencollab-mcp/pull/150))
- `check_issue_availability` warns about assigned issues with no activity for 60 days ([#157](https://github.com/prakhar1605/Opencollab-mcp/pull/157))
- `GH_TOKEN` is accepted as a fallback for `GITHUB_TOKEN` ([#159](https://github.com/prakhar1605/Opencollab-mcp/pull/159))
- `opencollab_generate_pr_plan` skips bot comments and reports `bot_comments_skipped` ([#148](https://github.com/prakhar1605/Opencollab-mcp/pull/148))
- `max_age_days` option (1–365, default 90) for `opencollab_find_issues` ([#149](https://github.com/prakhar1605/Opencollab-mcp/pull/149))
- `opencollab_generate_pr_plan` reports `issue.body_truncated` and `issue.body_length` ([#147](https://github.com/prakhar1605/Opencollab-mcp/pull/147))
- `--help` lists the supported environment variables ([#151](https://github.com/prakhar1605/Opencollab-mcp/pull/151))
- `SECURITY.md` with a vulnerability reporting policy ([#145](https://github.com/prakhar1605/Opencollab-mcp/pull/145))
- A warning is logged when the GitHub API rate limit is low ([#144](https://github.com/prakhar1605/Opencollab-mcp/pull/144))
- `limit` parameter (1–30) for `opencollab_match_me` ([#121](https://github.com/prakhar1605/Opencollab-mcp/pull/121))
- Troubleshooting section in the README ([#89](https://github.com/prakhar1605/Opencollab-mcp/pull/89))
- CI builds the package and smoke-tests the installed CLI ([#90](https://github.com/prakhar1605/Opencollab-mcp/pull/90))
- `limit` parameter (1–30) for `opencollab_find_issues` ([#42](https://github.com/prakhar1605/Opencollab-mcp/pull/42))
- `--version` and `-V` command-line flags ([#51](https://github.com/prakhar1605/Opencollab-mcp/pull/51))
- `/health` endpoint, plus cache TTL and eviction tests ([#44](https://github.com/prakhar1605/Opencollab-mcp/pull/44))
- Difficulty option for `opencollab_match_me`, matching `find_issues` ([#39](https://github.com/prakhar1605/Opencollab-mcp/pull/39))
- Difficulty filter for issue discovery ([#27](https://github.com/prakhar1605/Opencollab-mcp/pull/27))

### Changed
- `repo_health` scoring thresholds moved to named constants in `constants.py`, behaviour unchanged ([#146](https://github.com/prakhar1605/Opencollab-mcp/pull/146))
- CI also tests Python 3.13 ([#41](https://github.com/prakhar1605/Opencollab-mcp/pull/41))
- `opencollab_impact_estimator` returns MCP structured output (`structuredContent` and an `outputSchema`) alongside the unchanged JSON text; GitHub errors are returned as tool errors ([#163](https://github.com/prakhar1605/Opencollab-mcp/pull/163))
- PyPI project page links to the changelog and documentation ([#143](https://github.com/prakhar1605/Opencollab-mcp/pull/143))
- `opencollab_match_me` picks the top language by number of repositories, not repository disk size ([#125](https://github.com/prakhar1605/Opencollab-mcp/pull/125))
- Unknown command-line arguments are reported with a warning instead of being silently ignored ([#126](https://github.com/prakhar1605/Opencollab-mcp/pull/126))
- README tool table, Docker notes and roadmap brought up to date ([#87](https://github.com/prakhar1605/Opencollab-mcp/pull/87))
- Migrated to the MCP 2.x server API, replacing the temporary `mcp<2` pin ([#30](https://github.com/prakhar1605/Opencollab-mcp/pull/30), [#28](https://github.com/prakhar1605/Opencollab-mcp/pull/28))
- Reuse one `httpx.AsyncClient` instead of creating one per request ([#24](https://github.com/prakhar1605/Opencollab-mcp/pull/24))
- Version is now derived from package metadata instead of being copied ([#23](https://github.com/prakhar1605/Opencollab-mcp/pull/23))
- `opencollab_match_me` now says so when it falls back to Python ([#25](https://github.com/prakhar1605/Opencollab-mcp/pull/25))
- Contributing guidelines are also looked up in `.github/` and `docs/` ([#38](https://github.com/prakhar1605/Opencollab-mcp/pull/38))

### Fixed
- Date-dependent tests are now relative to the current time, so they no longer fail as the calendar moves on ([#196](https://github.com/prakhar1605/Opencollab-mcp/pull/196))
- Transient GitHub server failures are retried once ([#158](https://github.com/prakhar1605/Opencollab-mcp/pull/158))
- `check_issue_availability` explains why a closed issue is unavailable ([#160](https://github.com/prakhar1605/Opencollab-mcp/pull/160))
- Archived repositories are excluded from issue discovery ([#161](https://github.com/prakhar1605/Opencollab-mcp/pull/161))
- Bot pull requests are excluded from contributor merge statistics ([#162](https://github.com/prakhar1605/Opencollab-mcp/pull/162))
- Unsupported transport settings are rejected with a clear error ([#152](https://github.com/prakhar1605/Opencollab-mcp/pull/152))
- GitHub transport failures give actionable guidance ([#153](https://github.com/prakhar1605/Opencollab-mcp/pull/153))
- Expected GitHub client errors are logged without tracebacks ([#154](https://github.com/prakhar1605/Opencollab-mcp/pull/154))
- The `language` input is bounded before the GitHub search ([#155](https://github.com/prakhar1605/Opencollab-mcp/pull/155))
- Discovery searches exclude issues that are already assigned ([#156](https://github.com/prakhar1605/Opencollab-mcp/pull/156))
- `check_issue_availability` reports `wontfix`/`duplicate`/`invalid` issues as unavailable and warns on `blocked`/`needs-triage` labels ([#142](https://github.com/prakhar1605/Opencollab-mcp/pull/142))
- Whitespace around `GITHUB_TOKEN` (e.g. a trailing newline) no longer breaks every request ([#123](https://github.com/prakhar1605/Opencollab-mcp/pull/123))
- GitHub 422 validation errors are shown as a readable message instead of raw JSON ([#128](https://github.com/prakhar1605/Opencollab-mcp/pull/128))
- `check_issue_availability` marks locked issues as unavailable ([#124](https://github.com/prakhar1605/Opencollab-mcp/pull/124))
- `repo_health` handles repositories with Issues disabled ([#127](https://github.com/prakhar1605/Opencollab-mcp/pull/127))
- `impact_estimator` flags archived repositories and gives them no resume line ([#88](https://github.com/prakhar1605/Opencollab-mcp/pull/88))
- `repo_health` flags archived repositories as read-only ([#78](https://github.com/prakhar1605/Opencollab-mcp/pull/78))
- `generate_pr_plan` rejects pull request numbers ([#77](https://github.com/prakhar1605/Opencollab-mcp/pull/77))
- Issue tools accept a numeric `issue_number` such as `123` ([#76](https://github.com/prakhar1605/Opencollab-mcp/pull/76))
- An invalid `PORT` exits with a one-line error, and an unknown `OPENCOLLAB_LOG_LEVEL` logs a warning ([#75](https://github.com/prakhar1605/Opencollab-mcp/pull/75))
- Docker health check now uses the configured `PORT` instead of always 8000 ([#73](https://github.com/prakhar1605/Opencollab-mcp/pull/73))
- `check_issue_availability` now reports timeline failures and reads 100 events ([#43](https://github.com/prakhar1605/Opencollab-mcp/pull/43))
- Issues are marked unavailable when a linked PR was already merged ([#40](https://github.com/prakhar1605/Opencollab-mcp/pull/40))
- `repo_health` keeps working without community profile data ([#37](https://github.com/prakhar1605/Opencollab-mcp/pull/37))
- Stale availability checks, fork-skewed matching and unvalidated path input ([#36](https://github.com/prakhar1605/Opencollab-mcp/pull/36))
- A rate-limited 403 is now told apart from a denied one ([#26](https://github.com/prakhar1605/Opencollab-mcp/pull/26))
- Language is quoted and pull requests are excluded in both search queries ([#22](https://github.com/prakhar1605/Opencollab-mcp/pull/22))
