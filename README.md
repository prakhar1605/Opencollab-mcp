<![CDATA[<div align="center">

# 🚀 OpenCollab MCP

### The AI-powered open source contribution matchmaker

**22 tools** · **Zero AI costs** · **Works with Claude Desktop, Cursor, VS Code**

[![MIT License](https://img.shields.io/badge/License-MIT-green.svg)](https://choosealicense.com/licenses/mit/)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![MCP Compatible](https://img.shields.io/badge/MCP-Compatible-purple.svg)](https://modelcontextprotocol.io)

*Stop scrolling through random GitHub issues. Let AI analyze your profile and find contributions you're actually qualified for, in repos that are actually maintained.*

[Quick Start](#-quick-start) · [All 22 Tools](#-all-22-tools) · [Examples](#-example-conversations) · [Contributing](#-contributing)

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

OpenCollab MCP gives your AI assistant (Claude, Cursor, etc.) **22 specialized tools** to find, evaluate, and plan open source contributions — matched to YOUR actual skills.

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
<summary><b>Claude Desktop</b> (recommended)</summary>

Add to `~/Library/Application Support/Claude/claude_desktop_config.json` (macOS) or `%APPDATA%\Claude\claude_desktop_config.json` (Windows):

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
<summary><b>Cursor / VS Code</b></summary>

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
<summary><b>Install with pip</b></summary>

```bash
pip install git+https://github.com/prakhar1605/Opencollab-mcp.git
```

Then use in config:

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
| `match_me` | **All-in-one**: analyzes your profile + finds matched issues in one step |
| `find_issues` | Finds "good first issue" / "help wanted" issues for any language |
| `trending_repos` | Trending repos actively seeking contributors |
| `similar_repos` | Find repos similar to one you already like |
| `find_mentor_repos` | Repos with GSoC, Hacktoberfest, Outreachy programs |
| `weekend_issues` | Quick 1-2 hour issues — docs, typos, tests |

### 📊 Evaluation & Scoring

| Tool | What it does |
|---|---|
| `repo_health` | Health score (0-100) — is this repo worth contributing to? |
| `contribution_readiness` | Setup difficulty — Dockerfile, CI, docs, templates |
| `impact_estimator` | Contribution impact tier + suggested resume line |
| `repo_activity_pulse` | 30-day activity pulse — growing, stable, or dying? |
| `compare_repos` | Side-by-side comparison of two repos |
| `repo_languages` | Detailed language % breakdown |
| `dependency_check` | Tech stack inspection — libraries and frameworks used |

### 👤 Profile & Readiness

| Tool | What it does |
|---|---|
| `analyze_profile` | Deep analysis of your GitHub skills, languages, patterns |
| `first_timer_score` | Open source readiness score + personalized tips |
| `contributor_leaderboard` | Top contributors of any repo with commit counts |

### 🎯 Issue Intelligence

| Tool | What it does |
|---|---|
| `check_issue_availability` | Is this issue still free? No assignees, no open PRs |
| `issue_complexity` | Difficulty score (1-10) — beginner to expert |
| `stale_issue_finder` | Old unclaimed issues — hidden easy wins |
| `label_explorer` | All labels in a repo + which ones are beginner-friendly |
| `recent_prs` | Recently merged PRs — what contributions get accepted |
| `generate_pr_plan` | Full issue context for AI-assisted PR planning |

---

## 💬 Example Conversations

### 🎯 "Match me with issues"

> **You:** My GitHub username is prakhar1605. Find me open source issues I can contribute to.
>
> **Claude:** *analyzes profile → detects Python as your top language → returns 10 matching good-first-issues*

### ⚖️ "Help me choose between two repos"

> **You:** I'm choosing between langchain-ai/langchain and run-llama/llama_index. Compare them for contributor-friendliness.
>
> **Claude:** *fetches both → compares stars, PR merge rate, activity, open issues → recommends one*

### 🔓 "Is this issue still available?"

> **You:** Check if issue #456 in facebook/react is still free to work on.
>
> **Claude:** Available! No assignees, no open PRs. 3 comments, created 12 days ago. Go for it!

### 📊 "Rate my readiness"

> **You:** How ready am I for open source? My username is prakhar1605.
>
> **Claude:** Readiness: 72/100. You have 15 repos, know 4 languages, but haven't opened PRs yet. Tips: Fork a project you use, start with a docs fix...

### 🏃 "Weekend sprint"

> **You:** Find me quick Python issues I can knock out in 1-2 hours this weekend.
>
> **Claude:** *finds docs fixes, typo corrections, test additions — all with short descriptions and few comments*

### 🔬 "How hard is this issue?"

> **You:** How complex is issue #5432 in pytorch/pytorch?
>
> **Claude:** Complexity: 7/10 (Advanced). 2000+ char description, 12 comments, architecture label. Needs deep codebase knowledge.

### 🧭 "Find me a mentored project"

> **You:** Find Python repos with mentorship programs or GSoC.
>
> **Claude:** *finds repos tagged gsoc, hacktoberfest, mentorship — sorted by mentor signals*

### 🏗️ "Plan my PR"

> **You:** I want to work on issue #123 in org/repo. Help me plan a PR.
>
> **Claude:** *fetches issue body, all comments, contributing guide, directory structure → generates step-by-step plan*

### 📈 "Is this repo alive?"

> **You:** What's the activity pulse of tensorflow/tensorflow?
>
> **Claude:** 847 commits last 30 days. Momentum: Growing (+23%). 85 PRs merged. Very active.

### 🔍 "What tech stack is this?"

> **You:** What dependencies does fastapi/fastapi use?
>
> **Claude:** *reads pyproject.toml → lists starlette, pydantic, uvicorn, etc. with versions*

---

## ⚡ How It Works

```
You ask Claude → Claude calls OpenCollab tools → Tools fetch GitHub API → Data returns → Claude gives smart recommendations
```

OpenCollab is a **data bridge**, not an AI. It fetches and structures data from GitHub's free API. Claude does all the intelligent analysis. This means:

- **🆓 Zero AI costs** — uses GitHub's free API
- **🔑 No API keys** besides a free GitHub token
- **💻 Works locally** — STDIO transport, runs on your machine
- **🔒 Private** — your data never leaves your computer

---

## 🏗️ Development

```bash
# Clone
git clone https://github.com/prakhar1605/Opencollab-mcp.git
cd Opencollab-mcp

# Install in dev mode
pip install -e .

# Set token
export GITHUB_TOKEN="your_token_here"

# Run
python -m opencollab_mcp.server

# Test with MCP Inspector
npx @modelcontextprotocol/inspector python -m opencollab_mcp.server
```

---

## 🗺️ Roadmap

- [x] 22 tools for contribution discovery and evaluation
- [x] Profile analysis and skill matching
- [x] Issue complexity and availability checking
- [ ] PyPI package (`uvx opencollab-mcp` without git URL)
- [ ] Caching layer for faster responses
- [ ] GitHub Actions CI/CD pipeline
- [ ] SSE remote deployment support
- [ ] Contribution tracking dashboard

---

## 🤝 Contributing

Contributions welcome! This project is itself a good first contribution target.

Check the [issues tab](https://github.com/prakhar1605/Opencollab-mcp/issues) for tasks labeled `good first issue`.

---

## 📄 License

MIT — see [LICENSE](LICENSE).

---

<div align="center">

**Built with ❤️ by [Prakhar Pandey](https://github.com/prakhar1605)** — IIT Guwahati

*If this helped you, give it a ⭐ — it helps others find it too!*

</div>
]]>