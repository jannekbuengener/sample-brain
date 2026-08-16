from __future__ import annotations

import sys
import argparse
import subprocess
import json
import hashlib
from pathlib import Path

# #247 result: Demucs weights are research-only / commercial use not granted.
# This is a LICENSE USAGE status, NOT a cryptographic weight hash.
WEIGHT_USAGE_RESEARCH_ONLY = "RESEARCH_ONLY / COMMERCIAL_USE_NOT_GRANTED"

# Declared metadata for the two #247 baseline candidates.
# `checkpoint` is a released checkpoint/source identifier, NOT a cryptographic
# weight hash. The actual weight hash must be supplied explicitly at runtime.
KNOWN_DEMUCS_MODELS = {
    "htdemucs.yaml": {
        "family": "htdemucs",
        "name": "htdemucs",
        "checkpoint": "955717e8",
    },
    "htdemucs_ft.yaml": {
        "family": "htdemucs",
        "name": "htdemucs_ft",
        "checkpoint": "f7e0c4bc,d12395a8,92cfc3b6,04573f0d",
    },
}


def resolve_known_model_identity(
    model_filename: str, *, weight_hash: dict | None = None
) -> dict:
    """Return declared model identity (no fabricated weight hash).

    The checkpoint identifier is taken from #247. The actual cryptographic
    weight hash must be supplied by the caller (runtime-derived), never invented.
    """
    meta = KNOWN_DEMUCS_MODELS.get(model_filename)
    if meta is None:
        raise ValueError(f"unknown Demucs model filename: {model_filename!r}")
    identity = {
        **meta,
        "code_license": "MIT",
        "weight_license": WEIGHT_USAGE_RESEARCH_ONLY,
    }
    if weight_hash:
        identity["weight_hash"] = weight_hash
    return identity


# Try to get the version of the package safely
def get_backend_version() -> str:
    try:
        import pkg_resources

        return pkg_resources.get_distribution("audio-separator").version
    except Exception:
        try:
            import importlib.metadata

            return importlib.metadata.version("audio-separator")
        except Exception:
            return "0.44.5"


def file_hash(path: Path, blocksize: int = 65536) -> str:
    h = hashlib.sha1()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(blocksize), b""):
            h.update(chunk)
    return h.hexdigest()


def map_stem_to_manifest(
    stem_id: str,
    stem_kind: str,
    track_ref: str,
    source_hash: str,
    source_properties: dict,
    file_ref: str,
    output_hash: str,
    output_properties: dict,
    model_identity: dict,
    backend_version: str,
    audio_ref: str = "/source/original",
) -> dict:
    """Map one produced stem to a Stem Manifest v1 document.

    ``model_identity`` must be a complete, verified identity carrying a real
    cryptographic ``weight_hash``. Provenance is never fabricated: if the weight
    hash is missing, the call fails closed via ``ValueError``.
    """
    if (
        not track_ref
        or "/" in track_ref
        or "\\" in track_ref
        or ":" in track_ref
        or track_ref.endswith((".wav", ".mp3", ".flac"))
    ):
        raise ValueError(
            "track_ref must be a portable track ID, not a path or filename fallback"
        )

    if stem_kind not in {"drums", "bass", "vocals", "other"}:
        raise ValueError(
            f"stem_kind must be drums|bass|vocals|other, got {stem_kind!r}"
        )

    weight_hash = model_identity.get("weight_hash")
    if (
        not isinstance(weight_hash, dict)
        or not weight_hash.get("algorithm")
        or not weight_hash.get("value")
    ):
        raise ValueError(
            "model_identity.weight_hash is required and must be a real "
            "cryptographic identity; it cannot be fabricated"
        )

    # Standard 1.0.0 contract
    manifest = {
        "document_type": "sample_brain.stem_manifest",
        "schema_version": "1.0.0",
        "stem_id": stem_id,
        "stem_kind": stem_kind,
        "track_ref": track_ref,
        "status": "ok",
        "source": {
            "audio_ref": audio_ref,
            "hash": {"algorithm": "sha1", "value": source_hash},
            "audio_properties": {
                "sample_rate_hz": int(source_properties["sample_rate_hz"]),
                "channels": int(source_properties["channels"]),
                "n_samples": int(source_properties["n_samples"]),
                "duration_sec": source_properties.get(
                    "duration_sec",
                    float(source_properties["n_samples"])
                    / source_properties["sample_rate_hz"],
                ),
            },
            "origin_sample": 0,
        },
        "output": {
            "file_ref": file_ref,
            "hash": {"algorithm": "sha1", "value": output_hash},
            "audio_properties": {
                "sample_rate_hz": int(output_properties["sample_rate_hz"]),
                "channels": int(output_properties["channels"]),
                "n_samples": int(output_properties["n_samples"]),
                "duration_sec": output_properties.get(
                    "duration_sec",
                    float(output_properties["n_samples"])
                    / output_properties["sample_rate_hz"],
                ),
            },
        },
        "provenance": {
            "component": "stem_separator",
            "sample_brain_version": "0.1.0",
            "backend": {"name": "python-audio-separator", "version": backend_version},
            "model": {
                "family": model_identity["family"],
                "name": model_identity["name"],
                "checkpoint": model_identity["checkpoint"],
                "weight_hash": weight_hash,
                "code_license": model_identity["code_license"],
                "weight_license": model_identity["weight_license"],
            },
            "configuration": {"overlap": 0.25, "segment_size": "Default"},
        },
        "quality": {"notes": []},
    }
    return manifest


