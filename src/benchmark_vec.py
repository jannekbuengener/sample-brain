from __future__ import annotations

import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import sqlite_vec

from . import config
from .db import get_embedding_model_by_id, get_engine, init_db, insert_sample_embedding, text, upsert_embedding_model
from .index import SearchHit, decode_embedding_blob, normalize_vectors
from .search_backend import get_search_backend
from .vec_availability import is_sqlite_vec_available
from .vec_index import (
    VEC_SAMPLE_CURRENT_TABLE,
    load_current_embedding_rows,
    open_vec_connection,
    rebuild_vec0_cache,
)

OVERLAP_GATE = 0.95
WARM_P95_GATE_MS = 200.0
FILTERED_P95_GATE_MS = 250.0

VEC_SAMPLE_INT8_TABLE = "vec_sample_int8"


@dataclass(frozen=True)
class BenchmarkCaseResult:
    sample_count: int
    rebuild_ms: float
    warm_p50_ms: float
    warm_p95_ms: float
    warm_p99_ms: float = 0.0
    filtered_p50_ms: float = 0.0
    filtered_p95_ms: float = 0.0
    filtered_p99_ms: float = 0.0
    overlap_k10: float = 0.0
    precision_at_1: float = 0.0
    db_size_bytes: int = 0


def _percentile(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = int(round((pct / 100.0) * (len(ordered) - 1)))
    return ordered[index]


def _quantize_float32_to_int8(vector: np.ndarray) -> np.ndarray:
    return np.clip(np.round(vector * 127.0), -128.0, 127.0).astype(np.int8)


def _rebuild_int8_vec0_cache(
    model_id: int,
    db_path: Path,
) -> int:
    model = get_embedding_model_by_id(model_id)
    if model is None:
        raise ValueError(f"Unknown embedding model_id={model_id}")
    embedding_dim = model["embedding_dim"]

    rows = load_current_embedding_rows(model_id)

    conn = open_vec_connection(db_path)
    try:
        conn.execute(f"DROP TABLE IF EXISTS {VEC_SAMPLE_INT8_TABLE}")
        conn.execute(
            f"""
            CREATE VIRTUAL TABLE {VEC_SAMPLE_INT8_TABLE} USING vec0(
              embedding int8[{embedding_dim}]
            )
            """
        )

        insert_sql = f"""
            INSERT INTO {VEC_SAMPLE_INT8_TABLE}(rowid, embedding)
            VALUES (?, vec_int8(?))
        """
        for sample_id, blob, _source_hash, dim in rows:
            vector = decode_embedding_blob(blob, dim)
            normalized = normalize_vectors(vector.reshape(1, -1))[0]
            quantized = _quantize_float32_to_int8(normalized)
            serialized = sqlite_vec.serialize_int8(quantized)
            conn.execute(insert_sql, (sample_id, serialized))

        conn.commit()
    finally:
        conn.close()

    return len(rows)


def _int8_search(
    model_id: int,
    query_vector: np.ndarray,
    *,
    topk: int = 10,
    candidate_sample_ids: set[int] | None = None,
    db_path: Path | None = None,
) -> list[SearchHit]:
    model = get_embedding_model_by_id(model_id)
    if model is None:
        raise ValueError(f"Unknown embedding model_id={model_id}")
    embedding_dim = model["embedding_dim"]

    query_norm = normalize_vectors(query_vector.reshape(1, -1))[0]
    query_int8 = _quantize_float32_to_int8(query_norm)
    serialized = sqlite_vec.serialize_int8(query_int8)

    conn = open_vec_connection(db_path)
    try:
        conn.row_factory = sqlite3.Row
        fetch_k = topk
        if candidate_sample_ids is not None:
            fetch_k = max(topk * 50, 200)
        matches = conn.execute(
            f"""
            SELECT rowid, distance
            FROM {VEC_SAMPLE_INT8_TABLE}
            WHERE embedding MATCH vec_int8(?)
            ORDER BY distance
            LIMIT ?
            """,
            (serialized, fetch_k),
        ).fetchall()
    finally:
        conn.close()

    hits: list[SearchHit] = []
    for row in matches:
        sample_id = int(row["rowid"])
        if candidate_sample_ids is not None and sample_id not in candidate_sample_ids:
            continue
        distance = float(row["distance"])
        hits.append(SearchHit(sample_id=sample_id, path="", score=-distance))
        if len(hits) >= topk:
            break
    return hits


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
) -> tuple[float, float, float]:
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
    return (
        _percentile(timings, 50),
        _percentile(timings, 95),
        _percentile(timings, 99),
    )


