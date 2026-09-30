# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

Changes merged since v0.6.1.

### Added
- `--version` and `-V` command-line flags ([#51](https://github.com/prakhar1605/Opencollab-mcp/pull/51))
- `/health` endpoint, plus cache TTL and eviction tests ([#44](https://github.com/prakhar1605/Opencollab-mcp/pull/44))
- Difficulty option for `opencollab_match_me`, matching `find_issues` ([#39](https://github.com/prakhar1605/Opencollab-mcp/pull/39))
- Difficulty filter for issue discovery ([#27](https://github.com/prakhar1605/Opencollab-mcp/pull/27))

### Changed
- Migrated to the MCP 2.x server API, replacing the temporary `mcp<2` pin ([#30](https://github.com/prakhar1605/Opencollab-mcp/pull/30), [#28](https://github.com/prakhar1605/Opencollab-mcp/pull/28))
- Reuse one `httpx.AsyncClient` instead of creating one per request ([#24](https://github.com/prakhar1605/Opencollab-mcp/pull/24))
- Version is now derived from package metadata instead of being copied ([#23](https://github.com/prakhar1605/Opencollab-mcp/pull/23))
- `opencollab_match_me` now says so when it falls back to Python ([#25](https://github.com/prakhar1605/Opencollab-mcp/pull/25))
- Contributing guidelines are also looked up in `.github/` and `docs/` ([#38](https://github.com/prakhar1605/Opencollab-mcp/pull/38))

### Fixed
- Docker health check now uses the configured `PORT` instead of always 8000 ([#73](https://github.com/prakhar1605/Opencollab-mcp/pull/73))
- `check_issue_availability` now reports timeline failures and reads 100 events ([#43](https://github.com/prakhar1605/Opencollab-mcp/pull/43))
- Issues are marked unavailable when a linked PR was already merged ([#40](https://github.com/prakhar1605/Opencollab-mcp/pull/40))
- `repo_health` keeps working without community profile data ([#37](https://github.com/prakhar1605/Opencollab-mcp/pull/37))
- Stale availability checks, fork-skewed matching and unvalidated path input ([#36](https://github.com/prakhar1605/Opencollab-mcp/pull/36))
- A rate-limited 403 is now told apart from a denied one ([#26](https://github.com/prakhar1605/Opencollab-mcp/pull/26))
- Language is quoted and pull requests are excluded in both search queries ([#22](https://github.com/prakhar1605/Opencollab-mcp/pull/22))
