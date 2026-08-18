---
name: sample-brain-jules-dispatch
description: >
  Dispatch one already clearly scoped Sample Brain issue to Jules safely, then
  hand the result back into the normal Sample Brain process for independent
  verification. Does not plan, diagnose, merge, or close issues.
---
<!--
Canonical Skill Source: docs/skills/sample-brain-jules-dispatch/SKILL.md
Surface: cursor
Sync Status: mirrored-from-canon
Last Verified: 2026-08-18
Drift Policy: Cursor mirrors must match the canonical skill body.
-->

# Sample Brain Jules Dispatch Skill

## Purpose

Use this skill to delegate one already sufficiently scoped Sample Brain issue to
Jules and return the result into the normal Sample Brain process. Jules is a
controlled delegation gateway, not a Sample Brain authority.

The dispatch loop is:

```text
clearly scoped issue -> current Sample Brain canon -> minimal cleaned Jules task
-> Jules session -> plan review -> explicit plan approval -> status / activities
/ follow-up -> Jules PR -> independent local handoff
```

Jules may:

- work
- create a branch
- create a PR

Jules must NOT:

- merge
- close issues
- replace Sample Brain governance
- receive private data

A Jules result alone is never DONE proof.

## Non-Goals

- Does NOT replace general issue planning. Use
  `sample-brain-issue-to-session-plan` when the issue is not yet scoped.
- Does NOT invent a root cause. Use `sample-brain-root-cause` for an unclear bug
  cause.
- Does NOT automatically send every issue to Jules.
- Does NOT autonomously merge.
- Does NOT autonomously close issues.

## Hard Limits

- Jules must NOT merge.
- Jules must NOT close issues.
- Jules must NOT replace Sample Brain governance.
- Jules must NOT receive private data.
- A Jules result alone is never proof that Sample Brain work is done.

## Required Dispatch Gate

The skill may only dispatch when at least all of the following are clear:

- target issue
- current repository
- base branch / base SHA
- goal
- acceptance criteria
- allowed scope
- relevant repo files / facts
- relevant tests
- forbidden scope

## Routing Conditions

| Condition | Route |
|-----------|-------|
| Issue is unclear / not scoped | `route_to = sample-brain-issue-to-session-plan` or `BLOCKED` |
| Bug cause is unclear | `route_to = sample-brain-root-cause` |
| Known defect with missing guard | respect existing `regression-gap` / `test-first` rules |
| All required dispatch fields clear | dispatch to Jules via this skill |

Do not build a second routing authority. Routing to another skill means
"suggests next step", not "authorizes action".

## Jules Task Envelope

The runtime helper builds a structured task prompt with these sections:

```text
REPOSITORY
ISSUE
BASE
GOAL
ACCEPTANCE
RELEVANT REPO FACTS
ALLOWED SCOPE
MUST NOT TOUCH
VALIDATION
SAFETY
DELIVERABLE
```

`relevant_files` must be exclusively tracked, repo-relative paths. No automatic
repo dump.

DELIVERABLE for write tasks:

- implement requested slice
- relevant tests
- branch / PR allowed
- DO NOT MERGE the pull request
- DO NOT CLOSE ISSUE
- report PR URL and concise result

## Security / Redaction

`JULES_API_KEY`:

- read exclusively from environment
- never a CLI argument
- never a config file in the repo
- never in the prompt
- never in stdout / stderr
- never in logs
- never in exceptions
- never in evidence

HTTP auth: `X-Goog-Api-Key: <runtime value>`. No header dump.

The sanitizer / validator must at least block or clean:

- `JULES_API_KEY` value
- typical `KEY` / `TOKEN` / `SECRET` assignments
- absolute Windows paths
- UNC paths
- absolute Unix / home / user paths
- private sample / audio paths
- DB / cache / model paths outside the repo

If a context file lies outside the repo: do not transfer it to Jules.

- Sample audio: never transferred.
- Private tracks: never transferred.
- SQLite: never transferred.
- Model caches: never transferred.
- Runtime artifacts: never transferred.

When uncertain: fail closed.

## Official Jules API

Use only the documented public API:

```text
Base: https://jules.googleapis.com/v1alpha

GET    /sources
POST   /sessions
GET    /sessions/{id}
GET    /sessions/{id}/activities
POST   /sessions/{id}:approvePlan
POST   /sessions/{id}:sendMessage
```

No undocumented endpoints. No UI automation. No scraping.

Source selection:

- fetch sources live
- exactly `githubRepo.owner == jannekbuengener`
- exactly `githubRepo.repo == sample-brain`
- no fuzzy match

If not present: `BLOCKED_SOURCE_NOT_CONNECTED`. Never start a session against
the wrong repo.

## Session Create

On create:

- `sourceContext.source` = exactly the found Jules source
- `githubRepoContext.startingBranch` = explicit base branch
- `prompt` = cleaned, standardized task envelope
- for every task allowed to change repo files: `requirePlanApproval = true`
- never rely on Jules default
- for explicitly read-only / trivial smoke tasks `requirePlanApproval` may be
  `false`

`AUTO_CREATE_PR` is supported. If `allow_pr == true`: `automationMode =
AUTO_CREATE_PR`. If `allow_pr == false`: do not request PR automation.

The helper must never perform a merge.

