# Content Identity v2 — Versioned SHA-256 Migration

**Issue:** #417
**Status:** canonical migration contract
**Date:** 2026-08-18

## 1. Decision

Sample Brain content identity is algorithm-qualified. New content hashes use SHA-256:

```json
{"algorithm": "sha256", "value": "<64 lowercase hex chars>"}
```

Legacy SHA-1 remains a supported **read/migration** format only:

```json
{"algorithm": "sha1", "value": "<40 lowercase hex chars>"}
```

A bare digest is never enough to establish its algorithm at a new external contract boundary.

## 2. What this changes

New writes use SHA-256 for content-derived identities including:

- scanned sample content identity;
- Track Map source identity / track IDs;
- asset and stem audio content hashes;
- Performance Pack audio integrity hashes;
- deconstruction/resume content identity;
- new Track Analysis Cache source identities.

Cryptographic identities that are **not** Sample Brain content hashes are outside this migration. In particular Demucs/model weight hashes and already-SHA-256 cache/fingerprint digests keep their own contracts.

## 3. Database compatibility

The historical `samples.hash` column stored a bare SHA-1 value. v2 adds an additive `samples.hash_algorithm` column.

Rules:

1. New rows and rescanned rows write `hash_algorithm = "sha256"`.
2. Existing rows created before this column are not mass-rehashed. A `NULL` algorithm on such a legacy row is interpreted explicitly as `sha1` because that is the documented pre-v2 catalog contract.
3. Dedupe/path comparison must compare **algorithm + value**, not only the digest value.
4. Existing `sample_embeddings.source_hash` rows remain valid historical source fingerprints. A sample that is later rescanned to SHA-256 naturally becomes pending for a fresh embedding because its current `samples.hash` value changes.
5. No private catalog/database migration command is run automatically by this repo change.

## 4. External manifest compatibility

Readers verify audio using the algorithm declared in the manifest/hash record.

- Existing v1 manifests/packs declaring `sha1` remain readable and verifiable.
- New manifests/packs declare `sha256`.
- Unknown algorithms fail closed.
- A SHA-1 value is never relabeled as SHA-256, and a SHA-256 value is never verified with SHA-1.

The existing `{algorithm, value}` shape is already version-friendly, so most v1 document schemas do not need a breaking major-version bump solely for the digest upgrade.

## 5. Track Analysis Cache compatibility

The cache key is itself SHA-256 and remains so. The source-content field inside the key becomes algorithm-aware.

On a cache-enabled Track Map analysis:

1. hash the source bytes once while computing both current SHA-256 and legacy SHA-1 digests;
2. try the new SHA-256 cache key first;
3. if absent, try the exact legacy SHA-1 key/entry;
4. a valid legacy hit may reuse the expensive analysis, but the returned Track Map is rebuilt with current SHA-256 source identity;
5. publish/migrate that result under the new SHA-256 cache key so future runs no longer need the legacy key.

This is an on-touch cache migration, not a private-library bulk rehash.

## 6. Utility contract

The canonical file hashing helper supports only allowlisted algorithms:

```text
sha256  default for new writes
sha1    legacy compatibility only
```

Helpers that accept a hash record validate the algorithm explicitly. Multi-hash calculation reads the file once and updates both hashers, avoiding duplicate reads of large audio files during legacy-cache migration.

## 7. Security boundary

SHA-1 is no longer accepted as the default new content identity because collision resistance is insufficient for a durable provenance/dedupe boundary. Legacy SHA-1 remains supported only where an existing artifact/catalog explicitly identifies it as such.

This migration does not claim SHA-256 alone authenticates an untrusted file. It provides stronger collision-resistant content identity; trust/authenticity still depends on the surrounding provenance and source.

## 8. Acceptance / evidence

The migration is complete when:

- new content-hash helper output is SHA-256 by default;
- old SHA-1 can still be computed only through an explicit legacy/algorithm path;
- old catalog schema upgrades additively without rehashing existing rows;
- new scans record SHA-256 + algorithm;
- algorithm-aware DB dedupe does not conflate legacy and current identities;
- old SHA-1 Performance Pack/manifest integrity validation still succeeds;
- new SHA-256 pack/manifest integrity validation succeeds;
- new Track Maps declare SHA-256;
- legacy Track Analysis Cache entries can be read/migrated on touch;
- new cache entries declare SHA-256;
- model/checkpoint weight-hash semantics are unchanged;
- focused tests and full CI are green.
