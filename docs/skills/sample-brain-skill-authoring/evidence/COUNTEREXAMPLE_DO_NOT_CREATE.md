# COUNTEREXAMPLE — DO NOT CREATE

| Request | Why not a new skill |
|---------|---------------------|
| One-off bugfix for a single failing pytest | Use `sample-brain-root-cause` / product tests |
| “Ensure registry lifecycle enum is valid” | Already `tools/capability_lib.py` + `check_capability_drift.py` |
| “Remind agents about private samples” | Already AGENTS.md / project rules |
| “Write better commit messages” | External `jMerta/commit-work` — no SB adaptation needed |
| Copy Superpowers `writing-skills` into `docs/skills/` | Wholesale external copy; SB glue skill already covers adaptation |

Expected authoring output:

```yaml
reuse_decision: DO NOT CREATE
exit_decision: DO NOT CREATE
```
