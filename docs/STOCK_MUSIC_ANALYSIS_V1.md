# Stock-Music Analysis v1

**Issue:** [#449](https://github.com/jannekbuengener/sample-brain/issues/449)
**Schema version:** `1.0.0`
**Document type:** `sample_brain.stock_music_analysis`

## Boundary

This is a portable, provider-neutral semantic analysis artefact. It consumes
existing Track Map, Arrangement Map, Producer Group, and explicitly injected
optional semantic-backend evidence. It does not change Track Map v1, write a
database, provide a CLI, produce a listing/bundle/CSV, infer contributor or
rights facts, download a model, or perform network activity.

The top-level shape is fixed:

```json
{
  "document_type": "sample_brain.stock_music_analysis",
  "schema_version": "1.0.0",
  "track_ref": "sha256:<digest>",
  "semantic": {},
  "provenance": {"sources": {}}
}
```

No source filename, audio path, URI, cache, database, index, model path,
credential, contributor, or rights value is serialized.

## Status and value objects

All status values are exactly `ok`, `partial`, `not_run`, `failed`, or
`no_result`. `not_run` means an optional producer was not explicitly supplied;
`no_result` means a producer ran but established no controlled value; `failed`
means its input or execution contract failed.

Singular fields are status value objects. Collection fields are wrappers with
`status` and `items`; every item is a status value object. Each item has
`value`, `status`, `evidence_refs`, `source_ref`, `vocabulary`, and
`vocabulary_version`. Numeric model values are optional `score` values only and
must include `score_kind: clap_audio_text_cosine_similarity_v1`; this is raw
audio/text cosine similarity in `[-1, 1]`, never a confidence or probability.

`provenance.sources` is a registry keyed by every `source_ref`. Evidence refs
are stable logical refs (for example `track_map.analysis.musical.bpm`), never
local JSON paths or filesystem locations.

## Derivation policy

- `pace_character` is rule-derived only from `ok` BPM: `<80` `slow`, `80–<110`
  `moderate`, `110–<140` `upbeat`, `>=140` `fast`.
- `energy_class` and `arrangement_character` use automatic Arrangement Map
  evidence only. Manual overrides never contribute. `arrangement_character`
  uses the existing `sample_brain.arrangement_role_vocabulary` v1.0.0 exactly.
  Only the supported Arrangement Map `0.x` schema family is accepted; every
  supplied section must carry an automatic result and the root `status` is
  required. A supplied map that combines usable automatic sections with an
  `unknown` or `unavailable` section keeps derived values `partial`.
  A root-level `uncertain` status keeps both fields `partial`; an automatic map
  without a supported energy-bearing role produces `energy_class: no_result`.
  A lone `breakdown` never implies `low`: no energy value is emitted without
  independent automatic energy-bearing role evidence.
- `instrumentation` is derived only from confirmed Producer Group manifests.
  `melodic` and `atmos_fx` are HPSS proxies and remain `partial`.
- `genre`, `subgenre`, `mood`, `sound_palette`, `production_character`, and
  `usage_context` require an explicitly injected `EmbeddingBackend` and a
  runtime-only `audio_path`. Their fixed controlled prompts are evaluated
  deterministically. A candidate needs a cosine similarity of at least `0.5`;
  its raw score is retained with the documented score kind. All CLAP-derived
  values remain `partial` in v1.
- Without an injected backend or audio path, model fields are `not_run`; an
  unavailable backend is `not_run`; insufficient scored evidence is
  `no_result`; an invalid backend response is `failed`.

The controlled vocabulary is normative in
`stock_music_descriptor_vocabulary_v1.json`. It deliberately contains no
artist, brand, film, TV, game, rights, or contributor terms.
