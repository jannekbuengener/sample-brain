import json
import math
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Mapping

from sqlalchemy import create_engine, event, text
from pathlib import Path

from . import config
from .content_hash import (
    DEFAULT_CONTENT_HASH_ALGORITHM,
    LEGACY_CONTENT_HASH_ALGORITHM,
    hash_record,
    normalize_hash_record,
)
from .joint_key_profile import SEMITONES as JOINT_KEY_ROOTS
from .key_signature import format_key_signature


KEY_ANALYSIS_V2_SHADOW_CONTRACT_VERSION = 2
KEY_ANALYSIS_V2_SHADOW_MODE_CONTRAST_MIN = 0.30
_KEY_ANALYSIS_V2_ROOT_EVIDENCE_KEYS = frozenset(
    {
        "kind",
        "selected_root",
        "raw_top_score",
        "raw_top_mode",
        "raw_top_mode_authoritative",
    }
)
_KEY_ANALYSIS_V2_MODE_EVIDENCE_KEYS = frozenset(
    {
        "kind",
        "major_third_energy",
        "minor_third_energy",
        "contrast",
        "threshold",
        "mode",
        "root",
        "root_source",
    }
)
_KEY_ANALYSIS_V2_EVIDENCE_QUANTIZATION_HALF_STEP = 0.5e-6
_KEY_ANALYSIS_V2_PEARSON_EPSILON = 1e-12


@dataclass(frozen=True)
class KeyAnalysisV2ShadowRow:
    """Validated, explicitly requested V2-shadow data for one catalog sample."""

    sample_id: int
    source_identity: dict[str, str]
    contract_version: int
    key: str
    key_mode: str | None
    key_root_evidence: dict[str, Any]
    key_mode_evidence: dict[str, Any] | None
    analyzed_at: str


def _enable_sqlite_foreign_keys(dbapi_connection, _connection_record) -> None:
    """Enable SQLite foreign-key enforcement for every DB-API connection."""
    cursor = dbapi_connection.cursor()
    try:
        cursor.execute("PRAGMA foreign_keys=ON")
    finally:
        cursor.close()


def get_engine():
    config.DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    engine = create_engine(f"sqlite:///{config.DB_PATH}", future=True)
    event.listen(engine, "connect", _enable_sqlite_foreign_keys)
    return engine


