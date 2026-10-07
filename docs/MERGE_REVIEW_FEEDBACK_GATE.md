# Universal Merge Policy — Review Feedback Gate

**Status:** ACTIVE_CANON (process / merge governance)  
**Purpose:** Mandatory pre-merge gate for review feedback on the final PR head. Complements `CI_GREEN`; does not replace it.

## Rule

A PR must **not** be merged while relevant review feedback is unchecked or unanswered.

An untreated comment is a merge blocker.

## Scope (final PR head)

Before merge, agents and maintainers must recheck **all** of the following on the **final** head SHA:

- PR Conversation / top-level comments
- Inline review comments
- Review threads
- Submitted reviews
- Bot / automated reviews (including Codex and similar)
- New comments since the last fix / review round

GitHub live state wins over chat memory or stale local notes.

## Required disposition

Every relevant review point needs an explicit disposition. Feedback must not be silently ignored.

| Disposition | When |
|-------------|------|
| `FIXED` | Change landed on the final head that addresses the point |
| `ANSWERED` / `EXPLAINED` | Point assessed; response documents why no code change is needed (or what was already true) |
| `NOT_APPLICABLE` | Point does not apply; short technical rationale required |
| `DUPLICATE` | Point already handled; pointer to the already-handled comment/thread required |

A reviewer is not automatically right. External and automated feedback must be **technically verified**. Every comment must still be **read**.

## Inline review threads

Before merge, every inline review thread must be:

1. read
2. technically assessed
3. fixed or answered as needed
4. then resolved

**No open review threads at merge.**

`Resolved` means the point was read, understood, technically assessed, and consciously closed — not that the reviewer was right.

## Top-level comments

Top-level conversation comments may lack GitHub “resolved” status. Every top-level comment with technical feedback must be **visibly dispositioned** (`FIXED` / `ANSWERED` / `EXPLAINED` / `NOT_APPLICABLE` / `DUPLICATE`) with a short rationale when not implemented. `ANSWERED` and `EXPLAINED` are equivalent aliases.

## Fix loop (when feedback causes code changes)

```text
REVIEW → VERIFY → FIX → TEST → PUSH → WAIT FOR FINAL HEAD
→ RECHECK ALL COMMENTS/THREADS → RECHECK CI
→ restart merge-gate check on the new final head
```

Do not claim merge readiness on a superseded head.

## Final merge gate

Merge only when **all** of the following are true on the final head:

1. **ALL REVIEW FEEDBACK SEEN**
2. **ALL FEEDBACK DISPOSITIONED**
3. **ALL INLINE THREADS RESOLVED**
4. **NO NEW UNREVIEWED COMMENTS ON FINAL HEAD**
5. **REQUIRED CI READY ON FINAL HEAD** — either default `CI_GREEN`, **or** an approved exceptional path under `docs/CI_DEGRADED_MODE.md` (for example `DEGRADED_CI_ACTIVE` / narrow docs-only waiver when that runbook’s predicates are met). Degraded CI does **not** waive this review-feedback gate.
6. **NO UNRESOLVED BLOCKING REVIEW**

Then, and only then: **MERGE** (still requires explicit merge-GO where agent policy demands it).

## Final delivery / merge report (measurable)

Before claiming merge readiness or merging, the final delivery / merge report **must** state measurable review counts for the final head:

```text
REVIEW COMMENTS:
  total=<n>
  fixed=<n>
  answered_or_na=<n>
  unreviewed=0
  unresolved_threads=0
```

Counting rules:

- `total` — relevant review points on the final head (conversation, inline, threads, submitted reviews, bot/automated)
- `fixed` — dispositioned `FIXED`
- `answered_or_na` — dispositioned `ANSWERED` / `EXPLAINED` / `NOT_APPLICABLE` / `DUPLICATE`
- `unreviewed` — unread or undispositioned points; must be `0` for merge readiness
- `unresolved_threads` — open inline review threads; must be `0` for merge readiness

`unreviewed=0` and `unresolved_threads=0` are required merge-readiness predicates. Disposition vocabulary remains `FIXED` / `ANSWERED` / `EXPLAINED` / `NOT_APPLICABLE` / `DUPLICATE` as defined above. Do not invent a parallel status layer for this report.

## Failure rule (post-merge discovery)

If after merge it is found that relevant review feedback existed pre-merge but was unchecked:

→ **QUALITY PROCESS FAILURE**

Required response:

1. Fully triage the missed feedback
2. If technically valid, create a follow-up repair slice
3. Document the root cause
4. Correct the merge-gate process

Ignoring review feedback is a **delivery-process failure**, not a normal technical bug.

## Relationship to other authority

| Surface | Role |
|---------|------|
| `docs/CI_DEGRADED_MODE.md` | CI readiness / degraded infra exceptions; `CI_GREEN` default |
| `docs/BRANCH_PROTECTION.md` | Live GitHub ruleset facts (approvals, stale-review dismissal, thread resolution, checks) |
| This document | Process gate: feedback must be seen, assessed, dispositioned, and closed on the final head |
| `.cursor/agents/sample-brain-quality-gatekeeper.md` | Read-only merge-gate caller; must HOLD when this gate fails |
| `.cursor/agents/sample-brain-pr-packager.md` | Packaging readiness; must not report READY_FOR_MERGE while this gate fails |

Live ruleset enforcement (when present) is **necessary but not sufficient**. This process gate still requires disposition and resolved inline threads before merge, even when the live ruleset does not require thread resolution or approvals. See `docs/BRANCH_PROTECTION.md` for current GitHub facts.

## Agent status tokens (optional reporting)

When this gate blocks merge readiness, prefer:

- `HOLD_REVIEW_FEEDBACK_OPEN` — unread, undispositioned, or unanswered feedback; or open inline threads
- `QUALITY_PROCESS_FAILURE` — post-merge discovery that pre-merge feedback was unchecked
