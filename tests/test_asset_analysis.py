from __future__ import annotations

import soundfile as sf
from pathlib import Path

import numpy as np

from src.asset_analysis import (
    COMPONENT_KEY,
    COMPONENT_NAME,
    analyze_rendered_asset,
    attach_rendered_asset_analysis,
    reanalyze_rendered_output,
)
from src.asset_renderer import (
    ASSETS_DIR_NAME,
    RenderConfig,
    RenderRequest,
    render_asset,
)
from src.utils import file_hash

SEMITONES = {"C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"}
KNOWN_SAMPLE_TYPES = {
    "Kick",
    "Snare",
    "HiHat-Closed",
    "Impact",
    "Drone",
    "Pad",
    "Loop",
    "OneShot",
    "Drum Loop",
    "FX",
}


def _write_rhythmic_tonal(
    path: Path,
    *,
    bpm: float = 120.0,
    tone_hz: float = 261.63,
    duration_sec: float = 6.0,
    sr: int = 44100,
    amp: float = 0.5,
) -> None:
    """Deterministic source: a clear C tone plus a 120 BPM pulse train."""
    n = int(sr * duration_sec)
    t = np.linspace(0.0, duration_sec, n, endpoint=False, dtype=np.float32)
    y = (amp * 0.6 * np.sin(2.0 * np.pi * tone_hz * t)).astype(np.float32)
    interval = 60.0 / bpm
    pulse = max(1, int(0.005 * sr))
    tp = np.linspace(0.0, 0.005, pulse, dtype=np.float32)
    click = (amp * np.sin(2.0 * np.pi * 800.0 * tp) * (np.linspace(1.0, 0.0, pulse) ** 2)).astype(
        np.float32
    )
    for i in range(int(duration_sec / interval)):
        s = int(i * interval * sr)
        if s + pulse <= n:
            y[s : s + pulse] += click
    y = np.clip(y, -1.0, 1.0)
    sf.write(str(path), y, sr, subtype="PCM_16")


def _write_sine(path: Path, *, duration_sec: float, frequency_hz: float, sr: int = 44100) -> None:
    sample_count = max(1, int(sr * duration_sec))
    t = np.linspace(0.0, duration_sec, sample_count, endpoint=False, dtype=np.float32)
    wave = (0.5 * np.sin(2.0 * np.pi * frequency_hz * t)).astype(np.float32)
    sf.write(str(path), wave, sr, subtype="PCM_16")


def _render_to(
    tmp_path: Path,
    *,
    source_factory=None,
    source_kwargs: dict | None = None,
    start: int,
    end: int,
    asset_kind: str = "loop",
    asset_id: str = "asset_loop_01",
    source_kind: str = "master",
) -> tuple[dict, Path]:
    """Render an asset and return (rendering_block, audio_root)."""
    src = tmp_path / "src.wav"
    (source_factory or _write_rhythmic_tonal)(src, **(source_kwargs or {}))
    req = RenderRequest(
        asset_kind=asset_kind,
        asset_id=asset_id,
        source_kind=source_kind,  # type: ignore[arg-type]
        start_sample=start,
        end_sample_exclusive=end,
        source_audio_path=src,
    )
    res = render_asset(req, tmp_path, config=RenderConfig())
    assert res.status == "rendered"
    assert res.output is not None
    return res.as_manifest_rendering(), tmp_path


