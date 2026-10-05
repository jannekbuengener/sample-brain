## TL;DR

## Linked work / exact scope
- Refs/Closes: #
- Slice class: `product_code | docs | ci_tooling | dependency | workflow | governance`
- In scope:
- Explicit non-goals:

## Delivery gates

### Live state / ownership
- [ ] Current `main`, target issue, direct dependencies and materially relevant open PRs checked.
- [ ] Existing state/contract owner is reused; no duplicate authority, mutation path, config owner or parallel canon introduced.

### Integration / reachability
- [ ] Every new/changed public seam has a named consumer/call path in this slice, or the issue explicitly freezes it as standalone/headless and names the follow-up owner.
- [ ] State/event/persistence flow is traced end-to-end where applicable; no hidden second mutation path or orphaned wiring is introduced.
- [ ] N/A reason (no runtime/public seam change):

### Test-first gate
For significant `product_code` slices, follow `sample-brain-test-first` exactly. For other slice classes mark the whole block N/A with a reason.
- [ ] `DOCS_GATE` — intended behavior/contract is explicit and non-contradictory.
- [ ] `TEST_GATE` — focused acceptance/regression tests were defined before product implementation.
- [ ] `TEST_FREEZE` — frozen acceptance was not weakened to fit implementation.
- [ ] `IMPLEMENTATION_GATE` — implementation is the smallest change satisfying frozen acceptance.
- [ ] `CHECKS_GATE` — focused + protected validation is green.
- [ ] N/A reason (non-product-code only):

### Validation / drift
- [ ] Focused tests or task-specific checks: `<command + result>`
- [ ] Protected adjacent contract/integration tests: `<command + result or N/A>`
- [ ] `git diff --check`
- [ ] Ruff / compile / types as applicable
- [ ] `python tools/check_canon_drift.py` when docs/canon/governance/status are touched
- [ ] `python tools/check_capability_drift.py` when operations/capability/routing/skill mirrors are touched
- [ ] QML/UI only: exact-HEAD runtime evidence + agent-owned `VISUAL_ACCEPT_PASS`

### Merge readiness
- [ ] PR head SHA recorded and all evidence applies to that exact head.
- [ ] Required CI is green, or repository-approved degraded-mode evidence is documented.
- [ ] Active review/approval policy is satisfied; no unresolved blocking review thread remains.
- [ ] No private samples/audio, local DB/index/cache, credentials, machine-local paths or unnecessary binary artifacts.
- [ ] Baseline/pre-existing failures are separated from regressions; no invented green status.

## Evidence
- Final head:
- Tests/checks:
- Runtime/visual evidence (if applicable):
- Known baseline limitations:

## Risk / impact

## Rollback
- Revert path / migration notes (or `N/A`):
