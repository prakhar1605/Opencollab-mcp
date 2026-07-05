<div align="center">

# OpenCollab MCP

**Find your next open source contribution from your AI chat.**

[![PyPI version](https://img.shields.io/pypi/v/opencollab-mcp.svg?color=blue)](https://pypi.org/project/opencollab-mcp/)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![CI](https://github.com/prakhar1605/Opencollab-mcp/actions/workflows/ci.yml/badge.svg)](https://github.com/prakhar1605/Opencollab-mcp/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

6 focused tools. Works with Claude Desktop, Cursor, VS Code, or any MCP-compatible client.

</div>

---

## What it does

You ask your AI assistant something like:

> *"My GitHub is `@octocat`. Find me a good first issue I can actually pick up — make sure nobody's already working on it."*

OpenCollab gives the AI 6 tools that read the GitHub API. The AI uses them to:

1. **Find** issues matched to your skills.
2. **Evaluate** whether the repo is worth your time.
3. **Verify** the issue isn't already claimed.
4. **Plan** the PR with full context.

That's the whole loop: **find → evaluate → verify → plan**. OpenCollab does not generate text. Your AI client does the thinking; OpenCollab just gives it clean, real-time GitHub data.

> **v0.6.0 — relaunched lean.** Previous versions exposed 22 tools. Most went unused, and big tool lists hurt LLM routing. This release ships the 6 that earn their keep. The full 22-tool version is preserved on the [`v1-full`](https://github.com/prakhar1605/Opencollab-mcp/tree/v1-full) branch.

---

## Quick start

### Step 1 — Get a GitHub token

Go to [github.com/settings/tokens](https://github.com/settings/tokens) → **Generate new token (classic)** → tick `public_repo` → copy the token (it starts with `ghp_`).

### Step 2 — Add it to your AI client

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

> *"My GitHub username is `<your-username>`. Find me a good first issue I can pick up."*

If the AI runs `opencollab_match_me` and comes back with a list, you're set.

---

## What you can ask

These are real things the AI can answer once OpenCollab is connected:

- *"My GitHub is `@octocat` — find me a good first issue."*
- *"Find me a Python good-first-issue."*
- *"How healthy is `pandas-dev/pandas`? Is it worth contributing to?"*
- *"What's the impact tier of contributing to `tensorflow/tensorflow`?"*
- *"Is issue #123 in `facebook/react` still available, or has someone claimed it?"*
- *"Plan a PR for issue #456 in `owner/repo` — pull all the context the AI needs."*

The AI picks which tools to call based on what you ask.

---

## The 6 tools

<details open>
<summary><b>Discovery</b> — find issues to work on</summary>

| Tool | What it does |
|---|---|
| `opencollab_match_me` | Reads your GitHub profile, detects your top language, returns 10 matching good-first-issues — all in one call. |
| `opencollab_find_issues` | Up to 15 recent good-first-issues for a given language. |

</details>

<details open>
<summary><b>Evaluation</b> — score a repo before you invest time</summary>

| Tool | What it does |
|---|---|
| `opencollab_repo_health` | 0–100 contributor-friendliness score: activity, PR merge rate, community files, forks. |
| `opencollab_impact_estimator` | Impact tier (LOW → MASSIVE) based on stars + reach, plus a draft resume line. |

</details>

<details open>
<summary><b>Issue intelligence</b> — verify and plan a specific issue</summary>

| Tool | What it does |
|---|---|
| `opencollab_check_issue_availability` | Is the issue still open? Assigned? Already has a PR? Checks the timeline so you don't waste a weekend. |
| `opencollab_generate_pr_plan` | Bundles the issue body, comments, CONTRIBUTING.md, and repo layout for the AI to plan a fix. |

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
- **Parallel API calls.** The heavy tools (`match_me`, `repo_health`, `generate_pr_plan`) fan out their GitHub requests with `asyncio.gather`, so they're noticeably faster than sequential.
- **Pydantic-validated inputs.** Every tool input is a Pydantic model with `extra="forbid"`. Catches stray fields from LLM-generated tool calls before any logic runs.

---

## Authentication & rate limits

OpenCollab needs a GitHub token for two reasons:

1. **Higher rate limit.** Authenticated requests get 5,000/hour vs 60/hour unauthenticated.
2. **Some endpoints need auth.** A few tools (`/timeline`, etc.) may not work without it.

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
├── constants.py       # scoring thresholds & magic numbers
└── tools/
    ├── discovery.py   # 2 tools — finding issues
    ├── evaluation.py  # 2 tools — scoring a repo
    └── issues.py      # 2 tools — verifying & planning an issue

tests/                 # pytest suite
```

### Contributing

Issues and PRs are welcome. The codebase is small (~1000 lines) and intentionally easy to read. Every scoring threshold lives in `constants.py` so tuning is a one-line change. New tools follow the same pattern: a function in `tools/<category>.py`, a Pydantic input model in `models.py`, and a test in `tests/test_tools.py`.

The `main` branch is protected — please open a PR rather than pushing directly. CI runs on Python 3.10, 3.11, and 3.12.

---

## Roadmap

Already shipped (v0.6.0):

- 6 focused tools across discovery, evaluation, and issue intelligence
- PyPI release (`pip install opencollab-mcp` / `uvx opencollab-mcp`)
- 5-minute in-memory cache + parallel API calls
- pytest suite on Python 3.10/3.11/3.12 in CI
- Stdio (local) and streamable-HTTP (remote) transports
- Branch protection + required CI checks on `main`

Open ideas:

- `first_pr_generator` — chain `match_me` + `check_issue_availability` + `generate_pr_plan` into one prompt
- `track_my_prs` — list your open PRs with staleness nudges
- `skill_gap` — compare your skills to a repo's tech stack and tell you what to learn

If any of these sound interesting, [open an issue](https://github.com/prakhar1605/Opencollab-mcp/issues/new) — that's the fastest path in.

---

## Why only 6 tools?

Earlier versions shipped 22. In practice:

- LLMs route worse with crowded tool lists — they pick generic tools and miss the killer ones.
- Most of the 22 overlapped (5 different "find issues" variants, 3 different "score this repo" variants).
- The 6 that survive form a clean story: **find → evaluate → verify → plan**.

The full 22-tool catalogue still lives on the [`v1-full`](https://github.com/prakhar1605/Opencollab-mcp/tree/v1-full) branch if you want it.

---



## License

[MIT](LICENSE) — built by [Prakhar Pandey](https://github.com/prakhar1605), IIT Guwahati.

If OpenCollab helps you land your first PR, a ⭐ on the repo would mean a lot.
