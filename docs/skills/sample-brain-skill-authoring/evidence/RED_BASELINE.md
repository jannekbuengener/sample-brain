# RED baseline — `sample-brain-skill-authoring` (#1308)

**Status:** recorded before the skill existed  
**Capability set used:** generic Cursor `create-skill` habits + `docs/skills/README.md`
skim + AGENTS.md awareness (no `sample-brain-skill-authoring`)  
**Repo head at capture:** `origin/main` =
`c5c5877eb899303fde0bbed84f2502fbf81d094d`  
**Live packaging anchors (not fabricated):**

- Canonical skill authority is `docs/skills/<id>/SKILL.md`
  (`docs/skills/README.md`).
- Active mirror surface is `.cursor/skills/` only; Claude/Codex/OpenCode mirrors
  are not authorized without verified loader need.
- Machine routing authority is
  `docs/operations/CAPABILITY_REGISTRY.json`; generated views are
  `.cursor/rules/skill-routing.mdc` and `SB.VERFUEGBARE.SKILLS.md`.
- Lifecycle vocabulary on live main:
  `active | on-demand | historical | parked`
  (`tools/capability_lib.py` `VALID_LIFECYCLES`).
- Existing contract pattern: `tests/test_jules_dispatch_skill_contract.py`
  (canonical + mirror sync + registry/routing presence).

## Prompt given to the unskilled agent

> Add a small repository-owned specialist skill
> `sample-brain-path-hint` that helps agents choose
> `SAMPLE_BRAIN_DB_PATH` outside the repo for smoke tests and keep
> `git status` clean. Keep it minimal. Follow normal Sample Brain repo
> context.

No packaging rules beyond normal repo context were supplied.

## Inadequate package produced without the skill

Artifact recorded under
`fixtures/red-mirror-only-path-hint/` (defective mirror-only package).

| Check | Unskilled result |
|-------|------------------|
| Reuse search | skipped — did not check existing AGENTS.md / Cloud bootstrap notes that already cover external DB path |
| Baseline-without-skill | skipped — wrote the skill immediately |
| Canonical `docs/skills/.../SKILL.md` | **missing** |
| Cursor mirror `.cursor/skills/...` | created only (treated as primary) |
| Frontmatter `description` | workflow dump (“create dirs, export env, run init…”) instead of when-to-load triggers |
| Progressive disclosure | giant single `SKILL.md` with templates and shell dumps |
| Capability registry | **not updated** |
| Generated routing views | hand-edited prose claim in skill body (“add to skill-routing.mdc”) instead of registry + `generate_capability_views.py` |
| Behavior / activation tests | none; no counterexample; no non-activation |
| Unsupported mirrors | proposed `.claude/skills/` and `.codex/skills/` “for completeness” |
| Lifecycle | called the skill “candidate” in prose; never mapped to live enums |
| Standalone | implied mandatory predecessor `sample-brain-test-first` before any path hint |

## Exact mistake (strongest repo-specific defect)

**Mirror-only packaging:** the agent edited `.cursor/skills/` as if it were
authority, omitted canonical `docs/skills/`, skipped
`CAPABILITY_REGISTRY.json`, and treated generated routing as a hand-edit
target. Secondary defects (workflow-dump description, unsupported mirrors,
no behavior proof, false predecessor chain) compound the same failure class:
generic skill-writing instincts without Sample Brain glue.

## Rationalization observed

“Cursor loads `.cursor/skills/`, so that is the skill. Registry and docs can
be cleaned up later.” That rationalization is exactly what this meta skill
must interrupt.

## Verdict of RED pass

`SB_SKILL_PACKAGING_INCOMPLETE` — a Cursor-visible skill file exists while
canonical source, registry/routing, trigger-quality description, and
behavior validation remain wrong or absent.

## Same inputs required for GREEN

GREEN must process the **same** authoring prompt (or an equivalent small
specialist-skill request), classify need + reuse, and either:

1. **DO NOT CREATE** when AGENTS/canon/bootstrap already covers it, or
2. if CREATE is justified after a stronger observed failure, produce
   canonical + mirror + trigger description + registry/routing via
   generators + behavior scenarios + live lifecycle enum —

without renaming the packaging defect class.