def init_db():
    engine = get_engine()
    with engine.begin() as conn:
        # samples. hash_algorithm is additive in #417; NULL on a pre-v2 row is
        # explicitly interpreted as the historical SHA-1 catalog contract.
        conn.execute(text("""
        CREATE TABLE IF NOT EXISTS samples (
            id INTEGER PRIMARY KEY,
            path TEXT UNIQUE NOT NULL,
            relpath TEXT,
            samplerate INT,
            channels INT,
            duration REAL,
            size_bytes INT,
            hash TEXT,
            hash_algorithm TEXT
        );
        """))
        sample_cols = conn.execute(text("PRAGMA table_info(samples)")).fetchall()
        sample_col_names = {column[1] for column in sample_cols}
        if "hash_algorithm" not in sample_col_names:
            conn.execute(text("ALTER TABLE samples ADD COLUMN hash_algorithm TEXT"))

        # The V2 key-analysis shadow is deliberately separate from ``features``.
        # V1 remains the normal analyzer and consumer contract until a later,
        # explicitly scoped migration switches readers and writers.
        conn.execute(text("""
        CREATE TABLE IF NOT EXISTS key_analysis_v2_shadow (
            sample_id INTEGER PRIMARY KEY,
            source_hash TEXT NOT NULL,
            source_hash_algorithm TEXT NOT NULL,
            contract_version INTEGER NOT NULL,
            key TEXT,
            key_mode TEXT,
            key_root_evidence TEXT NOT NULL,
            key_mode_evidence TEXT,
            analyzed_at TEXT NOT NULL,
            FOREIGN KEY(sample_id) REFERENCES samples(id)
        );
        """))

        # features (mit pred_type!)
        conn.execute(text("""
        CREATE TABLE IF NOT EXISTS features (
            sample_id INTEGER PRIMARY KEY,
            bpm REAL,
            key TEXT,
            key_conf REAL,
            loudness REAL,
            brightness REAL,
            mfcc_mean BLOB,
            mfcc_std  BLOB,
            chroma_mean BLOB,
            chroma_std  BLOB,
            class TEXT,
            pred_type TEXT,
            quality_note TEXT,
            key_mode TEXT,
            key_mode_evidence TEXT,
            FOREIGN KEY(sample_id) REFERENCES samples(id)
        );
        """))
        feature_cols = conn.execute(text("PRAGMA table_info(features)")).fetchall()
        feature_col_names = {column[1] for column in feature_cols}
        for column_name in ("quality_note", "key_mode", "key_mode_evidence"):
            if column_name not in feature_col_names:
                conn.execute(text(f"ALTER TABLE features ADD COLUMN {column_name} TEXT"))

        # embedding models registry
        conn.execute(text("""
        CREATE TABLE IF NOT EXISTS embedding_models (
            id INTEGER PRIMARY KEY,
            provider TEXT NOT NULL,
            model_name TEXT NOT NULL,
            model_version TEXT,
            embedding_dim INTEGER NOT NULL,
            modality TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(provider, model_name, model_version, modality)
        );
        """))
        # sample embeddings (one per sample per model)
        conn.execute(text("""
        CREATE TABLE IF NOT EXISTS sample_embeddings (
            id INTEGER PRIMARY KEY,
            sample_id INTEGER NOT NULL,
            model_id INTEGER NOT NULL,
            embedding BLOB NOT NULL,
            embedding_format TEXT NOT NULL,
            source_hash TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(sample_id) REFERENCES samples(id),
            FOREIGN KEY(model_id) REFERENCES embedding_models(id),
            UNIQUE(sample_id, model_id, source_hash)
        );
        """))
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_sample_embeddings_sample_id ON sample_embeddings(sample_id);"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_sample_embeddings_model_id ON sample_embeddings(model_id);"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_sample_embeddings_source_hash ON sample_embeddings(source_hash);"))
        conn.execute(text("""
        CREATE TABLE IF NOT EXISTS vector_index_state (
            id INTEGER PRIMARY KEY,
            model_id INTEGER NOT NULL,
            backend TEXT NOT NULL,
            vec_table_name TEXT,
            embedding_dim INTEGER NOT NULL,
            sample_count INTEGER NOT NULL,
            last_rebuild_at TEXT,
            source_fingerprint TEXT,
            FOREIGN KEY(model_id) REFERENCES embedding_models(id),
            UNIQUE(model_id, backend)
        );
        """))
        conn.execute(text("""
        CREATE TABLE IF NOT EXISTS sample_tags (
            id INTEGER PRIMARY KEY,
            sample_id INTEGER NOT NULL,
            tag TEXT NOT NULL,
            source TEXT NOT NULL,
            FOREIGN KEY(sample_id) REFERENCES samples(id),
            UNIQUE(sample_id, tag, source)
        );
        """))
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_sample_tags_sample_id ON sample_tags(sample_id);"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_sample_tags_tag ON sample_tags(tag);"))
    return engine


def _serialize_key_analysis_v2_evidence(evidence: Mapping[str, Any]) -> str:
    return json.dumps(
        dict(evidence), sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    )


def _validated_root_evidence(value: object) -> dict[str, Any] | None:
    if not isinstance(value, dict) or set(value) != _KEY_ANALYSIS_V2_ROOT_EVIDENCE_KEYS:
        return None
    if value.get("kind") != "joint_24_profile_pearson":
        return None
    if value.get("selected_root") not in JOINT_KEY_ROOTS:
        return None
    if value.get("raw_top_mode") not in {"maj", "min"}:
        return None
    if value.get("raw_top_mode_authoritative") is not False:
        return None
    score = value.get("raw_top_score")
    if isinstance(score, bool) or not isinstance(score, (int, float)) or not math.isfinite(score):
        return None
    if not (
        -1.0 - _KEY_ANALYSIS_V2_PEARSON_EPSILON
        <= float(score)
        <= 1.0 + _KEY_ANALYSIS_V2_PEARSON_EPSILON
    ):
        return None
    return dict(value)


