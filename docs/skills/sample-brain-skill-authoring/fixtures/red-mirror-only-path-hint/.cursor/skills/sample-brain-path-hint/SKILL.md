---
name: sample-brain-path-hint
description: >
  Create a temp directory, export SAMPLE_BRAIN_DB_PATH to that directory,
  run python -m src.cli init, then scan/analyze so git status stays clean.
  Always run sample-brain-test-first first. Also copy this skill into
  .claude/skills and .codex/skills, and add a line to skill-routing.mdc.
---

# Sample Brain Path Hint Skill

Put the catalog DB outside the repo.

## Full workflow dump (should not be the skill body shape)

1. mkdir /tmp/sample-brain-demo
2. export SAMPLE_BRAIN_DB_PATH=...
3. python -m src.cli init
4. python -m src.cli scan --root ...
5. python -m src.cli analyze
6. Always require sample-brain-test-first before this skill
7. Hand-edit .cursor/rules/skill-routing.mdc
8. Duplicate into .claude/skills and .codex/skills

## Giant templates

(omitted shell transcripts and multi-page path tables that belong in
AGENTS.md / bootstrap docs, not a specialist skill)
