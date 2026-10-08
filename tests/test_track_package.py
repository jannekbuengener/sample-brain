"""Runtime acceptance for #1085A track package core.

Consumes the #1082 ownership freeze:
- docs/TRACK_PACKAGE_OWNERSHIP_CONTRACT.md
- docs/track_package_ownership_v1.json

Out of scope here: Browser registration, legacy migration, autosave wiring,
Arrangement/QML, and active-package restart precedence.
"""

from __future__ import annotations

import json
import os
import shutil
from pathlib import Path

import pytest

from src import track_package as tp
from tests.audio_fixtures import write_sine_wav


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _write_source(root: Path, name: str = "kick.wav", *, freq: float = 60.0) -> Path:
    path = root / name
    write_sine_wav(path, duration_sec=0.05, frequency_hz=freq)
    return path


def _draft_with_sources(
    *sources: Path,
    track_id: str | None = None,
    master_bpm: float = 128.0,
    sync_enabled: bool = True,
) -> tp.TrackPackageDraft:
    media_sources = tuple(
        tp.TrackPackageMediaSource(source_path=src) for src in sources
    )
    live_kit: dict[str, dict[str, dict[str, str] | None]] = {
        "Kick + Bass": {"Kick": None, "Bass": None},
        "Drums": {
            "Main Drum": None,
            "Closed Hat": None,
            "Open Hat": None,
            "Percussion": None,
            "Additional": None,
        },
        "Melodic": {"Lead": None, "Pad": None},
        "Atmos / FX": {"Atmos": None, "FX": None},
    }
    if sources:
        live_kit["Kick + Bass"]["Kick"] = {"path": str(sources[0].resolve())}
    if len(sources) > 1:
        live_kit["Drums"]["Main Drum"] = {"path": str(sources[1].resolve())}
    musical = {
        "live_kit": live_kit,
        "channel_rack": None,
        "master_bpm": master_bpm,
        "sync_enabled": sync_enabled,
    }
    return tp.TrackPackageDraft(
        media_sources=media_sources,
        musical=musical,
        track_id=track_id,
    )


def _package_json(package_root: Path) -> dict:
    raw = (package_root / tp.TRACK_PACKAGE_FILENAME).read_text(encoding="utf-8")
    return json.loads(raw)


# --- Create success ---------------------------------------------------------


def test_create_package_success_structure_and_relative_refs(tmp_path: Path) -> None:
    library = tmp_path / "library"
    library.mkdir()
    src = _write_source(library)
    before = src.read_bytes()

    dest_parent = tmp_path / "packages"
    dest_parent.mkdir()
    package_root = dest_parent / "track-one"

    result = tp.create_track_package(
        _draft_with_sources(src),
        package_root,
        repo_root=_repo_root(),
    )

    assert result.outcome == tp.OUTCOME_OPEN
    assert result.ok is True
    assert result.package_root == package_root
    assert result.track_id
    assert package_root.is_dir()
    assert (package_root / tp.TRACK_PACKAGE_FILENAME).is_file()
    assert (package_root / tp.MEDIA_DIR_NAME).is_dir()

    entries = sorted(p.name for p in package_root.iterdir())
    assert entries == [tp.MEDIA_DIR_NAME, tp.TRACK_PACKAGE_FILENAME]

    payload = _package_json(package_root)
    assert payload["schema_version"] == tp.SCHEMA_VERSION
    assert payload["package_kind"] == tp.PACKAGE_KIND
    assert payload["track_id"] == result.track_id
    assert payload["media"]
    for entry in payload["media"]:
        assert entry["relpath"].startswith(f"{tp.MEDIA_DIR_NAME}/")
        assert ".." not in entry["relpath"]
        assert not Path(entry["relpath"]).is_absolute()
        assert (package_root / entry["relpath"]).is_file()

    dumped = json.dumps(payload)
    assert ":\\" not in dumped
    assert "\\\\" not in dumped
    assert "file://" not in dumped
    assert str(library.resolve()) not in dumped
    assert str(src.resolve()) not in dumped

    assert src.read_bytes() == before
    assert src.exists()


