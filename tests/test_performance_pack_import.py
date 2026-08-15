from __future__ import annotations

import json
from pathlib import Path

import pytest
import soundfile as sf

from src.config import set_db_path
from src.db import init_db
from tests.audio_fixtures import write_sine_wav


PACK_ID = "pack_9f8e7d6c5b4a3c2d"
TRACK_ID = "track_9f8e7d6c5b4a3c2d1e0f11223344556677889900"


@pytest.fixture(autouse=True)
def isolated_catalog(tmp_path):
    """Point the catalog DB at an isolated temp file and create the schema."""
    db_path = tmp_path / "catalog.db"
    set_db_path(str(db_path))
    init_db()
    yield db_path


def _audio_props(wav_path: Path) -> dict:
    with sf.SoundFile(str(wav_path)) as f:
        return {
            "sample_rate_hz": int(f.samplerate),
            "channels": int(f.channels),
            "n_samples": int(len(f)),
        }


def _asset_manifest(
    asset_id: str,
    track_id: str,
    asset_kind: str,
    source_kind: str,
    wav_path: Path,
    file_ref: str,
    rendering_status: str = "rendered",
    asset_status: str = "ok",
) -> dict:
    from src.utils import file_hash

    props = _audio_props(wav_path)
    manifest = {
        "document_type": "sample_brain.asset_manifest",
        "schema_version": "1.1.0",
        "asset_id": asset_id,
        "track_ref": track_id,
        "asset_kind": asset_kind,
        "source": {
            "source_kind": source_kind,
            "audio": {
                "file_name": wav_path.name,
                "hash": {"algorithm": "sha1", "value": file_hash(wav_path)},
                "audio_properties": {
                    "duration_sec": props["n_samples"] / props["sample_rate_hz"],
                    "sample_rate_hz": props["sample_rate_hz"],
                    "channels": props["channels"],
                },
            },
        },
        "timebase": {
            "audio_ref": "/source/audio",
            "unit": "samples",
            "origin_sample": 0,
            "sample_rate_hz": props["sample_rate_hz"],
        },
        "range": {
            "start_sample": 0,
            "end_sample_exclusive": props["n_samples"],
            "n_samples": props["n_samples"],
            "sample_rate_hz": props["sample_rate_hz"],
        },
        "loop": {"bars": {"start_bar": 0, "end_bar_exclusive": 4}} if asset_kind == "loop" else None,
        "section": None if asset_kind == "loop" else {"arrangement_role": "unknown"},
        "boundary": {"status": "ok", "source": "beat_grid"},
        "candidate": {"status": "selected"},
        "rendering": {"status": rendering_status},
        "analysis": {"status": "not_run", "reason_code": "ANALYSIS_NOT_REQUESTED"},
        "provenance": {"components": {}},
        "quality": {"notes": []},
    }
    if rendering_status == "rendered":
        manifest["rendering"] = {
            "status": "rendered",
            "output": {
                "file_ref": file_ref,
                "file_name": wav_path.name,
                "hash": {"algorithm": "sha1", "value": file_hash(wav_path)},
                "audio_properties": props,
                "format": "wav/pcm_16",
            },
        }
    return manifest


def _stem_manifest(
    stem_id: str,
    track_id: str,
    wav_path: Path,
    file_ref: str,
    status: str = "ok",
) -> dict:
    from src.utils import file_hash

    props = _audio_props(wav_path)
    return {
        "document_type": "sample_brain.stem_manifest",
        "schema_version": "1.0.0",
        "stem_id": stem_id,
        "stem_kind": "drums",
        "track_ref": track_id,
        "status": status,
        "source": {
            "audio_ref": "/source/original",
            "hash": {"algorithm": "sha1", "value": file_hash(wav_path)},
            "audio_properties": {
                "sample_rate_hz": props["sample_rate_hz"],
                "channels": props["channels"],
                "n_samples": props["n_samples"],
            },
            "origin_sample": 0,
        },
        "provenance": {"component": "stem_separator"},
        "quality": {"notes": []},
        "output": {
            "file_ref": file_ref,
            "hash": {"algorithm": "sha1", "value": file_hash(wav_path)},
            "audio_properties": props,
        }
        if status in ("ok", "partial")
        else None,
    }


