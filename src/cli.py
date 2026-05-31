# src/cli.py
from __future__ import annotations
import argparse
import json
from pathlib import Path
import sys
import time


def _resolve_profile_or_exit(args) -> dict:
    import os
    from .config_loader import resolve_profile, ConfigError, DEFAULT_EXAMPLE_CONFIG

    try:
        return resolve_profile(
            profile_name=args.profile,
            example_path=Path(args.config) if args.config else DEFAULT_EXAMPLE_CONFIG,
            env=dict(os.environ),
        )
    except ConfigError as e:
        print(f"[ERROR] Config error: {e}", file=sys.stderr)
        sys.exit(1)


def _debug_log(
    hypothesis_id: str,
    location: str,
    message: str,
    data: dict,
    run_id: str = "pre-fix",
) -> None:
    payload = {
        "sessionId": "3c0b2c",
        "runId": run_id,
        "hypothesisId": hypothesis_id,
        "location": location,
        "message": message,
        "data": data,
        "timestamp": int(time.time() * 1000),
    }
    try:
        log_path = Path(__file__).resolve().parents[1] / "debug-3c0b2c.log"
        with open(log_path, "a", encoding="utf-8") as log_file:
            log_file.write(json.dumps(payload, ensure_ascii=False) + "\n")
    except Exception:
        pass


def _resolve_profile_for_init(args) -> dict:
    import os
    from .config_loader import resolve_profile, ConfigError, DEFAULT_EXAMPLE_CONFIG

    explicit_config = args.config is not None
    example_path = Path(args.config) if explicit_config else DEFAULT_EXAMPLE_CONFIG
    # region agent log
    _debug_log(
        hypothesis_id="H1",
        location="src/cli.py:resolve_profile_for_init_entry",
        message="Resolving init profile with fallback semantics",
        data={
            "explicit_config": explicit_config,
            "example_path": str(example_path),
            "cwd": str(Path.cwd()),
        },
    )
    # endregion
    try:
        return resolve_profile(
            profile_name=args.profile,
            example_path=example_path,
            env=dict(os.environ),
        )
    except ConfigError as e:
        if explicit_config:
            # region agent log
            _debug_log(
                hypothesis_id="H2",
                location="src/cli.py:resolve_profile_for_init_explicit_error",
                message="Explicit init config failed",
                data={"error": str(e), "example_path": str(example_path)},
            )
            # endregion
            print(f"[ERROR] Config error: {e}", file=sys.stderr)
            sys.exit(1)

        if "Example config not found" in str(e):
            # region agent log
            _debug_log(
                hypothesis_id="H3",
                location="src/cli.py:resolve_profile_for_init_implicit_fallback",
                message="Implicit init fallback on missing default example config",
                data={"error": str(e), "cwd": str(Path.cwd())},
                run_id="post-fix",
            )
            # endregion
            return {}

        # region agent log
        _debug_log(
            hypothesis_id="H4",
            location="src/cli.py:resolve_profile_for_init_unexpected_error",
            message="Implicit init config error is not fallback-eligible",
            data={"error": str(e)},
        )
        # endregion
        print(f"[ERROR] Config error: {e}", file=sys.stderr)
        sys.exit(1)


def _apply_runtime_db_path(config: dict) -> Path:
    from .config import set_db_path

    database = config.get("database", {})
    db_path = database.get("path") if isinstance(database, dict) else None
    return set_db_path(profile_db_path=db_path)


