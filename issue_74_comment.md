## Upstream `sqlite-vec` Recheck (2026-08-20)

- **Date:** 2026-08-20
- **Exact Versions:**
  - Stable: `v0.1.9` (GitHub Release `v0.1.9` published 2026-03-31; PyPI release `0.1.9`)
  - Pre-release: `v0.1.10-alpha.4` (GitHub Release `v0.1.10-alpha.4` published 2026-05-18; PyPI release `0.1.10a4`, along with `0.1.10a1`–`0.1.10a3`)
- **Windows / Linux Wheels:** Yes. Pre-compiled wheels exist on PyPI for both stable `0.1.9` and pre-release `0.1.10a4` across Windows (`win_amd64`), Linux (`manylinux_2_17_x86_64`, `manylinux_2_17_aarch64`), and macOS (`x86_64`, `arm64`).
- **Stable Documented ANN Build/Query Contract:** No. Stable `v0.1.9` supports brute-force `vec0` search only. The `v0.1.10-alpha` line introduces experimental DiskANN, IVF, and rescore features, but official documentation (`https://alexgarcia.xyz/sqlite-vec/`) displays "🚧 This documentation is a work-in-progress!", notes `sqlite-vec is pre-v1, so expect breaking changes`, and no stable documented ANN build/query contract exists in a stable release.
- **Verdict:** No stable ANN release exists as of 2026-08-20. The default search backend for `sample-brain` remains `numpy`. Issue #74 remains **OPEN** in tracking status; acceptance criteria for closing #74 (a stable upstream ANN release with a verified build/query contract and passing performance/accuracy gates) are not met.
