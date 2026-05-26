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
    parser.add_argument(
        "--profile",
        default=None,
        help="Configuration profile name. Overrides SAMPLE_BRAIN_PROFILE.",
    )
    parser.add_argument(
        "--config",
        default=None,
        help="Path to base profile config. Defaults to config/profiles.example.yaml.",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    # init
    p_init = sub.add_parser("init", help="DB und Verzeichnisse initialisieren")

    # scan
    p_scan = sub.add_parser("scan", help="Samples scannen und in DB registrieren")
    p_scan.add_argument(
        "--root",
        action="append",
        default=None,
        help="Library root to scan. Can be provided multiple times. Overrides configured library_roots.",
    )

    # analyze
    sub.add_parser("analyze", help="Audio-Features (librosa) berechnen")

    # autotype
    p_aut = sub.add_parser("autotype", help="Audio-basierte Typisierung -> features.pred_type")
    p_aut.add_argument("--no-knn", action="store_true", help="kNN/Seeds deaktivieren")

    # export_fl
    p_exp = sub.add_parser("export_fl", help="FL Studio Browser Tags schreiben")
    p_exp.add_argument(
        "--fl-user-data",
        default=None,
        help="FL Studio User Data directory. Overrides configured fl_user_data_path.",
    )
    p_exp.add_argument(
        "--max-tags",
        type=int,
        default=None,
        help="Maximum tags per sample. Overrides configured export.max_tags.",
    )

    # (optional) embed
    p_emb = sub.add_parser("embed", help="Embeddings berechnen (optional)")
    p_emb.add_argument("--limit", type=int, default=None, help="Nur X Dateien einbetten")
    p_emb.add_argument("--all", action="store_true", help="Alle neu berechnen")
    p_emb.add_argument(
        "--backend",
        choices=["noop", "clap"],
        default=None,
        help="Embedding backend to use. Overrides profile/env config. Defaults to configured backend or noop.",
    )

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
        if args.root:
            roots = [Path(r) for r in args.root]
        else:
            import os
            from .config_loader import resolve_profile, ConfigError, DEFAULT_EXAMPLE_CONFIG
            try:
                cfg = resolve_profile(
                    profile_name=args.profile,
                    example_path=Path(args.config) if args.config else DEFAULT_EXAMPLE_CONFIG,
                    env=dict(os.environ),
                )
            except ConfigError as e:
                print(f"[ERROR] Config error: {e}", file=sys.stderr)
                sys.exit(1)
            roots = [Path(r) for r in cfg.get("library_roots", [])]
        from .scan import run_scan
        run_scan(roots)
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
        import os
        from .config_loader import resolve_profile, ConfigError, DEFAULT_EXAMPLE_CONFIG
        try:
            cfg = resolve_profile(
                profile_name=args.profile,
                example_path=Path(args.config) if args.config else DEFAULT_EXAMPLE_CONFIG,
                env=dict(os.environ),
            )
        except ConfigError as e:
            print(f"[ERROR] Config error: {e}", file=sys.stderr)
            sys.exit(1)
        autotype_cfg = cfg.get("autotype", {})
        use_knn = not args.no_knn if args.no_knn else autotype_cfg.get("use_knn", True)
        knn_min_conf = autotype_cfg.get("knn_min_conf", 0.55)
        try:
            from .classify import write_autotype_to_db
        except Exception as e:
            print(f"[ERROR] Autotype-Modul fehlt/fehlerhaft: {e}", file=sys.stderr)
            sys.exit(1)
        write_autotype_to_db(use_knn=use_knn, knn_min_conf=knn_min_conf)
        print("Autotypisierung abgeschlossen.")
        return

    if args.cmd == "export_fl":
        import os
        from .config_loader import resolve_profile, ConfigError, DEFAULT_EXAMPLE_CONFIG
        try:
            cfg = resolve_profile(
                profile_name=args.profile,
                example_path=Path(args.config) if args.config else DEFAULT_EXAMPLE_CONFIG,
                env=dict(os.environ),
            )
        except ConfigError as e:
            print(f"[ERROR] Config error: {e}", file=sys.stderr)
            sys.exit(1)
        fl_user_data = args.fl_user_data or cfg.get("fl_user_data_path")
        if not fl_user_data:
            print("[ERROR] No FL Studio User Data path configured. Use --fl-user-data or set fl_user_data_path in your profile.", file=sys.stderr)
            sys.exit(1)
        max_tags = args.max_tags or cfg.get("export", {}).get("max_tags", 5)
        roots = [Path(r) for r in cfg.get("library_roots", [])]
        try:
            from .export_fl import run_export
        except Exception as e:
            print(f"[ERROR] Export-Modul fehlt/fehlerhaft: {e}", file=sys.stderr)
            sys.exit(1)
        run_export(fl_user_data, max_tags=max_tags, roots=roots)
        print("FL Tags export completed.")
        return

    if args.cmd == "embed":
        try:
            from .embed import run_embed
        except Exception as e:
            print(f"[WARN] Embeddings übersprungen (Modul fehlt/fehlerhaft): {e}")
            sys.exit(0)
        import os
        from .config_loader import resolve_profile, ConfigError, DEFAULT_EXAMPLE_CONFIG
        try:
            cfg = resolve_profile(
                profile_name=args.profile,
                example_path=Path(args.config) if args.config else DEFAULT_EXAMPLE_CONFIG,
                env=dict(os.environ),
            )
        except ConfigError as e:
            print(f"[ERROR] Config error: {e}", file=sys.stderr)
            sys.exit(1)
        configured_backend = cfg.get("embedding", {}).get("backend", "noop")
        backend_name = args.backend or configured_backend or "noop"
        run_embed(limit=args.limit, only_missing=not args.all, backend_name=backend_name)
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
