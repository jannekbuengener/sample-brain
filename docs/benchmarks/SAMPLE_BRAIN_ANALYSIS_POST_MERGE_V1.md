# Post-merge verification and recovery v1 (#1178)

Status: contract frozen for S8 implementation under #1040. This composes the
S6 locked result, S7 repository-promotion attempt and #1097 supervisor identity.
It does not prove the first complete autonomous closed cycle.

## Authority and boundary

A successful S7 repository merge is necessary but is not sufficient to accept a
new analyzer baseline. S8 starts only from a validated, committed S7 attempt in
`merged` state with an exact merge SHA and matching S6 lineage.

S8 owns:

- exact merged-repository verification;
- accepted-baseline lineage;
- LAST_KNOWN_GOOD identity;
- invalid-promotion state;
- bounded, history-preserving forward repair when verification fails;
- restart/replay reconciliation for these operations.

S8 does not own candidate search, TEST/HOLDOUT tuning, a second evaluator, a
second promotion controller, scheduler/daemon behavior or L3 code generation.

## Input lineage

The controller validates the existing S6 source, S7 manifest and S7 attempt
before post-merge execution. At minimum the following must agree exactly:

- domain;
- baseline and promoted candidate/config identities;
- locked-result, decision and evidence fingerprints;
- S7 manifest fingerprint;
- S7 attempt fingerprint;
- promoted PR/head identity;
- non-null S7 merge SHA;
- repository identity.

The live repository must contain the recorded merge SHA. Moved or ambiguous
lineage fails closed. A later accepted baseline may not be overwritten by a
stale S8 attempt.

## Verification plan

`sample-brain.analysis-post-merge-plan.v1`, artifact version `1.0.0`, is a
portable, versioned domain-owned policy. It binds the S7 lineage above plus:

- exact repository id and merge SHA;
- verification provider id/version;
- ordered verification contract ids;
- forbidden-regression / acceptance policy identity;
- recovery provider id/version and deterministic inputs;
- exact recovery changed-path allowlist and before/after content hashes;
- focused recovery validation contract ids;
- required repository checks, merge method and review gate;
- policy and plan fingerprints.

The shared controller never invents analyzer acceptance criteria. Provider
verification returns only a bounded machine result:
`PASS`, `HOLD`, `CONTROLLED_FAILURE` or `FORBIDDEN_REGRESSION`, an opaque
lowercase SHA-256 evidence fingerprint, and an optional portable reason code.
Anything except `PASS` is not baseline acceptance.

No credentials, raw host output, private audio, DB/index/cache/model paths,
machine-local absolute paths or opaque agent memory are legal portable values.

## Exact-repository replay

Verification is executed from a clean detached Git worktree at the exact SHA
being evaluated. The provider receives the worktree only as a host binding; the
path is never serialized. Provider-created repository changes are forbidden.

For the promoted candidate, the replay SHA is the S7 merge SHA. The provider
must verify the exact promoted candidate/config under the plan's ordered
contracts. The shared layer records a compact verification reference containing
repository SHA, candidate identity, contract id, outcome, evidence fingerprint
and a deterministic verification fingerprint.

The original locked TEST/HOLDOUT is not automatically reused as tuning input.
Post-merge verification is a reproduction/health surface chosen by domain
policy. Missing or unknown evidence is never PASS.

## Baseline lineage

S8 stores accepted authority separately from the #1097 v1 supervisor schema.
That preserves all existing supervisor-state readers unchanged.

`sample-brain.analysis-baseline-lineage.v1`, version `1.0.0`, records:

- domain;
- current accepted baseline reference;
- previous accepted baseline as `last_known_good` when present;
- monotonically increasing generation;
- source S8 attempt fingerprint;
- state fingerprint.

A baseline reference binds:

- candidate/config identity;
- repository SHA;
- verification-reference fingerprints;
- acceptance-policy fingerprint;
- lineage source fingerprint;
- its own deterministic baseline fingerprint.