def _track_map(track_id: str, status: str = "ok") -> dict:
    return {
        "document_type": "sample_brain.track_map",
        "schema_version": "1.0.0",
        "source": {
            "original": {
                "file_name": "demo_track.wav",
                "hash": {"algorithm": "sha1", "value": track_id},
                "audio_properties": {
                    "duration_sec": 240.0,
                    "sample_rate_hz": 44100,
                    "channels": 1,
                },
            }
        },
        "analysis": {"status": status},
    }


def _root_manifest(
    pack_id: str,
    track_id: str,
    assets: list[dict],
    stems: list[dict] | None = None,
    track_map_status: str = "ok",
    schema_version: str = "1.0.0",
    document_type: str = "sample_brain.performance_pack_manifest",
) -> dict:
    return {
        "document_type": document_type,
        "schema_version": schema_version,
        "pack_id": pack_id,
        "source_track": {
            "track_id": track_id,
            "track_ref": "analysis/track_map.json",
            "file_name": "demo_track.wav",
            "hash": {"algorithm": "sha1", "value": track_id},
            "audio_properties": {
                "duration_sec": 240.0,
                "sample_rate_hz": 44100,
                "channels": 1,
            },
        },
        "documents": {
            "track_map": {
                "ref": "analysis/track_map.json",
                "document_type": "sample_brain.track_map",
                "schema_version": "1.0.0",
                "status": track_map_status,
            }
        },
        "assets": assets,
        "stems": stems if stems is not None else [],
        "status": "complete" if track_map_status == "ok" else "failed",
        "provenance": {"components": {"pack_assembler": {"component": "pack_assembler"}}},
        "quality": {"notes": []},
    }


def build_synthetic_pack(
    pack_root: Path,
    *,
    with_stem: bool = True,
    asset_status: str = "ok",
    rendering_status: str = "rendered",
    stem_status: str = "ok",
) -> dict:
    """Build a fully valid synthetic pack; return the root manifest dict."""
    (pack_root / "analysis").mkdir(parents=True, exist_ok=True)

    loop_wav = write_sine_wav(pack_root / "loops" / "loop_a.wav", duration_sec=1.0, frequency_hz=440.0)
    loop_manifest = _asset_manifest(
        "asset_loop_a", TRACK_ID, "loop", "master", loop_wav,
        file_ref="loop_a.wav", rendering_status=rendering_status, asset_status=asset_status,
    )
    (pack_root / "loops").mkdir(parents=True, exist_ok=True)
    (pack_root / "loops" / "loop_a.json").write_text(json.dumps(loop_manifest), encoding="utf-8")

    section_wav = write_sine_wav(pack_root / "sections" / "section_b.wav", duration_sec=1.0, frequency_hz=220.0)
    section_manifest = _asset_manifest(
        "asset_section_b", TRACK_ID, "section", "master", section_wav,
        file_ref="section_b.wav", rendering_status=rendering_status, asset_status=asset_status,
    )
    (pack_root / "sections").mkdir(parents=True, exist_ok=True)
    (pack_root / "sections" / "section_b.json").write_text(json.dumps(section_manifest), encoding="utf-8")

    assets = [
        {
            "asset_id": "asset_loop_a",
            "asset_ref": "loops/loop_a.json",
            "document_type": "sample_brain.asset_manifest",
            "schema_version": "1.1.0",
            "asset_kind": "loop",
            "source_kind": "master",
            "track_ref": TRACK_ID,
            "range": loop_manifest["range"],
            "status": asset_status,
        },
        {
            "asset_id": "asset_section_b",
            "asset_ref": "sections/section_b.json",
            "document_type": "sample_brain.asset_manifest",
            "schema_version": "1.1.0",
            "asset_kind": "section",
            "source_kind": "master",
            "track_ref": TRACK_ID,
            "range": section_manifest["range"],
            "status": asset_status,
        },
    ]

    stems = []
    if with_stem:
        stem_wav = write_sine_wav(pack_root / "stems" / "stem_drums_01.wav", duration_sec=2.0, frequency_hz=110.0)
        stem_manifest = _stem_manifest(
            "stem_drums_01", TRACK_ID, stem_wav, file_ref="stem_drums_01.wav", status=stem_status,
        )
        (pack_root / "stems").mkdir(parents=True, exist_ok=True)
        (pack_root / "stems" / "stem_drums_01.json").write_text(json.dumps(stem_manifest), encoding="utf-8")
        stems = [
            {
                "stem_id": "stem_drums_01",
                "stem_ref": "stems/stem_drums_01.json",
                "document_type": "sample_brain.stem_manifest",
                "schema_version": "1.0.0",
                "track_ref": TRACK_ID,
                "status": stem_status,
            }
        ]

    root = _root_manifest(PACK_ID, TRACK_ID, assets, stems)
    (pack_root / "analysis" / "track_map.json").write_text(json.dumps(_track_map(TRACK_ID)), encoding="utf-8")
    (pack_root / "manifest.json").write_text(json.dumps(root), encoding="utf-8")
    return root