def _base_manifest(
    rendering: dict,
    *,
    asset_kind: str = "loop",
    source_kind: str = "master",
    asset_id: str = "asset_loop_01",
    track_ref: str = "track_test",
    with_parent: bool = False,
    with_section_ref: bool = False,
) -> dict:
    source_block: dict[str, object] = {"source_kind": source_kind}
    if source_kind == "master":
        source_block["track_audio_ref"] = "/source/working_audio"
    elif source_kind == "stem":
        source_block["stem_id"] = "stem_drums_01"
        source_block["stem_ref"] = "stemmanifest_drums_01"
    elif source_kind == "producer_group":
        source_block["producer_group_id"] = "pg_bridge_fx"
        source_block["producer_group_ref"] = "producergroup_bridge_fx"

    manifest: dict[str, object] = {
        "document_type": "sample_brain.asset_manifest",
        "schema_version": "1.1.0",
        "asset_id": asset_id,
        "track_ref": track_ref,
        "asset_kind": asset_kind,
        "source": source_block,
        "timebase": {
            "audio_ref": "/source/audio",
            "unit": "samples",
            "origin_sample": 0,
            "sample_rate_hz": 44100,
        },
        "range": {"start_sample": 0, "end_sample_exclusive": 100, "n_samples": 100},
        "boundary": {"status": "ok", "source": "beat_grid"},
        "candidate": {"status": "selected", "excluded": False},
        "rendering": rendering,
        "analysis": {"status": "not_run", "reason_code": "ANALYSIS_NOT_REQUESTED"},
        "provenance": {"components": {}},
    }
    if asset_kind == "loop":
        manifest["loop"] = {
            "bars": {"start_bar": 0, "end_bar_exclusive": 4, "bar_count": 4},
            "downbeat_start_sample": 0,
        }
    else:
        manifest["section"] = {"section_ref": "section_01", "arrangement_role": "groove"}
    if with_parent:
        manifest["parent_asset_ref"] = "asset_parent_00"
    if with_section_ref:
        manifest["section_ref"] = "section_01"
    return manifest


def _analyze_attached(manifest: dict, audio_root: Path) -> dict:
    result = attach_rendered_asset_analysis(manifest, audio_root)
    assert isinstance(result, dict)
    return result


# --- core: loops and sections produce metadata -------------------------------


def test_rendered_loop_produces_analysis_metadata(tmp_path: Path) -> None:
    rendering, root = _render_to(tmp_path, start=0, end=176400)  # 4s @44100
    manifest = _base_manifest(rendering, asset_kind="loop")
    out = _analyze_attached(manifest, root)
    analysis = out["analysis"]
    assert analysis["status"] == "ok"
    assert analysis["bpm"] is not None and analysis["bpm"] > 0
    assert analysis["key_root"] in SEMITONES
    assert analysis["sample_type"] in KNOWN_SAMPLE_TYPES
    assert analysis["loudness"] is not None
    assert analysis["brightness"] is not None
    assert analysis["source_ref"] == COMPONENT_KEY


def test_rendered_section_produces_analysis_metadata(tmp_path: Path) -> None:
    rendering, root = _render_to(
        tmp_path,
        start=0,
        end=176400,
        asset_kind="section",
        asset_id="asset_section_01",
        source_kind="stem",
    )
    manifest = _base_manifest(
        rendering, asset_kind="section", source_kind="stem", asset_id="asset_section_01"
    )
    out = _analyze_attached(manifest, root)
    analysis = out["analysis"]
    assert analysis["status"] == "ok"
    assert analysis["bpm"] is not None
    assert analysis["key_root"] in SEMITONES
    assert analysis["sample_type"] in KNOWN_SAMPLE_TYPES


# --- BPM semantics: no invented confidence -----------------------------------


def test_bpm_carried_with_clear_semantics(tmp_path: Path) -> None:
    rendering, root = _render_to(tmp_path, start=0, end=176400)
    manifest = _base_manifest(rendering)
    analysis = _analyze_attached(manifest, root)["analysis"]
    assert isinstance(analysis["bpm"], (int, float))
    assert analysis["bpm"] > 0
    assert "bpm_confidence" not in analysis
    assert "confidence" not in analysis


def test_key_contains_root_not_invented_mode(tmp_path: Path) -> None:
    rendering, root = _render_to(tmp_path, start=0, end=176400)
    manifest = _base_manifest(rendering)
    analysis = _analyze_attached(manifest, root)["analysis"]
    assert analysis["key_root"] in SEMITONES
    assert "mode" not in analysis
    assert "key_conf" not in analysis
    assert "key_confidence" not in analysis


