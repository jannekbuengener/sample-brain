# Package / registry checklist

## Canonical + mirror

- [ ] `docs/skills/<id>/SKILL.md` is the edit authority
- [ ] `.cursor/skills/<id>/SKILL.md` mirrors body and states
      `Canonical Skill Source: docs/skills/<id>/SKILL.md`
- [ ] Bodies match from first `#` heading onward
- [ ] No `.claude` / `.codex` / OpenCode / Gemini skill trees unless loader proven

## Frontmatter

- [ ] `name:` equals skill id
- [ ] `description:` is when-to-load (triggers/symptoms), not a workflow dump
- [ ] Description does not paste the full algorithm block

## Body

- [ ] `standalone: true` declared
- [ ] `## Relationships` with Can Receive From / Route If / When to STOP / Cycle Rules
- [ ] No mandatory predecessor chains
- [ ] Skill type classified when behavior-testing

## Registry / routing

- [ ] Exactly one entry in `docs/operations/CAPABILITY_REGISTRY.json`
- [ ] `canonical_source` under `docs/skills/`
- [ ] `lifecycle` ∈ `active` | `on-demand` | `historical` | `parked`
- [ ] Candidate language maps to `on-demand` (or stay unregistered until ready)
- [ ] Retired language maps to `historical` (not left `active`)
- [ ] Routing situations/chains updated only if needed
- [ ] Views regenerated: `python tools/generate_capability_views.py`
- [ ] Never hand-edit marked generated blocks

## Docs index

- [ ] `docs/skills/README.md` lists the skill
- [ ] `docs/SKILL_INTEGRATION_PLAN.md` mentions it when contract tests require

## Validation

- [ ] Behavior RED/GREEN (+ variant/counterexample) recorded
- [ ] `python tools/check_capability_drift.py`
- [ ] `python tools/check_canon_drift.py` when docs/canon/routing touched
- [ ] Focused skill contract tests green
- [ ] `scripts/check_authoring_package.py --skill-id <id>` green for CREATE/EDIT

## Promotion gate

Promotion to active routing requires proven need + behavior improvement +
nonactivation evidence + package/mirror/registry/routing/deterministic green +
no duplicate — not mere `SKILL.md` existence.