# ---- pack_reading ---------------------------------------------------------

def test_valid_synthetic_pack_loads_from_root(tmp_path):
    from src.performance_pack_import import run_pack_import

    pack_root = tmp_path / "pack"
    build_synthetic_pack(pack_root)
    result = run_pack_import(pack_root)
    assert result.pack_id == PACK_ID
    assert result.imported == 3
    assert result.reused == 0
    assert result.skipped == 0
    assert len(result.sample_ids) == 3


def test_valid_synthetic_pack_loads_from_manifest_path(tmp_path):
    from src.performance_pack_import import run_pack_import

    pack_root = tmp_path / "pack"
    build_synthetic_pack(pack_root)
    result = run_pack_import(pack_root / "manifest.json")
    assert result.imported == 3


def test_unsupported_major_fail_closed(tmp_path):
    from src.performance_pack_import import PackImportError, run_pack_import

    pack_root = tmp_path / "pack"
    root = build_synthetic_pack(pack_root)
    root["schema_version"] = "2.0.0"
    (pack_root / "manifest.json").write_text(json.dumps(root), encoding="utf-8")
    with pytest.raises(PackImportError):
        run_pack_import(pack_root)


def test_wrong_document_type_fail_closed(tmp_path):
    from src.performance_pack_import import PackImportError, run_pack_import

    pack_root = tmp_path / "pack"
    root = build_synthetic_pack(pack_root)
    root["document_type"] = "sample_brain.track_map"
    (pack_root / "manifest.json").write_text(json.dumps(root), encoding="utf-8")
    with pytest.raises(PackImportError):
        run_pack_import(pack_root)


def test_missing_track_map_fail_closed(tmp_path):
    from src.performance_pack_import import PackImportError, run_pack_import

    pack_root = tmp_path / "pack"
    build_synthetic_pack(pack_root)
    (pack_root / "analysis" / "track_map.json").unlink()
    with pytest.raises(PackImportError):
        run_pack_import(pack_root)


# ---- portability ----------------------------------------------------------

def _mutate_manifest(pack_root, fn):
    root = json.loads((pack_root / "manifest.json").read_text(encoding="utf-8"))
    fn(root)
    (pack_root / "manifest.json").write_text(json.dumps(root), encoding="utf-8")


def test_absolute_asset_ref_rejected(tmp_path):
    from src.performance_pack_import import PackImportError, run_pack_import

    pack_root = tmp_path / "pack"
    build_synthetic_pack(pack_root)
    _mutate_manifest(pack_root, lambda r: r["assets"][0].__setitem__("asset_ref", "C:/x/loop.json"))
    with pytest.raises(PackImportError):
        run_pack_import(pack_root)


def test_windows_drive_ref_rejected(tmp_path):
    from src.performance_pack_import import PackImportError, run_pack_import

    pack_root = tmp_path / "pack"
    build_synthetic_pack(pack_root)
    _mutate_manifest(pack_root, lambda r: r["assets"][0].__setitem__("asset_ref", "D:\\x\\loop.json"))
    with pytest.raises(PackImportError):
        run_pack_import(pack_root)


def test_unc_ref_rejected(tmp_path):
    from src.performance_pack_import import PackImportError, run_pack_import

    pack_root = tmp_path / "pack"
    build_synthetic_pack(pack_root)
    _mutate_manifest(pack_root, lambda r: r["assets"][0].__setitem__("asset_ref", "//server/share/loop.json"))
    with pytest.raises(PackImportError):
        run_pack_import(pack_root)


def test_file_uri_ref_rejected(tmp_path):
    from src.performance_pack_import import PackImportError, run_pack_import

    pack_root = tmp_path / "pack"
    build_synthetic_pack(pack_root)
    _mutate_manifest(pack_root, lambda r: r["assets"][0].__setitem__("asset_ref", "file:///loop.json"))
    with pytest.raises(PackImportError):
        run_pack_import(pack_root)