def _validated_mode_evidence(value: object, *, root: str, mode: str | None) -> dict[str, Any] | None:
    if not isinstance(value, dict) or set(value) != _KEY_ANALYSIS_V2_MODE_EVIDENCE_KEYS:
        return None
    if value.get("kind") != "third_contrast":
        return None
    if value.get("root") != root or value.get("root_source") != "joint_24_profile_pearson":
        return None
    if value.get("mode") != mode or mode not in {"maj", "min", None}:
        return None
    required_numeric = ("major_third_energy", "minor_third_energy", "contrast", "threshold")
    if any(field not in value for field in required_numeric):
        return None
    for field in required_numeric:
        number = value[field]
        if isinstance(number, bool) or not isinstance(number, (int, float)) or not math.isfinite(number):
            return None
    major_energy = float(value["major_third_energy"])
    minor_energy = float(value["minor_third_energy"])
    contrast = float(value["contrast"])
    threshold = float(value["threshold"])
    if major_energy < 0.0 or minor_energy < 0.0 or contrast < 0.0:
        return None
    if not _third_contrast_matches_quantized_evidence(major_energy, minor_energy, contrast):
        return None
    if threshold != KEY_ANALYSIS_V2_SHADOW_MODE_CONTRAST_MIN:
        return None
    half_step = _KEY_ANALYSIS_V2_EVIDENCE_QUANTIZATION_HALF_STEP
    directional_modes = (
        {"maj", "min"}
        if abs(major_energy - minor_energy) <= 2.0 * half_step
        else {"maj"}
        if major_energy > minor_energy
        else {"min"}
    )
    # ``estimate_key_mode`` decides from unrounded energies but persists its
    # contrast rounded to six decimals.  An abstention whose raw contrast is
    # just below 0.30 can therefore carry 0.300000 evidence; retain that
    # explicit abstention without inventing a new decision threshold.
    expected_modes = (
        {None}
        if contrast < threshold
        else directional_modes
        if contrast > threshold
        else {None, *directional_modes}
    )
    if mode not in expected_modes:
        return None
    return dict(value)


def _third_contrast_matches_quantized_evidence(
    major_energy: float, minor_energy: float, contrast: float
) -> bool:
    """Check whether six-decimal evidence can originate from one raw contrast."""

    half_step = _KEY_ANALYSIS_V2_EVIDENCE_QUANTIZATION_HALF_STEP
    major_bounds = (max(0.0, major_energy - half_step), major_energy + half_step)
    minor_bounds = (max(0.0, minor_energy - half_step), minor_energy + half_step)
    candidates = [
        abs(major - minor) / (major + minor + 1e-9)
        for major in major_bounds
        for minor in minor_bounds
    ]
    if major_bounds[0] <= minor_bounds[1] and minor_bounds[0] <= major_bounds[1]:
        candidates.append(0.0)
    raw_lower, raw_upper = min(candidates), max(candidates)
    stored_lower = max(0.0, contrast - half_step)
    stored_upper = contrast + half_step
    return raw_lower <= stored_upper and stored_lower <= raw_upper


def _validated_utc_timestamp(value: object) -> str | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    if parsed.tzinfo is None or parsed.utcoffset() != timedelta(0):
        return None
    return value


def _read_json_object(value: object) -> dict[str, Any] | None:
    if not isinstance(value, str):
        return None
    try:
        decoded = json.loads(value)
    except (TypeError, ValueError, json.JSONDecodeError):
        return None
    return decoded if isinstance(decoded, dict) else None


