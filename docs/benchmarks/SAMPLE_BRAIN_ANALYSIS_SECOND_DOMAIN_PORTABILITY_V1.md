# Second-domain closed-cycle portability proof v1 (#1040 S10)

Status: implementation contract for the AQ6 second-domain reuse proof.
Parent: #1040. Delivery child: #1200.

## Goal and proof boundary

The S5-S9 composition delivered for AQ1 Tempo (#1064, #1097, #1170, #1176,
#1178, #1182) must be reusable for a second real analyzer-quality domain
without AQ1-specific logic in the generic supervisor, closed-cycle or iterator
layers. This slice proves that reuse for AQ6 Harmonic Ranking.

It is a portability/reuse proof. It changes no production, default or harmonic
behaviour, it authorizes no promotion, and it does not change any analyzer
metric, weight, threshold or ground truth.

## Domain-owned search space

Each domain owns its bounded candidate search space under
`src/aq_candidate_search_spaces/`. The AQ6 provider derives its members from
the frozen AQ6 candidate registry (`HARMONIC_RANKING_CANDIDATES`) in
declaration order and binds each candidate to the canonical public candidate
config fingerprint. It exposes a stable search-space id/version, produces its
fingerprint through the existing #1064 contract, and hides no candidate,
parameter sweep or runtime-discovered mutation scope.

The generic chain resolves a domain search space through the domain-owned
registry in `src/aq_candidate_search_spaces/__init__.py`. The supervisor's
default-provider resolution therefore contains no domain literal, and a new
domain needs no generic branch. Unknown domains fail closed.

## Second-domain composition proof

The existing S9 composition runs for AQ6 with only domain-owned adapter,
search-space and policy inputs changed. The proof covers self-start from a valid
AQ6 baseline state, real sanitized AQ6 CALIBRATION execution, deterministic
next-candidate iteration over the bounded search space, freeze binding the exact
candidate/config/search-space identities, exactly one locked TEST/HOLDOUT
transition after the freeze, simulated bounded S7 repository-governance
handoff, simulated S8 post-merge acceptance with LAST_KNOWN_GOOD lineage, and
continuation from the accepted generation without replaying the previous
promotion. Restart and replay remain idempotent: no duplicated candidate
advancement, locked evaluation, promotion proof or baseline acceptance.

Repository operations stay explicitly simulation-only, and the guard still
rejects real Sample Brain self-promotion.

## Decision-policy boundary

The AQ6 decision policy is a domain-owned input over existing AQ6 evidence.
Theory remains a hard gate that ranking metrics cannot average away: a
failing theory truth table yields a non-reproducible domain exit and holds the
cycle without any promotion attempt. Preference remains `NOT_REQUIRED` with no
fabricated pseudo-signal. No TEST/HOLDOUT tuning, no new harmonic formula,
candidate, weight or threshold is introduced to make the proof progress.

## Evidence classes

1. `REAL_SANITIZED_DOMAIN_EXECUTION` - real AQ6 domain adapter plus the
   domain-owned bounded candidate provider on the frozen AQ6 fixtures;
2. `INJECTED_PROOF_EVALUATOR` - test-only host policy derived from actual AQ6
   artifacts, not a production threshold;
3. `INFRASTRUCTURE_SIMULATION` - deterministic temporary Git repositories and
   injected S7/S8 host behavior;
4. real PR/CI/review/merge evidence - repository-delivery evidence reported
   outside the portable cycle artifact.

## Cross-domain neutrality

The generic S5-S9 modules contain no AQ6 special-case path; AQ1 and AQ6 differ
only through their domain-owned adapter, search-space and policy inputs. The
AQ1 first-closed-cycle proof stays green unchanged. Persisted artifacts stay
portable and bind the exact domain, candidate, config, search-space and
evidence fingerprints.

## Boundaries

- `production_authorized=false` remains invariant.
- No real Sample Brain promotion, no real repository self-promotion, no
  production/default/harmonic behaviour change.
- No new generic evaluator, iterator, decision or promotion controller; no
  scheduler, daemon or cloud requirement; no L3 agent-generated candidates.
- No private samples, audio, database, index, cache, credential or host path in
  committed evidence.

## Exit

Exactly one:

- `AQ6_SECOND_DOMAIN_CLOSED_CYCLE_PROOF_DELIVERED`
- `AQ6_SECOND_DOMAIN_PORTABILITY_PARTIAL_HOLD`
- `AQ6_SECOND_DOMAIN_PORTABILITY_BLOCKED`

This slice is evidence toward #1040's program-level requirement for reusable
autonomous operation across representative AQ domains. It does not by itself
imply #1040 closure.