def test_traversal_ref_rejected(tmp_path):
    from src.performance_pack_import import PackImportError, run_pack_import

    pack_root = tmp_path / "pack"
    build_synthetic_pack(pack_root)
    _mutate_manifest(pack_root, lambda r: r["assets"][0].__setitem__("asset_ref", "../outside.json"))
    with pytest.raises(PackImportError):
        run_pack_import(pack_root)


def test_resolved_path_outside_pack_root_rejected(tmp_path):
    from src.performance_pack_import import PackImportError, run_pack_import

    pack_root = tmp_path / "pack"
    build_synthetic_pack(pack_root)
    # asset_ref resolving inside pack but file_ref escaping the asset dir
    loop_json = pack_root / "loops" / "loop_a.json"
    data = json.loads(loop_json.read_text(encoding="utf-8"))
    data["rendering"]["output"]["file_ref"] = "../../escaped.wav"
    loop_json.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(PackImportError):
        run_pack_import(pack_root)


# ---- integrity ------------------------------------------------------------

def test_asset_id_mismatch_rejected(tmp_path):
    from src.performance_pack_import import PackImportError, run_pack_import

    pack_root = tmp_path / "pack"
    build_synthetic_pack(pack_root)
    _mutate_manifest(pack_root, lambda r: r["assets"][0].__setitem__("asset_id", "WRONG"))
    with pytest.raises(PackImportError):
        run_pack_import(pack_root)


def test_asset_track_ref_mismatch_rejected(tmp_path):
    from src.performance_pack_import import PackImportError, run_pack_import

    pack_root = tmp_path / "pack"
    build_synthetic_pack(pack_root)
    asset_path = pack_root / "loops" / "loop_a.json"
    data = json.loads(asset_path.read_text(encoding="utf-8"))
    data["track_ref"] = "track_WRONG"
    asset_path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(PackImportError):
        run_pack_import(pack_root)


def test_missing_declared_wav_rejected(tmp_path):
    from src.performance_pack_import import PackImportError, run_pack_import

    pack_root = tmp_path / "pack"
    build_synthetic_pack(pack_root)
    (pack_root / "loops" / "loop_a.wav").unlink()
    with pytest.raises(PackImportError):
        run_pack_import(pack_root)


def test_audio_hash_mismatch_rejected(tmp_path):
    from src.performance_pack_import import PackImportError, run_pack_import

    pack_root = tmp_path / "pack"
    build_synthetic_pack(pack_root)
    # rewrite the WAV with different content but keep manifest hash
    write_sine_wav(pack_root / "loops" / "loop_a.wav", duration_sec=1.0, frequency_hz=880.0)
    with pytest.raises(PackImportError):
        run_pack_import(pack_root)


def test_sample_rate_mismatch_rejected(tmp_path):
    from src.performance_pack_import import PackImportError, run_pack_import

    pack_root = tmp_path / "pack"
    build_synthetic_pack(pack_root)
    loop_json = pack_root / "loops" / "loop_a.json"
    data = json.loads(loop_json.read_text(encoding="utf-8"))
    data["rendering"]["output"]["audio_properties"]["sample_rate_hz"] = 48000
    loop_json.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(PackImportError):
        run_pack_import(pack_root)


def test_channels_mismatch_rejected(tmp_path):
    from src.performance_pack_import import PackImportError, run_pack_import

    pack_root = tmp_path / "pack"
    build_synthetic_pack(pack_root)
    loop_json = pack_root / "loops" / "loop_a.json"
    data = json.loads(loop_json.read_text(encoding="utf-8"))
    data["rendering"]["output"]["audio_properties"]["channels"] = 2
    loop_json.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(PackImportError):
        run_pack_import(pack_root)


def test_n_samples_mismatch_rejected(tmp_path):
    from src.performance_pack_import import PackImportError, run_pack_import

    pack_root = tmp_path / "pack"
    build_synthetic_pack(pack_root)
    loop_json = pack_root / "loops" / "loop_a.json"
    data = json.loads(loop_json.read_text(encoding="utf-8"))
    data["rendering"]["output"]["audio_properties"]["n_samples"] += 1
    loop_json.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(PackImportError):
        run_pack_import(pack_root)


# ---- registration ---------------------------------------------------------

