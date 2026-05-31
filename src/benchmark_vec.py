from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from . import config
from .db import get_engine, init_db, insert_sample_embedding, text, upsert_embedding_model
from .index import normalize_vectors
from .search_backend import get_search_backend
from .vec_availability import is_sqlite_vec_available
from .vec_index import rebuild_vec0_cache


@dataclass(frozen=True)
class BenchmarkCaseResult:
    sample_count: int
    rebuild_ms: float
    warm_p50_ms: float
    warm_p95_ms: float
    filtered_p50_ms: float
    filtered_p95_ms: float
    db_size_bytes: int


def _percentile(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = int(round((pct / 100.0) * (len(ordered) - 1)))
    return ordered[index]


def _seed_benchmark_db(
    db_path: Path,
    sample_count: int,
    embedding_dim: int = 512,
) -> int:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    if db_path.exists():
        db_path.unlink()

    import os

    os.environ["SAMPLE_BRAIN_DB_PATH"] = str(db_path)
    from .config import set_db_path

    set_db_path(env={"SAMPLE_BRAIN_DB_PATH": str(db_path)})

    config.DB_PATH = db_path
    init_db()
    model_id = upsert_embedding_model(
        provider="bench",
        model_name="noop",
        model_version="1",
        embedding_dim=embedding_dim,
        modality="audio+text",
    )

    engine = get_engine()
    rng = np.random.default_rng(42)
    with engine.begin() as conn:
        for sample_id in range(1, sample_count + 1):
            conn.execute(
                text(
                    """
                    INSERT INTO samples (id, path, hash, duration)
                    VALUES (:id, :path, :hash, :duration)
                    """
                ),
                {
                    "id": sample_id,
                    "path": f"/bench/sample-{sample_id}.wav",
                    "hash": f"hash-{sample_id}",
                    "duration": 1.0 + (sample_id % 10) * 0.1,
                },
            )
            conn.execute(
                text(
                    """
                    INSERT INTO features (sample_id, bpm, key, pred_type, class)
                    VALUES (:sample_id, :bpm, :key, :pred_type, :class)
                    """
                ),
                {
                    "sample_id": sample_id,
                    "bpm": 120.0 + (sample_id % 20),
                    "key": "Am" if sample_id % 2 else "C",
                    "pred_type": "kick" if sample_id % 3 == 0 else "snare",
                    "class": "percussive",
                },
            )

    for sample_id in range(1, sample_count + 1):
        vector = rng.standard_normal(embedding_dim, dtype=np.float32)
        vector = normalize_vectors(vector.reshape(1, -1))[0]
        insert_sample_embedding(
            sample_id=sample_id,
            model_id=model_id,
            embedding=vector.tobytes(),
            embedding_format="float32",
            source_hash=f"hash-{sample_id}",
        )

    return model_id


def _timed_search_ms(
    backend_name: str,
    model_id: int,
    query_vector: np.ndarray,
    *,
    topk: int = 10,
    candidate_sample_ids: set[int] | None = None,
    repeats: int = 5,
) -> tuple[float, float]:
    backend = get_search_backend(backend_name)
    timings: list[float] = []
    for _ in range(repeats):
        start = time.perf_counter()
        backend.search(
            query_vector,
            model_id,
            topk=topk,
            candidate_sample_ids=candidate_sample_ids,
        )
        timings.append((time.perf_counter() - start) * 1000.0)
    return _percentile(timings, 50), _percentile(timings, 95)


def run_vec_benchmark(
    sample_counts: list[int] | None = None,
    *,
    backend: str = "sqlite-vec",
    work_dir: Path | None = None,
) -> list[BenchmarkCaseResult]:
    if not is_sqlite_vec_available():
        raise RuntimeError(
            "sqlite-vec is not available. Install with: pip install -e .[vec]"
        )

    counts = sample_counts or [1_000, 10_000]
    results: list[BenchmarkCaseResult] = []
    base_dir = work_dir or Path(".") / ".bench_sqlite_vec"
    base_dir.mkdir(parents=True, exist_ok=True)

    for sample_count in counts:
        db_path = base_dir / f"bench-{sample_count}.db"
        model_id = _seed_benchmark_db(db_path, sample_count)

        start = time.perf_counter()
        rebuild_vec0_cache(model_id, db_path=db_path)
        rebuild_ms = (time.perf_counter() - start) * 1000.0

        query = normalize_vectors(
            np.random.default_rng(7).standard_normal(512, dtype=np.float32).reshape(1, -1)
        )[0]
        warm_p50, warm_p95 = _timed_search_ms(backend, model_id, query)
        filtered_ids = {sid for sid in range(1, sample_count + 1) if sid % 2 == 0}
        filtered_p50, filtered_p95 = _timed_search_ms(
            backend,
            model_id,
            query,
            candidate_sample_ids=filtered_ids,
        )

        results.append(
            BenchmarkCaseResult(
                sample_count=sample_count,
                rebuild_ms=rebuild_ms,
                warm_p50_ms=warm_p50,
                warm_p95_ms=warm_p95,
                filtered_p50_ms=filtered_p50,
                filtered_p95_ms=filtered_p95,
                db_size_bytes=db_path.stat().st_size,
            )
        )

    return results


def print_benchmark_report(results: list[BenchmarkCaseResult]) -> None:
    for result in results:
        print(
            f"samples={result.sample_count} "
            f"rebuild_ms={result.rebuild_ms:.1f} "
            f"warm_p50_ms={result.warm_p50_ms:.2f} "
            f"warm_p95_ms={result.warm_p95_ms:.2f} "
            f"filtered_p50_ms={result.filtered_p50_ms:.2f} "
            f"filtered_p95_ms={result.filtered_p95_ms:.2f} "
            f"db_size_bytes={result.db_size_bytes}"
        )

        if result.sample_count >= 100_000:
            warm_gate = result.warm_p95_ms <= 200.0
            filtered_gate = result.filtered_p95_ms <= 250.0
            print(
                f"  gate_100k_warm_p95={'PASS' if warm_gate else 'FAIL'} "
                f"gate_100k_filtered_p95={'PASS' if filtered_gate else 'FAIL'}"
            )
