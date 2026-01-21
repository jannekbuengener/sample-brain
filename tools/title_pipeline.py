#!/usr/bin/env python3
"""
SampleBrain Title Pipeline (v1)

- Reads catalog.db (samples + features)
- Parses existing titles from filename
- Fills missing parts using analysis
- Applies per-folder profile lens (techno/house/hiphop/vocals/film_scoring)
- Outputs:
  - CSV with old_title -> new_title suggestion
  - optional PowerShell rename preview script (safe by default)

Usage:
  python tools/title_pipeline.py --db data/catalog.db --profiles profiles --config pipeline_config.yaml --out reports/TITLE_SUGGESTIONS.csv --emit-ps1 reports/RENAME_PREVIEW.ps1
"""
import argparse
import re
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
import yaml

TITLE_EXAMPLE = "HH, closed, [LOOP] - 132BPM, F#m, dark/vintage"

# --- Regex helpers ---
RE_BPM = re.compile(r"(\d{2,3})\s*BPM", re.IGNORECASE)
RE_KEY = re.compile(r"\b([A-G])([b#])?(m)?\b")  # accepts C, F#m, Bb, etc.
RE_TYPE = re.compile(r"\[(LOOP|ONE-SHOT|FX|VOCAL)\]", re.IGNORECASE)

# --- Windows-safe filename helper ---
INVALID_CHARS = '<>:"/\\|?*'


def safe_filename(name: str) -> str:
    """
    Convert a human title into a Windows-safe filename.
    Keeps it readable, but replaces forbidden characters.
    """
    if not isinstance(name, str):
        name = str(name)

    # Replace path separators first (Windows treats them as folders)
    name = name.replace("/", "-").replace("\\", "-")

    # Replace other invalid Windows filename characters
    name = "".join("_" if c in INVALID_CHARS else c for c in name)

    # Normalize whitespace and remove trailing dot/space (Windows forbids)
    name = " ".join(name.split()).strip().rstrip(" .")

    # Avoid super long filenames
    return name[:180]


def safe_stem(path_str: str) -> str:
    p = Path(path_str)
    return p.stem


def extract_bpm(text: str) -> Optional[int]:
    if not isinstance(text, str):
        return None
    m = RE_BPM.search(text.replace(" ", ""))
    if not m:
        # support 128bpm style
        m = re.search(r"(\d{2,3})\s*bpm", text, re.IGNORECASE)
    if m:
        try:
            return int(m.group(1))
        except Exception:
            return None
    return None


def extract_type(text: str) -> Optional[str]:
    if not isinstance(text, str):
        return None
    m = RE_TYPE.search(text)
    if m:
        return m.group(1).upper()
    return None


def extract_key(text: str) -> Optional[str]:
    if not isinstance(text, str):
        return None
    # Prefer explicit patterns like F#m, C#m, Bb
    m = re.search(r"\b([A-G])([b#])?(m)\b", text)
    if m:
        note = m.group(1).upper()
        acc = m.group(2) or ""
        return f"{note}{acc}m"
    m = re.search(r"\b([A-G])([b#])?\b", text)
    if m:
        note = m.group(1).upper()
        acc = m.group(2) or ""
        return f"{note}{acc}"
    return None


def normalize_key(key: str) -> str:
    # Keep as-is but enforce casing like F#m, Bb
    if not key:
        return key
    # pattern: Note + accidental + optional m
    m = re.match(r"^([A-Ga-g])([b#])?(m)?$", key.strip())
    if not m:
        return key.strip()
    note = m.group(1).upper()
    acc = m.group(2) or ""
    minor = m.group(3) or ""
    return f"{note}{acc}{minor}"


def normalize_bpm(bpm: int) -> str:
    return f"{int(bpm)}BPM"


@dataclass
class Profile:
    name: str
    expected_range: Optional[Tuple[int, int]]
    normalize_half_double: bool
    key_conf_min: float
    type_bias: List[str]
    character_defaults: List[str]


def load_profiles(profiles_dir: Path) -> Dict[str, Profile]:
    profiles: Dict[str, Profile] = {}
    for p in profiles_dir.glob("*.yaml"):
        data = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
        name = data.get("name", p.stem)
        bpm = data.get("bpm", {}) or {}
        rng = bpm.get("expected_range")
        expected = None
        if isinstance(rng, list) and len(rng) == 2:
            expected = (int(rng[0]), int(rng[1]))
        normalize = bool(bpm.get("normalize_half_double", False))
        key = data.get("key", {}) or {}
        key_conf_min = float(key.get("require_confidence", 2.5))
        type_bias = [
            t.replace("[", "").replace("]", "").upper()
            for t in (data.get("type_bias") or [])
        ]
        character_defaults = data.get("character_defaults") or []
        profiles[p.stem] = Profile(
            name=name,
            expected_range=expected,
            normalize_half_double=normalize,
            key_conf_min=key_conf_min,
            type_bias=type_bias,
            character_defaults=character_defaults,
        )
    return profiles


def load_config(config_path: Path) -> dict:
    return yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}


