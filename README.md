<div align="center">

# 🚀 OpenCollab MCP

### The AI-powered open source contribution matchmaker

**22 tools** · **Zero AI costs** · **Works with Claude Desktop, Cursor, VS Code**

[![MIT License](https://img.shields.io/badge/License-MIT-green.svg)](https://choosealicense.com/licenses/mit/)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![MCP Compatible](https://img.shields.io/badge/MCP-Compatible-purple.svg)](https://modelcontextprotocol.io)

*Stop scrolling through random GitHub issues. Let AI analyze your profile and find contributions you're actually qualified for, in repos that are actually maintained.*

[Quick Start](#-quick-start) · [All 22 Tools](#-all-22-tools) · [Examples](#-see-it-in-action) · [Contributing](#-contributing)

</div>

---

## 🤔 The Problem

You want to contribute to open source. So you:

1. ~~Scroll through hundreds of GitHub repos~~ 😩
2. ~~Find a "good first issue" that's already taken~~ 😤
3. ~~Spend hours understanding a dead repo~~ 💀
4. ~~Discover someone already submitted a PR~~ 😭
5. ~~Give up and go back to tutorials~~ 📺

**This is broken.** We built OpenCollab to fix it.

## ✨ The Solution

OpenCollab MCP gives your AI assistant **22 specialized tools** to find, evaluate, and plan open source contributions — matched to YOUR actual skills.

```
"Analyze my GitHub profile and find me issues I can work on this weekend"
```

That's it. One sentence. Claude does the rest.

---

## 📦 Quick Start

### 1. Get a GitHub token (free, 30 seconds)

Go to [github.com/settings/tokens](https://github.com/settings/tokens) → **Generate new token (classic)** → select `public_repo` scope → copy it.

### 2. Add to your AI tool

<details>
<summary><b>🖥️ Claude Desktop</b> (recommended)</summary>

Add to your config file:

**macOS:** `~/Library/Application Support/Claude/claude_desktop_config.json`  
**Windows:** `%APPDATA%\Claude\claude_desktop_config.json`

```json
{
  "mcpServers": {
    "opencollab": {
      "command": "uvx",
      "args": ["--from", "git+https://github.com/prakhar1605/Opencollab-mcp.git", "opencollab-mcp"],
      "env": {
        "GITHUB_TOKEN": "your_github_token_here"
      }
    }
  }
}
```

Restart Claude Desktop. Done!

</details>

<details>
<summary><b>⚡ Cursor / VS Code</b></summary>

Add to `.cursor/mcp.json` or VS Code MCP config:

```json
{
  "mcpServers": {
    "opencollab": {
      "command": "uvx",
      "args": ["--from", "git+https://github.com/prakhar1605/Opencollab-mcp.git", "opencollab-mcp"],
      "env": {
        "GITHUB_TOKEN": "your_github_token_here"
      }
    }
  }
}
```

</details>

<details>
<summary><b>📦 Install with pip</b></summary>

```bash
pip install git+https://github.com/prakhar1605/Opencollab-mcp.git
```

Then use in your MCP config:

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

</details>

---

## 🛠️ All 22 Tools

### 🔍 Discovery & Matching

| Tool | What it does |
|---|---|
| `opencollab_match_me` | **All-in-one** — analyzes your profile + finds matched issues in one step |
| `opencollab_find_issues` | Finds "good first issue" / "help wanted" issues for any language |
| `opencollab_trending_repos` | Trending repos actively seeking contributors, sorted by stars |
| `opencollab_similar_repos` | Find repos similar to one you already like |
| `opencollab_find_mentor_repos` | Repos with GSoC, Hacktoberfest, Outreachy mentorship programs |
| `opencollab_weekend_issues` | Quick 1-2 hour issues — docs, typos, tests, perfect for a weekend sprint |

### 📊 Evaluation & Scoring

| Tool | What it does |
|---|---|
| `opencollab_repo_health` | Health score (0-100) — is this repo actually worth contributing to? |
| `opencollab_contribution_readiness` | Setup difficulty check — Dockerfile, CI, docs, templates |
| `opencollab_impact_estimator` | Contribution impact tier (MASSIVE/HIGH/MEDIUM/LOW) + resume line |
| `opencollab_repo_activity_pulse` | 30-day activity pulse — is the project growing, stable, or dying? |
| `opencollab_compare_repos` | Side-by-side comparison of two repos with a recommendation |
| `opencollab_repo_languages` | Detailed language % breakdown — know what skills you need |
| `opencollab_dependency_check` | Inspect tech stack — what libraries and frameworks the project uses |

### 👤 Profile & Readiness

| Tool | What it does |
|---|---|
| `opencollab_analyze_profile` | Deep analysis of your GitHub skills, languages, activity patterns |
| `opencollab_first_timer_score` | Open source readiness score (0-100) + personalized tips to improve |
| `opencollab_contributor_leaderboard` | Top contributors of any repo with commit counts and profiles |

### 🎯 Issue Intelligence

| Tool | What it does |
|---|---|
| `opencollab_check_issue_availability` | Is this issue still free? Checks assignees + linked PRs |
| `opencollab_issue_complexity` | Difficulty score (1-10) — beginner, intermediate, advanced, or expert |
| `opencollab_stale_issue_finder` | Old unclaimed issues nobody is working on — hidden easy wins |
| `opencollab_label_explorer` | All labels in a repo + which ones are beginner-friendly |
| `opencollab_recent_prs` | Recently merged PRs — see what contributions actually get accepted |
| `opencollab_generate_pr_plan` | Full issue context + contributing guide + directory structure for PR planning |

---

## 💬 See It In Action

### 🎯 "Match me with issues"

> **You:** My GitHub username is prakhar1605. Find me open source issues I can contribute to.
>
> **Claude:** *analyzes profile → detects Python as top language → returns 10 matching good-first-issues instantly*

### 📊 "Rate my open source readiness"

> **You:** How ready am I for open source? Username: prakhar1605
>
> **Claude:** Readiness: 72/100. You know 4 languages, have 15 repos, but haven't opened PRs yet. Tips: Start with a docs fix, fork a project you use daily...

### ⚖️ "Help me choose between two repos"

> **You:** Compare langchain-ai/langchain vs run-llama/llama_index for contributing.
>
> **Claude:** *fetches both → compares stars, PR merge rate, activity → recommends langchain (85% merge rate, pushed 2 days ago)*

### 🔓 "Is this issue available?"

> **You:** Check if issue #456 in facebook/react is still free to work on.
>
> **Claude:** ✅ Available! No assignees, no open PRs. 3 comments, created 12 days ago. Go for it!

### 🏃 "Weekend sprint"

> **You:** Find me quick Python issues I can knock out in 1-2 hours this weekend.
>
> **Claude:** *finds docs fixes, typo corrections, test additions — all with short descriptions and few comments*

### 🔬 "How hard is this issue?"

> **You:** How complex is issue #5432 in pytorch/pytorch?
>
> **Claude:** Complexity: 7/10 (Advanced). 2000+ char body, 12 comments, architecture label. Needs deep codebase knowledge.

### 🧭 "Find me a mentored project"

> **You:** Find Python repos with GSoC or Hacktoberfest programs.
>
> **Claude:** *finds repos tagged gsoc, hacktoberfest, mentorship — sorted by mentor signals*

### 🏗️ "Plan my PR"

> **You:** I want to work on issue #123 in org/repo. Help me plan a PR.
>
> **Claude:** *fetches issue body, all comments, contributing guide, repo directory → generates step-by-step implementation plan*

### 📈 "Is this repo alive?"

> **You:** What's the activity pulse of tensorflow/tensorflow?
>
> **Claude:** 847 commits in last 30 days. Momentum: Growing (+23%). Very active — safe to invest time.

### 🔍 "What tech stack is this?"

> **You:** What dependencies does fastapi/fastapi use?
>
> **Claude:** *reads pyproject.toml → lists starlette, pydantic, uvicorn with versions*

### 🏆 "Who contributes the most?"

> **You:** Show me the top contributors of microsoft/vscode.
>
> **Claude:** *leaderboard with ranks, commit counts, and profile links*

### 🗺️ "Find similar repos"

> **You:** I like contributing to fastapi/fastapi. Find me similar repos.
>
> **Claude:** *finds 10 similar web framework repos with good-first-issues — starlette, litestar, sanic...*

### 📋 "What labels should I look for?"

> **You:** Show me all labels in fastapi/fastapi and which are beginner-friendly.
>
> **Claude:** *lists 35 labels → highlights 'good first issue', 'help wanted', 'docs' as beginner-friendly*

### 💪 "What's the impact?"

> **You:** How impactful would it be to contribute to facebook/react?
>
> **Claude:** Impact: MASSIVE. 230k+ stars. Resume line: "Contributed to a project used by millions of developers"

### 📐 "What languages do I need?"

> **You:** What languages are used in kubernetes/kubernetes?
>
> **Claude:** Go: 87.3%, Shell: 5.2%, Python: 3.1%... You'll primarily need Go.

---

## ⚡ How It Works

```
You ask Claude → Claude calls OpenCollab tools → Tools fetch GitHub API → Data returns → Claude gives smart recommendations
```

OpenCollab is a **data bridge**, not an AI. It fetches and structures data from GitHub's free API. Your AI assistant (Claude, Cursor, etc.) does all the intelligent analysis. This means:

- **🆓 Zero AI costs** — uses GitHub's free API, no paid services
- **🔑 No API keys** besides a free GitHub token
- **💻 Works locally** — STDIO transport, runs on your machine
- **🔒 Private** — your data never leaves your computer
- **⚡ Fast** — direct GitHub API calls, no middleware

---

## 🏗️ Development

```bash
# Clone
git clone https://github.com/prakhar1605/Opencollab-mcp.git
cd Opencollab-mcp

# Install in dev mode
pip install -e .

# Set your token
export GITHUB_TOKEN="your_token_here"

# Run directly
python -m opencollab_mcp.server

# Test with MCP Inspector
npx @modelcontextprotocol/inspector python -m opencollab_mcp.server
```

---

## 🗺️ Roadmap

- [x] 22 tools for contribution discovery, evaluation, and planning
- [x] Profile analysis and skill matching
- [x] Issue complexity and availability checking
- [x] Repo comparison and health scoring
- [x] Tech stack and dependency inspection
- [x] Mentorship program discovery (GSoC, Hacktoberfest, Outreachy)
- [ ] PyPI package (`uvx opencollab-mcp` without git URL)
- [ ] Caching layer for faster responses
- [ ] GitHub Actions CI/CD pipeline
- [ ] SSE remote deployment support
- [ ] Contribution tracking over time

---

## 🤝 Contributing

Contributions welcome! This project is itself a great first contribution target.

Check the [issues tab](https://github.com/prakhar1605/Opencollab-mcp/issues) for tasks labeled `good first issue`.

## 📄 License

MIT — see [LICENSE](LICENSE).

---

<div align="center">

**Built with ❤️ by [Prakhar Pandey](https://github.com/prakhar1605)** — IIT Guwahati

⭐ *If this helped you find your first open source contribution, give it a star!* ⭐

</div>
