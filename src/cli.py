# src/cli.py
from __future__ import annotations
import argparse
import json
from pathlib import Path
import sys
import time


def _examples_epilog(*lines: str) -> str:
    body = "\n".join(f"  {line}" for line in lines)
    return f"\nExamples:\n{body}\n"


def _agent_parser_kwargs(*examples: str) -> dict:
    kwargs: dict = {"formatter_class": argparse.RawDescriptionHelpFormatter}
    if examples:
        kwargs["epilog"] = _examples_epilog(*examples)
    return kwargs


_COMMAND_EXAMPLES: dict[tuple[str, ...], list[str]] = {
    (): [
        "sample-brain init",
        "sample-brain scan --root ./samples",
    ],
    ("init",): [
        "sample-brain init",
    ],
    ("scan",): [
        "sample-brain scan",
        "sample-brain scan --root ./samples --root ./packs",
        "sample-brain scan --root ./samples --dry-run",
    ],
    ("analyze",): [
        "sample-brain analyze",
        "sample-brain analyze --all",
    ],
    ("context", "analyze"): [
        "sample-brain context analyze track.wav",
        "sample-brain context analyze track.wav --json",
    ],
    ("pond5", "prepare"): [
        "sample-brain pond5 prepare track.wav --output ./pond5-bundle",
        "sample-brain pond5 prepare track.wav --output ./out --overrides-json overrides.json",
    ],
    ("deconstruct",): [
        "sample-brain deconstruct track.wav --pack-root ./pack-out",
        "sample-brain deconstruct track.wav --pack-root ./pack-out --live-profile",
        "sample-brain deconstruct track.wav --pack-root ./pack-out --dry-run",
    ],
    ("autotype",): [
        "sample-brain autotype",
        "sample-brain autotype --no-knn",
    ],
    ("export_fl",): [
        "sample-brain export_fl --fl-user-data ./fl-user-data",
        "sample-brain export_fl --fl-user-data ./fl-user-data --dry-run",
    ],
    ("match",): [
        "sample-brain match --target-bpm 128",
        "sample-brain match --target-bpm 128 --target-key Cm --desired-type kick",
    ],
    ("embed",): [
        "sample-brain embed",
        "sample-brain embed --backend clap --limit 100",
    ],
    ("index_build",): [
        "sample-brain index_build --model-id 1 --save",
        "sample-brain index_build --model-id 1 --search-backend sqlite-vec",
    ],
    ("search",): [
        'sample-brain search "kick drum" --model-id 1',
        "sample-brain search --query-audio reference.wav --model-id 1 --topk 20",
    ],
    ("db", "doctor"): [
        "sample-brain db doctor",
    ],
    ("vec", "status"): [
        "sample-brain vec status",
        "sample-brain vec status --json",
    ],
    ("vec", "smoke"): [
        "sample-brain vec smoke",
    ],
    ("pack-import",): [
        "sample-brain pack-import ./performance-pack",
        "sample-brain pack-import ./performance-pack --dry-run",
    ],
}


def _infer_command_path(argv: list[str]) -> tuple[str, ...]:
    known = {
        "init",
        "scan",
        "analyze",
        "context",
        "pond5",
        "deconstruct",
        "autotype",
        "export_fl",
        "match",
        "embed",
        "index_build",
        "search",
        "db",
        "benchmark",
        "vec",
        "workbench",
        "pack-import",
    }
    nested = {
        "analyze",
        "prepare",
        "doctor",
        "status",
        "smoke",
        "bpm-evidence",
        "key-conf-evidence",
        "vec",
        "search-quality",
    }
    path: list[str] = []
    i = 1
    while i < len(argv):
        token = argv[i]
        if token.startswith("-"):
            i += 1
            continue
        if token not in known and token not in nested:
            break
        path.append(token)
        i += 1
    return tuple(path)


class AgentFriendlyArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        cmd_path = _infer_command_path(sys.argv)
        examples = _COMMAND_EXAMPLES.get(cmd_path)
        if examples and "required" in message:
            print(f"Error: {message}", file=sys.stderr)
            print("\nExamples:", file=sys.stderr)
            for line in examples:
                print(f"  {line}", file=sys.stderr)
            self.exit(2)
        self.print_usage(sys.stderr)
        print(f"sample-brain: error: {message}", file=sys.stderr)
        self.exit(2)


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
    parser = AgentFriendlyArgumentParser(
        prog="sample-brain",
        description="Sample Brain CLI (argparse) – stabile Commands ohne Typer/Click.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=_examples_epilog(
            "sample-brain init",
            "sample-brain scan --root ./samples",
        ),
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
    sub = parser.add_subparsers(
        dest="cmd", required=True, parser_class=AgentFriendlyArgumentParser
    )

    # init
    sub.add_parser(
        "init",
        help="DB und Verzeichnisse initialisieren",
        **_agent_parser_kwargs("sample-brain init"),
    )

    # scan
    p_scan = sub.add_parser(
        "scan",
        help="Samples scannen und in DB registrieren",
        **_agent_parser_kwargs(
            "sample-brain scan",
            "sample-brain scan --root ./samples --root ./packs",
            "sample-brain scan --root ./samples --dry-run",
        ),
    )
    p_scan.add_argument(
        "--root",
        action="append",
        default=None,
        help="Library root to scan. Can be provided multiple times. Overrides configured library_roots.",
    )
    p_scan.add_argument(
        "--dry-run",
        action="store_true",
        help="Discover/plan catalog upserts without writing to the SQLite catalog.",
    )

    # analyze
    p_analyze = sub.add_parser(
        "analyze",
        help="Audio-Features (librosa) berechnen",
        **_agent_parser_kwargs(
            "sample-brain analyze",
            "sample-brain analyze --all",
        ),
    )
    p_analyze.add_argument(
        "--all",
        action="store_true",
        help="Alle Samples neu analysieren (nicht nur fehlende). Expliziter Reanalyse-Weg.",
    )

    # context analyze (DB-free one-shot file analysis)
    p_context = sub.add_parser(
        "context", help="Lokale Kontextdatei ohne Katalog analysieren"
    )
    context_sub = p_context.add_subparsers(
        dest="context_cmd", required=True, parser_class=AgentFriendlyArgumentParser
    )
    p_context_analyze = context_sub.add_parser(
        "analyze",
        help="Eine WAV- oder FLAC-Datei als Track Map v1 analysieren",
        **_agent_parser_kwargs(
            "sample-brain context analyze track.wav",
            "sample-brain context analyze track.wav --json",
        ),
    )
    p_context_analyze.add_argument("path", help="Path to a local WAV or FLAC file.")
    p_context_analyze.add_argument(
        "--json", action="store_true", help="Emit deterministic Track Map v1 JSON."
    )
    p_context_analyze.add_argument(
        "--track-cache-dir",
        default=None,
        help="Override the Track Analysis cache directory (default: user-local, outside repo).",
    )
    p_context_analyze.add_argument(
        "--no-track-cache",
        action="store_true",
        help="Disable the Track Analysis cache; always recompute.",
    )

    # pond5 readiness bundle
    p_pond5 = sub.add_parser("pond5", help="Pond5 readiness metadata locally prepare")
    pond5_sub = p_pond5.add_subparsers(
        dest="pond5_cmd", required=True, parser_class=AgentFriendlyArgumentParser
    )
    p_pond5_prepare = pond5_sub.add_parser(
        "prepare",
        help="Build a local Pond5 readiness bundle for one track",
        **_agent_parser_kwargs(
            "sample-brain pond5 prepare track.wav --output ./pond5-bundle",
            "sample-brain pond5 prepare track.wav --output ./out --overrides-json overrides.json",
        ),
    )
    p_pond5_prepare.add_argument("path", help="Path to the local source track.")
    p_pond5_prepare.add_argument(
        "--output", required=True, help="Directory for the local readiness bundle."
    )
    p_pond5_prepare.add_argument(
        "--track-cache-dir",
        default=None,
        help="Override the Track Analysis cache directory (default: user-local, outside repo).",
    )
    p_pond5_prepare.add_argument(
        "--no-track-cache",
        action="store_true",
        help="Disable the Track Analysis cache; always recompute.",
    )
    p_pond5_prepare.add_argument(
        "--overrides-json",
        default=None,
        help="Optional local JSON file containing per-track Pond5 contributor/rights overrides.",
    )

    # deconstruct
    p_deconstruct = sub.add_parser(
        "deconstruct",
        help="Track headless deconstructen und Pack-Artefakte erzeugen",
        **_agent_parser_kwargs(
            "sample-brain deconstruct track.wav --pack-root ./pack-out",
            "sample-brain deconstruct track.wav --pack-root ./pack-out --live-profile",
            "sample-brain deconstruct track.wav --pack-root ./pack-out --dry-run",
        ),
    )
    p_deconstruct.add_argument("path", help="Path to the local source track.")
    p_deconstruct.add_argument(
        "--pack-root",
        required=True,
        help="Output root for the Track Deconstruction run.",
    )
    p_deconstruct.add_argument(
        "--dry-run",
        action="store_true",
        help="Plan deconstruct steps and artifacts without writing pack outputs.",
    )
    p_deconstruct.add_argument(
        "--skip-arrangement",
        action="store_true",
        help="Skip the optional arrangement step.",
    )
    stem_group = p_deconstruct.add_mutually_exclusive_group()
    stem_group.add_argument(
        "--stems",
        action="store_true",
        help=(
            "EXPERIMENTAL / research-only: enable optional stem separation. "
            "Demucs weights are RESEARCH_ONLY / commercial use NOT granted. "
            "Requires --stem-model and --stem-weight-hash."
        ),
    )
    stem_group.add_argument(
        "--skip-stems",
        action="store_true",
        help="Skip the optional stems step (this is the default behavior).",
    )
    p_deconstruct.add_argument(
        "--stem-model",
        default=None,
        help="Stem model filename, e.g. htdemucs.yaml or htdemucs_ft.yaml.",
    )
    p_deconstruct.add_argument(
        "--stem-weight-hash",
        default=None,
        help="Actual cryptographic hash of the loaded weight file/set (truthful provenance).",
    )
    p_deconstruct.add_argument(
        "--stem-weight-hash-algo",
        default="sha256",
        help="Hash algorithm for --stem-weight-hash (sha256 for htdemucs, sha256-set-v1 for htdemucs_ft).",
    )
    p_deconstruct.add_argument(
        "--stem-cache-dir",
        default=None,
        help="Override the user-local stem cache directory.",
    )
    p_deconstruct.add_argument(
        "--no-stem-cache",
        action="store_true",
        help="Disable the global stem cache; always run separation.",
    )
    p_deconstruct.add_argument(
        "--stem-model-cache-dir",
        default=None,
        help="Optional model cache directory passed to the separation backend.",
    )
    p_deconstruct.add_argument(
        "--beat-backend",
        default="auto",
        help="Beat backend passed to Track Deconstruction.",
    )
    p_deconstruct.add_argument(
        "--bpm-normalization",
        default="none",
        help="BPM normalization passed to Track Deconstruction.",
    )
    p_deconstruct.add_argument(
        "--no-resume",
        action="store_true",
        help="Disable pack-level resume (overwrite existing step outputs).",
    )
    p_deconstruct.add_argument(
        "--track-cache-dir",
        default=None,
        help="Override the Track Analysis cache directory (default: user-local, outside repo).",
    )
    p_deconstruct.add_argument(
        "--no-track-cache",
        action="store_true",
        help="Disable the Track Analysis cache for the track_map step; always recompute.",
    )
    # --- #374 live performance layout (user-specified before deconstruction) ---
    p_deconstruct.add_argument(
        "--live-profile",
        action="store_true",
        help="Emit a compact live-performance layout (live/live_layout.json) instead of only generic candidates.",
    )
    p_deconstruct.add_argument(
        "--live-kick-bass",
        dest="live_kick_bass",
        action="store_true",
        default=True,
        help="Include a kick_bass playable loop (default: on).",
    )
    p_deconstruct.add_argument(
        "--no-live-kick-bass",
        dest="live_kick_bass",
        action="store_false",
        help="Omit the kick_bass playable loop.",
    )
    p_deconstruct.add_argument(
        "--live-drums-states",
        type=int,
        choices=(1, 2),
        default=1,
        help="Number of drum performance states (1 = drums_present; 2 adds an evidenced drums_reduced).",
    )
    p_deconstruct.add_argument(
        "--live-vocals",
        dest="live_vocals",
        action="store_true",
        default=True,
        help="Include a full-length vocal arrangement track (default: on).",
    )
    p_deconstruct.add_argument(
        "--no-live-vocals",
        dest="live_vocals",
        action="store_false",
        help="Omit the full-length vocal arrangement track.",
    )
    p_deconstruct.add_argument(
        "--live-melodic",
        dest="live_melodic",
        action="store_true",
        default=True,
        help="Include a full-length melodic/instrument arrangement track (default: on).",
    )
    p_deconstruct.add_argument(
        "--no-live-melodic",
        dest="live_melodic",
        action="store_false",
        help="Omit the full-length melodic/instrument arrangement track.",
    )
    p_deconstruct.add_argument(
        "--live-fx",
        dest="live_fx",
        action="store_true",
        default=True,
        help="Include a full-length FX/atmos arrangement track (default: on).",
    )
    p_deconstruct.add_argument(
        "--no-live-fx",
        dest="live_fx",
        action="store_false",
        help="Omit the full-length FX/atmos arrangement track.",
    )
    p_deconstruct.add_argument(
        "--live-other",
        dest="live_other",
        action="store_true",
        default=False,
        help="Include a full-length other arrangement track.",
    )
    p_deconstruct.add_argument(
        "--no-live-other",
        dest="live_other",
        action="store_false",
        help="Omit the full-length other arrangement track (default).",
    )
    p_deconstruct.add_argument(
        "--live-8bars",
        dest="live_8bars",
        action="store_true",
        default=False,
        help="Allow 8-bar loops when at least 8 bars are available (default: 4-bar loops only).",
    )

    # autotype
    p_aut = sub.add_parser(
        "autotype",
        help="Audio-basierte Typisierung -> features.pred_type",
        **_agent_parser_kwargs(
            "sample-brain autotype",
            "sample-brain autotype --no-knn",
        ),
    )
    p_aut.add_argument("--no-knn", action="store_true", help="kNN/Seeds deaktivieren")

    # export_fl
    p_exp = sub.add_parser(
        "export_fl",
        help="FL Studio Browser Tags schreiben",
        **_agent_parser_kwargs(
            "sample-brain export_fl --fl-user-data ./fl-user-data",
            "sample-brain export_fl --fl-user-data ./fl-user-data --dry-run",
        ),
    )
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
    p_exp.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview FL Browser tag export without writing Tags files.",
    )

    # match
    p_match = sub.add_parser(
        "match",
        help="Katalogbasiertes Matching gegen Zielprofil",
        **_agent_parser_kwargs(
            "sample-brain match --target-bpm 128",
            "sample-brain match --target-bpm 128 --target-key Cm --desired-type kick",
        ),
    )
    p_match.add_argument(
        "--target-bpm",
        type=float,
        required=True,
        help="Target BPM for catalog matching.",
    )
    p_match.add_argument(
        "--target-key",
        type=str,
        default=None,
        help="Optional target key for catalog matching.",
    )
    p_match.add_argument(
        "--desired-type",
        type=str,
        default=None,
        help="Optional desired pred_type for catalog matching.",
    )
    p_match.add_argument(
        "--limit",
        type=int,
        default=10,
        help="Maximum number of ranked matches to print (default: 10).",
    )

    # (optional) embed
    p_emb = sub.add_parser(
        "embed",
        help="Embeddings berechnen (optional)",
        **_agent_parser_kwargs(
            "sample-brain embed",
            "sample-brain embed --backend clap --limit 100",
        ),
    )
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
    p_idx = sub.add_parser(
        "index_build",
        help="Index aus Embeddings bauen (optional)",
        **_agent_parser_kwargs(
            "sample-brain index_build --model-id 1 --save",
            "sample-brain index_build --model-id 1 --search-backend sqlite-vec",
        ),
    )
    p_idx.add_argument(
        "--model-id",
        type=int,
        required=True,
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
    p_idx.add_argument(
        "--search-backend",
        choices=["numpy", "sqlite-vec"],
        default=None,
        help="Vector search cache backend. Overrides profile/env search.backend (default: numpy).",
    )

    # (optional) search
    p_src = sub.add_parser(
        "search",
        help="Ähnlichkeitssuche (optional)",
        **_agent_parser_kwargs(
            'sample-brain search "kick drum" --model-id 1',
            "sample-brain search --query-audio reference.wav --model-id 1 --topk 20",
        ),
    )
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
        "--search-backend",
        choices=["numpy", "sqlite-vec"],
        default=None,
        help="Vector search backend. Overrides profile/env search.backend (default: numpy).",
    )
    p_src.add_argument(
        "--index-path",
        type=str,
        default=None,
        help="Path to a saved .npz index file (numpy backend only).",
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
    p_src.add_argument(
        "--tag",
        action="append",
        default=[],
        help="Filter results to samples tagged with this value (repeatable).",
    )
    p_src.add_argument(
        "--min-bpm", type=float, default=None, help="Minimum BPM filter."
    )
    p_src.add_argument(
        "--max-bpm", type=float, default=None, help="Maximum BPM filter."
    )
    p_src.add_argument(
        "--key",
        dest="filter_key",
        default=None,
        help="Exact features.key filter (distinct from hybrid --target-key).",
    )
    p_src.add_argument(
        "--scale",
        default=None,
        help="Key scale filter: major|minor (parsed from features.key).",
    )
    p_src.add_argument(
        "--min-duration",
        type=float,
        default=None,
        help="Minimum sample duration in seconds.",
    )
    p_src.add_argument(
        "--max-duration",
        type=float,
        default=None,
        help="Maximum sample duration in seconds.",
    )
    p_src.add_argument(
        "--pred-type",
        default=None,
        help="Filter by features.pred_type (distinct from hybrid --target-type).",
    )

    p_db = sub.add_parser("db", help="Database diagnostics")
    db_sub = p_db.add_subparsers(
        dest="db_cmd", required=True, parser_class=AgentFriendlyArgumentParser
    )
    db_sub.add_parser(
        "doctor",
        help="Run SQLite integrity and catalog checks",
        **_agent_parser_kwargs("sample-brain db doctor"),
    )

    p_bench = sub.add_parser("benchmark", help="Performance harness (optional)")
    bench_sub = p_bench.add_subparsers(
        dest="bench_cmd", required=True, parser_class=AgentFriendlyArgumentParser
    )
    p_bench_vec = bench_sub.add_parser("vec", help="Benchmark sqlite-vec search paths")
    p_bench_vec.add_argument(
        "--samples",
        type=int,
        nargs="+",
        default=[1000, 10000],
        help="Synthetic sample counts to benchmark (default: 1000 10000).",
    )
    p_bench_vec.add_argument(
        "--quantization",
        choices=["float32", "int8", "binary"],
        default="float32",
        help="Vector quantization strategy for vec0 cache (default: float32).",
    )
    p_bench_vec.add_argument(
        "--partition-strategy",
        choices=["none", "synthetic"],
        default="none",
        help="Partition key strategy (default: none). "
        "'synthetic' creates separate vec0 tables per partition.",
    )
    p_bench_vec.add_argument(
        "--partition-counts",
        type=int,
        nargs="+",
        default=None,
        help="Number of partitions to benchmark (e.g. 10 25 50 100). "
        "Requires --partition-strategy.",
    )
    p_bench_vec.add_argument(
        "--work-dir",
        type=str,
        default=None,
        help="Directory for temporary benchmark databases (default: ./.bench_sqlite_vec).",
    )
    p_bench_quality = bench_sub.add_parser(
        "search-quality",
        help="Evaluate search ranking quality against a golden query suite",
    )
    p_bench_quality.add_argument(
        "--suite",
        type=str,
        default=None,
        help="Path to golden query suite YAML (default: tests/fixtures/search_quality/golden_v1.yaml).",
    )
    p_bench_quality.add_argument(
        "--work-dir",
        type=str,
        default=None,
        help="Directory for temporary benchmark databases (default: ./.bench_search_quality).",
    )
    p_bench_bpm = bench_sub.add_parser(
        "bpm-evidence",
        help="Evaluate BPM half/double detection error rates on synthetic fixtures",
    )
    p_bench_bpm.add_argument(
        "--work-dir",
        type=str,
        default=None,
        help="Directory for temporary fixture WAVs (default: ./.bench_bpm_evidence).",
    )
    p_bench_key_conf = bench_sub.add_parser(
        "key-conf-evidence",
        help="Evaluate key_conf distribution and export threshold on synthetic fixtures",
    )
    p_bench_key_conf.add_argument(
        "--work-dir",
        type=str,
        default=None,
        help="Directory for temporary fixture WAVs (default: ./.bench_key_conf_evidence).",
    )

    # sqlite-vec diagnostics
    p_vec = sub.add_parser("vec", help="sqlite-vec availability diagnostics (optional)")
    vec_sub = p_vec.add_subparsers(
        dest="vec_cmd", required=True, parser_class=AgentFriendlyArgumentParser
    )
    p_vec_status = vec_sub.add_parser(
        "status",
        help="Report sqlite-vec availability",
        **_agent_parser_kwargs(
            "sample-brain vec status",
            "sample-brain vec status --json",
        ),
    )
    p_vec_status.add_argument(
        "--json",
        action="store_true",
        help="Print diagnostics as JSON.",
    )
    vec_sub.add_parser(
        "smoke",
        help="Exit 0 when sqlite-vec loads; exit 1 with diagnostics otherwise.",
        **_agent_parser_kwargs("sample-brain vec smoke"),
    )

    sub.add_parser(
        "workbench",
        help="Lokale Werkbank starten (Playlist-Ansicht, tkinter)",
    )

    p_pack_import = sub.add_parser(
        "pack-import",
        help="Performance-Pack in den Katalog re-importieren (#263)",
        **_agent_parser_kwargs(
            "sample-brain pack-import ./performance-pack",
            "sample-brain pack-import ./performance-pack --dry-run",
        ),
    )
    p_pack_import.add_argument(
        "pack_root",
        help="Performance-Pack Verzeichnis oder direkte manifest.json",
    )
    p_pack_import.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate pack and preview catalog imports without DB writes.",
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
        from .vec_availability import format_availability_message, probe_sqlite_vec

        init_db()
        print(f"DB ready: {db_path}")
        vec_report = probe_sqlite_vec()
        if vec_report.available:
            print(format_availability_message(vec_report))
        else:
            print(
                "[INFO] sqlite-vec optional extra not loaded "
                f"({vec_report.reason}). Install with: pip install -e .[vec]"
            )
        return

    if args.cmd == "scan":
        cfg = _resolve_profile_or_exit(args)
        _apply_runtime_db_path(cfg)
        if args.root:
            roots = [Path(r) for r in args.root]
        else:
            roots = [Path(r) for r in cfg.get("library_roots", [])]
        from .scan import run_scan

        if args.dry_run:
            from .cli_dry_run import build_dry_run_preview, emit_dry_run_preview

            plan = run_scan(roots, dry_run=True)
            preview = build_dry_run_preview(
                command="scan",
                action="catalog_sample_upsert",
                target_kind="sqlite_catalog",
                planned_mutations={
                    "roots_configured": plan["roots_configured"],
                    "sample_upserts": plan["sample_upserts"],
                    "discovered_count": plan["sample_upserts"],
                },
                skipped_or_prevented_writes=[
                    "init_db",
                    "samples_table_upsert",
                    "_flush_scan_batch",
                ],
                validation={
                    "status": "ok",
                    "warning": plan.get("warning"),
                },
            )
            emit_dry_run_preview(preview)
            return

        run_scan(roots)
        print("Scan completed.")
        return

    if args.cmd == "analyze":
        cfg = _resolve_profile_or_exit(args)
        _apply_runtime_db_path(cfg)
        bpm_normalization = cfg.get("analyze", {}).get("bpm_normalization", "none")
        try:
            from .analyze import run_analyze
        except Exception as e:
            print(f"[ERROR] Analyze-Modul fehlt/fehlerhaft: {e}", file=sys.stderr)
            sys.exit(1)
        run_analyze(bpm_normalization=bpm_normalization, only_missing=not args.all)
        print("Analyze completed.")
        return

    if args.cmd == "context":
        if args.context_cmd == "analyze":
            from .context_analyze import (
                ContextAnalyzeError,
                analyze_context_file_cached,
            )

            try:
                result = analyze_context_file_cached(
                    Path(args.path),
                    cache_dir=args.track_cache_dir,
                    enabled=not args.no_track_cache,
                )
            except ContextAnalyzeError as exc:
                print(
                    json.dumps(
                        {
                            "status": "error",
                            "error": {"code": exc.code, "message": exc.message},
                        },
                        sort_keys=True,
                    ),
                    file=sys.stderr,
                )
                sys.exit(2)
            print(
                json.dumps(result.track_map, indent=2, sort_keys=True, allow_nan=False)
            )
            return

    if args.cmd == "pond5":
        if args.pond5_cmd == "prepare":
            from .context_analyze import ContextAnalyzeError, analyze_context_file_cached
            from .config_loader import ConfigError
            from .pond5_profile import resolve_pond5_profile
            from .pond5_readiness import build_pond5_bundle, write_pond5_bundle
            from .stock_music_analysis import produce_stock_music_analysis

            cfg = _resolve_profile_or_exit(args)
            overrides = None
            if args.overrides_json:
                try:
                    overrides = json.loads(
                        Path(args.overrides_json).read_text(encoding="utf-8")
                    )
                except (OSError, json.JSONDecodeError) as exc:
                    print(f"[ERROR] Invalid Pond5 overrides JSON: {exc}", file=sys.stderr)
                    sys.exit(2)
            try:
                result = analyze_context_file_cached(
                    Path(args.path),
                    cache_dir=args.track_cache_dir,
                    enabled=not args.no_track_cache,
                )
                semantic = produce_stock_music_analysis(result.track_map)
                profile = resolve_pond5_profile(
                    cfg, per_track_overrides=overrides
                )
                bundle = build_pond5_bundle(
                    result.track_map,
                    semantic,
                    profile,
                    source_path=Path(args.path),
                )
                write_pond5_bundle(bundle, Path(args.output))
            except (ContextAnalyzeError, ConfigError, OSError, ValueError) as exc:
                code = getattr(exc, "code", "POND5_PREPARE_FAILED")
                print(
                    json.dumps(
                        {"status": "error", "error": {"code": code, "message": str(exc)}},
                        sort_keys=True,
                    ),
                    file=sys.stderr,
                )
                sys.exit(2)
            readiness = bundle["readiness"]
            print(json.dumps(readiness, indent=2, sort_keys=True, allow_nan=False))
            sys.exit(0 if readiness["readiness"]["status"] == "POND5_READY" else 3)

    if args.cmd == "deconstruct":
        from .deconstruct import plan_deconstruct, run_deconstruct
        from .performance_pack import finalize_performance_pack

        skip = set()
        if args.skip_arrangement:
            skip.add("arrangement")
        if args.skip_stems:
            skip.add("stems")

        stems_enabled = bool(args.stems)
        stem_model = args.stem_model if stems_enabled else None
        stem_weight_hash = None
        if stems_enabled and args.stem_weight_hash:
            stem_weight_hash = {
                "algorithm": args.stem_weight_hash_algo,
                "value": args.stem_weight_hash,
            }

        if stems_enabled and not stem_model:
            print(
                "ERROR: --stems requires --stem-model (e.g. htdemucs.yaml).",
                file=sys.stderr,
            )
            sys.exit(2)
        if stems_enabled and not args.stem_weight_hash:
            print(
                "ERROR: --stems requires --stem-weight-hash (actual verified weight identity).",
                file=sys.stderr,
            )
            sys.exit(2)

        pack_root = Path(args.pack_root)
        if args.dry_run:
            from .cli_dry_run import build_dry_run_preview, emit_dry_run_preview

            plan = plan_deconstruct(
                Path(args.path),
                pack_root,
                bpm_normalization=args.bpm_normalization,
                beat_backend=args.beat_backend,
                skip=skip,
                stems_enabled=stems_enabled,
                stem_model=stem_model,
            )
            preview = build_dry_run_preview(
                command="deconstruct",
                action="performance_pack_deconstruct",
                target_kind="performance_pack",
                planned_mutations={
                    "steps": plan["steps"],
                    "artifacts": plan["artifacts"],
                    "stems_enabled": plan["stems_enabled"],
                },
                skipped_or_prevented_writes=[
                    "pack_root_mkdir",
                    "deconstruct_run.json",
                    "analysis_and_asset_artifacts",
                    "resume_state",
                    "finalize_performance_pack",
                    "run_deconstruct",
                ],
                validation={
                    "status": "ok",
                    "track_exists": plan["track"]["exists"],
                },
                track=plan["track"],
                pack_root_name=plan["pack_root_name"],
            )
            emit_dry_run_preview(preview)
            return

        live_profile_config = None
        if getattr(args, "live_profile", False):
            from src.live_profile import LiveLayoutConfig

            live_profile_config = LiveLayoutConfig(
                kick_bass=args.live_kick_bass,
                drums_states=args.live_drums_states,
                vocals_full=args.live_vocals,
                melodic_full=args.live_melodic,
                fx_full=args.live_fx,
                other_full=args.live_other,
                allow_8_bars=args.live_8bars,
            )
        result = run_deconstruct(
            Path(args.path),
            pack_root,
            bpm_normalization=args.bpm_normalization,
            beat_backend=args.beat_backend,
            skip=skip,
            resume=not args.no_resume,
            track_cache_dir=args.track_cache_dir,
            track_cache_enabled=not args.no_track_cache,
            stems_enabled=stems_enabled,
            stem_model=stem_model,
            stem_weight_hash=stem_weight_hash,
            stem_cache_dir=args.stem_cache_dir,
            stem_cache_enabled=not args.no_stem_cache,
            stem_model_cache_dir=args.stem_model_cache_dir,
            live_profile_config=live_profile_config,
        )

        pack_root.mkdir(parents=True, exist_ok=True)
        payload = result.to_dict()
        (pack_root / "deconstruct_run.json").write_text(
            json.dumps(
                payload,
                indent=2,
                sort_keys=True,
                allow_nan=False,
            ),
            encoding="utf-8",
        )
        print(
            json.dumps(
                payload,
                indent=2,
                sort_keys=True,
                allow_nan=False,
            )
        )

        # #260: Assemble Performance Pack manifest after successful deconstruct
        if result.status != "failed":
            finalize_performance_pack(result, pack_root)

        sys.exit(2 if result.status == "failed" else 0)

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
        if args.dry_run:
            from .cli_dry_run import build_dry_run_preview, emit_dry_run_preview

            plan = run_export(fl_user_data, max_tags=max_tags, roots=roots, dry_run=True)
            preview = build_dry_run_preview(
                command="export_fl",
                action="fl_browser_tags_export",
                target_kind="fl_browser_tags",
                planned_mutations={
                    "sample_rows": plan["sample_rows"],
                    "max_tags": plan["max_tags"],
                    "roots_configured": plan["roots_configured"],
                    "tags_relpath": plan["tags_relpath"],
                },
                skipped_or_prevented_writes=[
                    "fl_browser_tags_mkdir",
                    "FL Studio/Settings/Browser/Tags",
                    "write_fl_tags_from_sample_rows",
                    "_atomic_write_text",
                ],
            )
            emit_dry_run_preview(preview)
            return
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
            from .config_loader import resolve_search_backend
        except Exception as e:
            print(f"[WARN] Index übersprungen (Modul fehlt/fehlerhaft): {e}")
            sys.exit(0)
        save = args.save or args.index_path is not None
        search_backend = resolve_search_backend(
            cli_value=args.search_backend,
            config=cfg,
            env=dict(__import__("os").environ),
        )
        build_index(
            model_id=args.model_id,
            limit=args.limit,
            save=save,
            index_path=args.index_path,
            search_backend=search_backend,
        )
        return

    if args.cmd == "search":
        cfg = _resolve_profile_or_exit(args)
        _apply_runtime_db_path(cfg)
        try:
            from .search import hybrid_query_from_cli_args, run_search
            from .search_filters import search_filters_from_cli_args
            from .config_loader import resolve_search_backend
            from .vec_availability import probe_sqlite_vec
        except Exception as e:
            print(f"[ERROR] Search nicht verfügbar: {e}", file=sys.stderr)
            sys.exit(1)
        configured_backend = cfg.get("embedding", {}).get("backend", "noop")
        backend_name = args.backend or configured_backend or "noop"
        search_backend = resolve_search_backend(
            cli_value=args.search_backend,
            config=cfg,
            env=dict(__import__("os").environ),
        )
        if search_backend == "sqlite-vec":
            vec_report = probe_sqlite_vec()
            if not vec_report.available:
                print(
                    "[WARN] sqlite-vec selected but unavailable; "
                    "install with: pip install -e .[vec]"
                )
        sys.exit(
            run_search(
                query=args.query,
                query_audio=args.query_audio,
                model_id=args.model_id,
                topk=args.topk,
                backend_name=backend_name,
                search_backend=search_backend,
                index_path=args.index_path,
                hybrid_query=hybrid_query_from_cli_args(args),
                search_filters=search_filters_from_cli_args(args),
            )
        )

    if args.cmd == "match":
        cfg = _resolve_profile_or_exit(args)
        _apply_runtime_db_path(cfg)
        try:
            from .matching import run_match
        except Exception as e:
            print(f"[ERROR] Matching nicht verfügbar: {e}", file=sys.stderr)
            sys.exit(1)
        run_match(
            target_bpm=args.target_bpm,
            target_key=args.target_key,
            desired_type=args.desired_type,
            limit=args.limit,
        )
        return

    if args.cmd == "db":
        cfg = _resolve_profile_or_exit(args)
        _apply_runtime_db_path(cfg)
        if args.db_cmd == "doctor":
            from .db_doctor import print_db_doctor_report, run_db_doctor

            sys.exit(print_db_doctor_report(run_db_doctor()))
        return

    if args.cmd == "benchmark":
        if args.bench_cmd == "bpm-evidence":
            from .bpm_evidence import run_cli_bpm_evidence

            work_dir = (
                Path(args.work_dir) if args.work_dir else Path(".bench_bpm_evidence")
            )
            run_cli_bpm_evidence(work_dir)
            return

        if args.bench_cmd == "key-conf-evidence":
            from .key_conf_evidence import run_cli_key_conf_evidence

            work_dir = (
                Path(args.work_dir)
                if args.work_dir
                else Path(".bench_key_conf_evidence")
            )
            run_cli_key_conf_evidence(work_dir)
            return

        cfg = _resolve_profile_or_exit(args)
        _apply_runtime_db_path(cfg)
        if args.bench_cmd == "vec":
            from .benchmark_vec import print_benchmark_report, run_vec_benchmark

            work_dir = Path(args.work_dir) if args.work_dir else None
            try:
                results = run_vec_benchmark(
                    sample_counts=args.samples,
                    quantization=args.quantization,
                    partition_counts=args.partition_counts,
                    partition_strategy=args.partition_strategy,
                    work_dir=work_dir,
                )
            except RuntimeError as exc:
                print(f"[ERROR] {exc}", file=sys.stderr)
                sys.exit(1)
            print_benchmark_report(results)
            return
        if args.bench_cmd == "search-quality":
            from .benchmark_search_quality import (
                DEFAULT_SUITE_PATH,
                print_search_quality_report,
                run_search_quality_benchmark,
            )
            from .embed import EmbeddingBackendUnavailableError

            suite_path = Path(args.suite) if args.suite else DEFAULT_SUITE_PATH
            work_dir = Path(args.work_dir) if args.work_dir else None
            try:
                result = run_search_quality_benchmark(
                    suite_path,
                    work_dir=work_dir,
                )
            except (OSError, ValueError, EmbeddingBackendUnavailableError) as exc:
                print(f"[ERROR] {exc}", file=sys.stderr)
                sys.exit(1)
            print_search_quality_report(result)
            if any(row.error is not None for row in result.query_results):
                sys.exit(1)
            if result.tier == "A" and not all(result.threshold_pass().values()):
                sys.exit(1)
            if result.tier not in {"A", "B"}:
                sys.exit(1)
            return
        return

    if args.cmd == "vec":
        from .vec_availability import format_availability_message, probe_sqlite_vec

        report = probe_sqlite_vec()
        if args.vec_cmd == "status":
            if args.json:
                print(json.dumps(report.to_dict(), indent=2, sort_keys=True))
            else:
                print(format_availability_message(report))
                print(f"python={report.python_version}")
                print(f"sqlite={report.sqlite_version}")
                print(f"package_installed={report.package_installed}")
                print(f"extension_loaded={report.extension_loaded}")
            return

        if args.vec_cmd == "smoke":
            print(format_availability_message(report))
            if not report.available:
                sys.exit(1)
            return

    if args.cmd == "workbench":
        try:
            from .workbench import run_workbench
        except ImportError as e:
            print(
                f"[ERROR] Workbench UI nicht verfügbar (tkinter fehlt?): {e}",
                file=sys.stderr,
            )
            sys.exit(1)
        run_workbench()
        return

    if args.cmd == "pack-import":
        cfg = _resolve_profile_or_exit(args)
        _apply_runtime_db_path(cfg)
        from .performance_pack_import import PackImportError, run_pack_import

        try:
            result = run_pack_import(Path(args.pack_root), dry_run=bool(args.dry_run))
        except PackImportError as exc:
            print(
                f"[ERROR] pack-import failed ({exc.code}): {exc.message}",
                file=sys.stderr,
            )
            sys.exit(2)
        if args.dry_run:
            from .cli_dry_run import build_dry_run_preview, emit_dry_run_preview

            preview = build_dry_run_preview(
                command="pack-import",
                action="performance_pack_catalog_import",
                target_kind="sqlite_catalog",
                planned_mutations={
                    "pack_id": result["pack_id"],
                    "source_track_id": result["source_track_id"],
                    "assets_importable": result["assets_importable"],
                    "assets_skipped": result["assets_skipped"],
                    "stems_importable": result["stems_importable"],
                    "stems_skipped": result["stems_skipped"],
                    "errors": result["errors"],
                },
                skipped_or_prevented_writes=[
                    "init_db",
                    "_register_sample",
                    "sample_tags_lineage",
                    "filesystem_copies",
                ],
            )
            emit_dry_run_preview(preview)
            return
        print(f"Performance Pack re-import: pack_id={result.pack_id}")
        print(
            f"  imported={result.imported} reused={result.reused} "
            f"skipped={result.skipped} failed={len(result.errors)}"
        )
        if result.sample_ids:
            print(f"  sample_ids={result.sample_ids}")
        return


if __name__ == "__main__":
    main()