def test_loop_and_section_registered(tmp_path):
    from src.db import get_engine, text
    from src.performance_pack_import import run_pack_import

    pack_root = tmp_path / "pack"
    build_synthetic_pack(pack_root, with_stem=False)
    result = run_pack_import(pack_root)
    assert result.imported == 2
    engine = get_engine()
    with engine.begin() as conn:
        rows = conn.execute(text("SELECT path FROM samples ORDER BY id")).fetchall()
    assert len(rows) == 2


def test_optional_stem_registered(tmp_path):
    from src.performance_pack_import import run_pack_import

    pack_root = tmp_path / "pack"
    build_synthetic_pack(pack_root, with_stem=True)
    result = run_pack_import(pack_root)
    assert result.imported == 3


def test_failed_optional_stem_no_fake_sample(tmp_path):
    from src.db import get_engine, text
    from src.performance_pack_import import run_pack_import

    pack_root = tmp_path / "pack"
    build_synthetic_pack(pack_root, with_stem=True, stem_status="failed")
    result = run_pack_import(pack_root)
    # loop + section imported, failed stem skipped
    assert result.imported == 2
    assert result.skipped == 1
    engine = get_engine()
    with engine.begin() as conn:
        n = conn.execute(text("SELECT COUNT(*) FROM samples")).fetchone()[0]
    assert n == 2


def test_not_run_optional_asset_no_fake_sample(tmp_path):
    from src.db import get_engine, text
    from src.performance_pack_import import run_pack_import

    pack_root = tmp_path / "pack"
    build_synthetic_pack(pack_root, with_stem=False, asset_status="not_run")
    result = run_pack_import(pack_root)
    assert result.imported == 0
    assert result.skipped == 2
    engine = get_engine()
    with engine.begin() as conn:
        n = conn.execute(text("SELECT COUNT(*) FROM samples")).fetchone()[0]
    assert n == 0


# ---- dedupe ---------------------------------------------------------------

def test_reimport_same_pack_no_second_row(tmp_path):
    from src.db import get_engine, text
    from src.performance_pack_import import run_pack_import

    pack_root = tmp_path / "pack"
    build_synthetic_pack(pack_root)
    first = run_pack_import(pack_root)
    second = run_pack_import(pack_root)
    assert second.imported == 0
    assert second.reused == 3
    engine = get_engine()
    with engine.begin() as conn:
        n = conn.execute(text("SELECT COUNT(*) FROM samples")).fetchone()[0]
    assert n == 3
    assert set(second.sample_ids) == set(first.sample_ids)


def test_same_hash_two_paths_same_sample_id(tmp_path):
    from src.performance_pack_import import run_pack_import

    pack_root = tmp_path / "pack"
    build_synthetic_pack(pack_root)
    first = run_pack_import(pack_root)
    # second pack with identical audio content but different file paths
    pack_root2 = tmp_path / "pack2"
    root2 = build_synthetic_pack(pack_root2)
    second = run_pack_import(pack_root2)
    assert second.reused == 3
    assert set(second.sample_ids) == set(first.sample_ids)


def test_same_path_different_hash_fail_closed(tmp_path):
    from src.db import get_engine, text
    from src.performance_pack_import import PackImportError, run_pack_import
    from tests.audio_fixtures import write_sine_wav

    pack_root = tmp_path / "pack"
    build_synthetic_pack(pack_root)
    run_pack_import(pack_root)
    # change audio content but keep manifest hash by re-rendering then re-import
    write_sine_wav(pack_root / "loops" / "loop_a.wav", duration_sec=1.0, frequency_hz=990.0)
    with pytest.raises(PackImportError):
        run_pack_import(pack_root)
    engine = get_engine()
    with engine.begin() as conn:
        n = conn.execute(text("SELECT COUNT(*) FROM samples")).fetchone()[0]
    assert n == 3  # unchanged, no overwrite


def test_tags_not_duplicated(tmp_path):
    from src.db import get_engine, text
    from src.performance_pack_import import run_pack_import

    pack_root = tmp_path / "pack"
    build_synthetic_pack(pack_root)
    run_pack_import(pack_root)
    run_pack_import(pack_root)
    engine = get_engine()
    with engine.begin() as conn:
        n = conn.execute(
            text("SELECT COUNT(*) FROM sample_tags WHERE tag = :t AND source = 'performance_pack'"),
            {"t": f"pack:{PACK_ID}"},
        ).fetchone()[0]
    assert n == 3  # once per imported item, not multiplied by re-import