## Plan Gate

The runtime helper must NOT automatically approve a write plan.

Explicit separate actions:

```text
dispatch
status
activities
approve
message
```

`approve` happens only on explicit invocation.

The skill prescribes:

1. Jules generates a plan.
2. Caller reads the latest `planGenerated` activity.
3. Caller compares with issue, acceptance, allowed scope, forbidden files,
   dependency / workflow boundaries.
4. If the plan fits: approve explicitly.
5. Drift: exactly one targeted correction via `sendMessage`.
6. Re-check the new plan.
7. Further drift: `BLOCKED_PLAN_DRIFT`.

No approval loop.

## CLI / Module Interface

`src/jules_dispatch.py` is usable as a module:

```text
python -m src.jules_dispatch doctor
python -m src.jules_dispatch dispatch
python -m src.jules_dispatch status --session sessions/...
python -m src.jules_dispatch activities --session sessions/...
python -m src.jules_dispatch approve --session sessions/...
python -m src.jules_dispatch message --session sessions/...
```

`dispatch` reads its `DispatchContext` as JSON from stdin. `message` reads the
follow-up text from stdin. No full prompts as command-line arguments.

`doctor`:

- checks whether `JULES_API_KEY` is set
- never shows its value
- lists / matches the Sample Brain source
- outputs only safe status

Example:

```json
{
  "auth_configured": true,
  "source_connected": true,
  "source": "sources/github/jannekbuengener/sample-brain"
}
```

## Normalized Result

The helper outputs machine-readable JSON with at least:

```text
dispatch_status
jules_state
session
plan_id
pull_request_url
error_code
```

Allowed Sample Brain dispatch statuses include at least:

```text
CREATED
AWAITING_PLAN_APPROVAL
IN_PROGRESS
RESULT_READY
PARTIAL
BLOCKED
FAILED
```

Important:

- Jules state `COMPLETED` + PR -> `RESULT_READY`
- NOT: `DONE`, `MERGED`, `CLOSED`

Jules may never authoritatively claim Sample Brain is finished.

## Error Mapping

| Condition | Code |
|-----------|------|
| missing `JULES_API_KEY` | `BLOCKED_AUTH` |
| HTTP 401 / 403 | `BLOCKED_AUTH` |
| Sample Brain source missing | `BLOCKED_SOURCE_NOT_CONNECTED` |
| HTTP 429 | `BLOCKED_RATE_LIMIT` |
| timeout | `BLOCKED_REMOTE` or `PARTIAL` if a usable session already exists |
| HTTP 5xx | `BLOCKED_REMOTE` or `PARTIAL` if a session already exists |
| Jules state `FAILED` | `FAILED` |
| unknown Jules state / unexpected response | `PARTIAL_PROTOCOL_DRIFT` |

No fake-green. Do not blindly auto-retry POSTs when that could create duplicate
sessions / messages.

## Activities / Follow-Up

Read activities fully over documented pagination. At least process:

```text
planGenerated
planApproved
agentMessaged
userMessaged
progressUpdated
sessionCompleted
sessionFailed
```

Follow-up:

- send only cleaned text
- no secrets
- no local paths
- no scope expansion
- primarily for targeted correction of a running Jules task

## PR Handoff

When a session is `COMPLETED`:

- inspect outputs.
- if a `pullRequest` is present: return `pull_request_url`.
- status: `RESULT_READY`.

Jules authority ends here.

The skill must explicitly state: the caller then independently verifies:

- PR live
- correct repo
- correct base
- diff / changed paths
- issue acceptance
- relevant tests
- private artifacts
- secret safety
- scope

No additional review agent is required for this. The controlling Sample Brain
agent can perform this independent check itself.

Only after this check runs the normal flow:

```text
PR -> Merge -> Issue Close -> Live Verification
```

## Relationships

**Standalone Guarantee:** `standalone: true`

This skill runs independently with a fully scoped issue. Other skill outputs are
optional context enhancements.

### Can Receive From

- `sample-brain-issue-to-session-plan` — already scoped work slice
- `sample-brain-root-cause` — confirmed cause with explicit guard
- `sample-brain-regression-gap` — identified missing guard

### Route If

| Condition | Target | Required | Notes |
|-----------|--------|----------|-------|
| issue not scoped | `sample-brain-issue-to-session-plan` | Yes | Dispatch needs a clear slice first |
| bug cause unclear | `sample-brain-root-cause` | Yes | Do not invent a cause |
| known defect, missing guard | `sample-brain-regression-gap` -> `sample-brain-test-first` | No | Respect existing rules |
| dispatch fields clear | Jules via this skill | No | Explicit opt-in only |

### Next Recommended

After `RESULT_READY`: independent local verification by the controlling agent,
then normal PR -> Merge -> Issue Close -> Live Verification.

### When to STOP

- `BLOCKED`: required dispatch field missing.
- `BLOCKED_SOURCE_NOT_CONNECTED`: Sample Brain not connected to Jules.
- `BLOCKED_PLAN_DRIFT`: plan repeatedly diverges from accepted scope.
- `BLOCKED_AUTH`: API key missing or rejected.

### Cycle Rules

No forward loop. Plan correction is a single targeted `sendMessage`, then
re-check. Repeated drift stops at `BLOCKED_PLAN_DRIFT`.