def test_sample_type_rules_only(tmp_path: Path) -> None:
    rendering, root = _render_to(tmp_path, start=0, end=176400)
    manifest = _base_manifest(rendering)
    analysis = _analyze_attached(manifest, root)["analysis"]
    assert isinstance(analysis["sample_type"], str) and analysis["sample_type"]
    assert analysis["sample_type"] in KNOWN_SAMPLE_TYPES


def test_loudness_and_brightness_carried(tmp_path: Path) -> None:
    rendering, root = _render_to(tmp_path, start=0, end=176400)
    manifest = _base_manifest(rendering)
    analysis = _analyze_attached(manifest, root)["analysis"]
    assert isinstance(analysis["loudness"], (int, float))
    assert isinstance(analysis["brightness"], (int, float))
    assert analysis["brightness"] > 0


# --- short audio -> partial, no fake values ----------------------------------


def test_short_audio_without_bpm_key_is_partial(tmp_path: Path) -> None:
    src = tmp_path / "src.wav"
    _write_sine(src, duration_sec=4.0, frequency_hz=261.63)
    req = RenderRequest(
        asset_kind="loop",
        asset_id="asset_loop_short",
        source_kind="master",
        start_sample=0,
        end_sample_exclusive=int(0.3 * 44100),
        source_audio_path=src,
    )
    res = render_asset(req, tmp_path)
    assert res.status == "rendered"
    manifest = _base_manifest(res.as_manifest_rendering(), asset_id="asset_loop_short")
    analysis = _analyze_attached(manifest, tmp_path)["analysis"]
    assert analysis["status"] == "partial"
    assert "bpm" not in analysis
    assert "key_root" not in analysis
    assert analysis.get("reason_code") == "PARTIAL_MISSING_BPM_KEY"


# --- not_run ----------------------------------------------------------------


def test_not_rendered_asset_is_not_run(tmp_path: Path) -> None:
    rendering = {"status": "not_rendered"}
    manifest = _base_manifest(rendering)
    analysis = _analyze_attached(manifest, tmp_path)["analysis"]
    assert analysis["status"] == "not_run"
    assert analysis.get("reason_code") == "ASSET_NOT_RENDERED"


# --- fail-closed integrity gate ---------------------------------------------


def test_missing_rendered_wav_fails_closed(tmp_path: Path) -> None:
    rendering, root = _render_to(tmp_path, start=0, end=176400)
    written = root / ASSETS_DIR_NAME / rendering["output"]["file_name"]  # type: ignore[index]
    written.unlink()
    manifest = _base_manifest(rendering)
    result = analyze_rendered_asset(manifest, root)
    assert result.status == "failed"
    assert result.error["code"] == "RENDERED_ASSET_NOT_FOUND"  # type: ignore[index]


def test_corrupt_wav_fails_closed(tmp_path: Path) -> None:
    rendering, root = _render_to(tmp_path, start=0, end=176400)
    written = root / ASSETS_DIR_NAME / rendering["output"]["file_name"]  # type: ignore[index]
    garbage = b"not a wav file at all" * 50
    written.write_bytes(garbage)
    rendering["output"]["hash"]["value"] = file_hash(written)  # type: ignore[index]
    manifest = _base_manifest(rendering)
    result = analyze_rendered_asset(manifest, root)
    assert result.status == "failed"
    assert result.error["code"] == "AUDIO_LOAD_FAILED"  # type: ignore[index]


def test_hash_mismatch_fails_closed(tmp_path: Path) -> None:
    rendering, root = _render_to(tmp_path, start=0, end=176400)
    written = root / ASSETS_DIR_NAME / rendering["output"]["file_name"]  # type: ignore[index]
    data = bytearray(written.read_bytes())
    data[0] ^= 0xFF
    written.write_bytes(bytes(data))
    manifest = _base_manifest(rendering)
    result = analyze_rendered_asset(manifest, root)
    assert result.status == "failed"
    assert result.error["code"] == "RENDERED_ASSET_HASH_MISMATCH"  # type: ignore[index]


