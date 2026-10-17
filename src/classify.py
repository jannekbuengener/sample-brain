# src/classify.py
"""Application adapter for catalog-backed sample autotyping."""

from __future__ import annotations

import csv
from pathlib import Path

import numpy as np
from sqlalchemy import text

from .classification import (
    _RULE_BRIGHT_MIN,
    _RULE_DARK_MAX,
    _RULE_LONG_MIN_SEC,
    _RULE_MID_MAX_SEC,
    _RULE_PUNCHY_MIN_LOUDNESS,
    _RULE_SHORT_MAX_SEC,
    _knn_predict,
    _sigmoid,
    rule_type,
)
from .db import ensure_features_pred_type_column, init_db

SEED_CSV = Path("./data/label_seeds.csv")

def _load_seed_vectors():
    # Lazy import, um Abhängigkeit auf .index nur bei Bedarf zu haben
    try:
        from .index import load_embeddings  # optional
    except Exception:
        return None, None
    if not SEED_CSV.exists():
        return None, None
    ids, vecs = load_embeddings()
    if ids is None or vecs is None:
        return None, None
    id2vec = {i: v/(np.linalg.norm(v)+1e-9) for i, v in zip(ids, vecs)}

    X, y = [], []
    engine = init_db()
    with open(SEED_CSV, newline='', encoding="utf-8") as f:
        for path, label in csv.reader(f):
            with engine.begin() as conn:
                r = conn.execute(text("SELECT id FROM samples WHERE path=:p"), dict(p=path)).fetchone()
            if r and r[0] in id2vec:
                X.append(id2vec[r[0]]); y.append(label)
    if not X:
        return None, None
    return np.vstack(X).astype(np.float32), np.array(y, dtype=object)

# ---------- Main ----------
def write_autotype_to_db(use_knn: bool = True, knn_min_conf: float = 0.55):
    init_db()
    ensure_features_pred_type_column()

    # Seeds/Embeddings nur laden, wenn kNN wirklich genutzt wird
    X = y = None
    if use_knn:
        X, y = _load_seed_vectors()

    # Audio-Features lesen
    engine = init_db()
    with engine.begin() as conn:
        rows = conn.execute(text("""
            SELECT s.id, s.path, s.duration, f.loudness, f.brightness, f.mfcc_mean, f.class
            FROM samples s
            LEFT JOIN features f ON f.sample_id = s.id
            ORDER BY s.id
        """)).fetchall()

    # Embeddings (für kNN) nur bei Bedarf nachladen
    id2vec = {}
    if use_knn:
        try:
            from .index import load_embeddings  # optional
            ids, vecs = load_embeddings()
            if ids is not None:
                for i, v in zip(ids, vecs):
                    id2vec[i] = v/(np.linalg.norm(v)+1e-9)
        except Exception:
            X = y = None  # kNN deaktivieren, falls Import fehlschlägt

    with engine.begin() as conn:
        for sid, path, dur, loud, bright, mfcc, clazz in rows:
            tags = rule_type(dur, loud, bright, mfcc, clazz)
            pred = tags[0] if tags else None

            if use_knn and X is not None and sid in id2vec:
                knn = _knn_predict(id2vec[sid], X, y, topk=7)
                if knn and knn["confidence"] >= knn_min_conf:
                    pred = knn["label"]

            if pred:
                conn.execute(text("UPDATE features SET pred_type=:p WHERE sample_id=:sid"),
                             dict(p=pred, sid=sid))
