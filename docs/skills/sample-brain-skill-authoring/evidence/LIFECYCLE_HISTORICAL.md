# HISTORICAL / RETIRED lifecycle scenario

Live enums: `active | on-demand | historical | parked`.

## Example already in registry

`sb-verfuegbare-skills-liste-2026-08-09` is `lifecycle: historical`, marked
not active routing authority, and must not appear as a Priority-A route.

## Authoring rule demonstrated

When retiring a skill:

1. Remove or avoid `priority_a_matrix` / active chain references.
2. Set `lifecycle: historical` (map “retired” language here — do not invent
   `retired` as a new enum).
3. Preserve necessary historical refs with explicit historical wording.
4. Leave Cursor mirror only if still useful as archive; never leave it looking
   like an active first-choice skill without registry truth.
5. Regenerate views; confirm generated routing no longer promotes it.

Fixture: `fixtures/historical-retired-stub/README.md` records the checklist
without registering a fake second skill.