def write_key_analysis_v2_shadow_row(
    *,
    sample_id: int,
    source_identity: object,
    key: str,
    key_mode: str | None,
    key_root_evidence: Mapping[str, Any],
    key_mode_evidence: Mapping[str, Any] | None,
    contract_version: int = KEY_ANALYSIS_V2_SHADOW_CONTRACT_VERSION,
    analyzed_at: str | None = None,
) -> None:
    """Atomically upsert one explicit V2-shadow row without touching ``features``."""

    identity = normalize_hash_record(source_identity)
    root_evidence = _validated_root_evidence(dict(key_root_evidence))
    if root_evidence is None:
        raise ValueError("invalid V2 key root evidence")
    if contract_version != KEY_ANALYSIS_V2_SHADOW_CONTRACT_VERSION:
        raise ValueError("unsupported V2 shadow contract version")
    if key_mode not in {"maj", "min", None}:
        raise ValueError("invalid V2 key mode")
    if not isinstance(key, str) or not key:
        raise ValueError("V2 shadow key must be a non-empty canonical string")
    mode_evidence = _validated_mode_evidence(
        dict(key_mode_evidence) if key_mode_evidence is not None else None,
        root=root_evidence["selected_root"],
        mode=key_mode,
    )
    if mode_evidence is None:
        raise ValueError("invalid V2 key mode evidence")
    if key != format_key_signature(root_evidence["selected_root"], key_mode):
        raise ValueError("V2 shadow key does not match root and mode evidence")
    timestamp_value = datetime.now(timezone.utc).isoformat() if analyzed_at is None else analyzed_at
    timestamp = _validated_utc_timestamp(timestamp_value)
    if timestamp is None:
        raise ValueError("analyzed_at must be an explicit UTC timestamp string")

    engine = get_engine()
    with engine.begin() as conn:
        sample = conn.execute(
            text("SELECT hash, hash_algorithm FROM samples WHERE id = :sample_id"),
            {"sample_id": sample_id},
        ).fetchone()
        if sample is None:
            raise ValueError("sample does not exist")
        try:
            catalog_identity = hash_record(
                sample[1] or LEGACY_CONTENT_HASH_ALGORITHM,
                sample[0],
            )
        except (TypeError, ValueError):
            raise ValueError("sample has no valid content identity") from None
        if catalog_identity != identity:
            raise ValueError("source identity does not match sample")
        conn.execute(
            text("""
            INSERT INTO key_analysis_v2_shadow (
                sample_id, source_hash, source_hash_algorithm, contract_version,
                key, key_mode, key_root_evidence, key_mode_evidence, analyzed_at
            ) VALUES (
                :sample_id, :source_hash, :source_hash_algorithm, :contract_version,
                :key, :key_mode, :key_root_evidence, :key_mode_evidence, :analyzed_at
            )
            ON CONFLICT(sample_id) DO UPDATE SET
                source_hash=excluded.source_hash,
                source_hash_algorithm=excluded.source_hash_algorithm,
                contract_version=excluded.contract_version,
                key=excluded.key,
                key_mode=excluded.key_mode,
                key_root_evidence=excluded.key_root_evidence,
                key_mode_evidence=excluded.key_mode_evidence,
                analyzed_at=excluded.analyzed_at
            """),
            {
                "sample_id": sample_id,
                "source_hash": identity["value"],
                "source_hash_algorithm": identity["algorithm"],
                "contract_version": contract_version,
                "key": key,
                "key_mode": key_mode,
                "key_root_evidence": _serialize_key_analysis_v2_evidence(root_evidence),
                "key_mode_evidence": _serialize_key_analysis_v2_evidence(mode_evidence),
                "analyzed_at": timestamp,
            },
        )


