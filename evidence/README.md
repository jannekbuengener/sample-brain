# Curated Validation Evidence

`evidence/` is the repository's intentionally reviewed, public validation-evidence area. It is **not** a general runtime-output directory.

## Decision for #419

Sample Brain uses policy variant **A**: small, curated validation evidence may be committed when it is useful for reproducing or reviewing a product/quality claim. Arbitrary generated state remains local and untracked.

At adoption of this contract (2026-08-18), the tracked inventory contains 29 JSON records:

- `buffer_128_*`: 4 buffer-performance records
- `buffer_256_*`: 4 buffer-performance records
- `buffer_512_*`: 4 buffer-performance records
- `device_robustness_*`: 4 device-state/robustness records
- `dsp_*`: 3 DSP/sync performance records
- `haeffig_*`: 4 editing-contract records
- `recording_*`: 1 recording-contract record
- `sync_grid_*`: 5 sync/grid performance records

## Commit contract

A committed evidence JSON must:

- be intentionally selected for review rather than committed merely because a runtime produced it;
- be a small JSON object (maximum 100 KB);
- contain a non-empty `suite` field;
- contain only public validation metrics, statuses, contract values, and other reviewable technical facts;
- contain no absolute/private filesystem paths;
- contain no usernames, host/machine names, device names or device identifiers;
- contain no sample/audio file paths or private sample identifiers;
- contain no API keys, tokens, secrets, credentials, or raw private audio.

`tests/test_evidence_policy.py` enforces the machine-checkable part of this contract in the normal full-core pytest gate.

## Runtime output

Validation tools may write arbitrary raw output only to an explicitly chosen local/ignored destination. A file becomes repository evidence only after it is reviewed against this contract and deliberately added to `evidence/`.

Historical evidence is retained unless it is proven unsafe, misleading, or obsolete enough to remove through a reviewed change.
