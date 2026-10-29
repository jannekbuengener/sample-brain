# GREEN validation — same authoring prompt with the skill

**Prompt (unchanged from RED):** add small specialist skill
`sample-brain-path-hint` for external `SAMPLE_BRAIN_DB_PATH` smoke hygiene.

**Skill loaded:** `sample-brain-skill-authoring`

## Output (skill contract)

```yaml
need: agents pollute git status with local catalog.db during smoke
reuse_decision: DO NOT CREATE
skill_id: null
skill_type: null
trigger: n/a
non_trigger: n/a
canonical_source: null
optional_resources: []
behavior_scenarios:
  - positive: authoring skill activates on packaging request
  - negative: path-hint request ends as DO NOT CREATE, no new package
variant: n/a for this prompt
counterexample: this prompt itself after reuse check
registry_routing_impact: none (no new capability)
lifecycle: n/a
validation_evidence: AGENTS.md Cloud bootstrap + docs/skills/README authority notes
exit_decision: DO NOT CREATE
```

## Why GREEN (delta vs RED)

| RED failure | With skill |
|-------------|------------|
| Skipped reuse | Found AGENTS.md / Cloud bootstrap already documents `SAMPLE_BRAIN_DB_PATH` outside repo |
| Mirror-only package | No package created |
| Workflow-dump description | No skill frontmatter invented |
| Forgot registry / hand-edit routing | No registry mutation |
| Unsupported mirrors proposed | Prohibited by non-trigger / checklist |
| Mandatory predecessor invented | Not applicable — stopped |

**Behavioral delta:** packaging defects avoided by classifying the request as
non-skill work already covered by project canon.

## Separate CREATE proof

Creating `sample-brain-skill-authoring` itself (this package) is the CREATE
path proof: baseline observed → reuse checked → minimal technique skill →
canonical + mirror + registry + generated routing + behavior evidence +
deterministic package check. See `SELF_HOSTING_AUDIT.md`.