def test_create_preserves_source_bytes_and_contract_open_result(tmp_path: Path) -> None:
    library = tmp_path / "lib"
    library.mkdir()
    a = _write_source(library, "a.wav", freq=80.0)
    b = _write_source(library, "b.wav", freq=120.0)
    bytes_a, bytes_b = a.read_bytes(), b.read_bytes()

    package_root = tmp_path / "out" / "pkg"
    package_root.parent.mkdir()
    result = tp.create_track_package(
        _draft_with_sources(a, b, track_id="trk_fixed_for_test"),
        package_root,
        repo_root=_repo_root(),
    )
    assert result.outcome == tp.OUTCOME_OPEN
    assert result.track_id == "trk_fixed_for_test"
    assert a.read_bytes() == bytes_a
    assert b.read_bytes() == bytes_b
    media_files = list((package_root / tp.MEDIA_DIR_NAME).rglob("*"))
    assert len([p for p in media_files if p.is_file()]) == 2


# --- Portability ------------------------------------------------------------


def test_relocate_open_without_original_library(tmp_path: Path) -> None:
    library = tmp_path / "library"
    library.mkdir()
    src = _write_source(library)
    created_root = tmp_path / "created" / "pkg"
    created_root.parent.mkdir()
    created = tp.create_track_package(
        _draft_with_sources(src, track_id="trk_portable"),
        created_root,
        repo_root=_repo_root(),
    )
    assert created.outcome == tp.OUTCOME_OPEN

    relocated = tmp_path / "elsewhere" / "moved-pkg"
    relocated.parent.mkdir()
    shutil.copytree(created_root, relocated)
    shutil.rmtree(library)
    assert not src.exists()

    opened = tp.open_track_package(relocated)
    assert opened.outcome == tp.OUTCOME_OPEN
    assert opened.ok is True
    assert opened.track_id == "trk_portable"
    assert opened.manifest is not None
    for entry in opened.manifest.media:
        resolved = (relocated / entry.relpath).resolve()
        assert resolved.is_file()
        assert resolved.is_relative_to(relocated.resolve())


# --- Missing source during create -------------------------------------------


def test_missing_source_returns_missing_media_no_final_package(tmp_path: Path) -> None:
    library = tmp_path / "library"
    library.mkdir()
    missing = library / "gone.wav"
    draft = _draft_with_sources(missing)
    # Source never created; also keep a real sibling untouched.
    sibling = _write_source(library, "keep.wav")
    before = sibling.read_bytes()

    package_root = tmp_path / "packages" / "pkg"
    package_root.parent.mkdir()
    result = tp.create_track_package(draft, package_root, repo_root=_repo_root())

    assert result.outcome == tp.OUTCOME_MISSING_MEDIA
    assert result.ok is False
    assert not package_root.exists()
    assert sibling.read_bytes() == before
    staging_left = list(package_root.parent.glob(".sample-brain-track-package-*"))
    assert staging_left == []


# --- Existing destination ---------------------------------------------------


def test_existing_destination_fail_closed_leaves_foreign_files(tmp_path: Path) -> None:
    library = tmp_path / "library"
    library.mkdir()
    src = _write_source(library)
    package_root = tmp_path / "packages" / "pkg"
    package_root.mkdir(parents=True)
    foreign = package_root / "foreign.txt"
    foreign.write_text("keep-me", encoding="utf-8")

    result = tp.create_track_package(
        _draft_with_sources(src),
        package_root,
        repo_root=_repo_root(),
    )
    assert result.outcome == tp.OUTCOME_DESTINATION_UNAVAILABLE
    assert foreign.read_text(encoding="utf-8") == "keep-me"
    assert not (package_root / tp.TRACK_PACKAGE_FILENAME).exists()


def test_destination_inside_repo_rejected(tmp_path: Path) -> None:
    library = tmp_path / "library"
    library.mkdir()
    src = _write_source(library)
    synthetic_repo = tmp_path / "checkout"
    synthetic_repo.mkdir()
    inside = synthetic_repo / "nested" / "pkg"
    inside.parent.mkdir(parents=True)

    result = tp.create_track_package(
        _draft_with_sources(src),
        inside,
        repo_root=synthetic_repo,
    )
    assert result.outcome == tp.OUTCOME_DESTINATION_UNAVAILABLE
    assert not inside.exists()


# --- Interrupted copy -------------------------------------------------------


