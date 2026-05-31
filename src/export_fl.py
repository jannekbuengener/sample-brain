from __future__ import annotations

import json
import os
import re
from pathlib import Path

from .config import REGEX_MAP_PATH, SAMPLE_ROOTS

MAX_TAGS = 5
CONF_KEY_MIN = 0.55


def brightness_to_tag(val: float):
    if val is None:
        return None
    if val < 1500:
        return "Dark"
    if val > 3500:
        return "Bright"
    return None


def loudness_to_tag(db: float):
    if db is None:
        return None
    if db > -18:
        return "Punchy"
    if db < -28:
        return "Clean"
    return None


def duration_class_to_tag(clazz: str):
    if clazz == "oneshot":
        return "OneShot"
    if clazz == "loop":
        return "Loop"
    return None


def bpm_to_tag(bpm: float | None):
    if not bpm:
        return None
    return f"{int(round(bpm))}BPM"


def key_to_tag(key: str | None, conf: float | None):
    if not key or (conf is not None and conf < CONF_KEY_MIN):
        return None
    normalized = key.replace("min", "m").replace("maj", "").upper()
    if len(normalized) == 1:
        normalized = normalized + "maj"
    if normalized.endswith("M"):
        normalized = normalized[:-1] + "maj"
    if normalized.endswith("m"):
        normalized = normalized[:-1] + "min"
    return normalized


def load_regex_map():
    if not REGEX_MAP_PATH.exists():
        return {}
    return json.loads(REGEX_MAP_PATH.read_text(encoding="utf-8"))


def infer_type_from_filename(name: str):
    patterns = load_regex_map()
    name_l = name.lower()
    for tag, pat in patterns.items():
        try:
            if re.search(pat, name_l):
                return tag
        except re.error:
            continue
    return None


def build_tags_for_sample(row, roots, max_tags=MAX_TAGS):
    # row: (path, relpath, duration, brightness, loudness, clazz, key, key_conf, bpm, pred_type, filename)
    (
        path,
        relpath,
        duration,
        brightness,
        loudness,
        clazz,
        key,
        key_conf,
        bpm,
        pred_type,
        filename,
    ) = row
    tags: list[str] = []

    # 1) Typ-Priorität: pred_type (aus Autotype) > Dateiname
    sample_type = pred_type or infer_type_from_filename(filename)
    if sample_type:
        tags.append(sample_type)

    # 2) Charakter
    brightness_tag = brightness_to_tag(brightness)
    if brightness_tag and brightness_tag not in tags:
        tags.append(brightness_tag)
    loudness_tag = loudness_to_tag(loudness)
    if loudness_tag and loudness_tag not in tags:
        tags.append(loudness_tag)

    if (
        duration
        and duration > 6
        and "Atmospheric" not in tags
        and (sample_type in (None, "Pad", "Drone", "Texture", "AmbientLayer"))
    ):
        tags.append("Atmospheric")

    # 3) Form (Oneshot/Loop)
    class_tag = duration_class_to_tag(clazz)
    if class_tag and class_tag not in tags:
        tags.append(class_tag)

    # 4) Harmonik
    key_tag = key_to_tag(key, key_conf)
    if key_tag and key_tag not in tags:
        tags.append(key_tag)
    bpm_tag = bpm_to_tag(bpm)
    if bpm_tag and bpm_tag not in tags:
        tags.append(bpm_tag)

    return tags[:max_tags]


def _normalized_path(path: Path | str) -> str:
    return os.path.normcase(str(Path(path)))


def resolve_export_path(
    path: str, relpath: str | None, roots: list[Path]
) -> tuple[str, str | None]:
    if not roots:
        return path, None

    sample_path = Path(path)

    # Best case: relpath maps cleanly to one of the configured roots.
    if relpath:
        for root in roots:
            candidate = root / relpath
            if _normalized_path(candidate) == _normalized_path(sample_path):
                return str(candidate), None

    # Otherwise keep full source path when it is already under one configured root.
    for root in roots:
        try:
            sample_path.relative_to(root)
            return str(sample_path), None
        except ValueError:
            continue

    warning = (
        f"[WARN] Could not resolve sample path against configured roots: {sample_path}. "
        "Falling back to stored absolute path."
    )
    return str(sample_path), warning


def write_fl_tags(fl_userdata: Path, roots, max_tags=MAX_TAGS):
    from sqlalchemy import text
    from .db import init_db

    engine = init_db()
    tags_path = Path(fl_userdata) / "FL Studio" / "Settings" / "Browser" / "Tags"
    tags_path.parent.mkdir(parents=True, exist_ok=True)

    with engine.begin() as conn:
        rows = conn.execute(text("""
                SELECT s.path, s.relpath, s.duration,
                       f.brightness, f.loudness, f.class, f.key, f.key_conf, f.bpm, f.pred_type
                FROM samples s
                LEFT JOIN features f ON f.sample_id = s.id
                ORDER BY s.id
                """)).fetchall()

    all_tags = set()
    lines = []
    warned_paths: set[str] = set()
    for row in rows:
        path = row[0]
        relpath = row[1]
        filename = Path(path).name
        tags = build_tags_for_sample((*row, filename), roots, max_tags=max_tags)
        for tag in tags:
            all_tags.add(tag)

        final_path, warning = resolve_export_path(
            path=path, relpath=relpath, roots=roots
        )
        if warning and path not in warned_paths:
            print(warning)
            warned_paths.add(path)
        lines.append(f'"{final_path}",' + ",".join(tags))

    header = "@TagCase=*"
    for tag in sorted(all_tags, key=lambda value: value.lower()):
        if re.search(r'[,\s"]', tag):
            header += "," + '"' + tag.replace('"', "") + '"'
        else:
            header += "," + tag

    with open(tags_path, "w", encoding="utf-8") as f:
        f.write(header + "\n")
        for line in lines:
            f.write(line + "\n")
    print(f"Wrote FL Tags → {tags_path}")


def run_export(fl_user_data_folder: str, max_tags=MAX_TAGS, roots=None):
    if not str(fl_user_data_folder).strip():
        raise ValueError(
            "FL user data path is empty. Use --fl-user-data or configure fl_user_data_path."
        )

    if roots is None:
        roots = SAMPLE_ROOTS
    roots = [Path(root) for root in roots]
    if not roots:
        print(
            "[WARN] No sample roots configured for relative path resolution. "
            "Use --root or config/profiles.local.yaml before exporting."
        )
    write_fl_tags(Path(fl_user_data_folder), roots, max_tags=max_tags)
