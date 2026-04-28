<div align="center">

# OpenCollab MCP

**An MCP server that helps you find good first issues to contribute to — using your AI assistant.**

[![PyPI version](https://img.shields.io/pypi/v/opencollab-mcp.svg?color=blue)](https://pypi.org/project/opencollab-mcp/)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![CI](https://github.com/prakhar1605/Opencollab-mcp/actions/workflows/ci.yml/badge.svg)](https://github.com/prakhar1605/Opencollab-mcp/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

Works with Claude Desktop, Cursor, VS Code, or any MCP-compatible client.

</div>

---

## What it does

You ask your AI assistant something like:

> *"Find me a Python good-first-issue I can finish this weekend, and make sure nobody's working on it."*

OpenCollab gives the AI 22 tools that read the GitHub API. The AI uses them to:

1. Look at your GitHub profile to figure out your skills.
2. Search for matching open issues.
3. Filter out issues that already have an assignee or open pull request.
4. Hand the result back so the AI can recommend something specific.

That's it. **OpenCollab does not generate text.** Your AI client does the thinking; OpenCollab just gives it clean, real-time GitHub data.

---

## Quick start

### Step 1 — Get a GitHub token

Go to [github.com/settings/tokens](https://github.com/settings/tokens) → **Generate new token (classic)** → tick `public_repo` → copy the token (it starts with `ghp_`).

### Step 2 — Add it to your AI client

> An MCP server has **two install steps**: get the code on your machine, and tell your AI client where to find it. The recipes below do both.

<details open>
<summary><b>Claude Desktop</b> (recommended)</summary>

Open your config file:

- **macOS:** `~/Library/Application Support/Claude/claude_desktop_config.json`
- **Windows:** `%APPDATA%\Claude\claude_desktop_config.json`

Paste this (replace `your_token_here` with the token from Step 1):

```json
{
  "mcpServers": {
    "opencollab": {
      "command": "uvx",
      "args": ["opencollab-mcp"],
      "env": {
        "GITHUB_TOKEN": "your_token_here"
      }
    }
  }
}
```

Restart Claude Desktop. You're done.

> Requires [`uv`](https://docs.astral.sh/uv/) (`brew install uv` on macOS, `pipx install uv` elsewhere). `uvx` will pull `opencollab-mcp` from PyPI on first launch.

</details>

<details>
<summary><b>Cursor / VS Code</b></summary>

Same JSON as above, but in your client's MCP config file (`.cursor/mcp.json` for Cursor).

</details>

<details>
<summary><b>Plain pip (no uv)</b></summary>

```bash
pip install opencollab-mcp
```

Then in your client config, change `command` to the binary that pip put on your PATH:

```json
{
  "mcpServers": {
    "opencollab": {
      "command": "opencollab-mcp",
      "env": {
        "GITHUB_TOKEN": "your_token_here"
      }
    }
  }
}
```

Note: if you switch Python versions or virtualenvs, the `opencollab-mcp` binary may disappear and you'll need to `pip install` again. `uvx` avoids this.

</details>

<details>
<summary><b>Docker (for remote / streamable-HTTP setups)</b></summary>

```bash
docker build -t opencollab-mcp .
docker run -e GITHUB_TOKEN=ghp_xxx -p 8000:8000 opencollab-mcp
```

The container runs as a non-root user with `TRANSPORT=streamable-http` on port 8000.

</details>

### Step 3 — Try it

Open your AI client and ask:

> *"My GitHub username is `<your-username>`. Am I ready to contribute to open source?"*

If the AI starts running tools and gives you a readiness score, it's working.

---

## What you can ask

These are real things the AI can answer once OpenCollab is connected:

- *"Am I ready to contribute to open source? My username is `<your-username>`."*
- *"Find me a Python good-first-issue I can finish this weekend."*
- *"Is issue #123 in `facebook/react` still available, or has someone claimed it?"*
- *"How healthy is the `pandas-dev/pandas` repo? Is it worth contributing to?"*
- *"Compare `langchain-ai/langchain` vs `run-llama/llama_index` for first-time contributors."*
- *"Is `tensorflow/tensorflow` still active? How many commits in the last 30 days?"*
- *"How complex is issue #5432 in `pytorch/pytorch`?"*
- *"Plan a PR for issue #456 in `owner/repo` — pull all the context the AI needs."*
- *"What's the tech stack of `tiangolo/fastapi`?"*
- *"Show me the top contributors of `microsoft/vscode`."*

The AI picks which tools to call based on what you ask.

---

## All 22 tools

OpenCollab exposes 22 tools, organized into four groups. You don't usually call them by name — your AI client picks the right ones automatically.

<details>
<summary><b>Discovery (6 tools)</b> — find issues and repos to contribute to</summary>

| Tool | What it does |
|---|---|
| `opencollab_match_me` | One-shot: reads your GitHub profile, picks your top language, returns 10 matching good-first-issues |
| `opencollab_find_issues` | Returns up to 15 recent good-first-issues for a given language |
| `opencollab_trending_repos` | Trending repos (recent + many good-first-issues) for a language |
| `opencollab_similar_repos` | Given a repo you like, find others in the same domain |
| `opencollab_find_mentor_repos` | Repos with `gsoc`, `outreachy`, `mentorship`, or `hacktoberfest` topics |
| `opencollab_weekend_issues` | Small issues (docs, typos, tests) with short bodies and few comments |

</details>

<details>
<summary><b>Evaluation (7 tools)</b> — score a repo before you invest time</summary>

| Tool | What it does |
|---|---|
| `opencollab_repo_health` | 0–100 score on contributor-friendliness (activity, merge rate, community files) |
| `opencollab_contribution_readiness` | Checks for README, CONTRIBUTING, CI, Dockerfile, tests dir, templates |
| `opencollab_impact_estimator` | Tier (LOW / MODERATE / MEDIUM / HIGH / MASSIVE) based on stars + a draft resume line |
| `opencollab_repo_activity_pulse` | 30-day commit count and momentum (growing / stable / declining / inactive) |
| `opencollab_compare_repos` | Side-by-side comparison of two repos with a recommendation |
| `opencollab_repo_languages` | Language breakdown by % of bytes |
| `opencollab_dependency_check` | Reads package.json / pyproject.toml / requirements.txt etc. to show the tech stack |

</details>

<details>
<summary><b>Issue intelligence (6 tools)</b> — understand a specific issue before you start</summary>

| Tool | What it does |
|---|---|
| `opencollab_check_issue_availability` | Is the issue assigned? Is there an open PR for it? |
| `opencollab_issue_complexity` | 1–10 difficulty score from body length, comments, labels, code blocks |
| `opencollab_stale_issue_finder` | Open issues older than 30 days with no assignee — hidden wins |
| `opencollab_label_explorer` | Lists every label in a repo and flags the beginner-friendly ones |
| `opencollab_recent_prs` | Last 10 merged PRs with average days-to-merge |
| `opencollab_generate_pr_plan` | Bundles the issue body, comments, CONTRIBUTING.md, and repo layout for the AI to plan a fix |

</details>

<details>
<summary><b>Profile (3 tools)</b> — analyze a GitHub user</summary>

| Tool | What it does |
|---|---|
| `opencollab_analyze_profile` | Top languages, topics, recent activity types, notable repos |
| `opencollab_first_timer_score` | 0–100 readiness score for open source with personalized tips |
| `opencollab_contributor_leaderboard` | Top 10 contributors of a repo with commit counts |

</details>

---

## How it works

```
You ask Claude → Claude picks tools → OpenCollab hits GitHub API → JSON back to Claude → Claude answers in plain English
```

A few design choices worth knowing:

- **No AI inference on our end.** OpenCollab is a thin wrapper over the GitHub REST API. Your AI client (Claude / Cursor / etc.) does all the reasoning. Cost to run OpenCollab: $0.
- **Runs locally by default.** Stdio transport — no servers, no telemetry. Your token never leaves your machine.
- **5-minute in-memory cache.** Repeat lookups in the same conversation don't re-hit GitHub. Helps stay under rate limits.
- **Parallel API calls.** The heavy tools (`match_me`, `repo_health`, `generate_pr_plan`, etc.) fire their GitHub requests with `asyncio.gather`, so they're noticeably faster than sequential.
- **Pydantic-validated inputs.** Every tool input is a Pydantic model with `extra="forbid"`. Catches stray fields from LLM-generated tool calls before any logic runs.

---

## Authentication & rate limits

OpenCollab needs a GitHub token for two reasons:

1. **Higher rate limit.** Authenticated requests get 5,000/hour vs 60/hour unauthenticated.
2. **Some endpoints need auth.** A few tools (`/timeline`, contributor stats) may not work without it.

Scopes needed: just `public_repo`. OpenCollab never writes anything — it's all reads.

---

## Develop

```bash
git clone https://github.com/prakhar1605/Opencollab-mcp.git
cd Opencollab-mcp
pip install -e ".[dev]"
export GITHUB_TOKEN="ghp_xxx"

# Run the server (stdio mode, for piping into MCP clients)
python -m opencollab_mcp

# Run the test suite
pytest -v

# Lint
ruff check src tests

# Inspect interactively in the MCP Inspector
npx @modelcontextprotocol/inspector python -m opencollab_mcp
```

### Project layout

```
src/opencollab_mcp/
├── server.py          # entry point, transport selection (stdio / streamable-http)
├── github_client.py   # cached httpx wrapper, friendly error mapping
├── helpers.py         # date math, base64 decode, issue-number parser
├── models.py          # Pydantic input models
├── constants.py       # all scoring thresholds & magic numbers
└── tools/
    ├── discovery.py   # 6 tools — finding issues and repos
    ├── evaluation.py  # 7 tools — scoring a repo
    ├── issues.py      # 6 tools — analyzing a specific issue
    └── profile.py     # 3 tools — analyzing a user

tests/                 # pytest suite (45 tests, run with `pytest`)
```

### Contributing

Issues and PRs are welcome. The codebase is small (~1500 lines) and intentionally easy to read. Every scoring threshold lives in `constants.py` so tuning is a one-line change. New tools follow the same pattern: a function in `tools/<category>.py`, a Pydantic input model in `models.py`, and a test in `tests/test_tools.py`.

The `main` branch is protected — please open a PR rather than pushing directly. CI runs on Python 3.10, 3.11, and 3.12.

---

## Roadmap

Already shipped:

- 22 tools across discovery, evaluation, issue intel, and profile
- PyPI release (`pip install opencollab-mcp` / `uvx opencollab-mcp`)
- 5-minute in-memory cache + parallel API calls
- 45-test pytest suite running on Python 3.10/3.11/3.12 in CI
- Stdio (local) and streamable-HTTP (remote) transports
- Branch protection + required CI checks on `main`

Open ideas:

- `first_pr_generator` — chain `match_me` + `generate_pr_plan` into one prompt
- `track_my_prs` — list your open PRs with staleness nudges
- `skill_gap` — compare your skills to a repo's tech stack and tell you what to learn

If any of these sound interesting, [open an issue](https://github.com/prakhar1605/Opencollab-mcp/issues/new) — that's the fastest path in.

---

## Contributors

- [@Shashank-Tripathi-07](https://github.com/Shashank-Tripathi-07) — flagged a double-counting bug in `issue_complexity`'s code-block scoring, and pointed out that `main` had no branch protection (which has since been fixed).

---

## License

[MIT](LICENSE) — built by [Prakhar Pandey](https://github.com/prakhar1605), IIT Guwahati.

If OpenCollab helps you land your first PR, a ⭐ on the repo would mean a lot.