def test_interrupted_copy_cleans_staging_and_allows_retry(tmp_path: Path) -> None:
    library = tmp_path / "library"
    library.mkdir()
    src = _write_source(library)
    before = src.read_bytes()
    package_root = tmp_path / "packages" / "pkg"
    package_root.parent.mkdir()

    calls = {"n": 0}

    def flaky_copy(src_path: Path, dst_path: Path) -> None:
        calls["n"] += 1
        if calls["n"] == 1:
            dst_path.parent.mkdir(parents=True, exist_ok=True)
            dst_path.write_bytes(b"partial")
            raise OSError("simulated copy interrupt")
        shutil.copy2(src_path, dst_path)

    failed = tp.create_track_package(
        _draft_with_sources(src),
        package_root,
        repo_root=_repo_root(),
        copy_file=flaky_copy,
    )
    assert failed.outcome == tp.OUTCOME_COPY_INTERRUPTED
    assert not package_root.exists()
    assert list(package_root.parent.glob(".sample-brain-track-package-*")) == []
    assert src.read_bytes() == before

    ok = tp.create_track_package(
        _draft_with_sources(src),
        package_root,
        repo_root=_repo_root(),
        copy_file=flaky_copy,
    )
    assert ok.outcome == tp.OUTCOME_OPEN
    assert package_root.is_dir()
    assert (package_root / tp.TRACK_PACKAGE_FILENAME).is_file()


# --- Manifest validate / open -----------------------------------------------


def test_corrupt_json_rejected(tmp_path: Path) -> None:
    root = tmp_path / "pkg"
    root.mkdir()
    (root / tp.MEDIA_DIR_NAME).mkdir()
    (root / tp.TRACK_PACKAGE_FILENAME).write_text("{not-json", encoding="utf-8")
    result = tp.validate_track_package(root)
    assert result.outcome == tp.OUTCOME_CORRUPT_OR_UNSUPPORTED
    opened = tp.open_track_package(root)
    assert opened.outcome == tp.OUTCOME_CORRUPT_OR_UNSUPPORTED