def pick_profile(relpath: str, cfg: dict, default_profile: str) -> str:
    rel = (relpath or "").lower()
    mapping = cfg.get("folder_profile_map") or {}
    for profile_name, keywords in mapping.items():
        for kw in keywords or []:
            if kw.lower() in rel:
                return profile_name
    return default_profile


def infer_type(
    duration: float,
    class_val: Optional[str],
    pred_type: Optional[str],
    profile: Profile,
) -> str:
    # If model already classifies "loop", trust it
    if isinstance(class_val, str) and class_val.strip():
        c = class_val.strip().upper()
        if c in ["LOOP", "ONE-SHOT", "FX", "VOCAL"]:
            return c
        if c == "LOOP":
            return "LOOP"

    # heuristic: long => LOOP/FX, short => ONE-SHOT
    if duration is not None and duration >= 2.0:
        return "LOOP" if "LOOP" in profile.type_bias else (profile.type_bias[0] if profile.type_bias else "LOOP")

    return "ONE-SHOT" if "ONE-SHOT" in profile.type_bias else (profile.type_bias[0] if profile.type_bias else "ONE-SHOT")


def normalize_bpm_by_profile(bpm: float, profile: Profile) -> Optional[int]:
    if bpm is None or np.isnan(bpm):
        return None
    val = float(bpm)

    # half/double normalization (common half-tempo mistakes)
    if profile.normalize_half_double:
        if val < 90:
            val *= 2.0
        elif val > 200:
            val /= 2.0

    # clamp to expected range if provided by choosing the closer of val, val*2, val/2
    if profile.expected_range:
        lo, hi = profile.expected_range
        candidates = [val, val * 2.0, val / 2.0]

        def score(x: float) -> float:
            if x < lo:
                return lo - x
            if x > hi:
                return x - hi
            return 0.0

        val = min(candidates, key=score)

    return int(round(val))


def build_title(existing: dict, analysis: dict, profile: Profile, defaults: dict) -> str:
    name = existing.get("name") or existing.get("name2") or existing.get("fallback_name") or "--"
    detail = existing.get("detail") or defaults.get("missing_detail", "--")
    typ = existing.get("type") or analysis.get("type") or "ONE-SHOT"
    bpm = existing.get("bpm") or analysis.get("bpm") or defaults.get("missing_bpm", "--BPM")
    key = existing.get("key") or analysis.get("key") or defaults.get("missing_key", "--KEY")
    char = existing.get("character") or analysis.get("character") or ""

    if not char and profile.character_defaults:
        # only use defaults if missing
        char = "/".join(profile.character_defaults[:2])

    # enforce formatting
    typ = typ.upper()
    if typ == "ONE SHOT":
        typ = "ONE-SHOT"

    bpm_s = bpm if isinstance(bpm, str) else normalize_bpm(int(bpm))
    key_s = normalize_key(key) if isinstance(key, str) else str(key)
    char_s = (char or "").strip()

    return f"{name}, {detail}, [{typ}] - {bpm_s}, {key_s}, {char_s}".strip().rstrip(",")


def parse_existing_title(stem: str) -> dict:
    # We parse from filename stem. We do NOT rewrite the user's words.
    s = stem.strip()

    # Split on " - " if present
    left, right = (s.split(" - ", 1) + [""])[:2] if " - " in s else (s, "")

    # Left side: "HH, closed, [LOOP]" or similar
    parts = [p.strip() for p in left.split(",")]
    name = parts[0] if len(parts) >= 1 and parts[0] else None
    detail = parts[1] if len(parts) >= 2 and parts[1] else None
    typ = extract_type(left)

    bpm = extract_bpm(s)

    # Prefer key from right side
    key = None
    k = extract_key(right) or extract_key(s)
    if k:
        key = normalize_key(k)

    character = None
    if right:
        # if right contains commas, last chunk often character
        rparts = [p.strip() for p in right.split(",")]
        if len(rparts) >= 3:
            character = rparts[2]
        elif len(rparts) == 1 and "/" in rparts[0]:
            character = rparts[0]

    return {
        "name": name,
        "detail": detail,
        "type": typ,
        "bpm": bpm,
        "key": key,
        "character": character,
        "fallback_name": name,
    }


