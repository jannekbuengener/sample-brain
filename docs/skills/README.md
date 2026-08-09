# Sample Brain Skills

`docs/skills/` is the canonical source for repository-owned skills. Skill
changes start here.

The only active mirror surface is `.cursor/skills/`. Each Cursor mirror must
identify its canonical source and match its skill body. Do not add Claude,
Codex, or OpenCode mirrors until a repository loader and an active need are
verified.

External skills remain routing references; their bodies are not copied here.

## Repository-Owned Skills

- `sample-brain-test-first`
- `sample-brain-root-cause`
- `sample-brain-regression-gap`
- `sample-brain-issue-to-session-plan`

## Skill Relationships

All four core skills are **standalone** — each runs independently with complete
inputs. Other skill outputs are optional context enhancements, not mandatory
predecessors.

### Standalone Guarantee

Every skill explicitly declares `standalone: true`. This means:
- Direct start with explicit inputs (issue, symptom, defect, or plan)
- No skill requires another skill as a mandatory predecessor
- Receiving a handoff from another skill is optional context enhancement
- **Routing to another skill means "suggests next step", not "authorizes action"**

### Relationships Section

Each skill includes a `## Relationships` section with:
- **Can Receive From:** Optional sources of context; receiving does not authorize implementation
- **Route If:** Conditions for routing to next skill or STOP states
- **Optional External Routes:** jMerta routes with local fallback skills
- **When to STOP:** Conditions that block further progress
- **Cycle Rules:** Allowed vs. forbidden cycles

### Global Routing Entry Point

The **initial entry point** to the skill network is determined by
`.cursor/rules/skill-routing.mdc`, not by individual skills. This routing file
handles:
- Slice classification (product_code, docs, ci_tooling, etc.)
- Direct first-skill selection
- No second routing authority

Once the first skill is selected, routing between skills is governed by each
skill's `## Relationships` section.

### No Automatic Forwarding

Each skill owns its decision to route, stop, or loop. No skill automatically
forwards another skill's output without the current skill's explicit routing
condition matching. Handoffs are suggestions; the receiving skill must make its
own decision.
