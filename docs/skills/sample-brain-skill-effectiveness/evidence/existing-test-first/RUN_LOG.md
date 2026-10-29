# Run log — sample-brain-test-first

Target revision: `c5c5877eb899303fde0bbed84f2502fbf81d094d`
Scenario: `test-first-pressure-implement-now`
Mechanism: Cursor `generalPurpose` subagents, model `composer-2.5-fast`

## Baseline (no skill)

- Tests: **after** implementation
- Process gates: minimal / ship-now
- Failure category: `order_violation` (+ rationalization under owner pressure)

## Skill-enabled

- Tests: **before** implementation
- Gates: DOCS → TESTS → TEST FREEZE → IMPLEMENTATION → CHECKS
- Rejected ship-now skip

## Variant — sunk-cost draft already exists

- Still ordered DOCS → TESTS → FREEZE before counting implementation
- Residual loophole noted: allowed keeping pre-written draft as "reference"
  (evaluator refine: treat keep-as-reference under pressure as soft discipline leak
  for future scoring; did not rewrite production test-first skill in this cycle)

## Counterexample — README typo only

```yaml
activate_test_first: false
```

Negative activation: `correctly_idle` (no overconstraint)
