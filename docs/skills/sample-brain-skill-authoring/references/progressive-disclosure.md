# Progressive disclosure — when to split

Keep these **inline** in `SKILL.md`:

- purpose / primary rule
- triggers and non-triggers
- reuse / type / lifecycle decisions
- compact workflow
- output contract
- stop conditions
- relationships (receive / route / stop / cycles)

Move to `references/` or `scripts/` **only when** at least one is true:

| Signal | Prefer |
|--------|--------|
| Section exceeds ~40 lines of lookup tables | `references/<topic>.md` |
| Content is reused by multiple skills or a script | shared reference or `tools/` |
| Content is mechanical validation | `scripts/*.py` or existing drift tools |
| Content is a long worked example | one `references/example-*.md` or `fixtures/` |

Do **not** artificially split a short skill. Prefer **one** complete
representative example over many vague templates.

## Representative example (inline vs split)

For this authoring skill:

- Lifecycle enum mapping and package checklist → `package-checklist.md`
  (lookup tables; mechanical).
- Output field meanings → stay compact in SKILL.md YAML block.
- RED defective package → `fixtures/red-mirror-only-path-hint/` (evidence,
  not instruction bloat).
