# Branch Protection (Empfehlung)

Minimum:
- Require a pull request before merging
- Require status checks to pass before merging
  - CI
  - CodeQL
  - Dependency Review
  - Gitleaks
  - Trivy (falls Docker genutzt wird)
- Require linear history (optional)
- Dismiss stale approvals (optional)

Ziel: Keine "gruenen Illusionen". Merge nur, wenn Checks gruen sind.
