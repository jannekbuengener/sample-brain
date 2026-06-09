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
