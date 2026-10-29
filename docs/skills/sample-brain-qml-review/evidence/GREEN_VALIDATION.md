# GREEN validation — `sample-brain-qml-review` (#1303)

**Same RED input:** `tests/fixtures/qml_review/red_stale_delegate_index.qml`  
**Capability:** `sample-brain-qml-review` + mechanical helper `scripts/qml_review_scan.py`

## Same scenario (behavior delta)

Command:

```bash
python docs/skills/sample-brain-qml-review/scripts/qml_review_scan.py --json \
  tests/fixtures/qml_review/red_stale_delegate_index.qml
```

Observed GREEN mechanical helper result:

- `activated=true`
- `verdict=HOLD`
- Finding category: `STALE_CACHED_DELEGATE_INDEX` (mechanical reuse-risk signal)
- Location points at `cachedSampleIndex: index`
- Authority field: `n/a — semantic ownership review required`

Skill-guided **semantic** review then maps that signal to
`DELEGATE_IDENTITY_AS_AUTHORITY` when the deferred `toggleFavorite(cachedSampleIndex)`
path is treated as product sample identity under `reuseItems` — the RED miss that
generic review rationalized as harmless debounce UX.

Note: live `qmllint` (when available) reports unqualified-access nits but does
**not** classify Sample Brain authority defects. Helper output is not ownership
proof; semantic review does not depend on qmllint or authority-token lists.

## Variants

1. `tests/fixtures/qml_review/variants/binding_break_width.qml`
   → helper `BINDING_BREAK_ASSIGNMENT` / `HOLD` (mechanical)
2. `tests/fixtures/qml_review/variants/qml_shadow_bpm_authority.qml`
   → helper does **not** emit ownership findings (no BPM/token heuristics)
   → skill semantic review category `QML_SHADOW_AUTHORITY` / `HOLD`

## Counterexample

`tests/fixtures/qml_review/counterexamples/immediate_index_intent.qml`

- Immediate `selectRow(index)` only
- helper `verdict=PASS` (no false `STALE_CACHED_DELEGATE_INDEX`)

## Non-activation

`tests/fixtures/qml_review/non_activation_python_only.py`

- Pure Python helper, no QML surface
- `verdict=NOT_ACTIVATED`

## Exit

`SAMPLE_BRAIN_QML_REVIEW_SKILL_EFFECTIVE` when packaging + CI also pass.