`LAST_KNOWN_GOOD` means a baseline that has itself passed the S8 verification
contracts. Candidate identity alone is not sufficient repository-recovery
authority.

For the first S8 adoption, if no baseline-lineage artifact exists, the S7
pre-promotion baseline at the S7 base SHA is verified under the same frozen
verification policy before it can become the bootstrap current baseline. If
that verification cannot PASS, S8 holds; automatic recovery has no proven
LAST_KNOWN_GOOD target.

On promoted-candidate PASS, baseline-lineage is atomically advanced once:

`current = promoted@merge_sha`

`last_known_good = previously verified current baseline`

Repeated invocation with the same committed result is idempotent and does not
increase generation twice.

## Failure and recovery

A promoted replay result of HOLD, CONTROLLED_FAILURE or FORBIDDEN_REGRESSION
marks the promotion invalid. The promoted candidate never becomes accepted
baseline authority. Optimization must not continue from it.

If a verified baseline-lineage exists for the S7 pre-promotion baseline, S8
enters recovery-required and may execute the frozen recovery plan. Recovery is
history preserving:

`failed merged main -> isolated recovery branch/worktree -> bounded repair ->`
`focused validation -> PR -> exact-head gates -> merge -> repaired-main replay`

No reset of main, force push, history rewrite, direct main push, ruleset/admin
bypass or repo-wide agent repair is allowed.

Recovery materialization is domain owned and deterministic. The controller
independently reuses S7 `GitRepository` diff/path/content guards and the S7 host
policy/check/review/expected-head primitives. The recovery plan's changed paths
and before/after hashes are exact; extra, missing, binary, private or governance
changes fail closed.

V1 recovery begins only when live main is exactly the failed S7 merge SHA. If
main has advanced, the attempt holds for explicit replanning rather than
silently applying a stale repair to newer semantics.

After a recovery merge, the repaired repository SHA is replayed against the
LAST_KNOWN_GOOD candidate under the same verification contracts. Recovery is
complete only if that replay PASSes. Baseline-lineage is then atomically rebound
to the same verified LAST_KNOWN_GOOD candidate at the new recovery merge SHA;
the prior verified repository reference is retained as `last_known_good`. The
invalid promoted candidate is never recorded as accepted. This rebound is what
allows a later loop to start from the actual repaired `main`, not a stale SHA.

## Durable attempt / replay

`sample-brain.analysis-post-merge-attempt.v1`, version `1.0.0`, is stored in a
host-supplied directory outside the repository. It records portable fingerprints
and repository/PR/SHA identities only.

The attempt has durable pre-action phases for verification, baseline acceptance,
recovery materialization, commit/push/PR/merge and repaired-state verification.
An exclusive per-attempt lock prevents duplicate execution, and a second
host-local lock derived from the baseline-lineage path serializes distinct S8
attempts that could otherwise race on the same baseline generation. Orphan locks
fail closed for explicit reconciliation. Uncertain external actions are reconciled
from exact identities before retry; destructive actions are never blindly repeated.

Terminal/resumable outcomes distinguish accepted, recovery-required, recovered,
controlled failure and infrastructure hold without copying raw exception text.
Already committed acceptance/recovery replays return the stored result without
rerunning domain verification or creating duplicate branches/PRs/merges.

## Security and observability

Persist only bounded structured reason codes. Do not serialize environment dumps,
CLI stderr/stdout, Authorization headers, tokens, secrets or absolute host paths.
Authenticated GitHub command output is host evidence, not portable state.

`production_authorized=false` remains separate from repository merge and baseline
lineage. S8 establishes verified analysis-baseline authority; it does not create a
global runtime authorization flag.

## Proof boundary

Tests use deterministic temporary Git repositories plus injected provider/host
adapters for success, failure, moved-state, restart and recovery paths. A real
existing analysis adapter may be used for a narrow replay seam where safe, but
synthetic infrastructure proof is never reported as production analyzer quality.

Delivery exit after implementation, final-head checks/review, merge and issue
closure: `AQ_POST_MERGE_RECOVERY_V1_FROZEN`.
