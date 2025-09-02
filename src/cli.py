# src/cli.py
from __future__ import annotations
import argparse
from pathlib import Path
import sys

def main():
    parser = argparse.ArgumentParser(
        prog="sample-brain",
        description="Sample Brain CLI (argparse) – stabile Commands ohne Typer/Click."
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    # init
    p_init = sub.add_parser("init", help="DB und Verzeichnisse initialisieren")

    # scan
    p_scan = sub.add_parser("scan", help="Samples scannen und in DB registrieren")
    p_scan.add_argument("root", help="Wurzelordner mit Samples (z.B. D:\\...\\Samples)")

    # analyze
    sub.add_parser("analyze", help="Audio-Features (librosa) berechnen")

    # autotype
    p_aut = sub.add_parser("autotype", help="Audio-basierte Typisierung -> features.pred_type")
    p_aut.add_argument("--no-knn", action="store_true", help="kNN/Seeds deaktivieren")

    # export_fl
    p_exp = sub.add_parser("export_fl", help="FL Studio Browser Tags schreiben")
    p_exp.add_argument("fl_user_data", help=r'Z.B. C:\Users\DEINNAME\Documents\Image-Line')

    # (optional) embed
    p_emb = sub.add_parser("embed", help="OpenL3-Embeddings berechnen (optional)")
    p_emb.add_argument("--limit", type=int, default=None, help="Nur X Dateien einbetten")
    p_emb.add_argument("--all", action="store_true", help="Alle neu berechnen")

    # (optional) index_build
    sub.add_parser("index_build", help="FAISS-Index bauen (optional)")

    # (optional) search
    p_src = sub.add_parser("search", help="Ähnlichkeitssuche (optional)")
    p_src.add_argument("query", help="Pfad zur Audiodatei")
    p_src.add_argument("--topk", type=int, default=10)

    args = parser.parse_args()

    # Imports hier drin, damit das Skript startet, auch wenn einzelne Module fehlen.
    if args.cmd == "init":
        from .db import init_db
        init_db()
        print("DB ready: data\\catalog.db")
        return

    if args.cmd == "scan":
        from .scan import run_scan
        run_scan(Path(args.root))
        print("Scan completed.")
        return

    if args.cmd == "analyze":
        try:
            from .analyze import run_analyze
        except Exception as e:
            print(f"[ERROR] Analyze-Modul fehlt/fehlerhaft: {e}", file=sys.stderr)
            sys.exit(1)
        run_analyze()
        print("Analyze completed.")
        return

    if args.cmd == "autotype":
        try:
            from .classify import write_autotype_to_db
        except Exception as e:
            print(f"[ERROR] Autotype-Modul fehlt/fehlerhaft: {e}", file=sys.stderr)
            sys.exit(1)
        use_knn = not args.no_knn
        write_autotype_to_db(use_knn=use_knn, knn_min_conf=0.55)
        print("Autotypisierung abgeschlossen.")
        return

    if args.cmd == "export_fl":
        try:
            from .export_fl import run_export
        except Exception as e:
            print(f"[ERROR] Export-Modul fehlt/fehlerhaft: {e}", file=sys.stderr)
            sys.exit(1)
        run_export(args.fl_user_data)
        print("FL Tags export completed.")
        return

    if args.cmd == "embed":
        try:
            from .embed import run_embed
        except Exception as e:
            print(f"[WARN] Embeddings übersprungen (Modul fehlt/fehlerhaft): {e}")
            sys.exit(0)
        run_embed(limit=args.limit, only_missing=not args.all)
        print("Embeddings completed.")
        return

    if args.cmd == "index_build":
        try:
            from .index import build_index
        except Exception as e:
            print(f"[WARN] Index übersprungen (Modul fehlt/fehlerhaft): {e}")
            sys.exit(0)
        p = build_index()
        print(f"Index geschrieben: {p}")
        return

    if args.cmd == "search":
        try:
            from .search import run_search
        except Exception as e:
            print(f"[ERROR] Search nicht verfügbar: {e}", file=sys.stderr)
            sys.exit(1)
        res = run_search(args.query, topk=args.topk)
        for path, score in res:
            print(f"{score:.3f}  {path}")
        return

if __name__ == "__main__":
    main()