def read_key_analysis_v2_shadow_row(
    *, sample_id: int, source_identity: object
) -> KeyAnalysisV2ShadowRow | None:
    """Return a validated V2-shadow hit only for the exact source identity."""

    identity = normalize_hash_record(source_identity)
    engine = get_engine()
    with engine.begin() as conn:
        row = conn.execute(
            text("""
            SELECT sample_id, source_hash, source_hash_algorithm, contract_version,
                   key, key_mode, key_root_evidence, key_mode_evidence, analyzed_at
            FROM key_analysis_v2_shadow
            WHERE sample_id = :sample_id
              AND source_hash = :source_hash
              AND source_hash_algorithm = :source_hash_algorithm
              AND contract_version = :contract_version
            """),
            {
                "sample_id": sample_id,
                "source_hash": identity["value"],
                "source_hash_algorithm": identity["algorithm"],
                "contract_version": KEY_ANALYSIS_V2_SHADOW_CONTRACT_VERSION,
            },
        ).fetchone()
    if row is None:
        return None

    try:
        stored_identity = hash_record(row[2], row[1])
    except (TypeError, ValueError):
        return None
    root_evidence = _validated_root_evidence(_read_json_object(row[6]))
    key_mode = row[5]
    if key_mode not in {"maj", "min", None} or root_evidence is None:
        return None
    mode_evidence = _validated_mode_evidence(
        _read_json_object(row[7]), root=root_evidence["selected_root"], mode=key_mode
    )
    if mode_evidence is None or not isinstance(row[4], str) or not row[4]:
        return None
    if row[4] != format_key_signature(root_evidence["selected_root"], key_mode):
        return None
    timestamp = _validated_utc_timestamp(row[8])
    if timestamp is None:
        return None
    return KeyAnalysisV2ShadowRow(
        sample_id=int(row[0]),
        source_identity=stored_identity,
        contract_version=int(row[3]),
        key=row[4],
        key_mode=key_mode,
        key_root_evidence=root_evidence,
        key_mode_evidence=mode_evidence,
        analyzed_at=timestamp,
    )


def upsert_embedding_model(
    provider: str,
    model_name: str,
    model_version: str | None,
    embedding_dim: int,
    modality: str,
) -> int:
    engine = get_engine()
    with engine.begin() as conn:
        conn.execute(
            text("""
            INSERT OR IGNORE INTO embedding_models
                (provider, model_name, model_version, embedding_dim, modality)
            VALUES (:provider, :model_name, :model_version, :embedding_dim, :modality)
            """),
            {
                "provider": provider,
                "model_name": model_name,
                "model_version": model_version,
                "embedding_dim": embedding_dim,
                "modality": modality,
            },
        )
        row = conn.execute(
            text("""
            SELECT id FROM embedding_models
            WHERE provider = :provider
              AND model_name = :model_name
              AND (model_version = :model_version OR (model_version IS NULL AND :model_version IS NULL))
              AND modality = :modality
            """),
            {
                "provider": provider,
                "model_name": model_name,
                "model_version": model_version,
                "modality": modality,
            },
        ).fetchone()
    return row[0]


def get_embedding_model(
    provider: str,
    model_name: str,
    model_version: str | None,
    modality: str,
) -> dict | None:
    engine = get_engine()
    with engine.begin() as conn:
        row = conn.execute(
            text("""
            SELECT id, provider, model_name, model_version, embedding_dim, modality, created_at
            FROM embedding_models
            WHERE provider = :provider
              AND model_name = :model_name
              AND (model_version = :model_version OR (model_version IS NULL AND :model_version IS NULL))
              AND modality = :modality
            """),
            {
                "provider": provider,
                "model_name": model_name,
                "model_version": model_version,
                "modality": modality,
            },
        ).fetchone()
    if row is None:
        return None
    return {
        "id": row[0],
        "provider": row[1],
        "model_name": row[2],
        "model_version": row[3],
        "embedding_dim": row[4],
        "modality": row[5],
        "created_at": row[6],
    }


