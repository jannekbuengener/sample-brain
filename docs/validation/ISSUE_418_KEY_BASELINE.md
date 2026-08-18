# Issue #418 — Key Analysis Baseline

Status: `BASELINE_FROZEN_BEFORE_ALGORITHM_CHANGE`

## Purpose

This document records the deterministic key-analysis baseline before any future
root/mode algorithm change. It uses only synthetic audio generated during tests;
no private tracks, samples, databases, or caches are committed.

## Current root contract

`src.analyze.estimate_key()` computes mean CQT chroma, selects the strongest pitch
class with `argmax(chroma_mean)`, and returns:

- `root`: strongest chroma pitch class
- `key_conf`: `max(chroma_mean) / sum(chroma_mean)`

`key_conf` is relative peak evidence in `[0, 1]`; it is **not** a calibrated
probability or a generic confidence score.

## Current mode contract

`estimate_key_mode()` uses deterministic major-third versus minor-third chroma
contrast relative to the already selected root. It commits `maj` or `min` only
when the normalized contrast is at least `MODE_CONTRAST_MIN = 0.30`; otherwise it
abstains and retains the evidence with `mode = null`.

## Frozen synthetic baseline

The broad gate in `tests/test_key_mode_analysis.py` remains unchanged: twelve clear
fixtures (6 roots × major/minor) must satisfy its root/mode accuracy thresholds and
four deliberately ambiguous fixtures must abstain.

Issue #418 additionally freezes a smaller stress baseline in
`tests/test_issue418_final_acceptance.py`. It contains three clear tonal cases plus
one intentionally difficult C-major case whose **low G bass is much stronger than
the upper C-major material**, along with three ambiguity cases.

Current measured stress baseline:

| Metric | Result |
| --- | ---: |
| tonal cases | 4 |
| root correct | 3 / 4 |
| mode correct | 3 / 4 |
| combined root + mode correct | 3 / 4 |
| ambiguity abstentions | 3 / 3 |
| bass-dominant C-major observed output | `G`, mode `None` |
| bass-dominant C-major expected musical label | `Cmaj` |

The bass-dominant case is deliberately a **known weakness**, not a target made easy
enough for the current implementation to pass. The mean-chroma root heuristic is
pulled toward the dominant G bass and then the mode detector abstains. Future root
or mode changes must compare against this frozen evidence rather than replacing it
with a fixture that already matches the current heuristic.

## Error categories for future comparisons

Any future root/mode algorithm proposal must report at least:

- `wrong_root`
- `wrong_mode`
- `abstain_or_unknown`

and compare those counts against this baseline before replacing the current
deterministic implementation.

## Persistence evidence

Issue #418 makes analysis uncertainty durable in SQLite. New/updated `features`
rows persist:

- `quality_note` as nullable text
- `key_mode` as nullable `maj` / `min`
- `key_mode_evidence` as deterministic JSON text

Legacy databases are upgraded additively with nullable columns. Existing rows are
left intact; no bulk rewrite and no invented evidence is performed.

`tests/test_issue418_final_acceptance.py` verifies this through real `run_analyze()`
paths for a known major chord, an ambiguous single-note abstention, and a short clip,
and also proves that additive migration preserves an existing legacy feature row.
