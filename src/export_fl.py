# src/export_fl.py
from pathlib import Path
import re
from sqlalchemy import text
from .db import init_db
from .config import SAMPLE_ROOTS
import json, os

MAX_TAGS = 5
CONF_KEY_MIN = 0.55

def brightness_to_tag(val: float):
    if val is None: return None
    if val < 1500: return "Dark"
    if val > 3500: return "Bright"
    return None

def loudness_to_tag(db: float):
    if db is None: return None
    if db > -18: return "Punchy"
    if db < -28: return "Clean"
    return None

def duration_class_to_tag(clazz: str):
    if clazz == "oneshot": return "OneShot"
    if clazz == "loop":    return "Loop"
    return None

def bpm_to_tag(bpm: float|None):
    if not bpm: return None
    return f"{int(round(bpm))}BPM"

def key_to_tag(key: str|None, conf: float|None):
    if not key or (conf is not None and conf < CONF_KEY_MIN): 
        return None
    k = key.replace("min","m").replace("maj","").upper()
    if len(k) == 1: k = k + "maj"
    if k.endswith("M"): k = k[:-1] + "maj"
    if k.endswith("m"): k = k[:-1] + "min"
    return k

def load_regex_map():
    p = Path("./data/filename_tag_regex.json")
    if not p.exists():
        return {}
    return json.loads(p.read_text(encoding="utf-8"))

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

def build_tags_for_sample(row, roots):
    # row: (path, relpath, duration, brightness, loudness, clazz, key, key_conf, bpm, pred_type, filename)
    path, relpath, duration, brightness, loudness, clazz, key, key_conf, bpm, pred_type, filename = row
    tags: list[str] = []

    # 1) Typ-Priorität: pred_type (aus Autotype) > Dateiname
    t = pred_type or infer_type_from_filename(filename)
    if t: tags.append(t)

    # 2) Charakter
    bt = brightness_to_tag(brightness)
    if bt and bt not in tags: tags.append(bt)
    lt = loudness_to_tag(loudness)
    if lt and lt not in tags: tags.append(lt)

    if duration and duration > 6 and "Atmospheric" not in tags and (t in (None, "Pad","Drone","Texture","AmbientLayer")):
        tags.append("Atmospheric")

    # 3) Form (Oneshot/Loop)
    ct = duration_class_to_tag(clazz)
    if ct and ct not in tags: tags.append(ct)

    # 4) Harmonik
    kt = key_to_tag(key, key_conf)
    if kt and kt not in tags: tags.append(kt)
    btg = bpm_to_tag(bpm)
    if btg and btg not in tags: tags.append(btg)

    return tags[:MAX_TAGS]

def write_fl_tags(fl_userdata: Path, roots):
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
    for r in rows:
        path = r[0]
        relpath = r[1]
        filename = Path(path).name
        tags = build_tags_for_sample((*r, filename), roots)
        for t in tags: all_tags.add(t)

        base = Path(roots[0]) if roots else Path(path).drive + os.sep
        lib_root_lower = str(Path(base)).lower().rstrip("\\/") + os.sep
        final_path = (lib_root_lower + relpath.replace("/", os.sep)) if relpath else path
        lines.append(f"\"{final_path}\"," + ",".join(tags))

    header = "@TagCase=*"
    for t in sorted(all_tags, key=lambda x: x.lower()):
        if re.search(r'[,\s"]', t):
            header += "," + '"' + t.replace('"', '') + '"'
        else:
            header += "," + t

    with open(tags_path, "w", encoding="utf-8") as f:
        f.write(header + "\n")
        for L in lines:
            f.write(L + "\n")
    print(f"Wrote FL Tags → {tags_path}")

def run_export(fl_user_data_folder: str):
    write_fl_tags(Path(fl_user_data_folder), SAMPLE_ROOTS)
