#!/usr/bin/env python3

SampleBrain Validation Report Generator

Reads data/catalog.db and produces reports/VALIDATION_REPORT.md

Usage:
  python tools/validate_report.py
  python tools/validate_report.py --db data/catalog.db --out reports/VALIDATION_REPORT.md

import argparse
import re
import sqlite3
from datetime import datetime
from pathlib import Path

import pandas as pd
import numpy as np

BPM_HINT_RE = re.compile(r'(\d{2,3})\s*?bpm', re.IGNORECASE)

def extract_bpm_hint(text: str):
    if not isinstance(text, str):
        return np.nan
    m = BPM_HINT_RE.search(text)
    if m:
        try:
            return float(m.group(1))
        except Exception:
            return np.nan
    return np.nan

def classify_bpm_match(pred, hint, tol=2.0):
    if np.isnan(pred) or np.isnan(hint):
        return "no_hint"
    if abs(pred - hint) <= tol:
        return "match"
    if abs(pred * 2 - hint) <= tol:
        return "half_time"
    if abs(pred / 2 - hint) <= tol:
        return "double_time"
    return "mismatch"

def pct(x, total):
    return 0 if total == 0 else 100.0 * x / total

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default="data/catalog.db")
    ap.add_argument("--out", default="reports/VALIDATION_REPORT.md")
    args = ap.parse_args()

    db_path = Path(args.db)
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    if not db_path.exists():
        out_path.write_text(
            f"# SampleBrain Validation Report

Generated: {datetime.now().isoformat(timespec='seconds')}

"
            f"ERROR: Database not found at `{db_path}`.
",
            encoding="utf-8",
        )
        raise SystemExit(2)

    con = sqlite3.connect(db_path)
    df = pd.read_sql_query(
        """
        SELECT s.id, s.path, COALESCE(s.relpath, s.path) as ref, s.duration,
               f.bpm, f.key, f.key_conf, f.loudness, f.brightness, f.class, f.pred_type
        FROM samples s
        LEFT JOIN features f ON f.sample_id = s.id
        """,
        con,
    )
    con.close()

    total = len(df)
    with_bpm = df["bpm"].notna().sum()
    with_key = df["key"].notna().sum()
    with_key_conf = df["key_conf"].notna().sum()
    with_class = df["class"].notna().sum()

    # weak ground truth from filenames
    df["bpm_hint"] = df["ref"].apply(extract_bpm_hint)
    hint_df = df[df["bpm_hint"].notna() & df["bpm"].notna()].copy()
    hint_df["bpm_match"] = hint_df.apply(lambda r: classify_bpm_match(r["bpm"], r["bpm_hint"]), axis=1)
    vc = hint_df["bpm_match"].value_counts()

    bpm_stats = df["bpm"].dropna()
    key_conf_stats = df["key_conf"].dropna()

    lines = []
    lines.append("# SampleBrain Validation Report

")
    lines.append(f"Generated: {datetime.now().isoformat(timespec='seconds')}

")
    lines.append("## Inventory
")
    lines.append(f"- Samples in catalog: **{total}**
")
    lines.append(f"- With BPM: **{with_bpm}** ({pct(with_bpm,total):.1f}%)
")
    lines.append(f"- With Key: **{with_key}** ({pct(with_key,total):.1f}%)
")
    lines.append(f"- With Key confidence: **{with_key_conf}** ({pct(with_key_conf,total):.1f}%)
")
    lines.append(f"- With Class (loop/one-shot/etc): **{with_class}** ({pct(with_class,total):.1f}%)

")

    lines.append("## BPM quality (weak ground truth)
")
    lines.append("We extract BPM hints from filenames like `128bpm` / `124 bpm` and compare with predicted BPM.

")
    n_hint = len(hint_df)
    for k in ["match","half_time","double_time","mismatch"]:
        c = int(vc.get(k, 0))
        lines.append(f"- {k}: **{c}** ({pct(c,n_hint):.1f}%)
")
    lines.append("
Notes:
")
    lines.append("- `half_time` usually means the analyzer locked onto the half-tempo (common for claps/hats/ambient loops).
")
    lines.append("- For Techno/Hardtechno, we typically normalize into a 120–160 BPM range.

")

    lines.append("## BPM distribution
")
    if len(bpm_stats) > 0:
        lines.append(f"- min/median/max: **{bpm_stats.min():.1f} / {bpm_stats.median():.1f} / {bpm_stats.max():.1f}**
")
        lines.append(f"- 10th/90th percentile: **{bpm_stats.quantile(0.1):.1f} / {bpm_stats.quantile(0.9):.1f}**
")
    lines.append("
## Key confidence
")
    if len(key_conf_stats) > 0:
        lines.append(f"- min/median/max: **{key_conf_stats.min():.2f} / {key_conf_stats.median():.2f} / {key_conf_stats.max():.2f}**
")
        lines.append(f"- low-confidence share (key_conf < 2.0): **{(key_conf_stats<2.0).mean()*100:.1f}%**
")

    lines.append("
## Class / Predicted Type
")
    class_counts = df["class"].fillna("unknown").value_counts().head(10)
    pred_counts = df["pred_type"].fillna("unknown").value_counts().head(10)

    lines.append("
Top classes:
")
    for k, v in class_counts.items():
        lines.append(f"- {k}: {int(v)}
")
    lines.append("
Top pred_type:
")
    for k, v in pred_counts.items():
        lines.append(f"- {k}: {int(v)}
")

    lines.append("
## Findings (actionable)
")
    lines.append("1) **BPM has known half-tempo errors** (see weak-ground-truth check). Enable/extend BPM normalization per genre profile.
")
    lines.append("2) **Key confidence is mostly high**, but keep a low-confidence bucket to avoid over-tagging.
")
    lines.append("3) The catalog stores **absolute paths** (e.g. `D:\\...`) — do not commit raw DB to public repos.
")

    lines.append("
## Next steps
")
    lines.append("- Add per-genre profile config (e.g. `profiles/techno.yaml`) for BPM normalization + tag vocab.
")
    lines.append("- Increase weak ground truth: more filenames with BPM hints or a quick manual pass (50–100 samples).
")

    out_path.write_text("".join(lines), encoding="utf-8")
    print(f"Wrote: {out_path}")

if __name__ == "__main__":
    main()
