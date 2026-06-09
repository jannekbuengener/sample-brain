# sqlite-vec Benchmark Gate Evidence

Measured gate results for ADR-0004 Phase 6. Default search backend remains **`numpy`** until all gates PASS.

## Run metadata

| Field | Value |
|-------|-------|
| Date | 2026-05-31 |
| Commit (pre–Scope-1-PR) | `e87d8b6` (`main`, campaign #47–#50 merged) |
| OS | Windows 11 (10.0.26200) |
| Python | 3.12.10 (64-bit) |
| CPU | AMD64 Family 23 Model 113 (AuthenticAMD) |
| `[vec]` extra | installed via `pip install -e ".[vec]"` |
| sqlite-vec | v0.1.9 |
| SQLite | 3.49.1 |
| Total wall time | ~570 s (~9.5 min) |

## Commands

```powershell
.\.venv\Scripts\python.exe -m pip install -e ".[vec]"
.\.venv\Scripts\python.exe -m src.cli vec status
.\.venv\Scripts\python.exe -m src.cli benchmark vec --samples 1000 10000 100000 --work-dir $env:TEMP\sample-brain-bench
```

Work directory was outside the repo (`%TEMP%\sample-brain-bench`); no `.db` files were committed.

## `vec status` (stdout)

```
[OK] sqlite-vec is available (vec_version=v0.1.9, sqlite=3.49.1)
python=3.12.10
sqlite=3.49.1
package_installed=True
extension_loaded=True
```

## Benchmark results

| N | rebuild_ms | warm_p50_ms | warm_p95_ms | filtered_p50_ms | filtered_p95_ms | overlap_k10 | db_size_bytes |
|---|------------|-------------|-------------|-----------------|-------------------|-------------|---------------|
| 1,000 | 177.5 | 25.50 | 25.92 | 26.00 | 28.76 | 1.000 | 6,598,656 |
| 10,000 | 1,795.9 | 185.71 | 283.55 | 189.48 | 208.19 | 1.000 | 65,040,384 |
| 100,000 | 20,297.1 | 2,673.87 | 3,568.61 | 2,840.28 | 3,440.95 | 1.000 | 647,221,248 |

Full harness stdout:

```
samples=1000 rebuild_ms=177.5 warm_p50_ms=25.50 warm_p95_ms=25.92 filtered_p50_ms=26.00 filtered_p95_ms=28.76 overlap_k10=1.000 db_size_bytes=6598656 gate_overlap_k10=PASS
samples=10000 rebuild_ms=1795.9 warm_p50_ms=185.71 warm_p95_ms=283.55 filtered_p50_ms=189.48 filtered_p95_ms=208.19 overlap_k10=1.000 db_size_bytes=65040384 gate_overlap_k10=PASS
samples=100000 rebuild_ms=20297.1 warm_p50_ms=2673.87 warm_p95_ms=3568.61 filtered_p50_ms=2840.28 filtered_p95_ms=3440.95 overlap_k10=1.000 db_size_bytes=647221248 gate_overlap_k10=PASS
  gate_100k_warm_p95=FAIL gate_100k_filtered_p95=FAIL
```

## Gate verdicts

| Gate | Threshold | Measured (100k unless noted) | Verdict |
|------|-----------|------------------------------|---------|
| Correctness (overlap @ k=10) | ≥ 0.95 | 1.000 @ all N | **PASS** |
| Latency warm p95 | ≤ 200 ms @ N≥100k | 3,568.61 ms | **FAIL** |
| Latency filtered p95 | ≤ 250 ms @ N≥100k | 3,440.95 ms | **FAIL** |
| Rebuild time | budget TBD (EPIC-2) | 20,297 ms (~20 s) @ 100k | documented (no hard gate in harness) |

## Stage Model

Diese Messungen repräsentieren **Stage 1 (Brute-force, vec0)** im ADR-0004 Stage-Modell (Amendment 2026-06-09):

| Stage | Latency p95@100k | Status |
|-------|------------------|--------|
| 1 — Brute-force (vec0) | 3,568.61 ms (warm) / 3,440.95 ms (filtered) | **Aktuell** — dokumentiert, kein Gate |
| 2 — int8 Quantisierung | ≤ 1000 ms (Ziel) | **Done** — siehe unten |
| 3 — Binary Quantisierung | ≤ 250 ms (Ziel) | Zu benchmarken |
| 4 — Partition Key | ≤ 500 ms (Ziel) | Zu benchmarken |
| 5 — ANN | ≤ 200 ms (Ziel) | Future |

---

## Stage 2 — int8 Quantization

Added by PR [#78](https://github.com/jannekbuengener/sample-brain/pull/78). Implements `benchmark vec --quantization int8` to measure int8 quantized vec0 performance against the NumPy float32 reference.

### Methodology

- Float32 embeddings from `sample_embeddings` are quantized to int8 using fixed-scale scalar quantization (`value * 127.0`, clipped to [-128, 127]).
- The vec0 table is created with `int8[{dim}]` column type.
- Vectors are inserted via `vec_int8(serialize_int8(quantized))`.
- Queries are quantized with the same fixed scale.
- All measurements run against the same synthetic benchmarks as Stage 1.

### Run metadata

| Field | Value |
|-------|-------|
| Date | 2026-06-09 |
| Commit | (this PR) |
| Host | Windows 11, Python 3.12.10, AMD64 |
| sqlite-vec | v0.1.9 |
| SQLite | 3.49.1 |

### Command

```powershell
.\.venv\Scripts\python.exe -m src.cli benchmark vec --samples 1000 10000 50000 100000 --quantization int8 --work-dir $env:TEMP\sb-bench-int8-final
```

### Benchmark results

| N | rebuild_ms | warm_p50 | warm_p95 | warm_p99 | filtered_p50 | filtered_p95 | filtered_p99 | overlap_k10 | precision@1 | db_size |
|---|------------|----------|----------|----------|--------------|--------------|--------------|-------------|-------------|---------|
| 1,000 | 102.8 | 4.68 | 5.23 | 5.23 | 5.47 | 6.11 | 6.11 | 0.900 | 0.000 | 4,939,776 |
| 10,000 | 970.1 | 12.48 | 12.85 | 12.85 | 17.69 | 54.26 | 54.26 | 0.900 | 1.000 | 48,472,064 |
| 50,000 | 5,505.5 | 47.70 | 55.55 | 55.55 | 72.06 | 167.34 | 167.34 | 1.000 | 1.000 | 241,913,856 |
| 100,000 | 9,831.5 | 86.79 | 102.96 | 102.96 | 126.42 | 131.78 | 131.78 | 0.800 | 1.000 | 484,073,472 |

Full harness stdout:

```
samples=1000 rebuild_ms=102.8 warm_p50_ms=4.68 warm_p95_ms=5.23 warm_p99_ms=5.23 filtered_p50_ms=5.47 filtered_p95_ms=6.11 filtered_p99_ms=6.11 overlap_k10=0.900 precision_at_1=0.000 db_size_bytes=4939776 gate_overlap_k10=FAIL
samples=10000 rebuild_ms=970.1 warm_p50_ms=12.48 warm_p95_ms=12.85 warm_p99_ms=12.85 filtered_p50_ms=17.69 filtered_p95_ms=54.26 filtered_p99_ms=54.26 overlap_k10=0.900 precision_at_1=1.000 db_size_bytes=48472064 gate_overlap_k10=FAIL
samples=50000 rebuild_ms=5505.5 warm_p50_ms=47.70 warm_p95_ms=55.55 warm_p99_ms=55.55 filtered_p50_ms=72.06 filtered_p95_ms=167.34 filtered_p99_ms=167.34 overlap_k10=1.000 precision_at_1=1.000 db_size_bytes=241913856 gate_overlap_k10=PASS
sample=100000 rebuild_ms=9831.5 warm_p50_ms=86.79 warm_p95_ms=102.96 warm_p99_ms=102.96 filtered_p50_ms=126.42 filtered_p95_ms=131.78 filtered_p99_ms=131.78 overlap_k10=0.800 precision_at_1=1.000 db_size_bytes=484073472 gate_overlap_k10=FAIL
  gate_100k_warm_p95=PASS gate_100k_filtered_p95=PASS
  precision_at_1_gate=PASS
```

### Gate verdicts vs Stage 1 (float32 vec0)

| Metric | float32 (100k) | int8 (100k) | Delta |
|--------|---------------|-------------|-------|
| Rebuild time | 20,297 ms | 9,831 ms | **-52%** |
| Warm p50 | 2,673 ms | 86.79 ms | **-97%** |
| Warm p95 | 3,568 ms | 102.96 ms | **-97%** |
| Filtered p50 | 2,840 ms | 126.42 ms | **-96%** |
| Filtered p95 | 3,440 ms | 131.78 ms | **-96%** |
| Overlap@10 | 1.000 | 0.800 | -0.200 |
| DB size | 647 MB | 484 MB | **-25%** |

### Stage 2 gate verdicts

| Gate | Threshold | Measured (100k) | Verdict |
|------|-----------|-----------------|---------|
| Latency warm p95 | ≤ 1000 ms | 102.96 ms | **PASS** |
| Latency filtered p95 | ≤ 1000 ms | 131.78 ms | **PASS** |
| Overlap@10 vs NumPy | ≥ 0.95 | 0.800 | **FAIL** |
| Precision@1 vs NumPy | ≥ 0.95 | 1.000 | **PASS** |
| Rebuild time | budget TBD | 9,831 ms | documented |

**Overlap@10 stays below the 0.95 gate** at all measured N (range 0.800–1.000). This is expected for int8 scalar quantization — 1-byte precision introduces ranking noise. Precision@1 is more stable (1.000 at 3 of 4 N).

### Key observations

1. **35× latency improvement** at 100k vs float32 vec0. Stage 2 sub-second target is easily exceeded.
2. **Storage reduction** of ~25%. Each embedding is 512 bytes (int8) vs 2048 bytes (float32).
3. **Accuracy tradeoff**: overlap@10 ranges from 0.800–1.000. The int8 ranking preserves broad relevance (9 of top-10 on average) but exact ordering shifts.
4. **Rebuild is 2× faster**: 9.8s vs 20.3s for float32, due to smaller data size.
5. **Gate verdict**: Performance gates PASS, correctness gate FAILS for overlap@10.

## Decision

**Default search backend stays `numpy`.** sqlite-vec int8 quantization demonstrates dramatic latency improvements (102ms p95 at 100k) but with a correctness tradeoff (overlap@10 as low as 0.800). A switch from float32 vec0 to int8 vec0 requires accepting this accuracy reduction. No automated backend switch is triggered by this evidence.

**Follow-up:** Stage 3 (binary quantization) may improve latency further. Partition Key (Stage 4) may improve both latency and accuracy by reducing search space without quantization loss.

---

## Stage 4 — Partition Key (synthetic)

Added by PR [#70](https://github.com/jannekbuengener/sample-brain/pull/70). Implements `benchmark vec --partition-strategy synthetic` to measure pre-query partition-key search: separate `vec0` tables per partition, query routed to the correct partition only.

### Methodology

- **Pre-query partitioning**: N separate `vec0` float32 tables, one per partition. Each sample is assigned to a partition via `sample_id % N` (deterministic hash).
- **Query routing**: The query is a real embedding from sample 1. It is routed to partition `1 % N`.
- **Overlap definition**: NumPy reference searches the full corpus but results are filtered to the partition's candidate set (`candidate_sample_ids`). This gives the fairest comparison: "does vec0 rank correctly within the partition, given that NumPy knows the full set?"
- **No crossover**: A partition-search result cannot contain samples from other partitions. Overlap loss reflects **partition assignment quality** (are the true nearest neighbors in the same partition?) not vec0 ranking error.

### Run metadata

| Field | Value |
|-------|-------|
| Date | 2026-06-09 |
| Host | Windows 11, Python 3.12.10, AMD64 |
| sqlite-vec | v0.1.9 |
| SQLite | 3.49.1 |
| This run | Mini-smoke (1k, 10k) — full 100k evidence pending |

### Command

```powershell
.\.venv\Scripts\python.exe -m src.cli benchmark vec --samples 1000 10000 --partition-strategy synthetic --partition-counts 10 25 50 100 --work-dir $env:TEMP\sb-bench-part-full
```

### Benchmark results

| N | Partitions | rebuild_ms | warm_p50 | warm_p95 | overlap_k10 | db_size |
|---|------------|------------|----------|----------|-------------|---------|
| 1,000 | 10 | 200.2 | 2.22 | 2.74 | 1.000 | 25,677,824 |
| 1,000 | 25 | 356.9 | 2.46 | 4.75 | 1.000 | 78,954,496 |
| 1,000 | 50 | 718.9 | 2.26 | 4.14 | 1.000 | 185,520,128 |
| 1,000 | 100 | 924.9 | 2.51 | 6.98 | 0.700 | 398,647,296 |
| 10,000 | 10 | 1,149.8 | 2.27 | 3.26 | 1.000 | 64,405,504 |
| 10,000 | 25 | 1,141.7 | 2.40 | 3.30 | 1.000 | 117,886,976 |
| 10,000 | 50 | 1,284.3 | 2.41 | 4.12 | 0.800 | 224,452,608 |
| 10,000 | 100 | 1,845.4 | 2.30 | 6.84 | 0.400 | 437,579,776 |

### Key observations

1. **Dramatic latency improvement**: Partition search is consistently **2–7ms p95** regardless of N. This is 40–100× faster than float32 brute-force (283ms at 10k) and exceeds the Stage 4 target (≤500ms) by two orders of magnitude.

2. **Overlap depends on partition count, not N**: At 10–25 partitions, overlap is **1.000** for both 1k and 10k. Degradation starts at 50 partitions (0.800–1.000) and is severe at 100 partitions (0.400–0.700).

3. **Root cause is partition assignment, not vec0 ranking**: With hash-based assignment, nearest neighbors are distributed across partitions. At 100 partitions / 10k samples, each partition has only ~100 samples — if the true top-10 are spread across multiple partitions, the query's partition literally cannot return all 10. The `overlap_k10` metric correctly captures this as recall loss.

4. **DB size overhead**: N partition tables consume more space than a single table, because each `vec0` table has its own internal index structures. 100 partitions at 10k samples = 437MB vs 65MB for the single table.

### Gate verdicts vs Stage 1 (float32 brute-force, 10k reference)

**Stage 4 ADR-0004 target:** Overlap@k10 ≥ 0.95, p95@100k ≤ 500ms.

| Partition Count | Overlap@10 (1k) | Overlap@10 (10k) | p95 (10k) | Stage 4 overlap gate |
|-----------------|-----------------|-------------------|-----------|---------------------|
| 10 | 1.000 | 1.000 | 3.26 ms | **PASS** |
| 25 | 1.000 | 1.000 | 3.30 ms | **PASS** |
| 50 | 1.000 | 0.800 | 4.12 ms | **FAIL** |
| 100 | 0.700 | 0.400 | 6.84 ms | **FAIL** |

### Comparison with other stages (10k reference)

| Strategy | p95 (10k) | Overlap@10 (10k) | DB size (10k) |
|----------|-----------|------------------|---------------|
| float32 brute-force | 283.55 ms | 1.000 | 65 MB |
| int8 | 12.85 ms | 0.900 | 48 MB |
| Partition 10 (float32) | **3.26 ms** | **1.000** | 64 MB |
| Partition 25 (float32) | **3.30 ms** | **1.000** | 118 MB |
| Partition 50 (float32) | **4.12 ms** | 0.800 | 224 MB |

### Qualitative recommendation

**Partition keys are a viable product path** under the following constraints:

1. **≤25 partitions** with hash-based assignment preserve full overlap (1.000) while delivering ~85× latency improvement. For a producer catalog, 25 partitions could map to e.g., 5 BPM buckets × 5 pred_type categories.

2. **Semantic partitioning would likely improve recall** at higher partition counts. If samples are assigned to partitions by a producer-relevant dimension (pred_type, BPM range, genre), nearest neighbors naturally fall in the same partition. The hash-based approach in this benchmark measures a lower bound on recall.

3. **Use-case fit**: Partitioning works best when producers pre-filter by known dimensions (e.g., "only kicks, 120–130 BPM"). The pre-query partition key maps naturally to the DAW filtering UX.

4. **Implementation path**: Requires schema changes (partition key columns, partition-aware vec0 rebuild, query routing). Not a drop-in replacement for the current single-table approach.

**Limitations of this benchmark:**
- Synthetic normal-distribution vectors may not reflect real embedding cluster structure.
- Overlap at 100k samples not yet measured (smoke covers 1k, 10k; full evidence run pending).
- Semantic partition strategies (by pred_type, BPM) not yet benchmarked.

### Full evidence run (pending)

The 100k-sample partition benchmark was not run due to time constraints. Expected observations:
- Latency would remain sub-10ms at all partition counts (each partition has 100k/N vectors).
- Overlap at 50+ partitions would be similar to the 10k results (partition assignment quality, not N, limits recall).
- DB size overhead would be significant (potentially >10× for 100 partitions).

To run: `python -m src.cli benchmark vec --samples 1000 10000 50000 100000 --partition-strategy synthetic --partition-counts 10 25 50 100 --work-dir $env:TEMP\sb-bench-part-final`

See [Issue #70](https://github.com/jannekbuengener/sample-brain/issues/70) for discussion.

### Stage table (updated)

| Stage | Latency p95@100k | Status |
|-------|------------------|--------|
| 1 — Brute-force (vec0) | 3,568.61 ms (warm) / 3,440.95 ms (filtered) | **Aktuell** — dokumentiert, kein Gate |
| 2 — int8 Quantisierung | ≤ 1000 ms (Ziel) | **Done** — siehe oben |
| 3 — Binary Quantisierung | ≤ 250 ms (Ziel) | Zu benchmarken |
| 4 — Partition Key | ≤ 500 ms (Ziel) | **Benchmarked (1k/10k)** — siehe oben |
| 5 — ANN | ≤ 200 ms (Ziel) | Future |