# ---- lineage -------------------------------------------------------------

def test_lineage_tags_present(tmp_path):
    from src.db import get_engine, text
    from src.performance_pack_import import run_pack_import

    pack_root = tmp_path / "pack"
    build_synthetic_pack(pack_root)
    result = run_pack_import(pack_root)
    sid = result.sample_ids[0]
    engine = get_engine()
    with engine.begin() as conn:
        tags = {
            r[0]
            for r in conn.execute(
                text("SELECT tag FROM sample_tags WHERE sample_id = :s AND source = 'performance_pack'"),
                {"s": sid},
            ).fetchall()
        }
    assert f"pack:{PACK_ID}" in tags
    assert f"parent_track:{TRACK_ID}" in tags
    assert "item_kind:loop" in tags
    assert "item_id:asset_loop_a" in tags
    assert all("C:" not in t and not t.startswith("/") for t in tags)


def test_two_assets_groupable_by_parent_track(tmp_path):
    from src.db import get_engine, text
    from src.performance_pack_import import run_pack_import
    from src.search_filters import SearchFilters, resolve_filtered_sample_ids

    pack_root = tmp_path / "pack"
    build_synthetic_pack(pack_root, with_stem=False)
    run_pack_import(pack_root)
    ids = resolve_filtered_sample_ids(SearchFilters(tags=(f"parent_track:{TRACK_ID}",)))
    assert ids is not None and len(ids) == 2


# ---- normal pipeline -----------------------------------------------------

def test_run_analyze_produces_features(tmp_path):
    from src.analyze import run_analyze
    from src.db import get_engine, text
    from src.performance_pack_import import run_pack_import

    pack_root = tmp_path / "pack"
    build_synthetic_pack(pack_root)
    run_pack_import(pack_root)
    run_analyze(only_missing=True)
    engine = get_engine()
    with engine.begin() as conn:
        n = conn.execute(text("SELECT COUNT(*) FROM features")).fetchone()[0]
    assert n == 3


def test_matching_sees_imported_asset(tmp_path):
    from src.analyze import run_analyze
    from src.classify import write_autotype_to_db
    from src.matching import MatchProfile, collect_matches
    from src.performance_pack_import import run_pack_import

    pack_root = tmp_path / "pack"
    build_synthetic_pack(pack_root, with_stem=False)
    result = run_pack_import(pack_root)
    run_analyze(only_missing=True)
    write_autotype_to_db(use_knn=False)
    matches = collect_matches(MatchProfile(target_bpm=120.0, limit=50))
    assert matches.ok
    assert result.sample_ids[0] in {m.sample_id for m in matches.matches}


def test_search_filter_selects_imported_asset(tmp_path):
    from src.performance_pack_import import run_pack_import
    from src.search_filters import SearchFilters, resolve_filtered_sample_ids

    pack_root = tmp_path / "pack"
    build_synthetic_pack(pack_root)
    result = run_pack_import(pack_root)
    ids = resolve_filtered_sample_ids(SearchFilters(tags=(f"pack:{PACK_ID}",)))
    assert ids == set(result.sample_ids)


# ---- manifest truth -------------------------------------------------------

def test_manifest_not_mutated(tmp_path):
    from src.performance_pack_import import run_pack_import

    pack_root = tmp_path / "pack"
    root_before = build_synthetic_pack(pack_root)
    run_pack_import(pack_root)
    root_after = json.loads((pack_root / "manifest.json").read_text(encoding="utf-8"))
    assert root_after == root_before


# ---- privacy -------------------------------------------------------------

def test_only_synthetic_tmp_artifacts(tmp_path):
    # The fixture build path uses only tmp_path + synthetic WAVs; this asserts
    # no absolute private path leaks into tags.
    from src.db import get_engine, text
    from src.performance_pack_import import run_pack_import

    pack_root = tmp_path / "pack"
    build_synthetic_pack(pack_root)
    run_pack_import(pack_root)
    engine = get_engine()
    with engine.begin() as conn:
        bad = conn.execute(
            text("SELECT COUNT(*) FROM sample_tags WHERE tag LIKE 'C:%' OR tag LIKE '/%'"),
        ).fetchone()[0]
    assert bad == 0
