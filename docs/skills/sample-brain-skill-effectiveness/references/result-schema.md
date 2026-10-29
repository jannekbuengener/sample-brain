# Evaluation Result Schema

Compact YAML-like result. No confidence percentages.

```yaml
target_skill: <skill-id>
target_revision: <git-sha-or-skill-version>
skill_type: discipline | technique | pattern | reference
scenario_id: <id>
inputs_comparable: true
structural_only: false
baseline:
  ran: true
  outcome: pass | fail | partial | not_run
  failure_category: <string-or-null>
  notes: <short>
skill_enabled:
  ran: true
  skill_loaded: true
  outcome: pass | fail | partial | not_run
  notes: <short>
delta:
  improved: true
  material_change: true
  summary: <what changed behaviorally>
activation:
  positive: used | not_used | unknown
  negative: correctly_idle | false_positive | unknown
transfer:
  variants_passed: 0
  counterexamples_passed: 0
  overconstraint: false
verdict: EFFECTIVE | INEFFECTIVE | UNNECESSARY | INCOMPLETE
incomplete_reason: <optional; required when INCOMPLETE>
```

## Fail-closed incomplete reasons

| Reason | Meaning |
|--------|---------|
| `missing_baseline` | Baseline without skill was not run first |
| `inequivalent_inputs` | Skill availability was not the only treatment variable |
| `skill_not_loaded` | Skill-enabled run did not actually load the skill |
| `structural_only` | Only schema/registry/mirror checks were performed |
| `missing_required_fields` | Result contract incomplete |
| `invalid_skill_type` | Skill type missing or unknown |
| `missing_delta` | No behavioral delta recorded |
| `agent_run_unavailable` | Skill-enabled agent observation missing |

`INCOMPLETE` is not `INEFFECTIVE`. Do not abuse `INEFFECTIVE` for missing evidence.

## Forbidden

- Confidence percentages / model self-scores as acceptance
- Silent `EFFECTIVE` when baseline is missing
- Treating registry/mirror presence as behavioral proof
