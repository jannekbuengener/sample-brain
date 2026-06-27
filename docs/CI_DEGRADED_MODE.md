# CI Degraded Mode and Runner Fallback Policy

## Purpose

This document defines how Sample-Brain handles PR merge gates when GitHub Actions or runner infrastructure is degraded.

The default contract remains **CI_GREEN**. Degraded handling is an exception path for infrastructure failure, not a shortcut around review, safety, or branch protection.

## 1. Default Policy: `CI_GREEN`

- Normal merge readiness requires **green required checks**.
- Optional checks should be **green**, **skipped**, or explicitly explained as non-merge-relevant.
- Review findings, thread resolution, and scope checks still apply even when CI is green.
- No fake-green trigger commits, direct pushes to `main`, or silent bypasses.

## 2. When `DEGRADED_CI_ACTIVE` Applies

`DEGRADED_CI_ACTIVE` is an exception state. It may be used only when all of the following are true:

- GitHub Actions is blocked by external infrastructure.
- The failure is not caused by the PR content.
- The cause was checked live from repo and GitHub state.
- The blocking condition is documented in the PR or review report.

Examples:

- GitHub billing lock blocks workflows before job logic starts.
- GitHub-hosted runners are unavailable or in outage.
- A self-hosted runner is required but currently unavailable.

Non-examples:

- Test failures caused by the branch diff.
- Dependency-review, Gitleaks, or CodeQL failures with real findings.
- Broken workflow YAML introduced by the PR.

## 3. `BILLING_LOCK_DOCS_ONLY_WAIVER`

This waiver is limited to **one specific PR** and **one specific infrastructure lock**.

It may be used only when all of the following are true:

- The PR is **docs-only**.
- The diff scope is small, exact, and manually reviewed.
- No `src/`, `tests/`, dependencies, configs, or `.github/workflows/**` files are changed.
- No private samples, DBs, indexes, caches, model artifacts, or large binaries are introduced.
- No secrets or local absolute paths are introduced.
- Failed checks are failing **only** because of billing lock or equivalent infra lock.
- Local diff and safety review evidence is documented.
- An explicit merge-GO exists.
- A PR comment documents the waiver before merge.
- Branch protection still allows the merge.

If GitHub still blocks the merge, the status is **`HOLD_BRANCH_PROTECTION`**.

## 4. `LOCAL_VALIDATION_REQUIRED`

For code, test, runtime, dependency, or config scope under CI outage:

- No automatic merge is allowed just because billing or runner infra is broken.
- Scope-appropriate local validation must be run and documented.
- For Sample-Brain today, relevant local validation may include:
  - `python -m pytest -q`
  - `python -m src.cli --help`
  - `sample-brain --help`
  - `python -m py_compile src/analyze.py src/cli.py`
  - feature-specific commands such as `vec status` or search-quality checks when those surfaces are touched
- If the repo later adopts dedicated lint or format tools, those become part of scope-appropriate local validation when in scope.
- Local validation is replacement evidence for unavailable CI execution, but it is **not** a fake green status.
- Merge still requires explicit degraded-mode GO.

## 5. `SELF_HOSTED_RUNNER_FALLBACK`

The preferred technical workaround for recurring hosted-runner, billing, or capacity problems is a minimal self-hosted runner path.

Boundary note:

- A self-hosted runner fallback is most useful when GitHub can still dispatch Actions jobs but hosted capacity or runner availability is the bottleneck.
- It does **not** guarantee a bypass for repository/account billing lock. If GitHub does not dispatch jobs at all because the account is locked, billing remediation remains the first unblocker.

Rules:

- A runner may be shared across local repositories if it is safe, clearly labeled, and not expected to serve conflicting parallel workloads.
- Runner labels should be explicit and stable, for example: `self-hosted`, `windows`, `sample-brain`, `shared-local`.
- Keep runner setup minimal, maintainable, and auditable.
- Prefer enabling the smallest useful jobs first:
  - Python smoke
  - Gitleaks
  - dependency-review where feasible
  - CodeQL only if realistic and maintainable for the runner host
