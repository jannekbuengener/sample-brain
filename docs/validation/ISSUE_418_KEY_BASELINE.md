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

The existing `tests/test_key_mode_analysis.py` gate covers twelve clear fixtures
(6 roots × major/minor) plus four deliberately ambiguous fixtures.

| Case family | Count | Baseline contract |
| --- | ---: | --- |
| clear major/minor | 12 | root accuracy >= 0.90 |
| clear major/minor | 12 | mode accuracy >= 0.90 |
| clear major/minor | 12 | combined root+mode accuracy >= 0.85 |
| ambiguous single-note/octave/root+fifth/major-minor blend | 4 | abstention = 1.00 |
| dominant root-bass under C-major | 1 | root = C |
| dominant fifth-bass (G2) under C-major | 1 | observed root = G (known failure) |

The clear-fixture implementation meets the existing gate, while all four
ambiguous fixtures abstain. #418 now freezes two complementary bass cases:

1. A much stronger low **C2** under a quieter C-major upper triad still yields the
   expected `C` root.
2. A dominant low **G2** (the fifth) under a C-major upper triad makes the current
   mean-chroma argmax select `G`. This is a measured baseline weakness, not a
   result to hide or "fix" inside the persistence slice.

The second case is intentionally kept as a failing-quality **observation that
passes as a regression test of current behavior**. A future key-root algorithm
proposal should demonstrate that it improves this case without weakening the
clear-fixture or ambiguity-abstention contracts.

## Error categories for future comparisons

Any future root/mode algorithm proposal must report at least:

- `wrong_root`
- `wrong_mode`
- `abstain_or_unknown`

and compare those counts against this baseline before replacing the current
deterministic implementation.

## Persistence evidence

Issue #418 also makes analysis uncertainty durable in SQLite. New/updated
`features` rows persist:

- `quality_note` as nullable text
- `key_mode` as nullable `maj` / `min`
- `key_mode_evidence` as deterministic JSON text

Legacy databases are upgraded additively with nullable columns. Existing rows are
left intact; no bulk rewrite and no invented evidence is performed.