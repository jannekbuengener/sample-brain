# Branch Protection

Live Phase-A protection for `refs/heads/main` (issue #494 migration). GitHub live is authority; this file mirrors the active ruleset and must not invent desired settings.

- Active ruleset: `main-strict` (id `21112261`)
- Inactive temporary ruleset: `main-operator-temporary` (id `21112273`)
- PR-based delivery required
- `required_approving_review_count = 0`
- `dismiss_stale_reviews_on_push = false`
- `required_review_thread_resolution = false`
- Required linear history
- Deletion and non-fast-forward protection
- Bypass actors empty; no admin bypass
- Repository merge methods: merge commits OFF, squash ON, rebase ON
- Allowed merge methods on the pull_request rule: squash + rebase

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

The live ruleset does **not** currently require approving reviews, stale-review dismissal, or review-thread resolution. Process authority for dispositioning all review feedback (inline threads, top-level comments, bot/automated reviews, final-head recheck) and for requiring resolved inline threads before merge remains [`docs/MERGE_REVIEW_FEEDBACK_GATE.md`](MERGE_REVIEW_FEEDBACK_GATE.md), independent of the ruleset facts above.
