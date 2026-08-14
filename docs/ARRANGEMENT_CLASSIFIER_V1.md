# Arrangement Heuristic Classifier v1

Issue #240 adds a deterministic, rule-based adapter from neutral `StructureV1`
sections and #239 section signals to an Arrangement Map. It does not detect,
move, or write StructureV1 boundaries.

## Input and output

`ArrangementClassifier.classify_track()` consumes a `StructureV1Result`, one
`SectionSignals` value per neutral section, and optional `ManualOverride`s. Its
`to_arrangement_map()` output preserves each source section's IDs, seconds, and
bar bounds verbatim. It produces roles `intro`, `groove`, `build`, `drop`,
`breakdown`, `outro`, or `unknown`, with statuses from #241.

Each automatic result includes machine-readable positive, negative, missing,
and contradictory evidence plus per-signal contribution records. Internal
scores are deterministic, track-relative heuristic comparisons; they are not
calibrated probabilities or a universal `confidence` field.

## Uncertainty and overrides

Missing, weak, tied, or contradictory evidence returns `unknown`; it never
falls back to `groove`. Optional signals remain missing rather than receiving
fake values. Automatic output is kept unchanged beside a `manual_override`.
The derived effective role and event use an override only for the layer it
sets; removing the override therefore restores the automatic value without
reanalysis.

## Events and limits

`drop_onset` is an event, never a section role. It is emitted only where the
corresponding neutral StructureV1 boundary exists and all required public
transition signals are available at that boundary. The following section must
not be `unknown`; an uncertain or non-`drop` role leaves the event explicitly
`uncertain`. The classifier creates no boundary. `transition` is never emitted.

The event decision uses the boundary bar rather than the whole following
section average, so a local onset is not diluted by a long section. Missing
required evidence still suppresses the event. If StructureV1 used inferred
4/4 bars, the event and track stay `uncertain` and retain
`bar_grid_inference` provenance; inferred bars are never relabelled observed.

This is not a quality claim or a universal statement about Techno. It uses no
ML model, CLAP, stems, cloud service, or new dependency. Private-track pilots
remain the separate scope of #242.

## Runtime wiring

`SectionSignalsAssembler` is the production bridge between neutral StructureV1
bar evidence and the classifier. It aggregates each public, normalized bar
series over the unchanged neutral section range, retains the inferred-bar-grid
provenance, and passes one `SectionSignals` value per section to
`ArrangementClassifier`. `build_arrangement_map(structure_result)` provides
the small end-to-end consumer.

The assembler neither creates boundaries nor assigns roles. A missing or
misaligned bar series is recorded as missing; it is never replaced with a
default value. The classifier returns `unknown` without scores unless every
core signal is available. This keeps incomplete StructureV1 evidence from
being mistaken for neutral evidence.
