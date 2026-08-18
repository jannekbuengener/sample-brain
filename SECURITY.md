# Security Policy

## Supported version

Security fixes target the current `main` branch. Older commits and local experimental branches are best-effort only.

## Reporting a vulnerability

Do not publish vulnerability details, exploit steps, secrets, private sample paths, logs, or credentials in a public issue, pull request, discussion, or commit.

1. Open the repository's **Security** tab.
2. If **Report a vulnerability** is available, use that private GitHub reporting form.
3. If that private form is not available, open a public issue containing **only** a request for a private security contact. Do not include technical vulnerability details in that issue. A maintainer will establish a private channel for the report.

This fallback is intentionally limited so a missing repository-level private-reporting setting never forces disclosure of the vulnerability itself.

## Maintainer handling

- Triage security reports privately before public disclosure.
- Never copy API keys, credentials, private absolute paths, sample/audio data, or other user-private material into issues or PRs.
- Use a coordinated fix/disclosure process appropriate to the severity.
- Treat automated scanners as defense in depth, not proof that the repository is vulnerability-free.

## Repository security baseline

- Gitleaks secret scanning in pull requests and `main` pushes.
- CodeQL analysis on pull requests, `main` pushes, and the weekly schedule.
- Dependency Review on pull requests.
- Dependabot updates for Python and GitHub Actions dependencies.
- Third-party GitHub Actions are pinned to reviewed immutable commit SHAs.
- The core Python gate includes a minimal pinned Ruff static-correctness check plus the full pytest suite.