def test_absolute_file_ref_rejected(tmp_path: Path) -> None:
    rendering, root = _render_to(tmp_path, start=0, end=176400)
    rendering["output"]["file_ref"] = str(  # type: ignore[index]
        (root / ASSETS_DIR_NAME / rendering["output"]["file_name"]).resolve()  # type: ignore[index]
    )
    manifest = _base_manifest(rendering)
    result = analyze_rendered_asset(manifest, root)
    assert result.status == "failed"
    assert result.error["code"] == "INVALID_ASSET_FILE_REF"  # type: ignore[index]


def test_traversal_file_ref_rejected(tmp_path: Path) -> None:
    rendering, root = _render_to(tmp_path, start=0, end=176400)
    rendering["output"]["file_ref"] = "assets/../escape.wav"  # type: ignore[index]
    manifest = _base_manifest(rendering)
    result = analyze_rendered_asset(manifest, root)
    assert result.status == "failed"
    assert result.error["code"] == "INVALID_ASSET_FILE_REF"  # type: ignore[index]


# --- source / ref preservation ----------------------------------------------


def test_master_source_preserved(tmp_path: Path) -> None:
    rendering, root = _render_to(tmp_path, start=0, end=176400, source_kind="master")
    manifest = _base_manifest(rendering, source_kind="master")
    out = _analyze_attached(manifest, root)
    assert out["source"]["source_kind"] == "master"
    assert out["source"]["track_audio_ref"] == "/source/working_audio"


def test_stem_source_preserved(tmp_path: Path) -> None:
    rendering, root = _render_to(tmp_path, start=0, end=176400, source_kind="stem")
    manifest = _base_manifest(rendering, source_kind="stem")
    out = _analyze_attached(manifest, root)
    assert out["source"]["source_kind"] == "stem"
    assert out["source"]["stem_id"] == "stem_drums_01"
    assert out["source"]["stem_ref"] == "stemmanifest_drums_01"


def test_producer_group_source_preserved(tmp_path: Path) -> None:
    rendering, root = _render_to(
        tmp_path, start=0, end=176400, source_kind="producer_group"
    )
    manifest = _base_manifest(rendering, source_kind="producer_group")
    out = _analyze_attached(manifest, root)
    assert out["source"]["source_kind"] == "producer_group"
    assert out["source"]["producer_group_id"] == "pg_bridge_fx"


def test_section_and_parent_refs_preserved(tmp_path: Path) -> None:
    rendering, root = _render_to(
        tmp_path, start=0, end=176400, asset_kind="section", asset_id="asset_section_01"
    )
    manifest = _base_manifest(
        rendering,
        asset_kind="section",
        asset_id="asset_section_01",
        with_parent=True,
        with_section_ref=True,
    )
    out = _analyze_attached(manifest, root)
    assert out["asset_kind"] == "section"
    assert out["section"]["section_ref"] == "section_01"
    assert out["parent_asset_ref"] == "asset_parent_00"
    assert out["track_ref"] == "track_test"


def test_candidate_and_rendering_blocks_preserved(tmp_path: Path) -> None:
    rendering, root = _render_to(tmp_path, start=0, end=176400)
    manifest = _base_manifest(rendering)
    out = _analyze_attached(manifest, root)
    assert out["candidate"] == manifest["candidate"]
    assert out["rendering"] == manifest["rendering"]
    assert out["range"] == manifest["range"]
    assert out["boundary"] == manifest["boundary"]
    assert out["loop"] == manifest["loop"]


# --- determinism ------------------------------------------------------------


def test_same_input_and_config_is_deterministic(tmp_path: Path) -> None:
    rendering, root = _render_to(tmp_path, start=0, end=176400)
    manifest = _base_manifest(rendering)
    a = _analyze_attached(dict(manifest), root)["analysis"]
    b = _analyze_attached(dict(manifest), root)["analysis"]
    for key in ("bpm", "key_root", "sample_type", "loudness", "brightness"):
        assert a.get(key) == b.get(key)
    assert a["analyzed_output"]["hash"] == b["analyzed_output"]["hash"]


