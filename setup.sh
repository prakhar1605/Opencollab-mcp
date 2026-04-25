#!/usr/bin/env bash
# OpenCollab MCP — one-time setup script.
# Run this from the repo root after the v0.5.0 file rewrite.
#
#   chmod +x setup.sh && ./setup.sh
#
# Idempotent — safe to re-run.

set -e

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

echo "==> Creating directory structure..."
mkdir -p tests
mkdir -p .github/workflows
mkdir -p .github/ISSUE_TEMPLATE

echo "==> Moving staged files into place..."

# tests/
[ -f __SETUP__tests____init__.py ]      && mv __SETUP__tests____init__.py      tests/__init__.py
[ -f __SETUP__tests__test_smoke.py ]    && mv __SETUP__tests__test_smoke.py    tests/test_smoke.py
[ -f __SETUP__tests__test_github_client.py ] && mv __SETUP__tests__test_github_client.py tests/test_github_client.py

# .github/workflows/
[ -f __SETUP__.github__workflows__ci.yml ]      && mv __SETUP__.github__workflows__ci.yml      .github/workflows/ci.yml
[ -f __SETUP__.github__workflows__release.yml ] && mv __SETUP__.github__workflows__release.yml .github/workflows/release.yml

# .github/
[ -f __SETUP__.github__dependabot.yml ]            && mv __SETUP__.github__dependabot.yml            .github/dependabot.yml
[ -f __SETUP__.github__pull_request_template.md ]  && mv __SETUP__.github__pull_request_template.md  .github/pull_request_template.md
[ -f __SETUP__.github__FUNDING.yml ]               && mv __SETUP__.github__FUNDING.yml               .github/FUNDING.yml

# .github/ISSUE_TEMPLATE/
[ -f __SETUP__.github__ISSUE_TEMPLATE__bug_report.yml ]      && mv __SETUP__.github__ISSUE_TEMPLATE__bug_report.yml      .github/ISSUE_TEMPLATE/bug_report.yml
[ -f __SETUP__.github__ISSUE_TEMPLATE__feature_request.yml ] && mv __SETUP__.github__ISSUE_TEMPLATE__feature_request.yml .github/ISSUE_TEMPLATE/feature_request.yml

echo "==> Cleaning up macOS junk..."
find . -name ".DS_Store" -type f -delete 2>/dev/null || true

echo "==> Removing build artifacts and .DS_Store from git tracking..."
git rm -r --cached dist/ 2>/dev/null || echo "    (dist/ not tracked, skipping)"
git rm --cached .DS_Store 2>/dev/null || true
git rm --cached src/.DS_Store 2>/dev/null || true
git rm --cached src/opencollab_mcp/.DS_Store 2>/dev/null || true

echo "==> Removing stale dist/ directory locally..."
rm -rf dist/ build/ *.egg-info src/*.egg-info

echo "==> Installing dev dependencies..."
pip install -e ".[dev]" --quiet

echo "==> Running checks to verify everything works..."
ruff check src tests || echo "    (ruff lint had findings — review and run 'ruff check --fix src tests' if needed)"
ruff format --check src tests || echo "    (formatting needed — run 'ruff format src tests')"
pytest -v || echo "    (some tests failed — review output above)"

echo ""
echo "==> Done!"
echo ""
echo "Next steps:"
echo "  1. git add -A"
echo "  2. git status   # review what changed"
echo "  3. git commit -m 'feat: v0.5.0 — consolidate to 8 tools, add CI, tests, repo hygiene'"
echo "  4. git tag v0.5.0 && git push --tags"
echo ""
echo "After pushing the tag, set up PyPI Trusted Publishing at:"
echo "  https://pypi.org/manage/account/publishing/"
echo "  Project: opencollab-mcp"
echo "  Owner: prakhar1605"
echo "  Repository: Opencollab-mcp"
echo "  Workflow: release.yml"
echo "  Environment: pypi"
echo ""