def get_embedding_model_by_id(model_id: int) -> dict | None:
    engine = get_engine()
    with engine.begin() as conn:
        row = conn.execute(
            text("""
            SELECT id, provider, model_name, model_version, embedding_dim, modality, created_at
            FROM embedding_models
            WHERE id = :model_id
            """),
            {"model_id": model_id},
        ).fetchone()
    if row is None:
        return None
    return {
        "id": row[0],
        "provider": row[1],
        "model_name": row[2],
        "model_version": row[3],
        "embedding_dim": row[4],
        "modality": row[5],
        "created_at": row[6],
    }


def insert_sample_embedding(
    sample_id: int,
    model_id: int,
    embedding: bytes,
    embedding_format: str,
    source_hash: str,
) -> int:
    engine = get_engine()
    with engine.begin() as conn:
        conn.execute(
            text("""
            INSERT OR IGNORE INTO sample_embeddings
                (sample_id, model_id, embedding, embedding_format, source_hash)
            VALUES (:sample_id, :model_id, :embedding, :embedding_format, :source_hash)
            """),
            {
                "sample_id": sample_id,
                "model_id": model_id,
                "embedding": embedding,
                "embedding_format": embedding_format,
                "source_hash": source_hash,
            },
        )
        row = conn.execute(
            text("""
            SELECT id FROM sample_embeddings
            WHERE sample_id = :sample_id
              AND model_id = :model_id
              AND source_hash = :source_hash
            """),
            {
                "sample_id": sample_id,
                "model_id": model_id,
                "source_hash": source_hash,
            },
        ).fetchone()
    return row[0]


def iter_pending_samples(model_id: int, limit: int | None = None) -> list[tuple[int, str, str]]:
    if limit is not None and limit <= 0:
        return []
    engine = get_engine()
    query = """
        SELECT s.id, s.path, s.hash
        FROM samples s
        WHERE s.hash IS NOT NULL
          AND NOT EXISTS (
              SELECT 1
              FROM sample_embeddings e
              WHERE e.sample_id = s.id
                AND e.model_id = :model_id
                AND e.source_hash = s.hash
          )
        ORDER BY s.id
    """
    if limit is not None:
        query += "\n        LIMIT :limit"
    with engine.begin() as conn:
        params: dict = {"model_id": model_id}
        if limit is not None:
            params["limit"] = limit
        rows = conn.execute(text(query), params).fetchall()
    return [(row[0], row[1], row[2]) for row in rows]


def sample_embedding_exists(sample_id: int, model_id: int, source_hash: str) -> bool:
    engine = get_engine()
    with engine.begin() as conn:
        row = conn.execute(
            text("""
            SELECT 1 FROM sample_embeddings
            WHERE sample_id = :sample_id
              AND model_id = :model_id
              AND source_hash = :source_hash
            """),
            {
                "sample_id": sample_id,
                "model_id": model_id,
                "source_hash": source_hash,
            },
        ).fetchone()
    return row is not None


def upsert_vector_index_state(
    model_id: int,
    backend: str,
    embedding_dim: int,
    sample_count: int,
    *,
    vec_table_name: str | None = None,
    last_rebuild_at: str | None = None,
    source_fingerprint: str | None = None,
) -> None:
    engine = get_engine()
    with engine.begin() as conn:
        conn.execute(
            text("""
            INSERT INTO vector_index_state (
                model_id, backend, vec_table_name, embedding_dim, sample_count,
                last_rebuild_at, source_fingerprint
            ) VALUES (
                :model_id, :backend, :vec_table_name, :embedding_dim, :sample_count,
                :last_rebuild_at, :source_fingerprint
            )
            ON CONFLICT(model_id, backend) DO UPDATE SET
                vec_table_name = excluded.vec_table_name,
                embedding_dim = excluded.embedding_dim,
                sample_count = excluded.sample_count,
                last_rebuild_at = excluded.last_rebuild_at,
                source_fingerprint = excluded.source_fingerprint
            """),
            {
                "model_id": model_id,
                "backend": backend,
                "vec_table_name": vec_table_name,
                "embedding_dim": embedding_dim,
                "sample_count": sample_count,
                "last_rebuild_at": last_rebuild_at,
                "source_fingerprint": source_fingerprint,
            },
        )