def test_unsupported_schema_and_wrong_kind_rejected(tmp_path: Path) -> None:
    root = tmp_path / "pkg"
    root.mkdir()
    (root / tp.MEDIA_DIR_NAME).mkdir()
    media = root / tp.MEDIA_DIR_NAME / "a.wav"
    write_sine_wav(media, duration_sec=0.02, frequency_hz=40.0)

    bad_schema = {
        "schema_version": 99,
        "package_kind": tp.PACKAGE_KIND,
        "track_id": "trk_x",
        "media": [{"media_id": "m1", "relpath": "media/a.wav"}],
        "musical": {
            "live_kit": {},
            "channel_rack": None,
            "master_bpm": 120.0,
            "sync_enabled": False,
        },
    }
    (root / tp.TRACK_PACKAGE_FILENAME).write_text(
        json.dumps(bad_schema, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    assert (
        tp.validate_track_package(root).outcome == tp.OUTCOME_CORRUPT_OR_UNSUPPORTED
    )

    bad_kind = dict(bad_schema)
    bad_kind["schema_version"] = 1
    bad_kind["package_kind"] = "sample_brain_live_kit"
    (root / tp.TRACK_PACKAGE_FILENAME).write_text(
        json.dumps(bad_kind, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    assert (
        tp.validate_track_package(root).outcome == tp.OUTCOME_CORRUPT_OR_UNSUPPORTED
    )


def test_missing_media_on_open(tmp_path: Path) -> None:
    library = tmp_path / "library"
    library.mkdir()
    src = _write_source(library)
    package_root = tmp_path / "pkg"
    created = tp.create_track_package(
        _draft_with_sources(src),
        package_root,
        repo_root=_repo_root(),
    )
    assert created.outcome == tp.OUTCOME_OPEN
    media_dir = package_root / tp.MEDIA_DIR_NAME
    for path in media_dir.rglob("*"):
        if path.is_file():
            path.unlink()
    result = tp.open_track_package(package_root)
    assert result.outcome == tp.OUTCOME_MISSING_MEDIA


# --- Path confinement -------------------------------------------------------


@pytest.mark.parametrize(
    "evil_relpath",
    [
        "../escape.wav",
        "media/../../escape.wav",
        "C:/Windows/escape.wav",
        "D:\\escape.wav",
        "//server/share/escape.wav",
        "\\\\server\\share\\escape.wav",
        "file:///C:/escape.wav",
        "/tmp/escape.wav",
    ],
)
def test_path_escape_string_forms_rejected(tmp_path: Path, evil_relpath: str) -> None:
    root = tmp_path / "pkg"
    root.mkdir()
    (root / tp.MEDIA_DIR_NAME).mkdir()
    payload = {
        "schema_version": 1,
        "package_kind": tp.PACKAGE_KIND,
        "track_id": "trk_escape",
        "media": [{"media_id": "m1", "relpath": evil_relpath}],
        "musical": {
            "live_kit": {},
            "channel_rack": None,
            "master_bpm": 120.0,
            "sync_enabled": False,
        },
    }
    (root / tp.TRACK_PACKAGE_FILENAME).write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    result = tp.validate_track_package(root)
    assert result.outcome == tp.OUTCOME_PATH_ESCAPE_REJECTED


def test_symlink_escape_rejected(tmp_path: Path) -> None:
    root = tmp_path / "pkg"
    root.mkdir()
    media = root / tp.MEDIA_DIR_NAME
    media.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    outside_file = outside / "secret.wav"
    write_sine_wav(outside_file, duration_sec=0.02, frequency_hz=33.0)
    link = media / "linked.wav"
    try:
        os.symlink(outside_file, link)
    except (OSError, NotImplementedError):
        pytest.skip("symlink creation unavailable on this host")

    payload = {
        "schema_version": 1,
        "package_kind": tp.PACKAGE_KIND,
        "track_id": "trk_symlink",
        "media": [{"media_id": "m1", "relpath": "media/linked.wav"}],
        "musical": {
            "live_kit": {},
            "channel_rack": None,
            "master_bpm": 120.0,
            "sync_enabled": False,
        },
    }
    (root / tp.TRACK_PACKAGE_FILENAME).write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    result = tp.validate_track_package(root)
    assert result.outcome == tp.OUTCOME_PATH_ESCAPE_REJECTED


def test_windows_reparse_directory_escape_rejected(tmp_path: Path) -> None:
    root = tmp_path / "pkg"
    root.mkdir()
    media = root / tp.MEDIA_DIR_NAME
    media.mkdir()
    outside = tmp_path / "outside_dir"
    outside.mkdir()
    outside_file = outside / "escape.wav"
    write_sine_wav(outside_file, duration_sec=0.02, frequency_hz=41.0)
    junction = media / "junc"
    try:
        os.symlink(outside, junction, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("directory symlink/reparse unavailable on this host")

    payload = {
        "schema_version": 1,
        "package_kind": tp.PACKAGE_KIND,
        "track_id": "trk_reparse",
        "media": [{"media_id": "m1", "relpath": "media/junc/escape.wav"}],
        "musical": {
            "live_kit": {},
            "channel_rack": None,
            "master_bpm": 120.0,
            "sync_enabled": False,
        },
    }
    (root / tp.TRACK_PACKAGE_FILENAME).write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    result = tp.validate_track_package(root)
    assert result.outcome == tp.OUTCOME_PATH_ESCAPE_REJECTED


def test_confinement_helper_rejects_outside_resolved_target(tmp_path: Path) -> None:
    root = tmp_path / "pkg"
    root.mkdir()
    (root / tp.MEDIA_DIR_NAME).mkdir()
    outcome = tp.validate_confined_media_relpath("media/../outside.wav", root)
    assert outcome == tp.OUTCOME_PATH_ESCAPE_REJECTED


# --- Determinism ------------------------------------------------------------


def test_serialize_manifest_deterministic_and_stable_ordering() -> None:
    media = (
        tp.MediaEntry(media_id="m_b", relpath="media/b.wav"),
        tp.MediaEntry(media_id="m_a", relpath="media/a.wav"),
    )
    manifest = tp.TrackPackageManifest(
        schema_version=1,
        package_kind=tp.PACKAGE_KIND,
        track_id="trk_det",
        media=media,
        musical={
            "live_kit": {"Kick + Bass": {"Kick": {"path": "media/a.wav"}, "Bass": None}},
            "channel_rack": None,
            "master_bpm": 100.0,
            "sync_enabled": False,
        },
    )
    a = tp.serialize_track_package_json(manifest)
    b = tp.serialize_track_package_json(manifest)
    assert a == b
    parsed = json.loads(a)
    assert [e["media_id"] for e in parsed["media"]] == ["m_a", "m_b"]


def test_track_id_preserved_on_open_and_not_path_derived(tmp_path: Path) -> None:
    library = tmp_path / "library"
    library.mkdir()
    src = _write_source(library, "Display Name Kick!!.wav")
    package_root = tmp_path / "Fancy Display Package"
    result = tp.create_track_package(
        _draft_with_sources(src, track_id="trk_opaque_stable"),
        package_root,
        repo_root=_repo_root(),
    )
    assert result.outcome == tp.OUTCOME_OPEN
    assert result.track_id == "trk_opaque_stable"
    assert "Fancy" not in result.track_id
    assert "Display" not in result.track_id
    opened = tp.open_track_package(package_root)
    assert opened.track_id == "trk_opaque_stable"


def test_new_track_id_is_opaque_and_collision_resistant() -> None:
    ids = {tp.new_track_id() for _ in range(50)}
    assert len(ids) == 50
    for value in ids:
        assert value.startswith("trk_")
        assert "\\" not in value
        assert "/" not in value
        assert ":" not in value


def test_duplicate_media_ids_rejected_on_validate(tmp_path: Path) -> None:
    root = tmp_path / "pkg"
    root.mkdir()
    media = root / tp.MEDIA_DIR_NAME
    media.mkdir()
    write_sine_wav(media / "a.wav", duration_sec=0.02, frequency_hz=40.0)
    write_sine_wav(media / "b.wav", duration_sec=0.02, frequency_hz=50.0)
    payload = {
        "schema_version": 1,
        "package_kind": tp.PACKAGE_KIND,
        "track_id": "trk_dup",
        "media": [
            {"media_id": "same", "relpath": "media/a.wav"},
            {"media_id": "same", "relpath": "media/b.wav"},
        ],
        "musical": {
            "live_kit": {},
            "channel_rack": None,
            "master_bpm": 120.0,
            "sync_enabled": False,
        },
    }
    (root / tp.TRACK_PACKAGE_FILENAME).write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    assert (
        tp.validate_track_package(root).outcome == tp.OUTCOME_CORRUPT_OR_UNSUPPORTED
    )


def test_lifecycle_outcomes_subset_of_1082_vocabulary() -> None:
    allowed = {
        "draft",
        "package_creating",
        "ready",
        "open",
        "missing_media",
        "corrupt_or_unsupported",
        "migration_required",
        "migration_failed",
        "destination_unavailable",
        "copy_interrupted",
        "write_failed",
        "path_escape_rejected",
    }
    for name in (
        "OUTCOME_OPEN",
        "OUTCOME_MISSING_MEDIA",
        "OUTCOME_CORRUPT_OR_UNSUPPORTED",
        "OUTCOME_DESTINATION_UNAVAILABLE",
        "OUTCOME_COPY_INTERRUPTED",
        "OUTCOME_WRITE_FAILED",
        "OUTCOME_PATH_ESCAPE_REJECTED",
    ):
        assert getattr(tp, name) in allowed


def test_musical_absolute_ref_not_in_media_index_rejected(tmp_path: Path) -> None:
    library = tmp_path / "library"
    library.mkdir()
    src = _write_source(library)
    package_root = tmp_path / "packages" / "pkg"
    package_root.parent.mkdir()
    draft = _draft_with_sources(src)
    # Inject an unmapped POSIX absolute path into musical state.
    musical = dict(draft.musical)
    live_kit = dict(musical["live_kit"])
    kick_group = dict(live_kit["Kick + Bass"])
    kick_group["Bass"] = {"path": "/home/user/private/sample.wav"}
    live_kit["Kick + Bass"] = kick_group
    musical["live_kit"] = live_kit
    draft = tp.TrackPackageDraft(
        media_sources=draft.media_sources,
        musical=musical,
        track_id="trk_leak",
    )
    result = tp.create_track_package(draft, package_root, repo_root=_repo_root())
    assert result.outcome == tp.OUTCOME_PATH_ESCAPE_REJECTED
    assert not package_root.exists()


def test_open_rejects_musical_escape_ref_even_if_media_index_clean(
    tmp_path: Path,
) -> None:
    root = tmp_path / "pkg"
    root.mkdir()
    media = root / tp.MEDIA_DIR_NAME
    media.mkdir()
    write_sine_wav(media / "a.wav", duration_sec=0.02, frequency_hz=40.0)
    payload = {
        "schema_version": 1,
        "package_kind": tp.PACKAGE_KIND,
        "track_id": "trk_bad_musical",
        "media": [{"media_id": "m1", "relpath": "media/a.wav"}],
        "musical": {
            "live_kit": {
                "Kick + Bass": {
                    "Kick": {"path": "../../escape.wav"},
                    "Bass": None,
                }
            },
            "channel_rack": None,
            "master_bpm": 120.0,
            "sync_enabled": False,
        },
    }
    (root / tp.TRACK_PACKAGE_FILENAME).write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    assert tp.open_track_package(root).outcome == tp.OUTCOME_PATH_ESCAPE_REJECTED


def test_invalid_musical_field_types_rejected(tmp_path: Path) -> None:
    root = tmp_path / "pkg"
    root.mkdir()
    (root / tp.MEDIA_DIR_NAME).mkdir()
    write_sine_wav(
        root / tp.MEDIA_DIR_NAME / "a.wav", duration_sec=0.02, frequency_hz=40.0
    )
    payload = {
        "schema_version": 1,
        "package_kind": tp.PACKAGE_KIND,
        "track_id": "trk_types",
        "media": [{"media_id": "m1", "relpath": "media/a.wav"}],
        "musical": {
            "live_kit": "bad",
            "channel_rack": [],
            "master_bpm": "fast",
            "sync_enabled": "yes",
        },
    }
    (root / tp.TRACK_PACKAGE_FILENAME).write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    assert (
        tp.validate_track_package(root).outcome == tp.OUTCOME_CORRUPT_OR_UNSUPPORTED
    )


def test_non_serializable_draft_cleans_staging(tmp_path: Path) -> None:
    library = tmp_path / "library"
    library.mkdir()
    src = _write_source(library)
    package_root = tmp_path / "packages" / "pkg"
    package_root.parent.mkdir()
    draft = _draft_with_sources(src)
    musical = dict(draft.musical)
    musical["arrangement_hook"] = object()  # not JSON-serializable
    # Put non-serializable value under musical via opaque extension on draft.
    bad = tp.TrackPackageDraft(
        media_sources=draft.media_sources,
        musical=musical,
        track_id="trk_ser",
        arrangement={"x": object()},
    )
    result = tp.create_track_package(bad, package_root, repo_root=_repo_root())
    assert result.outcome == tp.OUTCOME_CORRUPT_OR_UNSUPPORTED
    assert not package_root.exists()
    assert list(package_root.parent.glob(".sample-brain-track-package-*")) == []


def test_writability_probe_does_not_clobber_existing_name(tmp_path: Path) -> None:
    library = tmp_path / "library"
    library.mkdir()
    src = _write_source(library)
    parent = tmp_path / "packages"
    parent.mkdir()
    sentinel = parent / ".sample-brain-track-package-probe"
    sentinel.write_text("do-not-delete", encoding="utf-8")
    package_root = parent / "pkg"
    result = tp.create_track_package(
        _draft_with_sources(src),
        package_root,
        repo_root=_repo_root(),
    )
    assert result.outcome == tp.OUTCOME_OPEN
    assert sentinel.read_text(encoding="utf-8") == "do-not-delete"


def test_failed_commit_does_not_delete_foreign_package(tmp_path: Path, monkeypatch) -> None:
    library = tmp_path / "library"
    library.mkdir()
    src = _write_source(library)
    parent = tmp_path / "packages"
    parent.mkdir()
    package_root = parent / "pkg"

    # First publish succeeds.
    first = tp.create_track_package(
        _draft_with_sources(src, track_id="trk_first"),
        package_root,
        repo_root=_repo_root(),
    )
    assert first.outcome == tp.OUTCOME_OPEN
    marker = (package_root / tp.TRACK_PACKAGE_FILENAME).read_text(encoding="utf-8")

    # Simulate a second create that somehow reaches commit while destination exists
    # by forcing os.replace to fail after staging is ready; ensure foreign package
    # is preserved. Use a different destination that we create mid-flight.
    other = parent / "other"
    other.mkdir()
    (other / "foreign.txt").write_text("keep", encoding="utf-8")

    def boom(src_path: str | bytes | os.PathLike, dst_path: str | bytes | os.PathLike) -> None:
        # Pretend destination appeared (concurrent publish) then fail rename.
        raise OSError("simulated replace failure")

    monkeypatch.setattr(tp.os, "replace", boom)
    second = tp.create_track_package(
        _draft_with_sources(src, track_id="trk_second"),
        other / "nested-pkg",
        repo_root=_repo_root(),
    )
    assert second.outcome in {
        tp.OUTCOME_WRITE_FAILED,
        tp.OUTCOME_DESTINATION_UNAVAILABLE,
    }
    assert (other / "foreign.txt").read_text(encoding="utf-8") == "keep"
    assert (package_root / tp.TRACK_PACKAGE_FILENAME).read_text(encoding="utf-8") == marker
    assert list(parent.glob(".sample-brain-track-package-*")) == []
