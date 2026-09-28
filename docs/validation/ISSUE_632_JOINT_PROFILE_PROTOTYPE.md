# Issue #632 — Joint 24-Key Profile Prototype

Status: `PROTOTYPE_ONLY / NO_ANALYZER_INTEGRATION`

## Scope

`src/joint_key_profile.py` is a deterministic, dependency-free core that ranks
all twelve major and twelve minor Krumhansl-Schmuckler hypotheses jointly from
one 12-bin chroma vector. It returns only a root, a mode, a raw Pearson score,
and the complete raw ranking. It does not expose a probability, calibrated
confidence, claimability score, or no-key score.

`src/joint_key_profile_benchmark.py` is a separate external-input adapter. It
reproduces the locked #631 representation:

```text
audio -> chroma_cqt (automatic tuning) -> temporal mean -> joint 24-key rank
```

Neither module is imported by `src.analyze`, `estimate_key()`,
`estimate_key_mode()`, `extract_features()`, `run_analyze()`, persistence,
search, Harmonic Match, or QML. This prototype changes no production semantics.

## Historical mode-separator distinction

The earlier Krumhansl-Schmuckler experiment described in
`docs/KEY_MODE_ANALYSIS_V1.md` was a rejected **mode separator**: it compared
major and minor margins after the existing root decision and could not preserve
the synthetic ambiguity-abstention contract.

This prototype instead ranks all 24 root-and-mode hypotheses jointly. It is a
different technical experiment, but it still has no abstention mechanism and
therefore must not be wired into the current analyzer contract.

## #418 synthetic regression matrix

The raw profile ranker was evaluated against the frozen #418 fixture families.

| Metric | Result |
| --- | ---: |
| clear root accuracy | 12 / 12 (100.00%) |
| clear mode accuracy | 12 / 12 (100.00%) |
| combined root+mode accuracy | 12 / 12 (100.00%) |
| ambiguous abstention | 0 / 4 (0.00%) |
| wrong_root, clear fixtures | 0 |
| wrong_mode, clear fixtures | 0 |
| abstain_or_unknown, clear fixtures | 0 |
| dominant root-bass under C-major | `Cmaj` |
| dominant fifth-bass under C-major | `Gmaj` |

The zero ambiguous abstention result is intentional evidence, not a defect
patched with a threshold. It conflicts with the frozen product contract, which
requires abstention for single-note, octave, root+fifth, and equal
major/minor-blend material. The fifth-bass result also retains the documented
current-baseline failure rather than hiding it.

## Frozen public #631 reproduction

Using the frozen public FSLD manifest
`8e443d603b712aeb15b66b87a6e87921b53a3cdf9c94834fb80a4d2b262a7571`, two
independent TEST runs over 400 externally supplied public WAVs were semantically
identical after excluding runtime measurements.

| Metric | Prototype | Locked #631 candidate |
| --- | ---: | ---: |
| MA root | 69.41% (59 / 85) | 69.41% |
| MA full-key | 56.00% (28 / 50) | 56.00% |
| SA root | 57.30% (51 / 89) | 57.30% |
| SA full-key | 39.44% (28 / 71) | 39.44% |

All 400 prototype root/mode/status tuples matched the locked #631 candidate.
The reproduction tolerance is an absolute rate delta of at most `0.00005`
(0.005 percentage points), which only accommodates display rounding beyond the
published two decimal places. The observed count and rate deltas were zero.
Compared with the current Sample Brain anchor captured in #631, full-key
transitions were 23 MA and 22 SA wrong-to-correct, with zero
correct-to-wrong transitions.

The public benchmark confirms the prototype implementation; it does not change
the #598 `NO_DEFENSIBLE_PUBLIC_GATE` result and does not authorize an analyzer
or contract migration.
