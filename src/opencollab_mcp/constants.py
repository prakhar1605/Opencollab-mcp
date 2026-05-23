"""Centralized constants and tuning thresholds for OpenCollab MCP.

Pulling these out of individual tools keeps scoring logic self-documenting
and makes tuning a one-line change instead of a hunt-and-peck across files.
"""

# ---- API / network ----
GITHUB_API_BASE = "https://api.github.com"
DEFAULT_TIMEOUT = 30.0
USER_AGENT = "opencollab-mcp/0.6.0"
GITHUB_API_VERSION = "2022-11-28"

# ---- Caching ----
# Short-lived cache to soften GitHub rate-limit pressure for repeat lookups
# inside a single conversation. Profile/repo metadata rarely changes mid-chat.
CACHE_TTL_SECONDS = 300  # 5 minutes
CACHE_MAX_ENTRIES = 256

# ---- Search windows (days) ----
RECENT_ISSUES_DAYS = 90

# ---- repo_health thresholds ----
HEALTH_VERDICT_EXCELLENT = 75
HEALTH_VERDICT_GOOD = 50
HEALTH_VERDICT_FAIR = 30

# ---- impact_estimator star tiers ----
IMPACT_MASSIVE_STARS = 50_000
IMPACT_HIGH_STARS = 10_000
IMPACT_MEDIUM_STARS = 1_000
IMPACT_MODERATE_STARS = 100
