# First autonomous analyzer quality closed cycle v1 (#1040 S9)

Status: implementation contract for the first complete #1040 composition proof.
Parent: #1040. Delivery child: #1182.

## Goal and proof boundary

One bounded entry point composes the delivered #1043, #1054, #1060, #1064,
#1097, S6/#1170, S7/#1176, and S8/#1178 contracts. It owns only cycle
composition, a durable cycle attempt/result, and the continuation transition.
The component contracts remain authoritative for their own operations.

The first real domain is AQ1 Tempo. Live main registers
`aq1.tempo.candidate_compare` in the headless adapter registry and provides
the default AQ1 bounded candidate iterator. AQ4 candidate comparison exists,
but is not registered in those two automation seams. AQ1 therefore needs less
composition glue for this first proof. AQ1's frozen comparison contract defines
no promotion thresholds and says no production switch; this slice does not
change its metrics/defaults or claim analyzer-quality uplift.

The domain adapter must run against deterministic sanitized AQ1 inputs. The
evaluation decision provider is an injected host boundary, like the opaque
ARVP evidence inputs already consumed by #1060. It receives the actual
headless result and portable eval artifact and must bind its machine decision
to those fingerprints. Missing or malformed results are HOLD/failure. The
cycle layer does not invent evaluation gates or decision tokens.

For a provider-derived S6 decision, the durable pre-dispatch claim binds the
freeze fingerprint, locked request fingerprint, and stable provider ID. The
terminal S6 result binds the provider decision to the actual run and eval
fingerprints. A claim without a committed result remains uncertain and cannot
be automatically dispatched a second time.

The deterministic integration proof may use a temporary Git repository and
injected S7/S8 host. Its evidence is labelled infrastructure simulation. The
S9 implementation PR's real GitHub checks, review, merge, and main
verification are reported separately. Neither proves production analyzer
quality or changes `production_authorized=false`.

Evidence classes stay explicit and non-interchangeable:

1. `REAL_SANITIZED_DOMAIN_EXECUTION` - real AQ1 domain adapter + bounded candidate provider on sanitized fixtures;
2. `INJECTED_PROOF_EVALUATOR` - test-only host evaluator derived from actual AQ1 artifacts, not a production threshold;
3. `INFRASTRUCTURE_SIMULATION` - deterministic temporary Git repositories and injected S7/S8 host behavior;
4. real S9 PR/CI/review/merge evidence - repository-delivery evidence reported outside the portable cycle artifact.

## Entry point and persistence

`run_quality_cycle(...)` loads or creates a portable cycle attempt bound to
the exact initial baseline generation. On each invocation it loads S5 state,
the cycle attempt, and any committed S6/S7/S8 artifacts, then derives the one
next legal action. It calls the owning existing controller, validates the
returned identities, atomically persists the cycle transition, and continues
while the next action is determinate. It stops on terminal HOLD, failure,
uncertain external identity, exhausted budget, or an unrecognized state.

The cycle attempt/result is separate from #1097 state v1; no existing v1
supervisor artifact changes meaning or becomes invalid. Per-domain generation
and the S8 baseline-authority lock prevent stale/competing attempts from
mutating the same baseline. A stale generation fails closed.

Before every delegated controller call, the cycle attempt commits the phase
and invocation identity. On restart it reconciles that identity with the
controller's durable claim/result instead of blindly repeating an evaluation,
PR creation, push, merge, or baseline write. It never consumes TEST/HOLDOUT
as calibration evidence. Unknown state cannot be converted to PASS.

## Success sequence

1. Self-start from an allowed persisted baseline state.
2. Run the real AQ1 CALIBRATION headless request through #1060 and the
   injected decision provider; persist portable run/eval/decision refs.
3. Let #1097 invoke the #1064 iterator. Evaluate the next bounded candidate
   and consume the provider's actual machine selection/rejection. A rejection
   may advance only to the next declared candidate; a selection freezes.
4. Bind candidate, config, baseline, partition/corpus provenance, search-space
   identity, history, and decision/evidence fingerprints at freeze.
