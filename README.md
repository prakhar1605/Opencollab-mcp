<div align="center">

# 🚀 OpenCollab MCP

### Land your first open source PR this weekend.

*Stop scrolling GitHub. Let AI find you a mergeable issue in 30 seconds — matched to your actual skills, in a repo that's actually alive.*

[![PyPI version](https://img.shields.io/pypi/v/opencollab-mcp.svg?color=blue)](https://pypi.org/project/opencollab-mcp/)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![CI](https://github.com/prakhar1605/Opencollab-mcp/actions/workflows/ci.yml/badge.svg)](https://github.com/prakhar1605/Opencollab-mcp/actions/workflows/ci.yml)
[![MIT License](https://img.shields.io/badge/License-MIT-green.svg)](https://choosealicense.com/licenses/mit/)
[![MCP Compatible](https://img.shields.io/badge/MCP-Compatible-purple.svg)](https://modelcontextprotocol.io)

**Works with Claude Desktop · Cursor · VS Code · any MCP client**

[Install in 60 seconds](#-install-in-60-seconds) · [See it in action](#-see-it-in-action) · [All 22 tools](#-all-22-tools)

</div>

---

## The problem

You want to contribute to open source. So you:

1. Scroll through hundreds of GitHub repos 😩
2. Find a "good first issue" — already taken 😤
3. Spend an hour understanding a dead repo 💀
4. Discover someone already opened a PR 😭
5. Give up, go back to tutorials 📺

**This loop is broken.** OpenCollab fixes it in one sentence to your AI assistant.

## The fix

```
"Find me a good first issue I can contribute to this weekend."
```

Claude calls OpenCollab → scans your GitHub profile → picks your strongest language → finds beginner-friendly issues in *active* repos with *no existing PR* → hands you the issue + full context to draft the fix.

One sentence. A real mergeable issue.

---

## 📦 Install in 60 seconds

> **Heads up:** an MCP server has **two install steps**, not one. This trips most people up the first time:
>
> 1. **Get the code on your machine** — usually `pip install` or `uvx` (auto-installs on first run).
> 2. **Tell your AI client about it** — add a small JSON entry to your client's config file.
>
> Step 2 is what registers OpenCollab as a tool your AI can actually call. Without it, `pip install opencollab-mcp` just sits in your site-packages doing nothing — Claude Desktop has no way to know it exists. The JSON tells Claude *"here's a server, launch it like this, with this token."*
>
> Both steps are quick. Recipes for every major client below.

### 1. Get a free GitHub token

[github.com/settings/tokens](https://github.com/settings/tokens) → **Generate new token (classic)** → check `public_repo` → copy.

### 2. Add to your AI tool

<details open>
<summary><b>🖥️ Claude Desktop</b> (recommended)</summary>

Edit your config file:

- **macOS:** `~/Library/Application Support/Claude/claude_desktop_config.json`
- **Windows:** `%APPDATA%\Claude\claude_desktop_config.json`

Add this:

```json
{
  "mcpServers": {
    "opencollab": {
      "command": "uvx",
      "args": ["opencollab-mcp"],
      "env": {
        "GITHUB_TOKEN": "your_github_token_here"
      }
    }
  }
}
```

Restart Claude Desktop. Done.

> **Why no `pip install` step here?** `uvx` does it for you — on first launch it pulls `opencollab-mcp` from PyPI, caches it, and runs it. No manual install needed. (You do need [`uv`](https://docs.astral.sh/uv/) installed; on macOS it's `brew install uv`.)

</details>

<details>
<summary><b>⚡ Cursor / VS Code</b></summary>

Add to `.cursor/mcp.json` or your VS Code MCP config:

```json
{
  "mcpServers": {
    "opencollab": {
      "command": "uvx",
      "args": ["opencollab-mcp"],
      "env": {
        "GITHUB_TOKEN": "your_github_token_here"
      }
    }
  }
}
```

</details>

<details>
<summary><b>🐍 Prefer plain pip over uvx?</b></summary>

If you don't want to install `uv`, use `pip` directly. Two steps:

**Step A — install the package:**

```bash
pip install opencollab-mcp
```

This puts an `opencollab-mcp` command on your PATH.

**Step B — register it with Claude Desktop** (or Cursor/VS Code):

```json
{
  "mcpServers": {
    "opencollab": {
      "command": "opencollab-mcp",
      "env": {
        "GITHUB_TOKEN": "your_github_token_here"
      }
    }
  }
}
```

Notice the difference vs the `uvx` recipe above: `command` is now just `opencollab-mcp` (the binary pip put on your PATH) instead of `uvx`. The JSON entry is still required — it's how Claude knows the server exists.

**Heads up about `pip`:** if you upgrade Python or switch virtualenvs, the `opencollab-mcp` binary may disappear and you'll need to `pip install` again. That's why `uvx` is recommended — it manages this automatically.

</details>

<details>
<summary><b>🐳 Docker (remote / streamable-http)</b></summary>

```bash
docker build -t opencollab-mcp .
docker run -e GITHUB_TOKEN=ghp_xxx -p 8000:8000 opencollab-mcp
```

The container defaults to `TRANSPORT=streamable-http` on port 8000 and runs as a non-root user.

</details>

---

## 🎬 See it in action

### The killer demo — 3 prompts to go from zero to a drafted PR

**1️⃣ Analyze me**
> *"My GitHub username is `prakhar1605`. Am I ready to contribute to open source?"*
>
> Readiness: **72/100**. You know 4 languages, 15 public repos, haven't opened PRs yet. Tips: start with a docs fix, try a repo you already use.

**2️⃣ Find me a mergeable issue**
> *"Find me a Python good-first-issue I can finish in 1–2 hours. Make sure nobody's working on it."*
>
> Returns 5 issues · filters out ones with assignees or linked PRs · sorts by "quickness score" (short body, few comments, easy label).

**3️⃣ Plan the PR**
> *"Plan a PR for issue #456 in `owner/repo`."*
>
> Pulls the issue body, comments, CONTRIBUTING.md, the repo's directory structure, and the default branch — hands Claude everything needed to draft the actual code.

That's the whole loop: **Analyze → Find → Plan → Ship.**

### More things you can just *say*

| You say… | What happens |
|---|---|
| *"Is issue #123 in facebook/react still available?"* | ✅ No assignees, no open PRs. 3 comments, 12 days old. Go for it. |
| *"Compare langchain vs llama_index for contributing."* | Side-by-side: stars, PR merge rate, activity. Recommends winner. |
| *"Is tensorflow/tensorflow alive?"* | 847 commits in last 30 days. Growing +23%. Safe to invest time. |
| *"How complex is issue #5432 in pytorch?"* | 7/10 · Advanced. 12 comments, architecture label. Skip unless you know the codebase. |
| *"Find Python repos with GSoC or Hacktoberfest."* | Mentored repos sorted by mentor signals. |
| *"What dependencies does fastapi use?"* | Reads pyproject.toml → starlette, pydantic, uvicorn. |
| *"What's the impact of contributing to react?"* | 🎯 MASSIVE · 230k+ stars · Resume line: "Contributed to a project used by millions of devs." |

---

## 🛠️ All 22 tools

<details>
<summary><b>🔍 Discovery & Matching (6)</b></summary>

| Tool | Does |
|---|---|
| `opencollab_match_me` | **All-in-one** — profile analysis + matched issues |
| `opencollab_find_issues` | Good-first-issues for any language |
| `opencollab_trending_repos` | Trending repos seeking contributors |
| `opencollab_similar_repos` | Find repos like one you already like |
| `opencollab_find_mentor_repos` | GSoC · Hacktoberfest · Outreachy repos |
| `opencollab_weekend_issues` | 1–2 hour issues — docs, typos, tests |

</details>

<details>
<summary><b>📊 Evaluation & Scoring (7)</b></summary>

| Tool | Does |
|---|---|
| `opencollab_repo_health` | Health score 0–100 |
| `opencollab_contribution_readiness` | Setup difficulty (Dockerfile, CI, docs) |
| `opencollab_impact_estimator` | Impact tier + resume line |
| `opencollab_repo_activity_pulse` | 30-day momentum — growing? dying? |
| `opencollab_compare_repos` | Two repos side-by-side + winner |
| `opencollab_repo_languages` | Language % breakdown |
| `opencollab_dependency_check` | Tech stack — what libs the project uses |

</details>

<details>
<summary><b>👤 Profile & Readiness (3)</b></summary>

| Tool | Does |
|---|---|
| `opencollab_analyze_profile` | Deep profile analysis |
| `opencollab_first_timer_score` | Open source readiness 0–100 + tips |
| `opencollab_contributor_leaderboard` | Top contributors of any repo |

</details>

<details>
<summary><b>🎯 Issue Intelligence (6)</b></summary>

| Tool | Does |
|---|---|
| `opencollab_check_issue_availability` | Is this issue still free? |
| `opencollab_issue_complexity` | Difficulty 1–10 |
| `opencollab_stale_issue_finder` | Old unclaimed issues — hidden wins |
| `opencollab_label_explorer` | All labels + beginner-friendly ones |
| `opencollab_recent_prs` | Recently merged PRs — what gets accepted |
| `opencollab_generate_pr_plan` | Full context for PR planning |

</details>

---

## ⚡ Why it's different

```
You ask Claude → Claude calls OpenCollab tools → Tools hit GitHub's free API → Data flows back → Claude reasons over it → You get a real, specific answer
```

OpenCollab is a **data bridge**, not an AI. Your AI assistant does the thinking. That means:

- 🆓 **Zero AI costs** — pure GitHub API, no paid services
- 🔑 **No secrets besides a free GitHub token**
- 💻 **Runs locally** on your machine (STDIO transport) or as a container (streamable-HTTP)
- 🔒 **Private** — your GitHub data never leaves your computer
- ⚡ **Fast** — direct API calls + 5-minute in-memory cache to soften rate-limit pressure
- 🧪 **Tested** — pytest suite + CI on every push

---

## 🏗️ Develop / Contribute

This project is itself a great first contribution target.

```bash
git clone https://github.com/prakhar1605/Opencollab-mcp.git
cd Opencollab-mcp
pip install -e ".[dev]"
export GITHUB_TOKEN="your_token_here"

# Run the server
python -m opencollab_mcp

# Run the tests
pytest

# Lint
ruff check src tests

# Or test interactively with the MCP Inspector:
npx @modelcontextprotocol/inspector python -m opencollab_mcp
```

### Project layout

```
src/opencollab_mcp/
├── server.py          # entry point, transport selection
├── github_client.py   # cached HTTP wrapper with friendly errors
├── helpers.py         # days_ago, truncate, parse_issue_number, …
├── models.py          # Pydantic input models
├── constants.py       # all magic numbers / thresholds
└── tools/
    ├── discovery.py   # 6 matching tools
    ├── evaluation.py  # 7 scoring tools
    ├── issues.py      # 6 issue-intelligence tools
    └── profile.py     # 3 readiness tools
```

Check [open issues](https://github.com/prakhar1605/Opencollab-mcp/issues) labelled `good first issue`.

---

## 🗺️ Roadmap

- [x] 22 tools shipped
- [x] **Published on PyPI — `uvx opencollab-mcp` works out of the box**
- [x] **In-memory caching layer (fewer API calls, less rate-limit friction)**
- [x] **GitHub Actions CI**
- [x] **Pytest suite with httpx MockTransport**
- [x] **Streamable-HTTP transport for remote deployment**
- [ ] `first_pr_generator` — one-shot "find + plan + draft my first PR"
- [ ] `track_my_prs` — dashboard of your open PRs with staleness nudges
- [ ] `skill_gap` — compare your skills vs a target repo's stack

Got an idea? [Open an issue](https://github.com/prakhar1605/Opencollab-mcp/issues/new) — that's the fastest path in.

---

## 📄 License

MIT — see [LICENSE](LICENSE).

---

<div align="center">

**Built with ❤️ by [Prakhar Pandey](https://github.com/prakhar1605)** · IIT Guwahati

⭐ **Star this repo if OpenCollab helps you land a PR.** ⭐
*It's the single biggest thing you can do to help other devs discover it.*

[Install now](#-install-in-60-seconds) · [Report a bug](https://github.com/prakhar1605/Opencollab-mcp/issues) · [Share on Twitter](https://twitter.com/intent/tweet?text=Just%20found%20OpenCollab%20MCP%20%E2%80%94%20it%20finds%20me%20mergeable%20open%20source%20issues%20in%2030%20seconds.%20Works%20with%20Claude%20Desktop%2C%20Cursor%2C%20VS%20Code.%20pip%20install%20opencollab-mcp&url=https://github.com/prakhar1605/Opencollab-mcp)

</div>
