# Pond5 Contributor / Rights Profile v1

**Issue:** #450  
**Document type:** `sample_brain.pond5_profile`  
**Schema version:** `1.0.0`

## Purpose

This profile supplies Pond5 facts that cannot be inferred from audio or Track
Map analysis. Real contributor and rights values live only in the existing
machine-local Sample Brain profile file (`config/profiles.local.yaml`, which is
gitignored). The repository contains placeholders and the resolver contract
only.

## Config shape

```yaml
profiles:
  default:
    pond5:
      contributor:
        composer: null
        ipi: null
        pro: null
        publisher: null
        copyright_owner: null
      rights:
        ownership_authorized: null
        third_party_elements_cleared_for_resale: null
        cleared_for_sampling: null
      listing:
        default_price_usd: null
```

No field above is inferred. `null` means unresolved. Rights booleans preserve
explicit `false`; it is never rewritten as unknown.

## Resolution

`resolve_pond5_profile(resolved_config, per_track_overrides=...)` applies the
fixed precedence:

1. explicit per-track override
2. resolved local profile value
3. unknown (`null`)

Each emitted value carries `status`, `value`, and a portable `source_ref`.
`provenance.sources` records whether a source is `profile`,
`per_track_override`, or `unknown`; machine-local paths are never serialized.

The contributor fields are `composer`, `ipi`, `pro`, `publisher`, and
`copyright_owner`. The rights fields are `ownership_authorized`,
`third_party_elements_cleared_for_resale`, and `cleared_for_sampling`.

## Fail-closed readiness helper

`profile_hold_reasons()` reports only blockers that belong to the manual-data
boundary of #450:

- `COMPOSER_MISSING`
- `OWNERSHIP_AUTHORIZATION_UNRESOLVED`
- `OWNERSHIP_NOT_AUTHORIZED`
- `THIRD_PARTY_CLEARANCE_UNRESOLVED`
- `THIRD_PARTY_CLEARANCE_DENIED`
- `SAMPLING_POLICY_UNSET`

`cleared_for_sampling=false` is a resolved licensing choice and is therefore
not a missing-value blocker. Full Pond5 technical/listing readiness remains the
responsibility of #451.

## Boundaries

- no Pond5 credentials, API, upload, browser automation, or network access
- no legal or copyright inference
- no Track Map or semantic fallback for contributor/rights facts
- no source-audio mutation
- no absolute local paths, caches, DBs, or secrets in portable output

This is the manual-only input surface consumed by the readiness contract in
`docs/POND5_READINESS_V1.md` and by the later #451 bundle/validator.
