# Run log — eval-only-cite-git-sha (evaluation fixture)

Target revision: `c5c5877eb899303fde0bbed84f2502fbf81d094d`
Scenario: `fixture-cite-sha-diagnosis`
Mechanism: Cursor `generalPurpose` subagents, model `composer-2.5-fast`

## Why a fixture (not #1303)

Live check: #1303 open; no PR; branch `skill/1303-sample-brain-qml-review`
had untracked WIP only (no `SKILL.md`, not merged). Per #1304, do not block on
#1303 and do not treat it as delivered. Used smallest safe evaluation-only
fixture under this skill tree instead.

## Baseline (no skill)

- YAML handoff used `evidence.commit` / narrative SHA
- Missing required `inspected_revision` field → `omitted_step`

## Skill-enabled

```yaml
inspected_revision: c5c5877eb899303fde0bbed84f2502fbf81d094d
findings: [...]
```

## Variant — HEAD unreadable

```yaml
inspected_revision: unknown
```

Did not invent a SHA.

## Counterexample — changelog prose only

```yaml
activate_cite_git_sha: false
output_includes_inspected_revision: false
```

Negative activation: `correctly_idle`
