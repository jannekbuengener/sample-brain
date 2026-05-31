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

## Decision

**Default search backend stays `numpy`.** sqlite-vec is opt-in via `--search-backend sqlite-vec` or profile/env override. Correctness vs NumPy is proven; interactive latency at 100k does not meet ADR-0004/EPIC-2 sub-second targets on this Windows host. Follow-up performance work is out of scope for this evidence slice.
