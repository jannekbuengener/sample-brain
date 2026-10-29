# SELF-HOSTING bootstrap audit (one pass)

1. **Baseline** — RED mirror-only packaging recorded (`RED_BASELINE.md`).
2. **Create** — minimal `sample-brain-skill-authoring` technique skill.
3. **Rerun** — same packaging pressures against this package.
4. **Audit defects found and repaired in this pass:**
   - Ensure Cursor mirror exists with canonical pointer (not primary edits).
   - Register exactly once; generate views (no hand-edit of marked blocks).
   - Description kept trigger-oriented (algorithm stays in body).
   - Progressive disclosure: checklist/tables moved to `references/`.
   - Mechanical checker added only after RED showed mirror/registry gaps.
   - Standalone: true; #1304 optional, not required.
5. **STOP** — no second full rewrite cycle without a new observed failure.

Exit: `SAMPLE_BRAIN_SKILL_AUTHORING_WORKFLOW_EFFECTIVE` after registry,
drift checks, and contract tests pass.