def get_vector_index_state(model_id: int, backend: str) -> dict | None:
    engine = get_engine()
    with engine.begin() as conn:
        row = conn.execute(
            text("""
            SELECT id, model_id, backend, vec_table_name, embedding_dim, sample_count,
                   last_rebuild_at, source_fingerprint
            FROM vector_index_state
            WHERE model_id = :model_id AND backend = :backend
            """),
            {"model_id": model_id, "backend": backend},
        ).fetchone()
    if row is None:
        return None
    return {
        "id": row[0],
        "model_id": row[1],
        "backend": row[2],
        "vec_table_name": row[3],
        "embedding_dim": row[4],
        "sample_count": row[5],
        "last_rebuild_at": row[6],
        "source_fingerprint": row[7],
    }


def replace_sample_tags(sample_id: int, tags: list[tuple[str, str]]) -> None:
    engine = get_engine()
    with engine.begin() as conn:
        conn.execute(
            text("DELETE FROM sample_tags WHERE sample_id = :sample_id"),
            {"sample_id": sample_id},
        )
        for tag, source in tags:
            conn.execute(
                text("""
                INSERT OR IGNORE INTO sample_tags (sample_id, tag, source)
                VALUES (:sample_id, :tag, :source)
                """),
                {"sample_id": sample_id, "tag": tag, "source": source},
            )


def list_sample_tags(sample_id: int | None = None) -> list[dict]:
    engine = get_engine()
    query = """
        SELECT id, sample_id, tag, source
        FROM sample_tags
    """
    params: dict = {}
    if sample_id is not None:
        query += " WHERE sample_id = :sample_id"
        params["sample_id"] = sample_id
    query += " ORDER BY sample_id, tag, source"
    with engine.begin() as conn:
        rows = conn.execute(text(query), params).fetchall()
    return [
        {"id": row[0], "sample_id": row[1], "tag": row[2], "source": row[3]}
        for row in rows
    ]


def upsert_sample_tag(sample_id: int, tag: str, source: str) -> None:
    """Add a sample tag idempotently (INSERT OR IGNORE on the unique triplet)."""
    engine = get_engine()
    with engine.begin() as conn:
        conn.execute(
            text("""
            INSERT OR IGNORE INTO sample_tags (sample_id, tag, source)
            VALUES (:sample_id, :tag, :source)
            """),
            {"sample_id": sample_id, "tag": tag, "source": source},
        )


def find_sample_by_path(path: str) -> tuple[int, str] | None:
    """Backward-compatible return of ``(id, bare_hash_value)``."""
    engine = get_engine()
    with engine.begin() as conn:
        row = conn.execute(
            text("SELECT id, hash FROM samples WHERE path = :path"),
            {"path": str(path)},
        ).fetchone()
    if row is None:
        return None
    return int(row[0]), row[1]


def find_sample_identity_by_path(path: str) -> tuple[int, dict[str, str]] | None:
    """Return an algorithm-qualified catalog content identity.

    ``NULL`` algorithm is the explicit legacy pre-#417 catalog state and is
    therefore interpreted as SHA-1 without mutating or rehashing the row.
    """
    engine = get_engine()
    with engine.begin() as conn:
        row = conn.execute(
            text("SELECT id, hash, hash_algorithm FROM samples WHERE path = :path"),
            {"path": str(path)},
        ).fetchone()
    if row is None or row[1] is None:
        return None
    algorithm = row[2] or LEGACY_CONTENT_HASH_ALGORITHM
    return int(row[0]), hash_record(algorithm, row[1])


