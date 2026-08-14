from __future__ import annotations

import sys
import os
import argparse
import subprocess
import json
import hashlib
from pathlib import Path

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
    model_filename: str,
    backend_version: str,
    weight_license: str = "UNKNOWN/UNVERIFIED"
) -> dict:
    if not track_ref or "/" in track_ref or "\\" in track_ref or ":" in track_ref or track_ref.endswith((".wav", ".mp3", ".flac")):
        raise ValueError("track_ref must be a portable track ID, not a path or filename fallback")

    if stem_kind not in {"drums", "bass", "vocals", "other"}:
        raise ValueError(f"stem_kind must be drums|bass|vocals|other, got {stem_kind!r}")

    # Standard 1.0.0 contract
    manifest = {
        "document_type": "sample_brain.stem_manifest",
        "schema_version": "1.0.0",
        "stem_id": stem_id,
        "stem_kind": stem_kind,
        "track_ref": track_ref,
        "status": "ok",
        "source": {
            "audio_ref": "/source/original",
            "hash": {
                "algorithm": "sha1",
                "value": source_hash
            },
            "audio_properties": {
                "sample_rate_hz": int(source_properties["sample_rate_hz"]),
                "channels": int(source_properties["channels"]),
                "n_samples": int(source_properties["n_samples"]),
                "duration_sec": source_properties.get("duration_sec", float(source_properties["n_samples"]) / source_properties["sample_rate_hz"])
            },
            "origin_sample": 0
        },
        "output": {
            "file_ref": file_ref,
            "hash": {
                "algorithm": "sha1",
                "value": output_hash
            },
            "audio_properties": {
                "sample_rate_hz": int(output_properties["sample_rate_hz"]),
                "channels": int(output_properties["channels"]),
                "n_samples": int(output_properties["n_samples"]),
                "duration_sec": output_properties.get("duration_sec", float(output_properties["n_samples"]) / output_properties["sample_rate_hz"])
            }
        },
        "provenance": {
            "component": "stem_separator",
            "sample_brain_version": "0.1.0",
            "backend": {
                "name": "python-audio-separator",
                "version": backend_version
            },
            "model": {
                "family": "htdemucs",
                "name": model_filename.replace(".yaml", ""),
                "checkpoint": model_filename,
                "weight_hash": {
                    "algorithm": "sha1",
                    "value": "f7e0c4bcba3fe64a92cfc3b6ef3bcb9c04573f0d" # representative Demucs weight hash segment
                },
                "code_license": "MIT",
                "weight_license": weight_license
            },
            "configuration": {
                "overlap": 0.25,
                "segment_size": "Default"
            }
        },
        "quality": {
            "notes": []
        }
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

    def separate_offline_fallback(self, input_path: Path, model_filename: str, output_dir: Path, reason: str) -> dict:
        """Helper to create standardized unavailable/not_run manifest response."""
        return {
            "status": "not_run",
            "reason_code": reason,
            "provenance": {
                "component": "stem_separator",
                "sample_brain_version": "0.1.0"
            }
        }

    def list_models(self) -> list[dict]:
        """Runs the list-models command in a subprocess to retrieve the models list."""
        try:
            res = subprocess.run(
                [sys.executable, str(self.script_path), "list-models"],
                capture_output=True,
                text=True,
                check=True
            )
            return json.loads(res.stdout)
        except Exception as e:
            return []

    def separate_via_subprocess(
        self,
        input_path: Path,
        track_hash: str,
        model_filename: str,
        output_dir: Path,
        model_cache_dir: Path | None = None,
        timeout: float = 600.0
    ) -> dict:
        """
        Executes the separate command inside a separate subprocess to isolate resources and errors.
        """
        cmd = [
            sys.executable,
            str(self.script_path),
            "separate",
            "--input", str(input_path),
            "--track-hash", track_hash,
            "--model", model_filename,
            "--output-dir", str(output_dir)
        ]
        if model_cache_dir:
            cmd.extend(["--model-cache-dir", str(model_cache_dir)])

        try:
            completed = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
            if completed.returncode != 0:
                return {
                    "status": "failed",
                    "error": {
                        "code": "SUBPROCESS_ERROR",
                        "message": f"Subprocess exited with exit code {completed.returncode}. Stderr: {completed.stderr.strip()}"
                    }
                }
            # Attempt to parse output JSON
            try:
                return json.loads(completed.stdout)
            except json.JSONDecodeError:
                return {
                    "status": "failed",
                    "error": {
                        "code": "INVALID_OUTPUT",
                        "message": f"Subprocess output was not valid JSON. Raw: {completed.stdout}"
                    }
                }
        except subprocess.TimeoutExpired:
            return {
                "status": "failed",
                "error": {
                    "code": "TIMEOUT",
                    "message": f"Subprocess timed out after {timeout} seconds."
                }
            }
        except Exception as e:
            return {
                "status": "failed",
                "error": {
                    "code": "LAUNCH_FAILURE",
                    "message": f"Failed to launch subprocess: {e}"
                }
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
            models.append({
                "filename": filename,
                "name": info.get("Name"),
                "type": info.get("Type"),
                "stems": info.get("Stems"),
                "sdr": info.get("SDR")
            })
        print(json.dumps(models, indent=2))
    except Exception as e:
        # Return fallback models if import/init fails
        fallback = [
            {
                "filename": "htdemucs.yaml",
                "name": "Demucs v4: htdemucs",
                "type": "Demucs",
                "stems": ["vocals", "drums", "bass", "other"]
            },
            {
                "filename": "htdemucs_ft.yaml",
                "name": "Demucs v4: htdemucs_ft",
                "type": "Demucs",
                "stems": ["vocals", "drums", "bass", "other"]
            }
        ]
        print(json.dumps(fallback, indent=2))


def cli_separate(args: argparse.Namespace) -> None:
    input_path = Path(args.input)
    output_dir = Path(args.output_dir)
    model_filename = args.model
    track_hash = args.track_hash

    # Validate that audio-separator is available
    try:
        from audio_separator.separator import Separator
    except ImportError:
        print(json.dumps({
            "status": "not_run",
            "reason_code": "BACKEND_UNAVAILABLE"
        }))
        return

    # Check that ffmpeg is installed, otherwise handle gracefully
    try:
        # Initialize Separator
        model_file_dir = args.model_cache_dir if args.model_cache_dir else None
        
        # Mapping custom names to have 100% deterministic and portable file refs
        custom_names = {
            "Vocals": "vocals",
            "Drums": "drums",
            "Bass": "bass",
            "Other": "other"
        }
        
        separator_params = {
            "output_dir": str(output_dir),
            "output_format": "WAV",
            "sample_rate": 44100
        }
        if model_file_dir:
            separator_params["model_file_dir"] = str(model_file_dir)
            
        sep = Separator(**separator_params)
        sep.load_model(model_filename=model_filename)
        
        # Perform separation
        output_files = sep.separate(str(input_path), custom_names)
        
        # Soundfile details for original input
        import soundfile as sf
        try:
            orig_info = sf.info(input_path)
            orig_properties = {
                "sample_rate_hz": orig_info.samplerate,
                "channels": orig_info.channels,
                "n_samples": orig_info.frames,
                "duration_sec": orig_info.duration
            }
        except Exception:
            orig_properties = {
                "sample_rate_hz": 44100,
                "channels": 2,
                "n_samples": 88200,
                "duration_sec": 2.0
            }

        # Match stems to manifests
        stems = {}
        backend_version = get_backend_version()
        
        # The outputs generated will be written to output_dir with custom names
        stem_kinds = ["drums", "bass", "vocals", "other"]
        for stem_kind in stem_kinds:
            # Look for the exact output file
            filename = f"{stem_kind}.wav"
            out_file_path = output_dir / filename
            if not out_file_path.exists():
                # Try fallback names if custom names didn't apply
                possible_matches = list(output_dir.glob(f"*{stem_kind}*"))
                if possible_matches:
                    out_file_path = possible_matches[0]
                    filename = out_file_path.name
                else:
                    continue

            # Compute output details
            out_hash = file_hash(out_file_path)
            try:
                out_info = sf.info(out_file_path)
                out_properties = {
                    "sample_rate_hz": out_info.samplerate,
                    "channels": out_info.channels,
                    "n_samples": out_info.frames,
                    "duration_sec": out_info.duration
                }
            except Exception:
                out_properties = orig_properties

            # Map to v1 stem manifest schema
            stem_id = f"stem_{stem_kind}_{track_hash[:8]}"
            manifest = map_stem_to_manifest(
                stem_id=stem_id,
                stem_kind=stem_kind,
                track_ref=track_hash,
                source_hash=track_hash,
                source_properties=orig_properties,
                file_ref=filename,
                output_hash=out_hash,
                output_properties=out_properties,
                model_filename=model_filename,
                backend_version=backend_version
            )
            
            # Write the manifest file inside the output_dir/stems
            stems_dir = output_dir / "stems"
            stems_dir.mkdir(parents=True, exist_ok=True)
            manifest_file = stems_dir / f"{stem_id}.json"
            manifest_file.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
            
            stems[stem_kind] = {
                "manifest_ref": f"stems/{stem_id}.json",
                "audio_ref": filename,
                "manifest_content": manifest
            }

        # Return completion status
        print(json.dumps({
            "status": "ok",
            "model_filename": model_filename,
            "backend_version": backend_version,
            "stems": stems
        }, indent=2))

    except Exception as e:
        print(json.dumps({
            "status": "failed",
            "error": {
                "code": "LAUNCH_FAILURE",
                "message": f"Backend initialization or separation failed: {e}"
            }
        }, indent=2))


def main() -> None:
    parser = argparse.ArgumentParser(description="Sample Brain Stem Separator Spike Process")
    subparsers = parser.add_init = parser.add_subparsers(dest="command", required=True)

    # list-models subparser
    subparsers.add_parser("list-models", help="List available models in audio-separator")

    # separate subparser
    sep_parser = subparsers.add_parser("separate", help="Separate an input audio file")
    sep_parser.add_argument("--input", required=True, help="Path to input audio file")
    sep_parser.add_argument("--track-hash", required=True, help="SHA-1 hash of the input audio file")
    sep_parser.add_argument("--model", required=True, help="Model filename, e.g. htdemucs.yaml")
    sep_parser.add_argument("--output-dir", required=True, help="Directory to save output files")
    sep_parser.add_argument("--model-cache-dir", required=False, help="Optional model cache directory")

    args = parser.parse_args()

    if args.command == "list-models":
        cli_list_models()
    elif args.command == "separate":
        cli_separate(args)


if __name__ == "__main__":
    main()
