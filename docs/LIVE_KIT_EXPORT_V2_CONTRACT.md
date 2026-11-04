# Live Kit Export V2 Contract — Sample Brain

**Status:** ACTIVE_SUPPORTING  
**Class:** ACTIVE_SUPPORTING  
**Issue:** [#1377](https://github.com/jannekbuengener/sample-brain/issues/1377)  
**Parents:** [#1075](https://github.com/jannekbuengener/sample-brain/issues/1075)  
**Depends on:** frozen Export V1 ([#1224](https://github.com/jannekbuengener/sample-brain/issues/1224) / `docs/LIVE_KIT_EXPORT_V1_CONTRACT.md`)

## Purpose

V2 is the **explicit, versioned** portable export for Live Kits that contain
growable Extra-N slots beyond the canonical 11-slot taxonomy. It does **not**
reinterpret or mutate frozen Export V1.

```text
canonical-only kit  → schema_version = 1  (V1 contract unchanged)
kit with Extra-N    → schema_version = 2  (this contract)
```

## Normative rules

1. V1 packages remain valid forever under `docs/LIVE_KIT_EXPORT_V1_CONTRACT.md`.
2. Runtime chooses V2 only when `live_kit_has_extra_slots(state)` is true.
3. Bundle topology, media copy semantics, atomic failure, path confinement, and
   metadata authority are identical to V1 unless stated below.
4. Each group lists **current ordered slots** (canonical seed followed by any
   `Extra N` identities). Empty slots remain listed with `assigned=false`.
5. Unsupported future `schema_version` values fail closed at inspect/read time.

## Slot identity

| Concern | V2 rule |
|---|---|
| Canonical seed | Still `LIVE_KIT_SLOT_MAPPING` group/slot keys |
| Growable slots | Domain keys `Extra 1`, `Extra 2`, … per group |
| Display labels | Not export identity |
| Ordering | Domain `slots_for(group)` order |

## Non-goals

Silent V1 field reinterpretation; Arrangement channel invention for Extra-N;
QML-only shadow kits; cloud/DAW package formats.
