# Need baseline — why sample-brain-skill-effectiveness exists

Issue: #1304 (parent #1302). Live main at capture: `c5c5877eb899303fde0bbed84f2502fbf81d094d`.

## Current validation can prove (structural)

- Canonical `docs/skills/*/SKILL.md` exists for registered local skills
- Cursor mirrors match skill bodies (`tools/capability_lib.validate_skill_mirrors`)
- `CAPABILITY_REGISTRY.json` entries + generated routing views stay in sync
  (`tools/check_capability_drift.py`, `tests/test_capability_ops.py`)
- Per-skill packaging contracts (example: `tests/test_jules_dispatch_skill_contract.py`)

## Current validation cannot prove (behavioral)

- An agent performs the target task better **with** the skill than **without** it
- Positive vs negative activation under realistic prompts
- Discipline skills hold under pressure / rationalization
- Transfer to variants / counterexamples (not one memorized scenario)
- Distinction between `EFFECTIVE`, `INEFFECTIVE`, `UNNECESSARY`, and fail-closed
  `INCOMPLETE`

## Observed gap (RED for this meta-skill)

Treating registry/mirror presence as skill quality would silently mark skills
`EFFECTIVE` without a baseline-without-skill run. That is exactly the failure
mode #1304 forbids.

## Bootstrap note

This evaluator did not require itself to exist before recording this need.
Need is established from #1304 + live structural-only tooling limits above.
