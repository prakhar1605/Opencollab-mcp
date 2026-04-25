# Security Policy

## Reporting a vulnerability

**Please do not file public issues for security vulnerabilities.**

Instead, email **prakhar9999pandey@gmail.com** with:

- A description of the vulnerability
- Steps to reproduce
- Potential impact
- Any suggested fix (if you have one)

You can expect:

- Acknowledgement within **72 hours**
- A status update within **7 days**
- A coordinated disclosure timeline once the fix is identified

## Scope

This project is an MCP server that calls the GitHub API on behalf of the user.
Areas of particular concern:

- **Token handling.** OpenCollab reads `GITHUB_TOKEN` from env. It must never
  log, leak, or transmit this token outside the GitHub API request headers.
- **Injection.** User-controlled input flows into search queries. We sanitize
  language strings; if you find a way to inject GitHub query operators with
  unintended effect, that's in scope.
- **Cache poisoning.** The TTL cache is keyed on `(path, params)`. If you
  find a way to make one user's request return another user's data, that's
  high severity.
- **Rate limit exhaustion.** Attacks that make the server burn the user's
  GitHub rate limit needlessly.

## Out of scope

- Anything that requires the attacker to already control the user's machine or
  GitHub token
- Issues in the upstream GitHub API
- Issues in the MCP SDK itself (please report those upstream)

## Supported versions

Only the latest minor version (`0.x`) receives security updates.
