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
| `opencollab_match_me` | **All-in-one**: analyzes your profile + finds matched issues in one step |
| `opencollab_compare_repos` | Compare two repos side-by-side for contributor-friendliness |
| `opencollab_check_issue_availability` | Check if an issue is still free — no assignees, no open PRs |
| `opencollab_contributor_leaderboard` | See top contributors of any repo with commit counts |
| `opencollab_stale_issue_finder` | Find old unclaimed issues — hidden easy wins no one is working on |

---

## Quick start

### 1. Get a GitHub token (free)

Go to [github.com/settings/tokens](https://github.com/settings/tokens) → **Generate new token (classic)** → select `public_repo` scope → copy the token.

### 2. Install in Claude Desktop

Add this to your Claude Desktop config:

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

### 3. Install in Cursor / VS Code

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

### 4. Alternative: Install with pip

```bash
pip install git+https://github.com/prakhar1605/Opencollab-mcp.git
```

Then use `opencollab-mcp` as the command (no `uvx` needed):

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

---

## Example conversations

### "Match me with issues"

> **You:** My GitHub username is prakhar1605. Find me open source issues I can contribute to.
>
> **Claude:** *analyzes profile → finds your top language → returns matched issues instantly*

### "Compare two repos"

> **You:** I'm choosing between langchain-ai/langchain and run-llama/llama_index to contribute to. Compare them.
>
> **Claude:** *fetches both repos → compares stars, PR merge rate, activity → recommends one*

### "Is this issue still available?"

> **You:** Check if issue #456 in facebook/react is still available to work on.
>
> **Claude:** *checks assignees, linked PRs → tells you if it's free or already claimed*

### "Who are the top contributors?"

> **You:** Show me the top contributors of microsoft/vscode.
>
> **Claude:** *fetches leaderboard with commit counts and profile links*

### "Find hidden gems"

> **You:** Find old unclaimed issues in fastapi/fastapi that no one is working on.
>
> **Claude:** *finds stale issues with no assignees — easy wins others overlooked*

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
git clone https://github.com/prakhar1605/Opencollab-mcp.git
cd Opencollab-mcp

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

**Built by [Prakhar Pandey](https://github.com/prakhar1605)** — IIT Guwahati | AI Engineer
