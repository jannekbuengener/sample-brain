# src/classify.py
from __future__ import annotations
import csv, math
from pathlib import Path
import numpy as np
from sqlalchemy import text
from .db import init_db

SEED_CSV = Path("./data/label_seeds.csv")

def _sigmoid(x: float) -> float:
    return 1.0 / (1.0 + math.exp(-x))

# ---------- Regelbasierte Autotypisierung ----------
def rule_type(duration, loudness, brightness, mfcc_mean_blob, clazz) -> list[str]:
    tags: list[str] = []
    mfcc = None
    if mfcc_mean_blob:
        try: mfcc = np.frombuffer(mfcc_mean_blob, dtype=np.float32)
        except Exception: mfcc = None

    is_short  = (duration is not None and duration < 0.35)
    is_mid    = (duration is not None and 0.35 <= duration <= 1.2)
    is_long   = (duration is not None and duration > 2.5)
    is_bright = (brightness is not None and brightness > 4500)
    is_dark   = (brightness is not None and brightness < 1500)
    is_punchy = (loudness  is not None and loudness  > -18)
    low_energy = (mfcc is not None and mfcc.shape[0] >= 2 and mfcc[1] > 0.0)

    if clazz == "oneshot":
        if is_short and is_dark and is_punchy and low_energy: tags.append("Kick")
        elif is_short and is_bright and is_punchy:            tags.append("HiHat-Closed")
        elif is_mid and (is_bright or is_punchy):             tags.append("Snare")
        elif is_long and is_dark and not is_bright:           tags.append("Drone")
        elif is_long and is_bright:                           tags.append("Impact")
        else:                                                 tags.append("OneShot")
    else:
        if is_bright and not is_long: tags.append("Drum Loop")
        elif is_long and is_dark:     tags.append("Drone")
        else:                          tags.append("Loop")

    if is_bright: tags.append("Bright")
    if is_dark:   tags.append("Dark")
    if is_punchy: tags.append("Punchy")
    if is_long and "Drone" not in tags: tags.append("Atmospheric")

    core: list[str] = []
    for t in ("Kick","Snare","HiHat-Closed","Impact","Drone","Pad","Loop","OneShot","Drum Loop"):
        if t in tags: core.append(t)
    if not core:
        core = ["FX"] if (clazz == "oneshot") else ["Loop"]
    for t in ("Bright","Dark","Punchy","Atmospheric"):
        if t in tags and len(core) < 5: core.append(t)
    return core

# ---------- kNN (optional; nur importieren, wenn wirklich gebraucht) ----------
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

def _knn_predict(qvec: np.ndarray, X: np.ndarray, y: np.ndarray, topk=7):
    q = qvec.astype(np.float32); q /= (np.linalg.norm(q)+1e-9)
    sims = X @ q
    idx = np.argsort(-sims)[:topk]
    labs = y[idx]; scs = sims[idx]
    from collections import defaultdict
    agg = defaultdict(float)
    for L,S in zip(labs, scs): agg[L] += float(max(0.0, S))
    best = sorted(agg.items(), key=lambda x: -x[1])
    scores = np.array([s for _,s in best], dtype=np.float32)
    conf = float(_sigmoid(scores[0])) if scores.size else 0.0
    return dict(label=best[0][0], confidence=conf)

# ---------- Main ----------
def _ensure_pred_type_column():
    engine = init_db()
    with engine.begin() as conn:
        cols = conn.execute(text("PRAGMA table_info(features)")).fetchall()
        names = {c[1] for c in cols}
        if "pred_type" not in names:
            conn.execute(text("ALTER TABLE features ADD COLUMN pred_type TEXT"))

def write_autotype_to_db(use_knn: bool = True, knn_min_conf: float = 0.55):
    _ensure_pred_type_column()

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
