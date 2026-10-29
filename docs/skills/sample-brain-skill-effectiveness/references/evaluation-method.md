# Evaluation Method

Adapt Superpowers writing-skills / TDD to Sample Brain skills.

```text
BASELINE WITHOUT SKILL
-> OBSERVED FAILURE / OMISSION / RATIONALIZATION
-> SKILL-ENABLED RUN (same task inputs)
-> BEHAVIORAL DELTA
-> VARIANTS / COUNTEREXAMPLES
-> EFFECTIVE | INEFFECTIVE | UNNECESSARY
(or INCOMPLETE when evidence is insufficient)
```

## Treatment variable

Skill availability is the treatment. Keep task prompt, repo revision, tools,
and acceptance rubric materially equivalent between baseline and skill-enabled
runs. Record `inputs_comparable: false` and fail closed when they diverge.

## Provider neutrality

Use Cursor subagents / local agent mechanisms available in the repository
environment. No mandatory vendor cloud, ChatGPT MCP, or paid external judge.
If a local agent run is unavailable, record `INCOMPLETE` /
`agent_run_unavailable` — do not invent a baseline after the fact.

## Required dimensions

1. Positive activation — target scenario should use the skill
2. Negative activation — nearby scenario should not spuriously trigger it
3. Baseline-vs-skill comparison — same scenario, skill as treatment
4. Output-shape compliance — when the skill defines a handoff shape
5. Pressure / rationalization — required for discipline skills
6. Transfer / variants — not memorization of one prompt
7. False positive / overconstraint — skill must not block valid nearby work
8. Deterministic helpers — tested separately from agent judgment

## Structural vs behavioral

Registry presence, `SKILL.md` existence, mirror sync, and routing entries are
**structural**. They are necessary packaging checks and insufficient for an
`EFFECTIVE` verdict. Set `structural_only: true` only when no behavioral runs
occurred; the helper must then force `INCOMPLETE`.

## Bootstrap rule

This evaluator must not require itself to already exist before capturing the
first baseline need. Establish the gap from issue evidence and current
validation limits, then implement the minimum evaluator.

## One refine cycle

After first GREEN evaluations, allow one bounded refine pass (close an observed
loophole). Stop. No infinite self-eval loop.

## Discipline scoring note (bounded refine from #1304 evidence)

Under sunk-cost pressure, agents may keep a pre-written implementation draft as
"reference" while claiming test-first order. For discipline scoring, treat
**keep-as-reference / adapt-existing-draft before TEST FREEZE** as a soft
leak signal on variants even when the primary scenario passes. Prefer recording
the residual loophole in evidence over silently marking perfect transfer. Do
not rewrite an existing production skill merely to clear an evaluator score
unless the skill's own contract is defective.
