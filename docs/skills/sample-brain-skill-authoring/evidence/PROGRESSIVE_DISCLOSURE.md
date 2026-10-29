# PROGRESSIVE DISCLOSURE decision

| Content | Placement | Why |
|---------|-----------|-----|
| Lifecycle workflow + output contract | Inline `SKILL.md` | Core decisions agents need every activation |
| Package checklist tables | `references/package-checklist.md` | Long mechanical lookup; reused by script narrative |
| Split rules | `references/progressive-disclosure.md` | Meta-guidance; would bloat inline Purpose |
| RED defective package | `fixtures/red-mirror-only-path-hint/` | Evidence artifact, not instructions |
| Package checker | `scripts/check_authoring_package.py` | Mechanical invariant automation |

No artificial split of short prose. One representative RED fixture instead of
many template stubs.