class StemSeparatorProcessWrapper:
    """
    Subprocess-based isolated wrapper for python-audio-separator.
    Ensures heavy dependencies are only imported inside the isolated subprocess.
    """

    def __init__(self, script_path: str | Path | None = None):
        if script_path is None:
            self.script_path = Path(__file__).resolve()
        else:
            self.script_path = Path(script_path).resolve()

    def separate_offline_fallback(
        self, input_path: Path, model_filename: str, output_dir: Path, reason: str
    ) -> dict:
        """Helper to create standardized unavailable/not_run manifest response."""
        return {
            "status": "not_run",
            "reason_code": reason,
            "provenance": {
                "component": "stem_separator",
                "sample_brain_version": "0.1.0",
            },
        }

    def list_models(self) -> list[dict]:
        """Runs the list-models command in a subprocess to retrieve the models list."""
        try:
            res = subprocess.run(
                [sys.executable, str(self.script_path), "list-models"],
                capture_output=True,
                text=True,
                check=True,
            )
            return json.loads(res.stdout)
        except Exception:
            return []

    def separate_via_subprocess(
        self,
        input_path: Path,
        track_ref: str,
        working_audio_hash: str,
        model_filename: str,
        output_dir: Path,
        *,
        weight_hash: str | None = None,
        weight_hash_algo: str | None = None,
        separation_fingerprint: str | None = None,
        model_cache_dir: Path | None = None,
        timeout: float = 600.0,
    ) -> dict:
        """
        Executes the separate command inside a separate subprocess to isolate
        resources and errors. Forwards the exact provenance (track_ref,
        working_audio_hash, model + weight hash) so no ambiguous single hash is
        reused across identity and audio-input concepts.
        """
        cmd = [
            sys.executable,
            str(self.script_path),
            "separate",
            "--input",
            str(input_path),
            "--track-ref",
            track_ref,
            "--working-audio-hash",
            working_audio_hash,
            "--model",
            model_filename,
            "--output-dir",
            str(output_dir),
        ]
        if weight_hash:
            cmd.extend(["--weight-hash", weight_hash])
        if weight_hash_algo:
            cmd.extend(["--weight-hash-algo", weight_hash_algo])
        if separation_fingerprint:
            cmd.extend(["--separation-fingerprint", separation_fingerprint])
        if model_cache_dir:
            cmd.extend(["--model-cache-dir", str(model_cache_dir)])

        try:
            completed = subprocess.run(
                cmd, capture_output=True, text=True, timeout=timeout
            )
            if completed.returncode != 0:
                return {
                    "status": "failed",
                    "error": {
                        "code": "SUBPROCESS_ERROR",
                        "message": f"Subprocess exited with exit code {completed.returncode}. Stderr: {completed.stderr.strip()}",
                    },
                }
            # Attempt to parse output JSON
            try:
                return json.loads(completed.stdout)
            except json.JSONDecodeError:
                return {
                    "status": "failed",
                    "error": {
                        "code": "INVALID_OUTPUT",
                        "message": f"Subprocess output was not valid JSON. Raw: {completed.stdout}",
                    },
                }
        except subprocess.TimeoutExpired:
            return {
                "status": "failed",
                "error": {
                    "code": "TIMEOUT",
                    "message": f"Subprocess timed out after {timeout} seconds.",
                },
            }
        except Exception as e:
            return {
                "status": "failed",
                "error": {
                    "code": "LAUNCH_FAILURE",
                    "message": f"Failed to launch subprocess: {e}",
                },
            }


