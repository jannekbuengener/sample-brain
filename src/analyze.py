*** a/src/analyze.py
--- b/src/analyze.py
@@
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
 
+def _load_json(p: Path):
+    import json
+    with open(p, "r", encoding="utf-8") as f:
+        return json.load(f)
+
+def _snap_to_grid(x: float, grid: list[float]) -> float:
+    return min(grid, key=lambda g: abs(g - x)) if grid else x
+
+def _normalize_bpm(bpm_raw: float|None, cfg: dict) -> float|None:
+    if bpm_raw is None or bpm_raw <= 0:
+        return None
+    # Konfiguration lesen
+    tol_abs = float(cfg.get("tolerance", {}).get("abs_bpm", 1.0))
+    rng = cfg.get("half_double_resolution", {}).get("prefer_range", [110, 170])
+    prefer_lo, prefer_hi = float(rng[0]), float(rng[1])
+    grid_vals = cfg.get("grid_snapping", {}).get("grid_values", [])
+    return_int = bool(cfg.get("output", {}).get("return_int", True))
+    # Kandidaten ½× / 1× / 2×
+    cands = [bpm_raw/2.0, bpm_raw, bpm_raw*2.0]
+    # Toleranz-Rundung (±1 BPM)
+    cands = [round(c) for c in cands]
+    # Bias-Range
+    prefer = [c for c in cands if prefer_lo <= c <= prefer_hi]
+    if prefer:
+        bpm_final = min(prefer, key=lambda c: abs(c - bpm_raw))
+    else:
+        bpm_final = _snap_to_grid(bpm_raw, grid_vals) if grid_vals else round(bpm_raw)
+    return int(round(bpm_final)) if return_int else float(bpm_final)
+
+def _estimate_bpm_hpss(y: np.ndarray, sr: int) -> float|None:
+    # Percussive Spur → stabilere Temposchätzung
+    try:
+        _, y_perc = librosa.effects.hpss(y)
+    except Exception:
+        y_perc = y
+    # einfache Mehrfachschätzung (Median)
+    est = []
+    tempo, _ = librosa.beat.beat_track(y=y_perc, sr=sr)
+    if tempo and tempo > 0:
+        est.append(float(tempo))
+    if not est:
+        return None
+    return float(np.median(est))
+
 def estimate_key(y, sr):
@@
 def extract_features(path: Path):
     y, sr = safe_load(path)
     if y is None:
         return None
@@
-    # tempo (BPM)
-    tempo, _ = librosa.beat.beat_track(y=y, sr=sr)
-    bpm = float(tempo) if tempo is not None else None
+    # tempo (BPM) → HPSS + Normalisierung (½×/1×/2×, Bias 110–170, Grid)
+    bpm_raw = _estimate_bpm_hpss(y, sr)
+    try:
+        bpm_cfg = _load_json(Path("data") / "bpm_normalization.json")
+    except Exception:
+        bpm_cfg = {
+            "tolerance":{"abs_bpm":1.0},
+            "half_double_resolution":{"prefer_range":[110,170]},
+            "grid_snapping":{"grid_values":[60,64,70,72,75,80,85,88,90,92,95,96,98,100,105,108,110,112,115,118,120,122,125,126,128,130,132,135,138,140,142,145,150,152,155,158,160,162,165,168,170]},
+            "output":{"return_int":True}
+        }
+    bpm = _normalize_bpm(bpm_raw, bpm_cfg)
@@
     return dict(
         bpm=bpm, key=key, key_conf=key_conf, loudness=loudness, brightness=brightness,
         mfcc_mean=mfcc_mean.tobytes(), mfcc_std=mfcc_std.tobytes(),
         chroma_mean=chroma_mean.tobytes(), chroma_std=chroma_std.tobytes(),
         clazz=clazz
     )

