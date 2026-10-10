"""Centralized constants and tuning thresholds for OpenCollab MCP.

Pulling these out of individual tools keeps scoring logic self-documenting
and makes tuning a one-line change instead of a hunt-and-peck across files.
"""

from importlib.metadata import PackageNotFoundError, version

# ---- Version ----
# pyproject.toml is the single source of truth; everything else reads it back
# out of the installed distribution metadata. A hard-coded copy here is how the
# User-Agent came to advertise 0.6.0 while the package was 0.6.1.
try:
    __version__ = version("opencollab-mcp")
except PackageNotFoundError:
    # Running from a source tree that was never installed.
    __version__ = "0.0.0-dev"

# ---- API / network ----
GITHUB_API_BASE = "https://api.github.com"
DEFAULT_TIMEOUT = 30.0
USER_AGENT = f"opencollab-mcp/{__version__}"
GITHUB_API_VERSION = "2022-11-28"
GITHUB_RATE_LIMIT_WARNING_THRESHOLD = 10

# ---- Caching ----
# Short-lived cache to soften GitHub rate-limit pressure for repeat lookups
# inside a single conversation. Profile/repo metadata rarely changes mid-chat.
CACHE_TTL_SECONDS = 300  # 5 minutes
CACHE_MAX_ENTRIES = 256

# ---- Issue labels that mean "don't start yet" ----
# Compared case-insensitively, with "-" and "_" treated as spaces, so
# "needs-triage", "Needs Triage" and "needs_triage" all match.
# Blocking: the maintainers have already decided the issue won't be fixed as
# written, so a PR for it is wasted work.
BLOCKING_ISSUE_LABELS = frozenset({"wontfix", "won't fix", "duplicate", "invalid"})
# Warning: the work may still happen, but not before a maintainer weighs in.
WARNING_ISSUE_LABELS = frozenset({
    "blocked",
    "needs triage",
    "needs discussion",
    "on hold",
})

# ---- Search windows (days) ----
RECENT_ISSUES_DAYS = 90

# ---- repo_health scoring ----
# Activity recency (days ago -> score points)
HEALTH_PUSH_DAYS_RECENT = 7
HEALTH_PUSH_DAYS_ACTIVE = 30
HEALTH_PUSH_DAYS_STALE = 90
HEALTH_POINTS_PUSH_RECENT = 20
HEALTH_POINTS_PUSH_ACTIVE = 15
HEALTH_POINTS_PUSH_STALE = 8

# Stargazer tiers -> score points
HEALTH_STARS_HIGH = 1000
HEALTH_STARS_MEDIUM = 100
HEALTH_STARS_LOW = 10
HEALTH_POINTS_STARS_HIGH = 15
HEALTH_POINTS_STARS_MEDIUM = 10
HEALTH_POINTS_STARS_LOW = 5

# PR merge rate (percentage -> score points)
HEALTH_MERGE_RATE_HIGH = 60
HEALTH_MERGE_RATE_MEDIUM = 30
HEALTH_POINTS_MERGE_RATE_HIGH = 20
HEALTH_POINTS_MERGE_RATE_MEDIUM = 12
HEALTH_POINTS_MERGE_RATE_LOW = 5

# Open issue volume (healthy range and points)
HEALTH_OPEN_ISSUES_MIN = 5
HEALTH_OPEN_ISSUES_MAX = 500
HEALTH_POINTS_OPEN_ISSUES_OPTIMAL = 10
HEALTH_POINTS_OPEN_ISSUES_ANY = 5

# Fork tiers -> score points
HEALTH_FORKS_HIGH = 100
HEALTH_FORKS_MEDIUM = 20
HEALTH_FORKS_LOW = 5
HEALTH_POINTS_FORKS_HIGH = 10
HEALTH_POINTS_FORKS_MEDIUM = 6
HEALTH_POINTS_FORKS_LOW = 3

# Metadata bonuses and community files
HEALTH_POINTS_DESCRIPTION = 2
HEALTH_POINTS_TOPICS = 3
HEALTH_POINTS_PER_COMMUNITY_FILE = 4
HEALTH_MAX_COMMUNITY_FILES_POINTS = 20
HEALTH_MAX_SCORE = 100

# Verdict cut-offs
HEALTH_VERDICT_EXCELLENT = 75
HEALTH_VERDICT_GOOD = 50
HEALTH_VERDICT_FAIR = 30

# ---- impact_estimator star tiers ----
IMPACT_MASSIVE_STARS = 50_000
IMPACT_HIGH_STARS = 10_000
IMPACT_MEDIUM_STARS = 1_000
IMPACT_MODERATE_STARS = 100