def emit_rename_ps1(rows: List[dict], out_path: Path):
    out_path.parent.mkdir(parents=True, exist_ok=True)
    lines: List[str] = []
    lines.append("# RENAME_PREVIEW.ps1\n")
    lines.append(f"# Generated: {datetime.now().isoformat(timespec='seconds')}\n")
    lines.append("# Safe by default: does NOT rename unless you pass -Apply.\n\n")
    lines.append("param([switch]$Apply)\n\n")
    lines.append("$errors = 0\n\n")

    for r in rows:
        src = r["abs_path"]
        dst = r["new_abs_path"]
        # escape single quotes for PS
        src_ps = src.replace("'", "''")
        dst_ps = dst.replace("'", "''")
        lines.append(f"# {r['relpath']}\n")
        lines.append(f"$src = '{src_ps}'\n")
        lines.append(f"$dst = '{dst_ps}'\n")
        lines.append("if (-not (Test-Path -LiteralPath $src)) { Write-Host \"MISSING: $src\"; $errors++; continue }\n")
        lines.append("if ($Apply) {\n")
        lines.append("  try { Rename-Item -LiteralPath $src -NewName (Split-Path -Leaf $dst) -ErrorAction Stop }\n")
        lines.append("  catch { Write-Host \"FAIL: $src\"; $errors++ }\n")
        lines.append("} else {\n")
        lines.append("  Write-Host \"PREVIEW: Rename '$src' -> '$dst'\"\n")
        lines.append("}\n\n")

    lines.append("if ($errors -gt 0) { Write-Host \"Done with $errors error(s).\"; exit 2 }\n")
    lines.append("Write-Host \"Done.\"; exit 0\n")
    out_path.write_text("".join(lines), encoding="utf-8")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default="data/catalog.db")
    ap.add_argument("--profiles", default="profiles")
    ap.add_argument("--config", default="pipeline_config.yaml")
    ap.add_argument("--out", default="reports/TITLE_SUGGESTIONS.csv")
    ap.add_argument("--emit-ps1", default=None)
    args = ap.parse_args()

    db_path = Path(args.db)
    profiles_dir = Path(args.profiles)
    cfg_path = Path(args.config)
    out_csv = Path(args.out)

    out_csv.parent.mkdir(parents=True, exist_ok=True)

    if not db_path.exists():
        raise SystemExit(f"DB not found: {db_path}")

    profiles = load_profiles(profiles_dir)
    cfg = load_config(cfg_path)
    defaults = cfg.get("defaults") or {}
    default_profile = defaults.get("profile", "techno")

    con = sqlite3.connect(db_path)
    df = pd.read_sql_query(
        """
        SELECT s.id, s.path, COALESCE(s.relpath, s.path) as relpath, s.duration,
               f.bpm, f.key, f.key_conf, f.class, f.pred_type
        FROM samples s
        LEFT JOIN features f ON f.sample_id = s.id
        """,
        con,
    )
    con.close()

    rows: List[dict] = []
    rename_rows: List[dict] = []

    for _, r in df.iterrows():
        relpath = str(r["relpath"])
        abs_path = str(r["path"])
        stem = safe_stem(relpath)
        existing = parse_existing_title(stem)

        profile_key = pick_profile(relpath, cfg, default_profile)
        profile = profiles.get(profile_key) or profiles.get(default_profile)
        if profile is None:
            # fallback profile if missing
            profile = Profile(
                name="Default",
                expected_range=None,
                normalize_half_double=False,
                key_conf_min=3.0,
                type_bias=["ONE-SHOT"],
                character_defaults=[],
            )

        # analysis-based fills
        analysis: dict = {}

        # TYPE
        analysis["type"] = infer_type(float(r["duration"] or 0), r.get("class"), r.get("pred_type"), profile)

        # BPM
        bpm_val = normalize_bpm_by_profile(r.get("bpm"), profile)
        analysis["bpm"] = bpm_val

        # KEY
        key_val = r.get("key")
        key_conf = r.get("key_conf")
        if isinstance(key_val, str) and key_val.strip() and key_conf is not None and float(key_conf) >= profile.key_conf_min:
            analysis["key"] = normalize_key(key_val.strip())
        else:
            analysis["key"] = None

        # CHARACTER: never invent from audio; only fallback to profile defaults
        analysis["character"] = None

        new_title = build_title(existing, analysis, profile, defaults)

        # New filename preserves extension (Windows-safe)
        ext = Path(relpath).suffix
        safe = safe_filename(new_title)

        new_rel = str(Path(relpath).with_name(safe + ext))
        new_abs = str(Path(abs_path).with_name(safe + Path(abs_path).suffix)) if abs_path else ""

        rows.append(
            {
                "id": int(r["id"]),
                "profile": profile_key,
                "relpath": relpath,
                "old_title": stem,
                "new_title": new_title,  # human title (may include "/")
                "new_filename": safe + ext,  # Windows-safe filename
                "duration_s": float(r["duration"] or 0),
                "bpm_pred": r.get("bpm"),
                "bpm_used": analysis.get("bpm"),
                "key_pred": r.get("key"),
                "key_conf": r.get("key_conf"),
                "key_used": analysis.get("key"),
            }
        )

        rename_rows.append(
            {
                "id": int(r["id"]),
                "profile": profile_key,
                "relpath": relpath,
                "abs_path": abs_path,
                "new_relpath": new_rel,
                "new_abs_path": new_abs,
            }
        )

    out_df = pd.DataFrame(rows)
    out_df.to_csv(out_csv, index=False, encoding="utf-8")

    if args.emit_ps1:
        emit_rename_ps1(rename_rows, Path(args.emit_ps1))

    print(f"Wrote CSV: {out_csv}")
    if args.emit_ps1:
        print(f"Wrote PS1: {args.emit_ps1}")


if __name__ == "__main__":
    main()