def _int8_timed_search_ms(
    model_id: int,
    query_vector: np.ndarray,
    *,
    topk: int = 10,
    candidate_sample_ids: set[int] | None = None,
    db_path: Path | None = None,
    repeats: int = 5,
) -> tuple[float, float, float]:
    timings: list[float] = []
    for _ in range(repeats):
        start = time.perf_counter()
        _int8_search(
            model_id,
            query_vector,
            topk=topk,
            candidate_sample_ids=candidate_sample_ids,
            db_path=db_path,
        )
        timings.append((time.perf_counter() - start) * 1000.0)
    return (
        _percentile(timings, 50),
        _percentile(timings, 95),
        _percentile(timings, 99),
    )


def _measure_topk_overlap(
    model_id: int,
    query_vector: np.ndarray,
    *,
    topk: int = 10,
    candidate_sample_ids: set[int] | None = None,
) -> float:
    numpy_hits = get_search_backend("numpy").search(
        query_vector,
        model_id,
        topk=topk,
        candidate_sample_ids=candidate_sample_ids,
    )
    vec_hits = get_search_backend("sqlite-vec").search(
        query_vector,
        model_id,
        topk=topk,
        candidate_sample_ids=candidate_sample_ids,
    )
    numpy_ids = {hit.sample_id for hit in numpy_hits}
    vec_ids = {hit.sample_id for hit in vec_hits}
    if topk <= 0:
        return 1.0
    return len(numpy_ids & vec_ids) / topk


def _measure_int8_topk_overlap(
    model_id: int,
    query_vector: np.ndarray,
    *,
    topk: int = 10,
    candidate_sample_ids: set[int] | None = None,
    db_path: Path | None = None,
) -> float:
    numpy_hits = get_search_backend("numpy").search(
        query_vector,
        model_id,
        topk=topk,
        candidate_sample_ids=candidate_sample_ids,
    )
    int8_hits = _int8_search(
        model_id,
        query_vector,
        topk=topk,
        candidate_sample_ids=candidate_sample_ids,
        db_path=db_path,
    )
    numpy_ids = {hit.sample_id for hit in numpy_hits}
    int8_ids = {hit.sample_id for hit in int8_hits}
    if topk <= 0:
        return 1.0
    return len(numpy_ids & int8_ids) / topk


def _measure_precision_at_1(
    model_id: int,
    query_vector: np.ndarray,
    *,
    db_path: Path | None = None,
) -> float:
    numpy_hits = get_search_backend("numpy").search(
        query_vector, model_id, topk=1
    )
    int8_hits = _int8_search(
        model_id, query_vector, topk=1, db_path=db_path
    )
    if not numpy_hits or not int8_hits:
        return 0.0
    return 1.0 if numpy_hits[0].sample_id == int8_hits[0].sample_id else 0.0


