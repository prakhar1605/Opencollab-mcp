<div align="center">

# 🚀 OpenCollab MCP

**Land your first merged PR this weekend — with Claude's help.**

An MCP server that turns Claude into your open source mentor.
Profile → matched issues → PR plan, in one prompt.

[![PyPI version](https://img.shields.io/pypi/v/opencollab-mcp.svg)](https://pypi.org/project/opencollab-mcp/)
[![CI](https://github.com/prakhar1605/Opencollab-mcp/workflows/CI/badge.svg)](https://github.com/prakhar1605/Opencollab-mcp/actions)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)

</div>

---

> **Demo coming soon** — a 90-second screen recording of OpenCollab finding,
> evaluating, and planning a PR for a real GitHub issue. Drop in here once recorded.

---

## Why this exists

Finding your first open source PR is brutal. You have to:

1. Pick a repo where maintainers actually merge community PRs
2. Find an issue that's still open, unclaimed, and small enough to ship
3. Read CONTRIBUTING.md, figure out the codebase, plan the change

OpenCollab does all three in one prompt. You ask Claude *"find me a Python
issue I can ship this weekend"*, and OpenCollab analyzes your GitHub profile,
matches your skills to active repos with healthy contributor cultures,
checks each issue for availability, scores complexity, and hands Claude
everything it needs to draft the PR.

## Quickstart (60 seconds)

**1. Install:**
```bash
pip install opencollab-mcp
```

**2. Get a GitHub token** ([generate one](https://github.com/settings/tokens),
`public_repo` scope is enough).

**3. Add to Claude Desktop** (`~/Library/Application Support/Claude/claude_desktop_config.json`):
```json
{
  "mcpServers": {
    "opencollab": {
      "command": "python",
      "args": ["-m", "opencollab_mcp"],
      "env": { "GITHUB_TOKEN": "ghp_your_token_here" }
    }
  }
}
```

**4. Restart Claude Desktop and ask:**
> *"Use OpenCollab to find me a Python good-first-issue I can finish this weekend, then plan the PR for it."*

Done. You should see Claude call `opencollab_match_me` → `opencollab_check_issue` → `opencollab_plan_pr` and produce a step-by-step plan for an actual open issue.

## The 8 tools

OpenCollab is **8 well-designed tools, not 22 narrow ones**. Each tool
returns rich, composable JSON so Claude can chain them naturally.

| Tool | What it does | Use when |
|---|---|---|
| `opencollab_match_me` | Profile → top languages → matched issues + readiness signals | The default entry point |
| `opencollab_repo_health` | Health score + 30-day momentum + impact tier + deps + languages | Evaluating a repo |
| `opencollab_check_issue` | Availability (assignees, linked PRs) + complexity rating | Before picking an issue |
| `opencollab_plan_pr` | Issue + comments + CONTRIBUTING + repo structure | Drafting the actual PR |
| `opencollab_find_opportunities` | Search with `mode`: `good_first_issue` / `weekend` / `trending` / `similar` / `mentor` / `stale` | Hunting for issues/repos |
| `opencollab_compare_repos` | Side-by-side: stars, merge rate, momentum, recommendation | Choosing between two repos |
| `opencollab_explore_repo` | Labels + top contributors + recent merged PRs | Deep dive on a repo's culture |
| `opencollab_first_timer_score` | 0–100 readiness rating + personalized tips | Self-assessment for newcomers |

<details>
<summary><strong>Example prompts</strong></summary>

```
"Use OpenCollab to rate my GitHub profile (octocat) and tell me what to improve"
"Find weekend issues in TypeScript I can finish in 2 hours"
"Compare facebook/react vs vuejs/vue for first-time contributors"
"Show me trending Python repos that mentor newcomers"
"Is issue #123 in vercel/next.js still available?"
"Plan a PR for issue #456 in microsoft/vscode"
```

</details>

## How is this different from official `github-mcp-server`?

GitHub's official MCP is a generic API proxy — every tool is a thin wrapper
over a REST endpoint. **OpenCollab is opinionated for contribution discovery**.
It computes scores, ranks issues by quickness-to-merge, evaluates community
health, and chains multi-step workflows automatically. You wouldn't use a
generic API wrapper to get a PR plan; you'd use OpenCollab.

## Configuration

| Env var | Default | Purpose |
|---|---|---|
| `GITHUB_TOKEN` | _(required)_ | GitHub PAT, `public_repo` scope is enough |
| `TRANSPORT` | `stdio` | `stdio` (local) or `streamable-http` (remote) |
| `PORT` | `8000` | Used when `TRANSPORT=streamable-http` |
| `OPENCOLLAB_LOG_LEVEL` | `INFO` | `DEBUG`, `INFO`, `WARNING`, `ERROR` |

## Remote deployment (Streamable HTTP)

OpenCollab supports the new MCP Streamable HTTP transport (spec 2025-03-26).
Deploy to any container platform:

```bash
docker build -t opencollab-mcp .
docker run -p 8000:8000 -e TRANSPORT=streamable-http -e GITHUB_TOKEN=... opencollab-mcp
```

Then connect from Claude Desktop using the URL `http://localhost:8000/mcp`.

## Roadmap

- [x] 8 consolidated tools, full test coverage
- [x] Connection-pooled HTTP client + 5-min response cache
- [x] Streamable HTTP transport
- [ ] `first_pr_generator` — chain match → check → plan → draft via Claude API
- [ ] GraphQL queries for heavy tools (`plan_pr`, `compare_repos`)
- [ ] Hosted `opencollab.dev` with web UI
- [ ] Outcome tracking — did your matched issue actually merge?

## Contributing

PRs welcome — see [CONTRIBUTING.md](CONTRIBUTING.md). The whole point of this
project is to make contributing easier, so it would be deeply ironic for it
to be hard to contribute to.

## License

MIT. See [LICENSE](LICENSE).

---

<div align="center">
Made with ❤️ for everyone who's stared at "good first issue" filters
wondering which one is actually a good first issue.
</div>
