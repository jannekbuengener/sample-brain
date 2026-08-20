# Pond5 Readiness Contract v1

**Parent:** [#448](https://github.com/jannekbuengener/sample-brain/issues/448)
**Schema version:** `1.0.0`
**Document type:** `sample_brain.pond5_readiness`
**Status:** normative contract; no runtime implementation in this slice

## 1. Purpose and boundary

This contract defines a portable, local readiness document for preparing one
owned music track for a later Pond5 submission.  It reuses existing
Sample-Brain analysis artefacts; it does not analyse audio, upload a file, log
in to Pond5, make legal decisions, or change Track Map v1.

It separates what Sample Brain measured from what a semantic analyser,
contributor profile, rights decision, listing generator, or Pond5 rule snapshot
supplies. `unknown` is a valid result. Consumers must not replace it with an
inference.

Follow-on ownership is deliberately split:

| Issue | Follow-on surface | Explicitly not implemented here |
|---|---|---|
| [#449](https://github.com/jannekbuengener/sample-brain/issues/449) | evidence-backed stock-music semantics | genre/mood/instrument generation |
| [#450](https://github.com/jannekbuengener/sample-brain/issues/450) | local contributor and rights profile | profile loading, defaults, overrides |
| [#451](https://github.com/jannekbuengener/sample-brain/issues/451) | readiness validator and local bundle/CSV export | CLI, CSV writing, PASS/HOLD evaluation |

## 2. Envelope and compatibility

Every document has exactly this top-level shape. Additional fields are allowed
only when they do not change the meaning of v1 fields.

```json
{
  "document_type": "sample_brain.pond5_readiness",
  "schema_version": "1.0.0",
  "source": {},
  "analysis": {},
  "semantic": {},
  "contributor": {},
  "rights": {},
  "listing": {},
  "platform": {},
  "provenance": {},
  "readiness": {}
}
```

`document_type` is fixed. `schema_version` is SemVer; v1 consumers accept
compatible `1.x.x` documents and reject an unsupported major version. This is
a portable metadata document: it must not contain an absolute path, `file://`
URI, drive letter, UNC path, username, account data, secret, source audio, or
runtime cache reference.

## 3. Shared status, evidence, and provenance rules

The analysis-compatible status vocabulary is fixed: `ok`, `partial`,
`not_run`, `failed`, and `no_result`. `unknown` is permitted only for an
explicitly non-inferable manual or platform fact; it is not an analysis status.
`not_run` means an optional producer was not requested; `no_result` means it
ran but did not establish a value.

Any value derived from a Sample-Brain artefact or semantic process has:

```json
{
  "status": "ok",
  "value": "example",
  "evidence_refs": ["track_map.analysis.musical.bpm"],
  "source_ref": "track_map_v1"
}
```

`source_ref` keys resolve in `provenance.sources`. `evidence_refs` are stable
logical references, not local paths. A numeric `confidence` or `score` may be
present only with its field-specific `confidence_kind` or `score_kind` that
defines method, range, and meaning. No consumer may invent a generic
confidence.

`provenance.sources` is required and records each input's `kind`,
`document_type` (when applicable), `schema_version`, stable identity/hash where
available, and producer/component version. `provenance.generated_at` is
optional and must be an ISO-8601 timestamp when present. Execution cache state
is not portable provenance and must not be serialized.

## 4. Source and technical analysis

`source` is required. Its portable identity fields copied from the selected
Track Map v1 source are `file_name`, `hash`, `size_bytes` when available, and
`audio_properties` (`duration_sec`, `sample_rate_hz`, and `channels`); they
carry `source_ref` to the Track Map/asset evidence. The original file is never
renamed or modified.

Track Map v1 is not the source of submission-container facts it does not
define. For #451, `source.submission_technical` is the authorized portable
technical-validation record for the selected submission file. It contains
`format` and `bit_depth` and may repeat container-established
`sample_rate_hz`, `channels`, or `duration_sec` only when needed to validate
that file. Every populated field has `status`, `value`, `evidence_refs`, and
`source_ref: "submission_file_header_probe"`. That source resolves in
`provenance.sources` to a local container/header metadata probe of the selected
submission file. The probe reads technical container/header metadata only: it
is not musical, audio-feature, semantic, or arrangement re-analysis. Its
portable provenance may identify the selected file by stable hash and file
name, but must never serialize a local/absolute path, URI, source audio, or
cache reference. If the probe cannot establish a required fact, it records the
applicable non-`ok` status and #451 must HOLD; it must not guess.

`analysis` is required and is an adapter view, never a reanalysis request. It
contains a required `status` plus these optional value objects when their source
artefact has a usable result:

| Field | Reused source of truth | Rule |
|---|---|---|
| `bpm` | `track_map.analysis.musical.bpm` | preserve status, normalization, unit, and source reference |
| `key` | `track_map.analysis.musical.key` | preserve root, mode/status, and documented confidence semantics |
| `loudness` | `track_map.analysis.audio_summary.loudness` | preserve method and unit |
| `brightness` | `track_map.analysis.audio_summary.brightness` | preserve method and unit |
| `timeline` | Track Map beats/downbeats/energy/sections or arrangement artefact | optional; preserve timebase and source references |
| `arrangement` | Arrangement/section/deconstruction artefact | optional; do not turn neutral boundaries into role claims |
| `asset_identity` | Asset/pack artefact | optional and only for the selected submission asset |

Missing analysis stays absent with the relevant status/reason evidence; it is
not synthesized. Track Map v1 remains neutral and receives no Pond5 fields.

## 5. Semantic listing descriptors

`semantic` is required as a container but may contain only `status: "not_run"`
until #449 produces evidence. Its controlled fields are `genre`, `subgenre`,
`mood`, `energy_class`, `pace_character`, `instrumentation`, `sound_palette`,
`production_character`, `usage_context`, and optional
`arrangement_character`.

Singular fields use the shared value-object shape. Collection members each use
that shape and additionally identify `vocabulary` and `vocabulary_version`.
No genre, mood, instrument, use case, artist similarity, trademark, brand,
film, TV, game, or rights fact may be fabricated from an absent or insufficient
source. A semantic producer must use `no_result`, `partial`, or `not_run` as
applicable and must not claim a score without a defined score meaning.

## 6. Contributor and rights: manual-only facts

`contributor` and `rights` are required containers. Their values are supplied
only by an explicit user/profile entry or an explicit per-track override; their
provenance `origin` is respectively `profile`, `per_track_override`, or
`unknown`. Audio analysis and semantic analysis are forbidden origins.

| Block | Required contract fields | Rule |
|---|---|---|
| `contributor` | `composer`, `ipi`, `pro`, `publisher`, `copyright_owner` | each is `{ "status": "ok|unknown", "value": string|null, "source_ref": string }`; only an explicit source may set `ok` |
| `rights` | `ownership_authorized`, `third_party_elements_cleared_for_resale`, `cleared_for_sampling` | each is `{ "status": "ok|unknown", "value": true|false|null, "source_ref": string }`; `null`/`unknown` remains unresolved |

`false` is an explicit decision, not an unknown value. This contract gives no
legal advice and does not determine whether any decision is correct. A later
validator must hold readiness when a required manual value is unresolved.

## 7. Generated listing data

`listing` is required and has `status` plus value objects for `title`,
`description`, `keywords`, optional `price`, and `target_upload_filename`.
Listing generation may combine confirmed semantic evidence, explicit profile
data, and the platform snapshot. It must record every contributing
`evidence_ref` and keep a manual override distinguishable from a generated
value in provenance.

`target_upload_filename` is a suggestion, not a source-file mutation. Its
`source_name_ref` identifies the original source identity. `title`,
`description`, and `keywords` must not contain copyrighted artist/band/brand/
film/TV/game/company references or `sounds like` marketing. Language and
platform-limit validation is the later #451 responsibility.

## 8. Pond5 platform snapshot (2026-08-20)

`platform` is required. It records the snapshot rather than asserting a live
Pond5 API contract. Each `platform.fields.<field>` record has `required`,
`rules`, `csv_supported`, `primary_source_url`, and `snapshot_date`. The only
permitted `csv_supported` values are `true`, `false`, and `unknown`.

Primary sources for every record below:

- <https://contributor.pond5.com/getting-started/preparing-your-files-2/music/>
- <https://contributor.pond5.com/getting-started/preparing-your-files/>

| Pond5-facing field/group | Required for readiness | Snapshot rule | `csv_supported` |
|---|---:|---|---|
| `audio` | yes | music is WAV or AIFF; 16/24/32-bit; 44.1/48/96 kHz; stereo; duration under 10 minutes; MP3/FLAC rejected | `false` |
| `OriginalFilename` | yes for Apply CSV | documented mandatory Apply CSV column; identifies the prepared source/target mapping | `true` |
| `target_upload_filename` | yes | no spaces/dashes or listed prohibited special/accented characters | `unknown` |
| `title` | yes | English; maximum 80 characters | `true` |
| `description` | optional | English; maximum 500 characters when supplied | `true` |
| `keywords` | yes | English, relevant, maximum 50; no prohibited references | `true` |
| `copyright` | optional | metadata field documented by Apply CSV | `true` |
| `price` | optional | metadata field documented by Apply CSV | `true` |
| `composer` | yes | required at submission; IPI may accompany it | `unknown` |
| `pro` | optional | may be supplied | `unknown` |
| `publisher` | optional | may be supplied | `unknown` |
| `cleared_for_sampling` | yes | per-file licensing choice | `unknown` |
| `rights assertions` | yes | seller owns/controls rights and clears third-party elements for resale/commercial use | `false` |

`OriginalFilename`, `Title`, and `Keywords` are the documented mandatory Apply
CSV fields. CSV capability never changes readiness requirements: a prepared
required value whose CSV support is `unknown` remains a manual/UI submission
value until primary evidence proves otherwise.

## 9. Readiness model

`readiness` is required and is declarative in this contract; #451 implements
its evaluation. It contains `status` (`POND5_READY` or `HOLD`),
`satisfied`, `missing`, `blocking`, and `warnings`. Each entry is an object
with `rule_id`, `field_ref`, `status`, `evidence_refs`, and a human-readable
`message`. A blocking entry prevents `POND5_READY`; a missing non-blocking
entry is reported but does not by itself change the result.

At minimum, later evaluation must distinguish technical input failure, missing
semantic evidence, missing composer, unresolved ownership/third-party
clearance, unresolved sampling choice, invalid listing data, and unknown CSV
support. It must not conflate `POND5_READY` with CSV completeness or with a
legal conclusion.

The required `audio` rule is evaluated deterministically from these evidence
sources: `format` and `bit_depth` from `source.submission_technical`; duration,
sample rate, and channels from the selected Track Map `source.audio_properties`
unless the header probe supplies the corresponding selected-file fact. #451
must HOLD when any required source is absent, non-`ok`, or cannot be bound to
the selected submission file; it must not substitute a missing field from a
different file or infer it from musical analysis.

## 10. Non-goals and validation boundary

This v1 contract introduces no CLI, database schema, upload, FTP/API/browser
automation, credentials, network transfer, dependency, workflow, sample
processing, or runtime profile. It does not include private samples, local
paths, generated bundles, or account data. Contract consumers must preserve
these boundaries and use synthetic fixtures for future tests.

## 11. Related contracts

- [Track Map v1](TRACK_MAP_V1.md) — portable identity, technical analysis,
  status vocabulary, component provenance
- [Arrangement Signal Matrix v1](ARRANGEMENT_SIGNAL_MATRIX_V1.md) — neutral
  arrangement signal evidence
- [Track Deconstruction Orchestrator v1](TRACK_DECONSTRUCTION_ORCHESTRATOR_V1.md)
  — artefact orchestration boundary
- [Performance Pack Manifest v1](PERFORMANCE_PACK_MANIFEST_V1.md) — portable
  pack/asset context