- Runner or workflow changes are a **separate scope** from PR content review.
- No secrets, local machine paths, or private environment details should be committed into workflow files.

If repeated CI outages occur and no runner fallback exists, the escalation status is **`RUNNER_FALLBACK_REQUIRED`**.

For Sample-Brain, the technical rollout of shared self-hosted runner fallback remains separate implementation scope and is tracked in Issue [#99](https://github.com/jannekbuengener/sample-brain/issues/99).

### 5.1 Sample-Brain Self-Hosted Runner (2026-06-27)

**Why:** GitHub-hosted runners (`ubuntu-latest`) are blocked by an account/repo-level billing lock since 2026-06-15. All 4 existing workflows fail before job dispatch. The CDB repository (`jannekbuengener/Claire_de_Binare`) demonstrated that self-hosted runners bypass this lock.

**Runner scope:** repo-level, registered against `jannekbuengener/sample-brain`. NOT part of the CDB runner group.

**Labels:** `self-hosted`, `sample-brain`. No `cdb`, `docker`, or `merge-gate` labels.

**Workflow:** `.github/workflows/ci-smoke-self-hosted.yml` (new, separate file). Contains only Python smoke steps: checkout, Python version, `pip install`, `py_compile`, `--help`.

**Trigger:** `workflow_dispatch` only. No `pull_request`, no `push`.

**Security:**
- No secrets in the workflow file
- `contents: read` only
- No deployment or publishing steps
- No fork PR code can auto-trigger (manual dispatch only)
- Runner is a separate process instance, separate workdir, separate config from CDB runners

**Validation status:** `WORKFLOW_READY_WAITING_FOR_RUNNER_REGISTRATION` – the workflow file exists but cannot be tested until a runner is registered.

**Operator runbook:** See `docs/runbooks/SAMPLE_BRAIN_SELF_HOSTED_RUNNER.md`.

## 6. No-Waiver Surfaces

No degraded-mode docs waiver is allowed for:

- dependency bumps with security or supply-chain relevance
- workflow changes
- secrets, Gitleaks, or CodeQL findings
- runtime, DB, index, cache, or model artifacts
- private samples
- large binaries
- unclear or expanding scope
- unresolved review threads or missing review clarity

These should be held with the most specific status available, including:

- `HOLD_SECURITY_CHECK_UNAVAILABLE`
- `HOLD_WORKFLOW_SCOPE`
- `HOLD_ARTIFACT_OR_SECRET_RISK`

## 7. Status Values

| Status | Meaning |
|--------|---------|
| `CI_GREEN` | Standard state: required checks green; normal merge path |
| `DEGRADED_CI_ACTIVE` | CI is infra-blocked; degraded policy is active |
| `BILLING_LOCK_DOCS_ONLY_WAIVER` | PR-specific docs-only waiver for billing-blocked checks |
| `LOCAL_VALIDATION_REQUIRED` | CI unavailable for code/runtime scope; local validation evidence required |
| `RUNNER_FALLBACK_REQUIRED` | Repeated CI failure should be addressed via self-hosted runner fallback |
| `HOLD_BRANCH_PROTECTION` | GitHub rules or required checks still block merge; do not force |
| `HOLD_SECURITY_CHECK_UNAVAILABLE` | Security-significant checks are unavailable; no waiver |
| `HOLD_WORKFLOW_SCOPE` | Workflow or CI config changed; docs-only waiver not applicable |
| `HOLD_ARTIFACT_OR_SECRET_RISK` | Artifacts, secrets, or local-path risk present |

## 8. Merge Comment Requirement

Any approved degraded docs-only waiver must be documented in the PR before merge.

The comment should state:

- why CI is infra-blocked
- that the diff is docs-only and manually reviewed
- that no artifacts, secrets, or workflow/dependency changes are present
- that the waiver is PR-specific and not reusable by default

## 9. Relationship to Other Repo Rules

- `AGENTS.md` remains the top-level active agent rule surface.
- `SB.AGENT.RULESET.md` defines how agents classify and report degraded CI outcomes.
- `SB.BOOTLOADER.md` points CI and merge-governance tasks to this runbook.
- Branch protection and GitHub rules remain authoritative at merge time.