def run_vec_benchmark(
    sample_counts: list[int] | None = None,
    *,
    backend: str = "sqlite-vec",
    quantization: str = "float32",
    work_dir: Path | None = None,
) -> list[BenchmarkCaseResult]:
    if not is_sqlite_vec_available():
        raise RuntimeError(
            "sqlite-vec is not available. Install with: pip install -e .[vec]"
        )

    if quantization not in ("float32", "int8"):
        raise ValueError(
            f"Unknown quantization strategy: {quantization!r}. "
            "Must be 'float32' or 'int8'."
        )

    counts = sample_counts or [1_000, 10_000, 50_000, 100_000]
    results: list[BenchmarkCaseResult] = []
    base_dir = work_dir or Path(".") / ".bench_sqlite_vec"
    base_dir.mkdir(parents=True, exist_ok=True)

    is_int8 = quantization == "int8"

    for sample_count in counts:
        db_path = base_dir / f"bench-{sample_count}.db"
        model_id = _seed_benchmark_db(db_path, sample_count)

        start = time.perf_counter()
        if is_int8:
            _rebuild_int8_vec0_cache(model_id, db_path=db_path)
        else:
            rebuild_vec0_cache(model_id, db_path=db_path)
        rebuild_ms = (time.perf_counter() - start) * 1000.0

        query = normalize_vectors(
            np.random.default_rng(7).standard_normal(512, dtype=np.float32).reshape(1, -1)
        )[0]
        filtered_ids = {sid for sid in range(1, sample_count + 1) if sid % 2 == 0}

        if is_int8:
            warm_p50, warm_p95, warm_p99 = _int8_timed_search_ms(
                model_id, query, db_path=db_path
            )
            filtered_p50, filtered_p95, filtered_p99 = _int8_timed_search_ms(
                model_id, query, candidate_sample_ids=filtered_ids, db_path=db_path
            )
            overlap_k10 = _measure_int8_topk_overlap(
                model_id, query, topk=10, db_path=db_path
            )
            precision_at_1 = _measure_precision_at_1(
                model_id, query, db_path=db_path
            )
        else:
            warm_p50, warm_p95, warm_p99 = _timed_search_ms(backend, model_id, query)
            filtered_p50, filtered_p95, filtered_p99 = _timed_search_ms(
                backend, model_id, query, candidate_sample_ids=filtered_ids
            )
            overlap_k10 = _measure_topk_overlap(model_id, query, topk=10)
            precision_at_1 = 0.0

        results.append(
            BenchmarkCaseResult(
                sample_count=sample_count,
                rebuild_ms=rebuild_ms,
                warm_p50_ms=warm_p50,
                warm_p95_ms=warm_p95,
                warm_p99_ms=warm_p99,
                filtered_p50_ms=filtered_p50,
                filtered_p95_ms=filtered_p95,
                filtered_p99_ms=filtered_p99,
                overlap_k10=overlap_k10,
                precision_at_1=precision_at_1,
                db_size_bytes=db_path.stat().st_size,
            )
        )

    return results


def print_benchmark_report(results: list[BenchmarkCaseResult]) -> None:
    for result in results:
        overlap_gate = result.overlap_k10 >= OVERLAP_GATE
        print(
            f"samples={result.sample_count} "
            f"rebuild_ms={result.rebuild_ms:.1f} "
            f"warm_p50_ms={result.warm_p50_ms:.2f} "
            f"warm_p95_ms={result.warm_p95_ms:.2f} "
            f"warm_p99_ms={result.warm_p99_ms:.2f} "
            f"filtered_p50_ms={result.filtered_p50_ms:.2f} "
            f"filtered_p95_ms={result.filtered_p95_ms:.2f} "
            f"filtered_p99_ms={result.filtered_p99_ms:.2f} "
            f"overlap_k10={result.overlap_k10:.3f} "
            f"precision_at_1={result.precision_at_1:.3f} "
            f"db_size_bytes={result.db_size_bytes} "
            f"gate_overlap_k10={'PASS' if overlap_gate else 'FAIL'}"
        )

        if result.sample_count >= 100_000:
            warm_gate = result.warm_p95_ms <= WARM_P95_GATE_MS
            filtered_gate = result.filtered_p95_ms <= FILTERED_P95_GATE_MS
            print(
                f"  gate_100k_warm_p95={'PASS' if warm_gate else 'FAIL'} "
                f"gate_100k_filtered_p95={'PASS' if filtered_gate else 'FAIL'}"
            )

        if result.precision_at_1 > 0.0:
            print(
                f"  precision_at_1_gate={'PASS' if result.precision_at_1 >= 0.95 else 'FAIL'}"
            )
