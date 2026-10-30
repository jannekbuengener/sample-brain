# Policy-controlled repository promotion v1 (#1176)

Status: frozen contract for S7 implementation under #1040. Repository merge is
distinct from runtime authorization; `production_authorized=false` is invariant.
S8 analyzer replay, baseline acceptance and recovery are excluded.

## Authority and input

`run_promotion(source_state_path, manifest, provider, repository, host,
worktree_root, attempt_root, review_evidence=None)` is optional automation tooling.
It never enters normal analyzer execution. No scheduler or new SDK is required.
Host paths are invocation bindings only and never serialized into portable state.

Read the S6 state, derived `.locked-claim.json` and `.locked-result.json` together.
Validate the existing state/result contracts, frozen state fingerprint, claim
fingerprint, request/evidence/policy and baseline/current/domain bindings.
A claim without a committed result is insufficient. Only decision v1.1.0,
ready/PROMOTION_CANDIDATE_IDENTIFIED/handoff_promotion_controller/PASS and locked
test|holdout may enter. No new evaluator or policy-to-decision mapping.

## Manifest and domain seam

`sample-brain.analysis-promotion-manifest.v1`, artifact version `1.0.0`, has an
exact field set: document_type, artifact_version, domain, baseline_candidate,
current_candidate, locked_result_fingerprint, decision_fingerprint,
evidence_fingerprint, expected_base_sha, repository_id, allowed_paths,
forbidden_paths, materializer, changes, change_fingerprint, validation,
policy, policy_fingerprint, manifest_fingerprint. Fingerprints are lowercase
SHA-256 over canonical #956 JSON; self-fingerprint excluded. Base is a full
lowercase Git SHA. Repository identity is portable `owner/name`.

`materializer={id,version,inputs}` identifies a registered/injected domain-owned
provider with matching `domain`, `materializer_id`, `materializer_version`.
Provider `validate_plan(manifest, locked_result)` owns semantic candidate/config
and policy validation; returning anything except True rejects promotion.
Provider `materialize(inputs)` returns an exact mapping of allowed paths to UTF-8
text. It receives no repository/worktree handle. There is no dynamic code/import
discovery, arbitrary shell command in the manifest or candidate-id-to-file guess.

`changes` maps each exact path to `{before_sha256,after_sha256}` (null before
means new file). All paths must equal the allowlist; no glob, traversal, Windows
alias, case collision, symlink, submodule or binary support in v1. The change
fingerprint hashes this map. Before/after equal is invalid. Domain manifests
bind content before dispatch. The controller independently checks actual Git
changed paths and file hashes, including untracked/ignored outputs. Empty,
missing or extra mutation fails. Forbidden paths include declared prefixes plus
unconditionally protected Git/workflow/security/credentials/private/cache/audio/
DB/model surfaces. Text must pass portability/secret/path guards before write
and again before commit; this is a conservative bounded guard, not a claim of
general secret detection. Existing repository security CI remains mandatory.

`validation` is a nonempty ordered list of domain-owned portable contract IDs.
Provider `validate_candidate(worktree, contract_id)` executes a known focused
validation and returns True only on success. The provider is trusted repository
code, not an untrusted plugin sandbox. Recheck the diff after validation.

`policy={version,required_checks,merge_method,review_gate}` fixes a nonempty set
of `{name,app_id}` required checks, squash|rebase, and
`all_feedback_dispositioned.v1`. Live required rules must equal the frozen check
set including app identities; unsupported or unreadable rules fail closed.
No host-local commands or paths are accepted in semantic inputs.

## Isolation and durable attempt

The host repository must be clean (tracked, untracked and ignored files included)
and origin must identify the manifest repository. Origin comparison is fail-closed
on host, owner, repository name, and protocol/security identity; only URL userinfo
(credentials/token) may be ignored when an otherwise identical GitHub remote is
rewritten by the execution host. Local origin/main and live
main must equal expected_base_sha before mutation and before merge. Never rebase.
An isolated branch/worktree is derived from the manifest fingerprint; host supplies
the parent directory. Existing foreign branch/worktree contents are not adopted.
No reset/clean/stash/force/admin operation. Commit only explicit allowed paths.

`sample-brain.analysis-promotion-attempt.v1` has version 1.0.0 and records source
and manifest fingerprints, base, attempt/branch identity, changed paths/change
fingerprint, focused validation references, committed/pushed/PR head, PR number,
required checks and observed states, repository_merge_eligible, merge SHA, phase,
status/reason and `production_authorized=false`, sealed by state_fingerprint.
Atomic durable writes reuse S6 fsync/replace discipline. A per-attempt exclusive
execution lock prevents simultaneous writers. An orphan lock requires explicit
host reconciliation; never delete it automatically.

Each external step has a durable pre-action phase. Completed steps are resumed
without re-materialization or duplicate PR/merge. Uncertain local materialization
or validation fails closed for host reconciliation. An uncertain commit/push/PR/
merge is reconciled from exact Git/host identities before any retry. If a PR-create
claim has no visible PR, hold rather than blindly create again. Existing PRs must
match repository/base/branch/head and unique identity. Corrupt/conflicting state
or changed source/manifest never resets the attempt. Failed/pending gates can be
observed again on resume without repeating completed local work.

## Host and merge eligibility

A narrow injectable host exposes live main/rules, branch push, PR lookup/create,
snapshot, expected-head merge, and merged-result verification. The concrete
adapter uses local git and authenticated gh, structured JSON, no shell execution,
bounded timeouts and pagination. Auth/network errors become infrastructure_hold;
policy/candidate errors become controlled_failure. Error strings/output are never
copied into portable artifacts. Unsupported host evidence is UNKNOWN/HOLD.

Checks are bound to exact PR head and app ID, with SUCCESS, FAILED, PENDING,
MISSING, UNKNOWN, CANCELLED distinct. Duplicate matching observations are UNKNOWN.
Only completed success satisfies a required check; skips/neutral do not.
Require open non-draft PR, correct base/repository/branch/head, acceptable live
mergeability, review approvals required by live rules, no blocking review or open
inline threads. Feedback snapshots include all conversation/inline/review IDs,
bodies and update/resolution state in their fingerprint. A trusted host-supplied
review_evidence binds head and feedback fingerprint and dispositions every item
as FIXED|ANSWERED|EXPLAINED|NOT_APPLICABLE|DUPLICATE. With no feedback, no attestation
is needed. The controller never auto-resolves threads or self-approves.

Re-read main, policy and PR snapshot immediately before merge; drift holds.
Merge uses expected_head_sha (gh `--match-head-commit`) with the frozen method.
After a lost response, read PR merged state before retry; an ambiguous incomplete
merge holds. Record success only when live PR is merged with exact validated head,
merge SHA exists, and fetched main contains that SHA. This verifies repository
delivery only; no S8 analyzer acceptance is inferred.

## Proof boundary

Temporary real Git repositories and a fake injectable host prove controller
behavior/failures/restart. Concrete gh adapter tests verify request/response and
pagination semantics. The implementation PR supplies normal real CI/review/merge
evidence. No artificial product default change or extra demonstration PR is
required; no actual analyzer promotion quality is claimed.

Exit after actual implementation delivery: AQ_PROMOTION_CONTROLLER_V1_FROZEN;
otherwise AQ_PROMOTION_CONTROLLER_PARTIAL_HOLD or
AQ_PROMOTION_CONTROLLER_INSUFFICIENT. DONE_MERGED_CLOSED requires merged PR and
closed #1176, plus #1040 delivery update.