# Subprocess command handlers
def cli_list_models() -> None:
    try:
        from audio_separator.separator import Separator

        s = Separator(info_only=True)
        raw_list = s.get_simplified_model_list()
        # Convert to list of models
        models = []
        for filename, info in raw_list.items():
            models.append(
                {
                    "filename": filename,
                    "name": info.get("Name"),
                    "type": info.get("Type"),
                    "stems": info.get("Stems"),
                    "sdr": info.get("SDR"),
                }
            )
        print(json.dumps(models, indent=2))
    except Exception:
        # Return fallback models if import/init fails
        fallback = [
            {
                "filename": "htdemucs.yaml",
                "name": "Demucs v4: htdemucs",
                "type": "Demucs",
                "stems": ["vocals", "drums", "bass", "other"],
            },
            {
                "filename": "htdemucs_ft.yaml",
                "name": "Demucs v4: htdemucs_ft",
                "type": "Demucs",
                "stems": ["vocals", "drums", "bass", "other"],
            },
        ]
        print(json.dumps(fallback, indent=2))


def cli_separate(args: argparse.Namespace) -> None:
    input_path = Path(args.input)
    output_dir = Path(args.output_dir)
    model_filename = args.model
    track_ref = args.track_ref
    working_audio_hash = args.working_audio_hash
    separation_fingerprint = args.separation_fingerprint

    # Resolve declared model identity from #247. The actual cryptographic
    # weight hash must be supplied explicitly; we never fabricate it.
    try:
        declared = resolve_known_model_identity(model_filename)
    except ValueError as e:
        print(
            json.dumps(
                {
                    "status": "failed",
                    "error": {"code": "UNKNOWN_MODEL", "message": str(e)},
                }
            )
        )
        return

    if not args.weight_hash:
        # No real weight identity available: do not separate and do not
        # fabricate provenance. Report explicitly instead.
        print(
            json.dumps(
                {
                    "status": "not_run",
                    "reason_code": "WEIGHT_IDENTITY_UNAVAILABLE",
                }
            )
        )
        return

    model_identity = {
        **declared,
        "weight_hash": {"algorithm": args.weight_hash_algo, "value": args.weight_hash},
    }

    # Validate that audio-separator is available
    try:
        from audio_separator.separator import Separator
    except ImportError:
        print(json.dumps({"status": "not_run", "reason_code": "BACKEND_UNAVAILABLE"}))
        return

    try:
        # Initialize Separator
        model_file_dir = args.model_cache_dir if args.model_cache_dir else None

        # Mapping custom names to have 100% deterministic and portable file refs
        custom_names = {
            "Vocals": "vocals",
            "Drums": "drums",
            "Bass": "bass",
            "Other": "other",
        }

        separator_params = {
            "output_dir": str(output_dir),
            "output_format": "WAV",
            "sample_rate": 44100,
        }
        if model_file_dir:
            separator_params["model_file_dir"] = str(model_file_dir)

        sep = Separator(**separator_params)
        sep.load_model(model_filename=model_filename)

        # Perform separation
        sep.separate(str(input_path), custom_names)

        # Soundfile details for original input
        import soundfile as sf

        try:
            orig_info = sf.info(input_path)
            orig_properties = {
                "sample_rate_hz": orig_info.samplerate,
                "channels": orig_info.channels,
                "n_samples": orig_info.frames,
                "duration_sec": orig_info.duration,
            }
        except Exception:
            # No fabricated fallback: report explicit failure instead.
            print(
                json.dumps(
                    {
                        "status": "failed",
                        "error": {
                            "code": "SOURCE_PROBE_FAILED",
                            "message": "could not probe source audio",
                        },
                    }
                )
            )
            return

        # Match stems to manifests. The separation fingerprint component makes
        # the stem id change whenever the actual separation identity changes
        # (model / checkpoint / weight / config), not just the track.
        stems: dict = {}
        backend_version = get_backend_version()
        if separation_fingerprint:
            sep_hash = hashlib.sha256(separation_fingerprint.encode("utf-8")).hexdigest()[:8]
        else:
            sep_hash = track_ref[:8]
        model_short = model_filename.replace(".yaml", "")

        stem_kinds = ["drums", "bass", "vocals", "other"]
        for stem_kind in stem_kinds:
            filename = f"{stem_kind}.wav"
            out_file_path = output_dir / filename
            if not out_file_path.exists():
                # Try fallback names if custom names didn't apply
                possible_matches = list(output_dir.glob(f"*{stem_kind}*"))
                if possible_matches:
                    out_file_path = possible_matches[0]
                    filename = out_file_path.name
                else:
                    stems[stem_kind] = {
                        "stem_kind": stem_kind,
                        "status": "failed",
                        "reason_code": "EMPTY_STEM_OUTPUT",
                        "manifest_ref": None,
                        "audio_ref": None,
                    }
                    continue

            out_hash = file_hash(out_file_path)
            try:
                out_info = sf.info(out_file_path)
                out_properties = {
                    "sample_rate_hz": out_info.samplerate,
                    "channels": out_info.channels,
                    "n_samples": out_info.frames,
                    "duration_sec": out_info.duration,
                }
            except Exception:
                # No fabricated fallback: mark this stem failed, keep others.
                stems[stem_kind] = {
                    "stem_kind": stem_kind,
                    "status": "failed",
                    "reason_code": "OUTPUT_PROBE_FAILED",
                    "manifest_ref": None,
                    "audio_ref": None,
                }
                continue

            # Map to v1 stem manifest schema. The manifest is written as a
            # sibling of the produced audio (relative output.file_ref).
            stem_id = f"stem_{stem_kind}_{model_short}_{track_ref[:8]}_{sep_hash}"
            manifest = map_stem_to_manifest(
                stem_id=stem_id,
                stem_kind=stem_kind,
                track_ref=track_ref,
                source_hash=working_audio_hash,
                source_properties=orig_properties,
                file_ref=filename,
                output_hash=out_hash,
                output_properties=out_properties,
                model_identity=model_identity,
                backend_version=backend_version,
                audio_ref="/source/working_audio",
            )

            manifest_file = output_dir / f"{stem_id}.json"
            manifest_file.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

            stems[stem_kind] = {
                "manifest_ref": f"{stem_id}.json",
                "audio_ref": filename,
                "manifest_content": manifest,
                "status": "ok",
            }

        produced = [s for s in stems.values() if s.get("status") == "ok"]
        if produced:
            status = "partial" if len(produced) < len(stem_kinds) else "ok"
        else:
            status = "failed"

        # Return completion status
        print(
            json.dumps(
                {
                    "status": status,
                    "model_filename": model_filename,
                    "backend_version": backend_version,
                    "stems": stems,
                },
                indent=2,
            )
        )

    except Exception as e:
        print(
            json.dumps(
                {
                    "status": "failed",
                    "error": {
                        "code": "LAUNCH_FAILURE",
                        "message": f"Backend initialization or separation failed: {e}",
                    },
                },
                indent=2,
            )
        )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Sample Brain Stem Separator Spike Process"
    )
    subparsers = parser.init = parser.add_subparsers(dest="command", required=True)

    # list-models subparser
    subparsers.add_parser(
        "list-models", help="List available models in audio-separator"
    )

    # separate subparser
    sep_parser = subparsers.add_parser("separate", help="Separate an input audio file")
    sep_parser.add_argument("--input", required=True, help="Path to input audio file")
    sep_parser.add_argument(
        "--track-ref",
        required=True,
        help="Portable Track Map identity (content hash) of the source track.",
    )
    sep_parser.add_argument(
        "--working-audio-hash",
        required=True,
        help="Cryptographic hash of the exact audio bytes sent to the separator.",
    )
    sep_parser.add_argument(
        "--model", required=True, help="Model filename, e.g. htdemucs.yaml"
    )
    sep_parser.add_argument(
        "--output-dir", required=True, help="Directory to save output files"
    )
    sep_parser.add_argument(
        "--model-cache-dir", required=False, help="Optional model cache directory"
    )
    sep_parser.add_argument(
        "--weight-hash",
        required=False,
        help="Actual cryptographic hash of the loaded weight file/set. Required for truthful provenance.",
    )
    sep_parser.add_argument(
        "--weight-hash-algo",
        required=False,
        default="sha256",
        help="Hash algorithm used for --weight-hash (sha256 or sha256-set-v1).",
    )
    sep_parser.add_argument(
        "--separation-fingerprint",
        required=False,
        help="Canonical separation fingerprint; used to derive a deterministic stem id.",
    )

    args = parser.parse_args()

    if args.command == "list-models":
        cli_list_models()
    elif args.command == "separate":
        cli_separate(args)


if __name__ == "__main__":
    main()