def main():
    parser = argparse.ArgumentParser(
        prog="sample-brain",
        description="Sample Brain CLI (argparse) – stabile Commands ohne Typer/Click.",
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
    sub.add_parser("init", help="DB und Verzeichnisse initialisieren")

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
    p_aut = sub.add_parser(
        "autotype", help="Audio-basierte Typisierung -> features.pred_type"
    )
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
    p_emb.add_argument(
        "--limit", type=int, default=None, help="Nur X Dateien einbetten"
    )
    p_emb.add_argument("--all", action="store_true", help="Alle neu berechnen")
    p_emb.add_argument(
        "--backend",
        choices=["noop", "clap"],
        default=None,
        help="Embedding backend to use. Overrides profile/env config. Defaults to configured backend or noop.",
    )

    # (optional) index_build
    p_idx = sub.add_parser("index_build", help="Index aus Embeddings bauen (optional)")
    p_idx.add_argument(
        "--model-id",
        type=int,
        default=None,
        help="Embedding model ID (required).",
    )
    p_idx.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Max embeddings to load.",
    )
    p_idx.add_argument(
        "--save",
        action="store_true",
        help="Persist index to data/indexes/ as .npz file.",
    )
    p_idx.add_argument(
        "--index-path",
        type=str,
        default=None,
        help="Custom path for saved index file. Implies --save.",
    )

    # (optional) search
    p_src = sub.add_parser("search", help="Ähnlichkeitssuche (optional)")
    p_src.add_argument("query", nargs="?", default=None, help="Text Suchanfrage")
    p_src.add_argument(
        "--query-audio",
        type=str,
        default=None,
        help="Pfad zu einer Referenz-Audiodatei für Audio-zu-Audio Suche.",
    )
    p_src.add_argument("--topk", type=int, default=10)
    p_src.add_argument(
        "--model-id",
        type=int,
        default=None,
        help="Embedding model ID (required).",
    )
    p_src.add_argument(
        "--backend",
        choices=["noop", "clap"],
        default=None,
        help="Embedding backend to use. Overrides profile config. Defaults to configured backend or noop.",
    )
    p_src.add_argument(
        "--index-path",
        type=str,
        default=None,
        help="Path to a saved .npz index file. If not provided, index is built from DB.",
    )
    p_src.add_argument(
        "--target-bpm",
        type=float,
        default=None,
        help="Target BPM for hybrid reranking (default metadata weight 0.5 when set).",
    )
    p_src.add_argument(
        "--target-key",
        type=str,
        default=None,
        help="Target musical key for hybrid reranking (default metadata weight 0.5 when set).",
    )
    p_src.add_argument(
        "--target-type",
        type=str,
        default=None,
        help="Target pred_type for hybrid reranking (default metadata weight 0.5 when set).",
    )
    p_src.add_argument(
        "--semantic-weight",
        type=float,
        default=1.0,
        help="Weight for semantic similarity in hybrid score (default: 1.0).",
    )
    p_src.add_argument(
        "--bpm-weight",
        type=float,
        default=0.0,
        help="Weight for BPM match in hybrid score (default: 0.0, or 0.5 when --target-bpm is set).",
    )
    p_src.add_argument(
        "--key-weight",
        type=float,
        default=0.0,
        help="Weight for key match in hybrid score (default: 0.0, or 0.5 when --target-key is set).",
    )
    p_src.add_argument(
        "--type-weight",
        type=float,
        default=0.0,
        help="Weight for type match in hybrid score (default: 0.0, or 0.5 when --target-type is set).",
    )
    p_src.add_argument(
        "--bpm-tolerance",
        type=float,
        default=8.0,
        help="BPM distance tolerance for partial BPM match scoring (default: 8.0).",
    )

    args = parser.parse_args()

    # Imports hier drin, damit das Skript startet, auch wenn einzelne Module fehlen.
    if args.cmd == "init":
        # region agent log
        _debug_log(
            hypothesis_id="H5",
            location="src/cli.py:init_entry",
            message="Entered init command path",
            data={
                "config_arg": args.config,
                "profile_arg": args.profile,
                "cwd": str(Path.cwd()),
            },
        )
        # endregion
        cfg = _resolve_profile_for_init(args)
        db_path = _apply_runtime_db_path(cfg)
        # region agent log
        _debug_log(
            hypothesis_id="H6",
            location="src/cli.py:init_db_path_applied",
            message="Init runtime DB path resolved",
            data={"resolved_db_path": str(db_path)},
            run_id="post-fix",
        )
        # endregion
        from .db import init_db

        init_db()
        print(f"DB ready: {db_path}")
        return

    if args.cmd == "scan":
        cfg = _resolve_profile_or_exit(args)
        _apply_runtime_db_path(cfg)
        if args.root:
            roots = [Path(r) for r in args.root]
        else:
            roots = [Path(r) for r in cfg.get("library_roots", [])]
        from .scan import run_scan

        run_scan(roots)
        print("Scan completed.")
        return

    if args.cmd == "analyze":
        cfg = _resolve_profile_or_exit(args)
        _apply_runtime_db_path(cfg)
        try:
            from .analyze import run_analyze
        except Exception as e:
            print(f"[ERROR] Analyze-Modul fehlt/fehlerhaft: {e}", file=sys.stderr)
            sys.exit(1)
        run_analyze()
        print("Analyze completed.")
        return

    if args.cmd == "autotype":
        cfg = _resolve_profile_or_exit(args)
        _apply_runtime_db_path(cfg)
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
        cfg = _resolve_profile_or_exit(args)
        _apply_runtime_db_path(cfg)
        fl_user_data = args.fl_user_data or cfg.get("fl_user_data_path")
        if not fl_user_data:
            print(
                "[ERROR] No FL Studio User Data path configured. Use --fl-user-data or set fl_user_data_path in your profile.",
                file=sys.stderr,
            )
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
        cfg = _resolve_profile_or_exit(args)
        _apply_runtime_db_path(cfg)
        try:
            from .embed import run_embed
        except Exception as e:
            print(f"[WARN] Embeddings übersprungen (Modul fehlt/fehlerhaft): {e}")
            sys.exit(0)
        configured_backend = cfg.get("embedding", {}).get("backend", "noop")
        backend_name = args.backend or configured_backend or "noop"
        run_embed(
            limit=args.limit, only_missing=not args.all, backend_name=backend_name
        )
        print("Embeddings completed.")
        return

    if args.cmd == "index_build":
        cfg = _resolve_profile_or_exit(args)
        _apply_runtime_db_path(cfg)
        try:
            from .index import build_index
        except Exception as e:
            print(f"[WARN] Index übersprungen (Modul fehlt/fehlerhaft): {e}")
            sys.exit(0)
        save = args.save or args.index_path is not None
        build_index(
            model_id=args.model_id,
            limit=args.limit,
            save=save,
            index_path=args.index_path,
        )
        return

    if args.cmd == "search":
        cfg = _resolve_profile_or_exit(args)
        _apply_runtime_db_path(cfg)
        try:
            from .search import hybrid_query_from_cli_args, run_search
        except Exception as e:
            print(f"[ERROR] Search nicht verfügbar: {e}", file=sys.stderr)
            sys.exit(1)
        configured_backend = cfg.get("embedding", {}).get("backend", "noop")
        backend_name = args.backend or configured_backend or "noop"
        run_search(
            query=args.query,
            query_audio=args.query_audio,
            model_id=args.model_id,
            topk=args.topk,
            backend_name=backend_name,
            index_path=args.index_path,
            hybrid_query=hybrid_query_from_cli_args(args),
        )
        return


if __name__ == "__main__":
    main()
