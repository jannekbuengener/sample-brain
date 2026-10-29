# Skill Type Success Criteria

Do not use one generic scoring rule for every skill. Classify first.

## discipline

Rule compliance under pressure. Agent knows better but may skip.

Success when:

- baseline shows skip / rationalization under pressure
- skill-enabled run complies with the rule
- pressure/rationalization counters hold on at least one variant
- negative activation stays idle on non-discipline nearby tasks

Primary signals: `failure_category: rationalization|skipped_gate|order_violation`

## technique

Concrete method application (ordered steps, diagnosis flow).

Success when:

- baseline misses required method steps or collapses to ad-hoc work
- skill-enabled run applies the technique on the same scenario
- at least one transfer variant still applies the technique
- missing-info handling does not invent unsupported conclusions

Primary signals: `failure_category: omitted_step|wrong_method|unsupported_claim`

## pattern

Recognition of when a mental model applies / does not apply.

Success when:

- baseline mis-applies or fails to recognize the pattern
- skill-enabled run recognizes and applies correctly
- counterexample shows non-application when pattern does not fit
- overconstraint (forcing the pattern everywhere) is absent

Primary signals: `failure_category: misrecognition|overapplication`

## reference

Retrieval and correct use of documented facts / contracts.

Success when:

- baseline cannot find or misstates the needed reference fact
- skill-enabled run retrieves and applies the correct fact
- gap coverage for common look-ups is demonstrated
- fabricated citations are rejected

Primary signals: `failure_category: retrieval_miss|incorrect_citation|fabricated_reference`
