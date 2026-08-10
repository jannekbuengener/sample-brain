# Arrangement Signal Matrix v1

**Issue:** [#239](https://github.com/jannekbuengener/sample-brain/issues/239)
**Parent:** [#228](https://github.com/jannekbuengener/sample-brain/issues/228)
**Consumes:** [Track Map v1](TRACK_MAP_V1.md), [Canon Audio Timebase](CANON_AUDIO_TIMEBASE.md), [BeatGrid Backend](BEATGRID_BACKEND.md)
**Machine-readable matrix:** [arrangement_signal_matrix_v1.json](arrangement_signal_matrix_v1.json)

This document defines the measurable signals that later StructureV1 (#265) and
Arrangement Map (#240) work can use. It does not classify roles and does not
change the Track Map v1 schema. It records the contract that #265 must satisfy
for neutral boundaries and the signal surface that #240 may consume later.

## 1. Scope And Layer Split

| Layer | Uses | Emits | Must not emit |
|-------|------|-------|---------------|
| StructureV1 boundary layer (#265) | BeatGrid, bar-level energy/loudness, low-end, onset, rhythm, timbre, spectral, self-similarity, recurrence, novelty, neighbor deltas, 4/8/16 bar trends | Neutral boundary candidates and neutral `analysis.timeline.sections` | `intro`, `groove`, `build`, `drop`, `breakdown`, `outro`, `unknown`, `transition`, `drop_onset` |
| Arrangement role layer (#240) | Neutral sections plus the role-relevant signals in this matrix | Arrangement Map roles/events from the #238 vocabulary | New boundary positions, stem truth without stem provenance, CLAP truth without evidence |

Boundary confidence and role confidence stay separate. A strong boundary can
still have role `unknown`; a strong role hint must not create a boundary.

## 2. Role Vocabulary Source

The only currently available role vocabulary source is issue #238, which is
still open. This matrix therefore binds to the current #238 draft vocabulary:

- Section roles: `intro`, `groove`, `build`, `drop`, `breakdown`, `outro`, `unknown`
- Boundary event: `drop_onset`
- Deferred: `transition`

If #238 later changes the vocabulary, this matrix must be updated before #240
uses it. This file does not resolve #238.

## 3. Normalization Rules

No signal in this contract uses universal Techno thresholds. Consumers compare
signals relative to the current track:

- track percentiles
- median/MAD robust z-scores
- previous/next bar or section deltas
- relative low-end or stem shares inside the same track
- 4, 8, and 16 bar rolling trends

Missing signals stay missing. Do not invent replacement confidence, do not
treat absence as silence, and do not promote optional stems or CLAP to MVP
requirements.

## 4. MVP For StructureV1 (#265)

StructureV1 must be able to work without CLAP, stem separation, or a new large
model. Its MVP signal surface is:

| Signal | Boundary input | Role input later | Track Map / provenance anchor |
|--------|----------------|------------------|-------------------------------|
| `bar_grid` | yes | context | `analysis.timeline.beats`, `analysis.timeline.downbeats`, `timebase`, `beat_grid` provenance |
| `bar_energy_rms` | yes | yes | `analysis.timeline.energy`, `downbeats`, energy `source_ref` |
| `bar_loudness_delta` | yes | yes | derived from declared energy/loudness series |
| `low_end_share` | yes | yes | StructureV1 spectral/low-end component config |
| `onset_density` | yes | yes | StructureV1 onset component config |
| `rhythm_stability` | yes | yes | BeatGrid plus StructureV1 rhythm component |
| `timbre_delta` | yes | yes | StructureV1 timbre component; raw MFCC remains outside Track Map v1 |
| `spectral_delta` | yes | yes | StructureV1 spectral component; global brightness is only context |
| `self_similarity` | yes | yes | StructureV1 similarity component |
| `recurrence` | yes | yes | StructureV1 recurrence component |
| `novelty` | yes | yes | StructureV1 novelty component |
| `neighbor_delta` | yes | yes | before/after windows around candidate boundaries |
| `multi_bar_trend` | yes | yes | rolling 4/8/16 bar windows |
| `neutral_section_boundary` | output | context | `analysis.timeline.sections.items`, neutral labels only |

If any MVP signal is unavailable, #265 records `not_run`, `failed`,
`no_result`, or nullable derived values with provenance and continues only when
the remaining evidence is meaningful. It must not fabricate a substitute.

## 5. Optional Later Signals

| Signal | Why optional |
|--------|--------------|
| `stem_drum_activity` | Requires a separate stem pipeline and stem provenance. It is not required for #265. |
| `stem_bass_activity` | Requires a separate stem pipeline. `low_end_share` is not confirmed bass activity. |
| `semantic_role_hint` | Requires separate semantic evidence and is never Techno ground truth. |

## 6. Role View

This view is for later #240 scoring. It is not a classifier and contains no
fixed thresholds.

| Role/event | Positive measurable signals | Negative measurable signals |
|------------|-----------------------------|-----------------------------|
| `intro` | `relative_track_position`, `multi_bar_trend`, optional `semantic_role_hint` | `bar_energy_rms`, `low_end_share`, `onset_density`, optional `stem_drum_activity`, optional `stem_bass_activity`, low `evidence_completeness` |
| `groove` | `bar_energy_rms`, `low_end_share`, `onset_density`, `rhythm_stability`, `self_similarity`, `recurrence`, optional stem activity, optional `semantic_role_hint` | `relative_track_position`, `bar_loudness_delta`, `timbre_delta`, `spectral_delta`, `novelty`, `neighbor_delta`, `multi_bar_trend`, low `evidence_completeness` |
| `build` | `bar_loudness_delta`, `onset_density`, `timbre_delta`, `spectral_delta`, `neighbor_delta`, `multi_bar_trend`, optional `semantic_role_hint` | `relative_track_position`, stable `rhythm_stability`, `self_similarity`, `recurrence`, low `evidence_completeness` |
| `drop` | `bar_energy_rms`, `bar_loudness_delta`, `low_end_share`, `onset_density`, `rhythm_stability`, `spectral_delta`, `self_similarity`, `recurrence`, optional stem activity, optional `semantic_role_hint` | `relative_track_position`, `multi_bar_trend`, low `evidence_completeness` |
| `breakdown` | `timbre_delta`, `novelty`, `neighbor_delta`, optional `semantic_role_hint` | `relative_track_position`, `bar_energy_rms`, `bar_loudness_delta`, `low_end_share`, `onset_density`, `rhythm_stability`, `self_similarity`, `recurrence`, optional stem activity, low `evidence_completeness` |
| `outro` | `relative_track_position`, `neighbor_delta`, `multi_bar_trend`, optional `semantic_role_hint` | `bar_energy_rms`, `bar_loudness_delta`, `onset_density`, `rhythm_stability`, `spectral_delta`, optional `stem_bass_activity`, low `evidence_completeness` |
| `unknown` | `evidence_completeness` showing missing, failed, weak, or contradictory inputs | optional `semantic_role_hint` |
| `drop_onset` | `bar_loudness_delta`, `timbre_delta`, `spectral_delta`, `novelty`, `neighbor_delta` | `self_similarity`, `recurrence`, low `evidence_completeness` |

`drop_onset` is an event, not a section role. `unknown` is the correct output
when evidence is weak, missing, contradictory, or outside the role vocabulary.

## 7. Signal View

These are signals for later scoring, not rules. Positive and negative mean
"supports" or "argues against" a later role candidate after track-relative
normalization. They are not universal thresholds.

| Signal | Positive role/event hint | Negative role hint |
|--------|--------------------------|--------------------|
| `relative_track_position` | `intro`, `outro` | `groove`, `build`, `drop`, `breakdown` |
| `bar_energy_rms` | `groove`, `drop` | `intro`, `breakdown`, `outro` |
| `bar_loudness_delta` | `build`, `drop`, `drop_onset` | `groove`, `breakdown`, `outro` |
| `low_end_share` | `groove`, `drop` | `intro`, `breakdown` |
| `onset_density` | `groove`, `drop`, `build` | `intro`, `breakdown`, `outro` |
| `rhythm_stability` | `groove`, `drop` | `build`, `breakdown`, `outro` |
| `timbre_delta` | `build`, `drop_onset`, `breakdown` | `groove` |
| `spectral_delta` | `build`, `drop`, `drop_onset` | `groove`, `outro` |
| `self_similarity` | `groove`, `drop` | `build`, `breakdown`, `drop_onset` |
| `recurrence` | `groove`, `drop` | `build`, `breakdown`, `drop_onset` |
| `novelty` | `drop_onset`, `breakdown` | `groove` |
| `neighbor_delta` | `build`, `drop_onset`, `breakdown`, `outro` | `groove` |
| `multi_bar_trend` | `intro`, `build`, `outro` | `groove`, `drop` |
| `evidence_completeness` | `unknown` | concrete roles and events when evidence is too sparse or contradictory |
| `stem_drum_activity` | `groove`, `drop` | `intro`, `breakdown` |
| `stem_bass_activity` | `groove`, `drop` | `intro`, `breakdown`, `outro` |
| `semantic_role_hint` | `intro`, `groove`, `build`, `drop`, `breakdown`, `outro` | `unknown` |

## 8. Full Signal Matrix

The JSON matrix is normative for machine checks. It includes, for every signal:

- signal name
- meaning
- source/calculation
- aggregation type
- positive and negative role relevance
- boundary relevance
- role-scoring relevance
- MVP or optional status
- required Track Map fields
- provenance
- missing-signal behavior

## 9. Contract For #265

#265 must provide or consume, at minimum:

- bar-synchronous feature series on the BeatGrid/downbeat grid
- track-relative energy and loudness development
- low-end share as a proxy, not confirmed bass activity
- onset density and rhythmic stability
- timbre and spectral deltas
- self-similarity, recurrence, and novelty
- previous/next differences at candidate boundaries
- 4/8/16 bar trends
- neutral sections in `analysis.timeline.sections`

It must not emit arrangement roles or `drop_onset`. Those belong to the later
Arrangement Map layer.

## 10. Acceptance Mapping

| #239 criterion | Covered by |
|----------------|------------|
| Signals per role with positive and negative relevance | Sections 2, 6, 7 and JSON `role_signal_summary` / `role_positive` / `role_negative` |
| MVP signals traceable to Track Map fields and provenance | Sections 4, 9 and JSON `required_track_map_fields` / `provenance` |
| Boundary and role signals separated | Sections 1, 9 and JSON booleans |
| MVP and optional signals separated | Sections 4, 5 and JSON `mvp_level` |
| #265 requirements and #240 foundation complete | Sections 4, 6, 7, 9 |

## 11. References

- [Issue #228](https://github.com/jannekbuengener/sample-brain/issues/228)
- [Issue #238](https://github.com/jannekbuengener/sample-brain/issues/238)
- [Issue #239](https://github.com/jannekbuengener/sample-brain/issues/239)
- [Issue #240](https://github.com/jannekbuengener/sample-brain/issues/240)
- [Issue #265](https://github.com/jannekbuengener/sample-brain/issues/265)
