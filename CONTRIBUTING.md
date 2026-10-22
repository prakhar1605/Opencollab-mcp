# Contributing to OpenCollab MCP

Thank you for your interest in contributing to OpenCollab MCP! We welcome contributions from everyone—whether you are fixing a typo, improving documentation, reporting a bug, writing tests, or adding features.

This guide provides everything you need to know to set up your local development environment and submit high-quality contributions.

---

## 1. Welcome and Scope of Contributions

OpenCollab MCP is an AI-powered open source contribution matchmaker built as a Model Context Protocol (MCP) server. It connects AI clients (such as Claude Desktop, Cursor, or VS Code) to GitHub, enabling developers to find, evaluate, verify, and plan open source contributions.

The codebase is designed to be lean, fast, and easy to maintain (~1,000 lines). We welcome:
- **Bug fixes**: Resolving unintended behavior, edge cases, or API incompatibilities.
- **Documentation improvements**: Clarifying setups, guides, and tool usage.
- **Test coverage**: Adding tests for edge cases, queries, and input validation.
- **Feature enhancements**: New tools or enhancements that align with our focused, lean architecture.

---

## 2. Code of Conduct

All contributors and participants are expected to adhere to our [Code of Conduct](CODE_OF_CONDUCT.md). Please read it to ensure a welcoming, respectful, and harassment-free community for everyone.

---

## 3. Before Starting

To prevent duplicate effort and ensure changes align with project goals:

- **Check existing issues and PRs**: Before opening a new issue or PR, search open and closed issues to see if the topic has already been discussed.
- **Discuss major changes**: For non-trivial features or architecture changes, open an issue first to discuss the design with maintainers.
- **Request assignment**: Before implementing an issue, comment on it and request maintainer assignment or confirmation. Wait for maintainer confirmation before writing code so multiple contributors do not duplicate work on the same issue.

---

## 4. Development Setup

### Prerequisites
- Python 3.10 or higher (`python --version`)
- Git

### Step-by-Step Setup

1. **Clone the repository**:
   ```bash
   git clone https://github.com/prakhar1605/Opencollab-mcp.git
   cd Opencollab-mcp
   ```

2. **Create a virtual environment**:
   ```bash
   python -m venv .venv
   ```

3. **Activate the virtual environment**:
   - **Linux / macOS**:
     ```bash
     source .venv/bin/activate
     ```
   - **Windows (PowerShell)**:
     ```powershell
     .venv\Scripts\Activate.ps1
     ```
   - **Windows (Command Prompt)**:
     ```cmd
     .venv\Scripts\activate.bat
     ```

4. **Install the package in editable mode with development dependencies**:
   ```bash
   pip install -e ".[dev]"
   ```

5. **Run the server locally (stdio mode)**:
   ```bash
   python -m opencollab_mcp
   ```

6. *(Optional)* **Inspect interactively via the MCP Inspector**:
   ```bash
   npx @modelcontextprotocol/inspector python -m opencollab_mcp
   ```

---

## 5. Configuration and GitHub Token Safety

OpenCollab MCP interacts with the GitHub API.

- **Automated tests run without a token**: The repository's automated tests are designed to use mocks and should run without a live GitHub token. Do not make live GitHub API requests in tests.
- **Unauthenticated vs. authenticated access**: Unauthenticated access may work for public GitHub API requests, while configuring a token can be useful for authenticated requests and higher API rate limits.
- **Configuring the token**: When testing manual tool calls, running the server live, or verifying end-to-end integration with an MCP client, set the token as an environment variable in your session:
  - **Linux / macOS**:
    ```bash
    export GITHUB_TOKEN="ghp_your_personal_access_token"
    ```
  - **Windows (PowerShell)**:
    ```powershell
    $env:GITHUB_TOKEN="ghp_your_personal_access_token"
    ```
  - **Windows (Command Prompt)**:
    ```cmd
    set GITHUB_TOKEN=ghp_your_personal_access_token
    ```
  *(Note: `GH_TOKEN` is also recognized if `GITHUB_TOKEN` is unset.)*
- **Required permissions**: Use a classic token with only the `public_repo` scope. OpenCollab only performs read requests.
- **Credential safety**: **Never commit real tokens, keys, or credentials** to source files, commit messages, or pull requests. If a `.env` file is used locally, ensure it is ignored by git.

---

## 6. Branching and Development Workflow

- **The `main` branch is protected**: Direct pushes to `main` are blocked. All contributions must be submitted via pull requests.
- **Create a descriptive branch**: Branch off the latest `main`:
  ```bash
  git checkout -b descriptive-branch-name
  ```
  *(Tip: Descriptive names like `fix/issue-123-token-handling` or `docs/add-contributing-guide` help reviewers understand your branch.)*
- **Keep changes focused**: Limit each branch and pull request to a single issue or improvement. Avoid bundle-commits that mix unrelated features, formatting sweeps, or dependency changes.

---

## 7. Testing

OpenCollab MCP uses `pytest` with `pytest-asyncio` in `auto` mode and strict markers.

- **Run the full test suite**:
  ```bash
  pytest -v
  ```

- **Run a specific test file**:
  ```bash
  pytest tests/test_discovery_queries.py -v
  ```

- **Test expectations**:
  - Tests live in the `tests/` directory.
  - New tools, bug fixes, and model changes should include corresponding tests.
  - Follow existing patterns using mocked fixtures (`mock_github`, `captured_params`, etc.). Automated tests are designed to use mocks and should run without a live GitHub token.
  - Do not make live GitHub API requests in tests.

---

## 8. Linting and Code Style

OpenCollab MCP uses [Ruff](https://docs.astral.sh/ruff/) to maintain code quality.
- Configuration: targets Python 3.10, 100-character line length, with rule sets `E`, `F`, `W`, `I`, `UP`, and `B` enabled (`E501` and `E701` ignored).

- **Run Ruff lint checks**:
  ```bash
  ruff check src tests
  ```

- **Automatically apply safe fixes**:
  ```bash
  ruff check --fix src tests
  ```

Ensure `ruff check src tests` passes cleanly before opening a pull request.

---

## 9. Pull Requests

When your changes are ready:

1. **Push your branch** to your fork or repository.
2. **Open a pull request** targeting the `main` branch.
3. **Write a clear PR description**:
   - Summarize the motivation and changes made.
   - Link related issues using GitHub closing keywords when appropriate (e.g., `Closes #123` or `Fixes #123`).
   - Mention the verification commands you ran (e.g., `pytest -v`, `ruff check src tests`) and their results.
4. **Continuous Integration (CI)**:
   - CI runs on Ubuntu with Python 3.10, 3.11, 3.12, and 3.13.
   - CI executes `ruff check src tests`, `pytest -v`, and a package smoke test. All checks must pass.
5. **Code review**:
   - Maintainers will review your PR and may suggest adjustments.
   - Address feedback constructively and push follow-up commits to the same branch; GitHub updates the PR automatically.

---

## 10. Submission Checklist

Before submitting your pull request, please verify:

- [ ] I checked existing issues and confirmed assignment/alignment with maintainers before starting.
- [ ] I created a dedicated branch off the latest `main` (not working directly on `main`).
- [ ] I set up the environment using `pip install -e ".[dev]"`.
- [ ] I added or updated tests in `tests/` for my changes.
- [ ] All tests pass locally with `pytest -v` (no live API token required).
- [ ] All lint checks pass locally with `ruff check src tests`.
- [ ] I have not committed any personal tokens, credentials, or secrets.
- [ ] My PR description clearly explains the changes, links related issues, and reports test results.
