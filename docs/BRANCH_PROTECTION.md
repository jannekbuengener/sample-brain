# Branch Protection

Live Phase-A protection for `refs/heads/main` (issue #494 migration):

- Active ruleset: `main-strict` (id `21112261`)
- Inactive temporary ruleset: `main-operator-temporary` (id `21112273`)
- PR-based delivery required
- `required_approving_review_count = 1`
- Stale reviews dismissed on push
- Required review-thread resolution
- Required linear history
- Deletion and non-fast-forward protection
- Bypass actors empty; no admin bypass
- Repository merge methods: merge commits OFF, squash ON, rebase ON

Required status checks (preserve names and integration identities):

- `Ruff static gate` (GitHub Actions / `15368`)
- `Full core pytest` (GitHub Actions / `15368`)
- `Workbench transport tests` (GitHub Actions / `15368`)
- `Arrangement CLAP tests` (GitHub Actions / `15368`)
- `Search quality exit regression` (GitHub Actions / `15368`)
- `Python smoke` (GitHub Actions / `15368`)
- `CodeQL` (GitHub Advanced Security / `57789`)
- `gitleaks` (GitHub Actions / `15368`)
- `dependency-review` (GitHub Actions / `15368`)
- `analyze (python)` (GitHub Actions / `15368`)

`mcp-quality-gate` / exact-head remains advisory until Phase B (#388). Merge only when required checks are green and the repository merge predicate is satisfied.

Required review-thread resolution at the ruleset layer is **necessary but not sufficient**. Process authority for dispositioning all review feedback (inline threads, top-level comments, bot/automated reviews, final-head recheck) is [`docs/MERGE_REVIEW_FEEDBACK_GATE.md`](MERGE_REVIEW_FEEDBACK_GATE.md).
