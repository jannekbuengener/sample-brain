# run_pipeline.py
from __future__ import annotations
import argparse, json, os
from pathlib import Path

# Datei, in der wir zuletzt genutzte Pfade merken (praktisch für spätere UI)
STATE_FILE = Path(__file__).resolve().parent / "data" / "last_paths.json"

def _load_state():
    try:
        with STATE_FILE.open("r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}

def _save_state(state: dict):
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    with STATE_FILE.open("w", encoding="utf-8") as f:
        json.dump(state, f, indent=2, ensure_ascii=False)

def parse_args():
    p = argparse.ArgumentParser(
        description="sample-brain: Scan → Analyze → Autotype (DAW-neutral pipeline)"
    )
    p.add_argument(
        "--root", "-r", action="append",
        help="Sample-Root (kann mehrfach angegeben werden: -r D:\\PRODUCING -r E:\\Samples)"
    )
    p.add_argument("--no-analyze", action="store_true", help="Analyze-Schritt überspringen")
    p.add_argument("--no-autotype", action="store_true", help="Autotype-Schritt überspringen")
    p.add_argument("--rules-only", action="store_true", help="Autotype ohne kNN/Embeddings")
    p.add_argument("--save", action="store_true", help="übergebene Pfade in data/last_paths.json speichern")
    return p.parse_args()

def main():
    args = parse_args()
    state = _load_state()

    # 1) Pfade ermitteln: CLI > gespeicherter State > config.py Defaults
    roots: list[Path] | None = None
    if args.root:
        roots = [Path(r) for r in args.root]
    elif state.get("roots"):
        roots = [Path(r) for r in state["roots"]]
    else:
        # Fallback: aus src.config einlesen
        from src.config import SAMPLE_ROOTS
        roots = SAMPLE_ROOTS

    # Optional speichern
    if args.save:
        _save_state({"roots": [str(p) for p in roots]})

    print("== sample-brain: pipeline start ==")
    print("Roots:", *[str(p) for p in roots], sep="\n  - ")

    # 2) init
    from src.db import init_db
    init_db(); print("[init] ok")

    # 3) scan (run_scan kann eine Liste entgegennehmen)
    from src.scan import run_scan
    run_scan(custom_roots=roots); print("[scan] ok")

    # 4) analyze
    if not args.no_analyze:
        try:
            from src.analyze import run_analyze
            run_analyze(); print("[analyze] ok")
        except Exception as e:
            print(f"[analyze] übersprungen/Fehler: {e}")
    else:
        print("[analyze] übersprungen (flag)")

    # 5) autotype
    if not args.no_autotype:
        from src.classify import write_autotype_to_db
        use_knn = not args.rules_only  # rules-only → kNN aus
        write_autotype_to_db(use_knn=use_knn, knn_min_conf=0.55)
        print(f"[autotype] ok ({'rules+knn' if use_knn else 'rules only'})")
    else:
        print("[autotype] übersprungen (flag)")

    print("== fertig ==")

if __name__ == "__main__":
    main()