5. Run exactly one locked TEST/HOLDOUT through #1170. Only its committed
   machine-readable eligible handoff may proceed.
6. Pass the committed S6 handoff to #1176 without manual manifest translation.
   The integration proof uses a temporary repository and injected host; normal
   S7 branch/PR/check/review/merge guards remain authoritative.
7. Pass the exact merged S7 identity to #1178. Require post-merge PASS before
   accepting the candidate at the exact merge SHA. Preserve the prior accepted
   baseline as LAST_KNOWN_GOOD.
8. Reload from disk, seed a generation-specific S5 state from the S8 accepted
   baseline, and self-start one next bounded CALIBRATION action. The result
   binds this continuation state and proves no old candidate/promotion evidence
   was reused. A second promotion cycle is not required.
9. Persist a portable closed-cycle result with exact phase refs and outcome
   token `AUTONOMOUS_QUALITY_LOOP_FIRST_CLOSED_CYCLE`.

## Portable result

Document type: `sample-brain.analysis-quality-loop-closed-cycle.v1`,
artifact version `1.0.0`. The result binds domain, cycle id, initial accepted
baseline and generation, selected/final candidate and config, calibration
orchestration/eval/decision refs, candidate history, freeze state, locked
result/final decision, promotion manifest/attempt and PR/head identities,
merge SHA, post-merge verification, accepted baseline, LAST_KNOWN_GOOD,
continuation generation/next action, component contract versions, evidence
classifications, outcome, and deterministic result fingerprint.

Only portable IDs, SHAs, structured statuses, and fingerprints are allowed.
Never serialize local absolute paths, usernames, credentials, private audio,
DB/index/cache paths, raw host output, or raw logs.

## Failure outcomes

Every action fails closed and preserves the last committed generation:

- `domain_unavailable`
- `invalid_state`
- `baseline_evidence_missing`
- `candidate_space_exhausted`
- `no_justified_candidate`
- `calibration_hold`
- `freeze_mismatch`
- `locked_test_holdout_failure`
- `promotion_not_eligible`
- `promotion_governance_failure`
- `merge_uncertainty`
- `post_merge_verification_failure`
- `recovery_required`
- `recovery_failure`
- `stale_generation`
- `infrastructure_failure`

## Frozen test matrix

This matrix is fixed before implementation. Test names may be refined without
removing a behavior or weakening an assertion.

| Case | Frozen assertion |
|---|---|
| Success | One entry point composes real AQ1 baseline + bounded candidate evaluation, selection, freeze, locked TEST/HOLDOUT, S7, S8, and continuation-ready state. |
| Candidate rejection | Machine rejection invokes only the next declared candidate; exhausted space terminates without promotion. |
| Unknown/HOLD | Missing or malformed evaluation/decision evidence stops without candidate advancement or promotion. |
| Locked failure | TEST/HOLDOUT HOLD/FAIL is terminal for that candidate and never reaches S7. |
| Promotion failure | Failed/ineligible S7 preserves accepted baseline and does not enter S8 acceptance. |
| Post-merge failure | S8 recovery-required/failure keeps the promoted candidate unaccepted and retains LAST_KNOWN_GOOD semantics. |
| Restart | Resume after each durable phase reconciles existing S5/S6/S7/S8 identities and does not duplicate side effects. |
| Concurrency | Competing or stale generation cannot mutate the same baseline authority. |
| Continuation | Reloaded S8 acceptance seeds a new generation and deterministically derives the next action without reusing old promotion evidence. |
| Portability | Result fingerprint validates; forbidden local paths, secrets, private data, and raw logs are rejected. |
| Backward compatibility | Existing #1060 callers without the optional decision-provider seam and all existing #1097/S6/S7/S8 contracts remain unchanged. |

## Out of scope

Analyzer algorithms, AQ metric redesign, production-default changes, new
production promotion policy, real promotion against Sample Brain main, L3
codegen, scheduler/daemon, dashboard/UI/QML, Arrangement/Live, private samples,
and cloud dependencies.
