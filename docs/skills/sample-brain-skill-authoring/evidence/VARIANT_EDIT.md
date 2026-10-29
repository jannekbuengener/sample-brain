# VARIANT — material edit for omitted output field

## Scenario

Existing skill `sample-brain-jules-dispatch` is imagined to omit
`validation_evidence` from an authoring-style output checklist used during a
packaging audit (synthetic pressure on the authoring skill, not a live
product rewrite of Jules).

## Reproduce (without authoring discipline)

Agent rewrites large sections of Jules skill body and hand-edits
`skill-routing.mdc` “to be safe”.

## With `sample-brain-skill-authoring`

1. Observe baseline: omitted field is an authoring-audit concern, not a Jules
   dispatch defect.
2. Minimal edit target: authoring skill output contract already includes
   `validation_evidence` — **no Jules body rewrite required**.
3. If a real skill were missing a required Relationships subsection: edit
   canonical `docs/skills/<id>/SKILL.md` only, sync mirror, rerun contract
   test, regenerate views **only if** registry/routing changed.
4. No regression: existing Jules contract tests remain the freeze surface.

## Result

```yaml
reuse_decision: EXTEND EXISTING  # authoring contract, not Jules rewrite
exit_decision: PROCEED
registry_routing_impact: none for the Jules body
```

Fixture note: no live mutation of `sample-brain-jules-dispatch` in this PR —
the variant proves the authoring decision procedure, not a drive-by rewrite.
