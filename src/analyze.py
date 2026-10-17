"""Sample Brain application adapter for catalog-backed feature analysis."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import text
from tqdm import tqdm

from . import feature_analysis as _feature_analysis
from .analysis_contracts import ANALYZE_HOP_LENGTH, ANALYZE_SR, Features
from .db import init_db
from .feature_analysis import (
    KEY_ANALYSIS_CONTRACT_VERSION,
    MODE_CONTRAST_MIN,
    SHORT_AUDIO_DURATION_SEC,
    SHORT_AUDIO_QUALITY_NOTE,
    SHORT_AUDIO_WARNING_CODE,
    _bpm_in_domain_110_170,
    _chroma_mean,
    _duration_class,
    _effective_n_fft,
    _extract_bpm_scalar,
    _is_short_clip,
    _rms_dbfs,
    _serialize_key_mode_evidence,
    _suppress_known_short_audio_librosa_warnings,
    estimate_key,
    estimate_key_mode,
    normalize_bpm,
    safe_load,
)


def extract_features(
    path: Path, duration: float | None, bpm_normalization: str = "none"
) -> Features | None:
    """Legacy-compatible facade over DB-free feature computation.

    The loader is resolved from this module at call time so existing callers that
    monkeypatch ``src.analyze.safe_load`` keep their historical behavior.
    """

    return _feature_analysis._extract_features_with_loader(
        path,
        duration,
        bpm_normalization,
        load_audio=safe_load,
    )


# V1 upsert owns key-analysis provenance (#688): always clear leftover V2
# markers. NULL contract/root-evidence means legacy/V1 (no backfill to 1).
_FEATURE_UPSERT = text(
    """
    INSERT INTO features (
        sample_id, bpm, key, key_conf, loudness, brightness,
        mfcc_mean, mfcc_std, chroma_mean, chroma_std, "class",
        quality_note, key_mode, key_mode_evidence,
        key_analysis_contract_version, key_root_evidence
    ) VALUES (
        :sample_id, :bpm, :key, :key_conf, :loudness, :brightness,
        :mfcc_mean, :mfcc_std, :chroma_mean, :chroma_std, :clazz,
        :quality_note, :key_mode, :key_mode_evidence,
        NULL, NULL
    )
    ON CONFLICT(sample_id) DO UPDATE SET
        bpm=excluded.bpm,
        key=excluded.key,
        key_conf=excluded.key_conf,
        loudness=excluded.loudness,
        brightness=excluded.brightness,
        mfcc_mean=excluded.mfcc_mean,
        mfcc_std=excluded.mfcc_std,
        chroma_mean=excluded.chroma_mean,
        chroma_std=excluded.chroma_std,
        "class"=excluded."class",
        quality_note=excluded.quality_note,
        key_mode=excluded.key_mode,
        key_mode_evidence=excluded.key_mode_evidence,
        key_analysis_contract_version=NULL,
        key_root_evidence=NULL
    """
)


def _load_analyze_batch(
    engine,
    *,
    last_id: int,
    batch_size: int,
    only_missing: bool,
) -> list[tuple]:
    missing_clause = "AND f.sample_id IS NULL" if only_missing else ""
    query = text(
        f"""
        SELECT s.id, s.path, s.duration, f.sample_id AS has_features
        FROM samples s
        LEFT JOIN features f ON f.sample_id = s.id
        WHERE s.id > :last_id
          {missing_clause}
        ORDER BY s.id
        LIMIT :batch_size
        """
    )
    with engine.connect() as conn:
        return conn.execute(
            query,
            {"last_id": int(last_id), "batch_size": int(batch_size)},
        ).fetchall()


def _flush_feature_batch(engine, rows: list[dict]) -> None:
    if not rows:
        return
    with engine.begin() as conn:
        conn.execute(_FEATURE_UPSERT, rows)


@dataclass(frozen=True)
class AnalyzeRunSummary:
    """Boundary counts for Measurement Contract v1 (ADR-0006).

    ``items_skip`` is reserved for future observed skips. In this slice the
    SQL ``only_missing`` filter excludes already-analyzed rows before the loop,
    so skip counts are not observed here and remain ``0``.
    """

    items_ok: int
    items_skip: int
    items_fail: int


def run_analyze(
    limit: int | None = None,
    only_missing: bool = True,
    bpm_normalization: str = "none",
    batch_size: int = 100,
) -> AnalyzeRunSummary:
    """Compute features for samples in bounded batches.

    Safe by default:
    - reads sample paths from DB (does not scan filesystem roots)
    - skips rows that already have a features row in SQL when only_missing=True
    - performs expensive audio analysis outside DB write transactions
    - keeps catalog reads bounded by primary-key pages
    """
    if batch_size <= 0:
        raise ValueError("batch_size must be positive")

    engine = init_db()
    processed = 0
    items_fail = 0
    last_id = 0
    done = False

    with tqdm(desc="Analyzing", unit="file") as bar:
        while not done:
            rows = _load_analyze_batch(
                engine,
                last_id=last_id,
                batch_size=batch_size,
                only_missing=only_missing,
            )
            if not rows:
                break

            last_id = int(rows[-1][0])
            writes: list[dict] = []

            for sid, path_str, duration, _has_features in rows:
                bar.update(1)
                feats = extract_features(
                    Path(path_str),
                    duration,
                    bpm_normalization=bpm_normalization,
                )
                if feats is None:
                    items_fail += 1
                    continue

                writes.append(
                    dict(
                        sample_id=int(sid),
                        bpm=feats.bpm,
                        key=feats.key,
                        key_conf=feats.key_conf,
                        loudness=feats.loudness,
                        brightness=feats.brightness,
                        mfcc_mean=feats.mfcc_mean,
                        mfcc_std=feats.mfcc_std,
                        chroma_mean=feats.chroma_mean,
                        chroma_std=feats.chroma_std,
                        clazz=feats.clazz,
                        quality_note=feats.quality_note,
                        key_mode=feats.key_mode,
                        key_mode_evidence=_serialize_key_mode_evidence(feats.key_mode_evidence),
                    )
                )
                processed += 1
                if limit is not None and processed >= int(limit):
                    done = True
                    break

            _flush_feature_batch(engine, writes)

    return AnalyzeRunSummary(
        items_ok=processed,
        items_skip=0,
        items_fail=items_fail,
    )



__all__ = [
    "SHORT_AUDIO_DURATION_SEC",
    "SHORT_AUDIO_QUALITY_NOTE",
    "SHORT_AUDIO_WARNING_CODE",
    "KEY_ANALYSIS_CONTRACT_VERSION",
    "MODE_CONTRAST_MIN",
    "AnalyzeRunSummary",
    "run_analyze",
    "extract_features",
    "safe_load",
    "estimate_key",
    "estimate_key_mode",
]
