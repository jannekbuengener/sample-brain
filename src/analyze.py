from pathlib import Path
import numpy as np
import soundfile as sf
import librosa
from sqlalchemy import text, select
from tqdm import tqdm

from .db import init_db
from .config import DATA_DIR

# --- helpers ---
SEMITONES = ['C','C#','D','D#','E','F','F#','G','G#','A','A#','B']

def estimate_key(y, sr):
    # Chroma + Krumhansl-Schmuckler Template
    chroma = librosa.feature.chroma_cqt(y=y, sr=sr)
    chroma_mean = chroma.mean(axis=1)
    # Major/Minor key profiles
    maj = np.array([6.35,2.23,3.48,2.33,4.38,4.09,2.52,5.19,2.39,3.66,2.29,2.88])
    min_ = np.array([6.33,2.68,3.52,5.38,2.60,3.53,2.54,4.75,3.98,2.69,3.34,3.17])
    scores_maj = [np.correlate(chroma_mean, np.roll(maj, i))[0] for i in range(12)]
    scores_min = [np.correlate(chroma_mean, np.roll(min_, i))[0] for i in range(12)]
    i_maj = int(np.argmax(scores_maj)); i_min = int(np.argmax(scores_min))
    if scores_maj[i_maj] >= scores_min[i_min]:
        return f"{SEMITONES[i_maj]}", float(scores_maj[i_maj] / (np.sum(chroma_mean)+1e-9)), chroma
    else:
        return f"{SEMITONES[i_min]}m", float(scores_min[i_min] / (np.sum(chroma_mean)+1e-9)), chroma

def safe_load(path: Path, target_sr=44100):
    try:
        y, sr = librosa.load(path, sr=target_sr, mono=True)
        return y, sr
    except Exception:
        return None, None

def extract_features(path: Path):
    y, sr = safe_load(path)
    if y is None:
        return None
    # loudness (RMS dB)
    rms = librosa.feature.rms(y=y).flatten()
    loudness = float(np.mean(20*np.log10(np.maximum(rms, 1e-6))))
    # brightness (spectral centroid)
    centroid = librosa.feature.spectral_centroid(y=y, sr=sr).flatten()
    brightness = float(np.mean(centroid))
    # tempo (BPM)
    tempo, _ = librosa.beat.beat_track(y=y, sr=sr)
    bpm = float(tempo) if tempo is not None else None
    # key + chroma
    key, key_conf, chroma = estimate_key(y, sr)
    # mfcc
    mfcc = librosa.feature.mfcc(y=y, sr=sr, n_mfcc=13)
    mfcc_mean = mfcc.mean(axis=1).astype(np.float32)
    mfcc_std  = mfcc.std(axis=1).astype(np.float32)
    chroma_mean = chroma.mean(axis=1).astype(np.float32)
    chroma_std  = chroma.std(axis=1).astype(np.float32)
    # simple class heuristic
    duration = len(y)/sr
    clazz = "oneshot" if duration < 1.2 and np.mean(rms) > 0.02 else "loop"
    return dict(
        bpm=bpm, key=key, key_conf=key_conf, loudness=loudness, brightness=brightness,
        mfcc_mean=mfcc_mean.tobytes(), mfcc_std=mfcc_std.tobytes(),
        chroma_mean=chroma_mean.tobytes(), chroma_std=chroma_std.tobytes(),
        clazz=clazz
    )

def run_analyze(limit: int | None = None, only_missing: bool = True):
    engine = init_db()
    with engine.begin() as conn:
        # select targets
        if only_missing:
            rows = conn.execute(text("""                SELECT s.id, s.path FROM samples s
                LEFT JOIN features f ON f.sample_id = s.id
                WHERE f.sample_id IS NULL
                ORDER BY s.id
                LIMIT :lim
            """), dict(lim=limit or -1)).fetchall()
        else:
            rows = conn.execute(text("SELECT id, path FROM samples ORDER BY id LIMIT :lim"), dict(lim=limit or -1)).fetchall()

        for sid, spath in tqdm(rows, desc="Analyze (librosa)"):
            feats = extract_features(Path(spath))
            if feats is None:
                continue
            conn.execute(text("""                INSERT INTO features (sample_id, bpm, key, key_conf, loudness, brightness,
                                      mfcc_mean, mfcc_std, chroma_mean, chroma_std, class)
                VALUES (:sid, :bpm, :key, :key_conf, :loudness, :brightness,
                        :mfcc_mean, :mfcc_std, :chroma_mean, :chroma_std, :clazz)
                ON CONFLICT(sample_id) DO UPDATE SET
                    bpm=excluded.bpm, key=excluded.key, key_conf=excluded.key_conf,
                    loudness=excluded.loudness, brightness=excluded.brightness,
                    mfcc_mean=excluded.mfcc_mean, mfcc_std=excluded.mfcc_std,
                    chroma_mean=excluded.chroma_mean, chroma_std=excluded.chroma_std,
                    class=excluded.class
            """), dict(sid=sid, **feats))