def find_sample_id_by_hash(
    content_hash: str,
    *,
    hash_algorithm: str | None = None,
) -> int | None:
    """Return the smallest sample id sharing an algorithm-qualified identity.

    Callers that omit ``hash_algorithm`` retain the historical value-only lookup.
    New provenance/dedupe paths must pass the algorithm explicitly.
    """
    engine = get_engine()
    with engine.begin() as conn:
        if hash_algorithm is None:
            row = conn.execute(
                text("SELECT id FROM samples WHERE hash = :h ORDER BY id ASC LIMIT 1"),
                {"h": content_hash},
            ).fetchone()
        else:
            row = conn.execute(
                text("""
                    SELECT id FROM samples
                    WHERE hash = :h
                      AND COALESCE(hash_algorithm, :legacy) = :algorithm
                    ORDER BY id ASC
                    LIMIT 1
                """),
                {
                    "h": content_hash,
                    "algorithm": hash_algorithm,
                    "legacy": LEGACY_CONTENT_HASH_ALGORITHM,
                },
            ).fetchone()
    if row is None:
        return None
    return int(row[0])


def insert_sample(
    path: str,
    relpath: str | None,
    samplerate: int | None,
    channels: int | None,
    duration: float | None,
    size_bytes: int,
    content_hash: str,
    content_hash_algorithm: str = DEFAULT_CONTENT_HASH_ALGORITHM,
) -> int:
    """Insert a new sample row (plain INSERT; path is UNIQUE)."""
    identity = hash_record(content_hash_algorithm, content_hash)
    engine = get_engine()
    with engine.begin() as conn:
        conn.execute(
            text("""
            INSERT INTO samples (
                path, relpath, samplerate, channels, duration, size_bytes, hash,
                hash_algorithm
            )
            VALUES (
                :path, :relpath, :sr, :ch, :dur, :size_bytes, :hash,
                :hash_algorithm
            )
            """),
            dict(
                path=str(path),
                relpath=relpath,
                sr=samplerate,
                ch=channels,
                dur=duration,
                size_bytes=size_bytes,
                hash=identity["value"],
                hash_algorithm=identity["algorithm"],
            ),
        )
        row = conn.execute(
            text("SELECT id FROM samples WHERE path = :path"),
            {"path": str(path)},
        ).fetchone()
    return int(row[0])


def load_sample_paths(sample_ids: list[int]) -> dict[int, str]:
    if not sample_ids:
        return {}

    engine = get_engine()
    placeholders = ", ".join(f":id_{index}" for index in range(len(sample_ids)))
    params = {f"id_{index}": sample_id for index, sample_id in enumerate(sample_ids)}
    query = f"""
        SELECT id, path
        FROM samples
        WHERE id IN ({placeholders})
    """
    with engine.begin() as conn:
        rows = conn.execute(text(query), params).fetchall()

    return {row[0]: row[1] for row in rows}


def ensure_features_pred_type_column() -> None:
    engine = get_engine()
    with engine.begin() as conn:
        cols = conn.execute(text("PRAGMA table_info(features)")).fetchall()
        names = {column[1] for column in cols}
        if "pred_type" not in names:
            conn.execute(text("ALTER TABLE features ADD COLUMN pred_type TEXT"))


def load_hybrid_metadata(sample_ids: list[int]) -> dict[int, "HybridMetadata"]:
    from .hybrid_rank import HybridMetadata

    if not sample_ids:
        return {}

    ensure_features_pred_type_column()
    engine = get_engine()
    placeholders = ", ".join(f":id_{index}" for index in range(len(sample_ids)))
    params = {f"id_{index}": sample_id for index, sample_id in enumerate(sample_ids)}
    query = f"""
        SELECT sample_id, bpm, key, pred_type, class
        FROM features
        WHERE sample_id IN ({placeholders})
    """
    with engine.begin() as conn:
        rows = conn.execute(text(query), params).fetchall()

    return {
        row[0]: HybridMetadata(
            sample_id=row[0],
            bpm=row[1],
            key=row[2],
            pred_type=row[3],
            audio_class=row[4],
        )
        for row in rows
    }
