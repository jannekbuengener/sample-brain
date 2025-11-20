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

    # export
    p_export = sub.add_parser("export", help="Export metadata (DAW-neutral)")
    p_export.add_argument("--format", "-f", choices=["json", "csv", "yaml", "xml", "parquet"], default="json",
                          help="Export format (default: json)")
    p_export.add_argument("--output", "-o", help="Output file path (optional)")
    p_export.add_argument("--streaming", action="store_true", help="Use streaming export for large libraries")
    p_export.add_argument("--chunk-size", type=int, default=1000, help="Chunk size for streaming (default: 1000)")

    # export-daw (DAW-specific adapters)
    p_daw = sub.add_parser("export-daw", help="Export to DAW-specific formats")
    p_daw.add_argument("daw", choices=["ableton", "bitwig", "fl", "logic", "cubase", "studio-one", "reaper"],
                       help="Target DAW")
    p_daw.add_argument("--format", "-f", choices=["json", "xml", "csv"], default="json",
                       help="Format (DAW-dependent: Bitwig/Logic/Cubase/Studio One support xml, Reaper supports csv)")
    p_daw.add_argument("--output", "-o", help="Output file path (optional)")
    p_daw.add_argument("--fl-user-data", help="FL Studio user data path (e.g. C:\\Users\\NAME\\Documents\\Image-Line)")

    # create-views (SQLite views)
    p_views = sub.add_parser("create-views", help="Create SQLite metadata views")
    p_views.add_argument("--export-schema", action="store_true", help="Export views schema to SQL file")

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

    if args.cmd == "export":
        try:
            if args.format in ["xml", "parquet"]:
                from .export_extended import run_export_xml, run_export_parquet
                output = Path(args.output) if args.output else None
                if args.format == "xml":
                    result_path = run_export_xml(output)
                else:  # parquet
                    result_path = run_export_parquet(output)
            elif args.streaming:
                from .export_generic import run_export_streaming
                output = Path(args.output) if args.output else None
                result_path = run_export_streaming(
                    format=args.format,
                    output_path=output,
                    chunk_size=args.chunk_size
                )
            else:
                from .export_generic import run_export
                output = Path(args.output) if args.output else None
                result_path = run_export(format=args.format, output_path=output)
        except Exception as e:
            print(f"[ERROR] Export-Modul fehlt/fehlerhaft: {e}", file=sys.stderr)
            sys.exit(1)
        print(f"Export completed: {result_path}")
        return

    if args.cmd == "export-daw":
        try:
            output = Path(args.output) if args.output else None

            if args.daw == "ableton":
                from .export_ableton import run_export_ableton
                collection_path, tag_index_path = run_export_ableton(output)
                print(f"Ableton export completed:")
                print(f"  Collection: {collection_path}")
                print(f"  Tag index:  {tag_index_path}")

            elif args.daw == "bitwig":
                from .export_bitwig import run_export_bitwig
                result_path = run_export_bitwig(format=args.format, output_path=output)
                print(f"Bitwig export completed: {result_path}")

            elif args.daw == "fl":
                from .export_fl import run_export_fl
                fl_user_data = Path(args.fl_user_data) if args.fl_user_data else None
                result_path = run_export_fl(output_path=output, fl_user_data=fl_user_data)
                print(f"FL Studio export completed: {result_path}")

            elif args.daw == "logic":
                from .export_logic import run_export_logic
                result_path = run_export_logic(output)
                print(f"Logic Pro export completed: {result_path}")

            elif args.daw == "cubase":
                from .export_cubase import run_export_cubase
                result_path = run_export_cubase(output)
                print(f"Cubase/Nuendo export completed: {result_path}")

            elif args.daw == "studio-one":
                from .export_studio_one import run_export_studio_one
                result_path = run_export_studio_one(output)
                print(f"Studio One export completed: {result_path}")

            elif args.daw == "reaper":
                from .export_reaper import run_export_reaper
                result_path = run_export_reaper(format=args.format, output_path=output)
                print(f"REAPER export completed: {result_path}")

        except Exception as e:
            print(f"[ERROR] DAW export fehlt/fehlerhaft: {e}", file=sys.stderr)
            sys.exit(1)
        return

    if args.cmd == "create-views":
        try:
            from .export_extended import run_create_sqlite_views, export_sqlite_views_schema
            views = run_create_sqlite_views()
            print(f"Created {len(views)} SQLite views:")
            for view_name in views.keys():
                print(f"  - {view_name}")

            if args.export_schema:
                schema_path = export_sqlite_views_schema()
                print(f"\nSchema exported to: {schema_path}")
        except Exception as e:
            print(f"[ERROR] Views creation fehlt/fehlerhaft: {e}", file=sys.stderr)
            sys.exit(1)
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