# --- no DB / network / model ------------------------------------------------


def test_analyzes_without_db_or_model(tmp_path: Path) -> None:
    rendering, root = _render_to(tmp_path, start=0, end=176400)
    manifest = _base_manifest(rendering)
    analysis = _analyze_attached(manifest, root)["analysis"]
    assert analysis["status"] == "ok"
    assert "embedding" not in analysis
    assert "model" not in analysis
    assert "confidence" not in analysis


# --- no private absolute paths in serialized result -------------------------


def test_no_private_absolute_paths_in_result(tmp_path: Path) -> None:
    rendering, root = _render_to(tmp_path, start=0, end=176400)
    manifest = _base_manifest(rendering)
    out = _analyze_attached(manifest, root)
    file_ref = out["analysis"]["analyzed_output"]["file_ref"]
    assert isinstance(file_ref, str)
    assert not any(seg.startswith("C:") or seg.startswith("/") for seg in [file_ref])
    assert file_ref.startswith(f"{ASSETS_DIR_NAME}/")
    prov = out["provenance"]["components"][COMPONENT_KEY]
    assert COMPONENT_NAME in str(prov["component"])


# --- manifest versioning ----------------------------------------------------


def test_canonical_version_1_1_0_accepted(tmp_path: Path) -> None:
    rendering, root = _render_to(tmp_path, start=0, end=176400)
    manifest = _base_manifest(rendering)
    # The canonical post-#254 version is 1.1.0 (MINOR bump for the analysis fields).
    manifest["schema_version"] = "1.1.0"
    analysis = _analyze_attached(manifest, root)["analysis"]
    assert analysis["status"] == "ok"


def test_legacy_version_1_0_0_still_accepted(tmp_path: Path) -> None:
    # Pre-analysis manifests without the #254 fields remain valid v1 documents.
    rendering, root = _render_to(tmp_path, start=0, end=176400)
    manifest = _base_manifest(rendering)
    manifest["schema_version"] = "1.0.0"
    analysis = _analyze_attached(manifest, root)["analysis"]
    assert analysis["status"] == "ok"


def test_compatible_manifest_version_accepted(tmp_path: Path) -> None:
    rendering, root = _render_to(tmp_path, start=0, end=176400)
    manifest = _base_manifest(rendering)
    manifest["schema_version"] = "1.2.3"
    analysis = _analyze_attached(manifest, root)["analysis"]
    assert analysis["status"] == "ok"


def test_unsupported_major_version_fails_closed(tmp_path: Path) -> None:
    rendering, root = _render_to(tmp_path, start=0, end=176400)
    manifest = _base_manifest(rendering)
    manifest["schema_version"] = "2.0.0"
    result = analyze_rendered_asset(manifest, root)
    assert result.status == "failed"
    assert result.error["code"] == "UNSUPPORTED_MANIFEST_VERSION"  # type: ignore[index]


def test_missing_schema_version_fails_closed(tmp_path: Path) -> None:
    rendering, root = _render_to(tmp_path, start=0, end=176400)
    manifest = _base_manifest(rendering)
    del manifest["schema_version"]
    result = analyze_rendered_asset(manifest, root)
    assert result.status == "failed"
    assert result.error["code"] == "UNSUPPORTED_MANIFEST_VERSION"  # type: ignore[index]


# --- output-level entry point -----------------------------------------------


def test_reanalyze_rendered_output_returns_provenance_entry(tmp_path: Path) -> None:
    rendering, root = _render_to(tmp_path, start=0, end=176400)
    output = rendering["output"]
    result = reanalyze_rendered_output(output, root)
    assert result.status == "ok"
    assert result.provenance_entry is not None
    assert result.provenance_entry["component"] == COMPONENT_NAME
    assert "backend" in result.provenance_entry
    assert result.analysis["source_ref"] == COMPONENT_KEY
