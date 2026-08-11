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

`drop_onset` is an event, never a section role. It is emitted only for a
classified `drop` where the corresponding neutral StructureV1 boundary exists;
the classifier creates no boundary. `transition` is never emitted.

This is not a quality claim or a universal statement about Techno. It uses no
ML model, CLAP, stems, cloud service, or new dependency. Private-track pilots
remain the separate scope of #242.
