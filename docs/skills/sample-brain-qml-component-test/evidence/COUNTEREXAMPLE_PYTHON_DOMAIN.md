# COUNTEREXAMPLE — pure Python domain (#1305)

**Status:** must route away from QML component testing  
**Prompt:** Design automated coverage for BPM normalization / catalog filter
behavior owned by Python analysis/controller code with no QML-specific gesture,
focus, Loader, or virtualized-delegate path.

## Design with skill (non-activation)

```text
Behavior/authority:
  BPM / filter / ranking values are Python Core/Controller/Catalog authority.
  QML may later project a number; it must not own normalization.

Why QML component coverage NOT required:
  There is no QML failure mode — a green QML test would only re-assert a
  projected string while the defect lives in Python.

Layer decision: python_unit | python_contract

Fixture/boundary:
  Existing Python unit/contract fixtures (synthetic rows, temp DB via
  SAMPLE_BRAIN_DB_PATH outside the repo).

Inputs/events:
  Function/CLI/controller calls with synthetic BPM / filter inputs.

Observable assertions:
  Normalized BPM / filtered catalog results / schema fields.

Async/wait strategy: n/a (or Python async only if the domain is async).

Lifecycle/virtualization: n/a

Companion tests: integration/CLI as needed; still not QML component.

Non-goals:
  QML component tests; screenshot acceptance; moving BPM authority into QML.
```

## Verdict

`NOT_ACTIVATED` for QML component testing — skill correctly routes to Python
tests / `sample-brain-test-first` without inventing QML coverage.
