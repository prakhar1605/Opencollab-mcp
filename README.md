# 🚀 OpenCollab MCP

**AI-powered open source contribution matchmaker** — finds perfect "good first issues" matched to YOUR skills.

Stop scrolling through random issues. Let AI analyze your GitHub profile and find contributions you're actually qualified for, in repos that are actually maintained.

---

## What it does

| Tool | What it does |
|---|---|
| `opencollab_analyze_profile` | Analyzes your GitHub profile — languages, topics, contribution patterns |
| `opencollab_find_issues` | Finds "good first issue" / "help wanted" issues matched to your skills |
| `opencollab_repo_health` | Scores a repo's contributor-friendliness (0–100) |
| `opencollab_contribution_readiness` | Checks setup difficulty — Dockerfile, CI, docs, templates |
| `opencollab_generate_pr_plan` | Gathers full issue context so AI can draft a PR plan |
| `opencollab_trending_repos` | Finds trending repos actively seeking contributors |
| `opencollab_impact_estimator` | Estimates contribution impact — stars, reach, resume line |

---

## Quick start

### 1. Get a GitHub token (free)

Go to [github.com/settings/tokens](https://github.com/settings/tokens) → **Generate new token (classic)** → select `public_repo` scope → copy the token.

### 2. Install in Claude Desktop

Add this to your Claude Desktop config (`~/Library/Application Support/Claude/claude_desktop_config.json` on Mac):

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

Restart Claude Desktop. Done!

### 3. Install in Cursor / VS Code

Add to `.cursor/mcp.json` or VS Code MCP config:

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

---

## Example conversations

### "Analyze my profile and find me issues"

> **You:** Analyze my GitHub profile (username: prakhar9999) and then find me beginner Python issues in AI/ML projects.
>
> **Claude:** *analyzes profile → finds matching issues → ranks by relevance*

### "Is this repo good to contribute to?"

> **You:** Check if langchain-ai/langchain is a good repo to contribute to.
>
> **Claude:** Health score: 85/100. Very active — last push 2 days ago, 72% PR merge rate, has CONTRIBUTING.md...

### "Help me plan a PR"

> **You:** I want to work on this issue: https://github.com/org/repo/issues/123. Generate a PR plan.
>
> **Claude:** *fetches issue, comments, repo structure → generates step-by-step plan*

### "What's the impact?"

> **You:** How impactful would it be to contribute to facebook/react?
>
> **Claude:** Impact tier: MASSIVE. 230k+ stars. Suggested resume line: "Contributed to a project used by tens of thousands of developers"

---

## Development

```bash
# Clone
git clone https://github.com/PrakharPandey/opencollab-mcp.git
cd opencollab-mcp

# Install in development mode
pip install -e .

# Set your token
export GITHUB_TOKEN="your_token_here"

# Run directly
python -m opencollab_mcp.server

# Test with MCP Inspector
npx @modelcontextprotocol/inspector python -m opencollab_mcp.server
```

---

## How it works

```
User asks Claude → Claude calls OpenCollab tools → Tools fetch GitHub API → Data returns to Claude → Claude gives smart recommendations
```

The MCP server is a **data bridge**, not an AI. It fetches and structures data from GitHub's free API. Claude (which the user already has) does all the intelligent analysis. This means:

- **Zero AI costs** for you or your users
- **No API keys needed** besides a free GitHub token
- **Works offline** (STDIO transport, runs locally)

---

## Requirements

- Python 3.10+
- A free GitHub Personal Access Token with `public_repo` scope
- Any MCP-compatible client (Claude Desktop, Cursor, VS Code, etc.)

---

## Contributing

Contributions welcome! This project is itself a good first contribution target. Check the issues tab for tasks labeled `good first issue`.

## License

MIT — see [LICENSE](LICENSE).

---

**Built by [Prakhar Pandey](https://github.com/PrakharPandey)** — IIT Guwahati | AI Engineer
