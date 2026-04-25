"""Centralized constants and tuning thresholds for OpenCollab MCP.

Pulling these out of individual tools keeps scoring logic self-documenting
and makes tuning a one-line change instead of a hunt-and-peck across files.
"""

# ---- API / network ----
GITHUB_API_BASE = "https://api.github.com"
DEFAULT_TIMEOUT = 30.0
USER_AGENT = "opencollab-mcp/0.5.0"
GITHUB_API_VERSION = "2022-11-28"

# ---- Caching ----
# Short-lived cache to soften GitHub rate-limit pressure for repeat lookups
# inside a single conversation. Profile/repo metadata rarely changes mid-chat.
CACHE_TTL_SECONDS = 300  # 5 minutes
CACHE_MAX_ENTRIES = 256

# ---- Search windows (days) ----
RECENT_ISSUES_DAYS = 90
RECENT_TRENDING_DAYS = 60
MENTOR_REPOS_DAYS = 180
WEEKEND_ISSUES_DAYS = 60

# ---- repo_health thresholds ----
HEALTH_VERDICT_EXCELLENT = 75
HEALTH_VERDICT_GOOD = 50
HEALTH_VERDICT_FAIR = 30

# ---- impact_estimator star tiers ----
IMPACT_MASSIVE_STARS = 50_000
IMPACT_HIGH_STARS = 10_000
IMPACT_MEDIUM_STARS = 1_000
IMPACT_MODERATE_STARS = 100

# ---- first_timer_score readiness levels ----
READINESS_READY = 80
READINESS_ALMOST = 60
READINESS_GETTING_STARTED = 40

# ---- issue complexity thresholds ----
COMPLEXITY_BEGINNER = 3
COMPLEXITY_INTERMEDIATE = 5
COMPLEXITY_ADVANCED = 7

# ---- label keyword sets ----
BEGINNER_LABEL_KEYWORDS = frozenset({
    "good first issue", "beginner", "easy", "starter", "help wanted",
    "first-timers-only", "up-for-grabs", "newcomer", "low-hanging-fruit",
})

EASY_ISSUE_LABELS = frozenset({
    "good first issue", "beginner", "easy", "starter", "help wanted",
    "low-hanging-fruit", "trivial", "documentation",
})

HARD_ISSUE_LABELS = frozenset({
    "critical", "complex", "breaking", "architecture", "security",
    "performance", "refactor",
})

QUICK_WEEKEND_LABELS = (
    "documentation", "docs", "typo", "test", "tests",
    "chore", "style", "cleanup", "refactor", "translation",
)

DEPENDENCY_FILES = (
    "package.json", "pyproject.toml", "requirements.txt", "go.mod",
    "Cargo.toml", "Gemfile", "setup.py", "setup.cfg",
)
