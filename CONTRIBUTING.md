# Contributing to OpenCollab MCP

Thanks for thinking about contributing — this project literally exists to make
contributing easier, so it would be very on-brand of you to send a PR.

## Quick start

```bash
git clone https://github.com/prakhar1605/Opencollab-mcp.git
cd Opencollab-mcp
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
```

Set your token:

```bash
cp .env.example .env
# edit .env and add your GITHUB_TOKEN
```

## Running locally

```bash
# stdio (for Claude Desktop)
python -m opencollab_mcp

# HTTP (for remote testing)
TRANSPORT=streamable-http PORT=8000 python -m opencollab_mcp
```

## Tests, lint, types

```bash
pytest                    # tests
ruff check src tests      # lint
ruff format src tests     # format
mypy src                  # types
```

CI runs all of the above on every PR. Please run them locally first.

## Good first contributions

If you're new, look for issues labelled `good first issue`. Some ideas that
are always welcome:

- Add a test for an existing tool
- Improve an error message
- Tighten a tool description so Claude picks it more reliably
- Add a new `mode` to `opencollab_find_opportunities`
- Fix a typo in the README

## PR process

1. Fork, branch (`feat/your-thing` or `fix/your-thing`)
2. Make the change + add a test
3. Update `CHANGELOG.md` under `## [Unreleased]`
4. Open the PR — link any related issue
5. CI must be green before review

## Tool design principles

The whole point of the consolidation from 22 → 8 tools is **fewer, richer
tools** beat many narrow ones. Before adding a new tool, ask:

1. Can this be a new `mode` on an existing tool?
2. Can this be a new field in an existing tool's response?
3. Is the use case distinct enough that LLMs will reliably pick the right one?

Default answer for new tools: **no**. Default answer for enriching existing
ones: **yes**.

## Code of conduct

By participating, you agree to follow the [Contributor Covenant](CODE_OF_CONDUCT.md).

## License

Contributions are licensed under MIT, the same as the project.
