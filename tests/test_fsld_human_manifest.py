from __future__ import annotations

import hashlib
import json
import zipfile
from pathlib import Path

from src.fsld_human_manifest import (
    EXPECTED_ANNOTATIONS_MD5,
    build_manifest,
    canonical_manifest_bytes,
    calibration_target,
    manifest_sha256,
    verify_manifest_files,
    write_manifest_files,
)


def _annotation(
    *,
    key: str | None = "c",
    mode: str | None = "maj",
    bpm: str | None = "120",
    defined_tempo: bool | None = True,
    discard: bool = False,
) -> dict[str, object]:
    payload: dict[str, object] = {"discard": discard}
    if key is not None:
        payload["key"] = key
    if mode is not None:
        payload["mode"] = mode
    if bpm is not None:
        payload["bpm"] = bpm
    if defined_tempo is not None:
        payload["defined_tempo"] = defined_tempo
    return payload


def _write_annotations_zip(tmp_path: Path, entries: dict[str, dict[str, object]]) -> Path:
    path = tmp_path / "annotations.zip"
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w") as archive:
        for name, payload in entries.items():
            archive.writestr(name, json.dumps(payload, sort_keys=True))
    return path


def _build(tmp_path: Path, entries: dict[str, dict[str, object]], metadata=None):
    archive = _write_annotations_zip(tmp_path, entries)
    return build_manifest(
        archive,
        expected_md5=hashlib.md5(archive.read_bytes()).hexdigest(),
        metadata=metadata,
    )


def _ground_truth(record: dict[str, object]) -> dict[str, object]:
    return record["ground_truth"]


def test_ma_and_sa_remain_separate_and_preserve_tier_specific_bpm(tmp_path: Path) -> None:
    manifest = _build(
        tmp_path,
        {
            "annotations/1/sound-100.json": _annotation(bpm="120"),
            "annotations/2/sound-100.json": _annotation(bpm="120"),
            "annotations/1/sound-101.json": _annotation(key="d", mode="min", bpm="99"),
        },
    )

    by_id = {record["public_sample_id"]: record for record in manifest["records"]}
    assert by_id["100"]["annotation_tier"] == "ma"
    assert _ground_truth(by_id["100"])["bpm"] == 120.0
    assert by_id["101"]["annotation_tier"] == "sa"
    assert _ground_truth(by_id["101"])["bpm"] == 99.0


def test_ma_c_unknown_is_unknown_not_known(tmp_path: Path) -> None:
    manifest = _build(
        tmp_path,
        {
            "annotations/1/sound-100.json": _annotation(key="c", mode="maj"),
            "annotations/2/sound-100.json": _annotation(key="unknown", mode="maj"),
        },
    )

    record = manifest["records"][0]
    ground_truth = _ground_truth(record)
    assert ground_truth["tonality"] == "tonal"
    assert ground_truth["key_root"] is None
    assert ground_truth["root_evidence"] == "unknown"
    assert ground_truth["key_mode"] == "maj"
    assert ground_truth["mode_evidence"] == "known"


def test_ma_none_and_tonal_mix_is_excluded_as_tonality_conflict(tmp_path: Path) -> None:
    manifest = _build(
        tmp_path,
        {
            "annotations/1/sound-100.json": _annotation(key="none", mode="none"),
            "annotations/2/sound-100.json": _annotation(key="c", mode="maj"),
        },
    )

    assert manifest["records"] == []
    assert manifest["source_summary"]["exclusions"]["tonality_conflicting"] == 1


def test_no_key_requires_every_valid_ma_annotation_to_be_none_none(tmp_path: Path) -> None:
    manifest = _build(
        tmp_path,
        {
            "annotations/1/sound-100.json": _annotation(key="none", mode="none"),
            "annotations/2/sound-100.json": _annotation(key=None, mode=None),
        },
    )

    assert manifest["records"] == []
    assert manifest["source_summary"]["exclusions"]["tonality_missing"] == 1


def test_no_key_has_not_applicable_root_and_mode(tmp_path: Path) -> None:
    manifest = _build(
        tmp_path,
        {
            "annotations/1/sound-100.json": _annotation(key="none", mode="none"),
            "annotations/2/sound-100.json": _annotation(key="none", mode="none"),
        },
    )

    record = manifest["records"][0]
    ground_truth = _ground_truth(record)
    assert ground_truth["tonality"] == "no_key"
    assert ground_truth["root_evidence"] == "not_applicable"
    assert ground_truth["mode_evidence"] == "not_applicable"


def test_degraded_ma_never_becomes_sa(tmp_path: Path) -> None:
    manifest = _build(
        tmp_path,
        {
            "annotations/1/sound-100.json": _annotation(),
            "annotations/2/sound-100.json": _annotation(discard=True),
        },
    )

    assert manifest["records"] == []
    assert manifest["source_summary"]["exclusions"]["ma_degraded_below_two_valid"] == 1


def test_automatic_annotation_path_is_ignored(tmp_path: Path) -> None:
    manifest = _build(
        tmp_path,
        {
            "annotations/AA/sound-100.json": _annotation(),
            "annotations/1/sound-101.json": _annotation(),
        },
    )

    assert [record["public_sample_id"] for record in manifest["records"]] == ["101"]
    assert manifest["source_summary"]["ignored_non_human_annotation_paths"] == 1


def test_limit_split_and_input_order_are_stable(tmp_path: Path) -> None:
    entries: dict[str, dict[str, object]] = {}
    for index in range(300):
        entries[f"annotations/1/sound-{1000 + index}.json"] = _annotation(
            key="none", mode="none"
        )
    for index in range(300):
        entries[f"annotations/2/sound-{2000 + index}.json"] = _annotation(
            key="c", mode="maj"
        )

    first = _build(tmp_path / "first", entries)
    second = _build(tmp_path / "second", dict(reversed(list(entries.items()))))

    assert len(first["records"]) == 500
    assert first["split_summary"] == {"CALIBRATION": 100, "TEST": 400}
    assert canonical_manifest_bytes(first) == canonical_manifest_bytes(second)
    assert manifest_sha256(first) == manifest_sha256(second)


def test_undercoverage_rounding_is_explicit() -> None:
    assert calibration_target(1) == 0
    assert calibration_target(2) == 1
    assert calibration_target(7) == 1
    assert calibration_target(8) == 2
    assert calibration_target(500) == 100


def test_metadata_groups_are_hashed_and_never_cross_splits(tmp_path: Path) -> None:
    entries = {
        "annotations/1/sound-100.json": _annotation(),
        "annotations/1/sound-101.json": _annotation(key="d", mode="min"),
        "annotations/1/sound-102.json": _annotation(key="none", mode="none"),
        "annotations/1/sound-103.json": _annotation(key="none", mode="none"),
    }
    manifest = _build(
        tmp_path,
        entries,
        metadata={
            "100": {"username": "uploader-a"},
            "101": {"username": "uploader-a"},
            "102": {"username": "uploader-b"},
            "103": {"username": "uploader-b"},
        },
    )

    groups: dict[str, set[str]] = {}
    calibration_count = 0
    for record in manifest["records"]:
        groups.setdefault(record["source_group_id"], set()).add(record["split"])
        calibration_count += record["split"] == "CALIBRATION"
        assert "uploader-a" not in json.dumps(record)
        assert "uploader-b" not in json.dumps(record)
    assert all(len(splits) == 1 for splits in groups.values())
    assert abs(calibration_count - manifest["selection"]["calibration_target"]) == 1


def test_ma_bpm_requires_consensus_and_sa_keeps_its_confirmed_value(tmp_path: Path) -> None:
    manifest = _build(
        tmp_path,
        {
            "annotations/1/sound-100.json": _annotation(bpm="120"),
            "annotations/2/sound-100.json": _annotation(bpm="121"),
            "annotations/1/sound-101.json": _annotation(bpm="130"),
        },
    )

    by_id = {record["public_sample_id"]: record for record in manifest["records"]}
    assert _ground_truth(by_id["100"])["bpm"] is None
    assert _ground_truth(by_id["100"])["bpm_evidence"] == "conflicting"
    assert _ground_truth(by_id["101"])["bpm"] == 130.0
    assert _ground_truth(by_id["101"])["bpm_evidence"] == "known"


def test_tonal_records_remain_eligible_when_key_evidence_conflicts_or_is_missing(tmp_path: Path) -> None:
    manifest = _build(
        tmp_path,
        {
            "annotations/1/sound-100.json": _annotation(key="c", mode="maj"),
            "annotations/2/sound-100.json": _annotation(key="d", mode="maj"),
            "annotations/1/sound-101.json": _annotation(key="c", mode="maj"),
            "annotations/2/sound-101.json": _annotation(key=None, mode="maj"),
        },
    )

    by_id = {record["public_sample_id"]: record for record in manifest["records"]}
    assert _ground_truth(by_id["100"])["tonality"] == "tonal"
    assert _ground_truth(by_id["100"])["root_evidence"] == "conflicting"
    assert _ground_truth(by_id["101"])["tonality"] == "tonal"
    assert _ground_truth(by_id["101"])["root_evidence"] == "missing"


def test_metadata_without_matching_rows_keeps_the_exact_ungrouped_split(tmp_path: Path) -> None:
    entries = {
        f"annotations/1/sound-{100 + index}.json": _annotation() for index in range(8)
    }
    manifest = _build(tmp_path, entries, metadata={"not-a-sample": {"username": "other"}})

    assert manifest["selection"]["calibration_target"] == 2
    assert manifest["selection"]["ungrouped_split_is_exact"] is True
    assert manifest["split_summary"] == {"CALIBRATION": 2, "TEST": 6}


def test_partial_metadata_disables_grouping_without_leaking_a_partial_group(tmp_path: Path) -> None:
    entries = {
        "annotations/1/sound-100.json": _annotation(),
        "annotations/1/sound-101.json": _annotation(key="d", mode="min"),
        "annotations/1/sound-102.json": _annotation(key="none", mode="none"),
        "annotations/1/sound-103.json": _annotation(key="none", mode="none"),
    }
    manifest = _build(
        tmp_path,
        entries,
        metadata={"100": {"username": "uploader-a"}},
    )

    assert manifest["provenance"]["source_grouping"] == "unavailable_annotations_only"
    assert manifest["selection"]["ungrouped_split_is_exact"] is True
    assert manifest["split_summary"] == {"CALIBRATION": 1, "TEST": 3}
    assert all(record["source_group_id"] is None for record in manifest["records"])


def test_canonical_files_verify_and_do_not_contain_absolute_paths(tmp_path: Path) -> None:
    manifest = _build(
        tmp_path,
        {"annotations/1/sound-100.json": _annotation()},
    )
    manifest_path = tmp_path / "manifest.json"
    sha_path = tmp_path / "manifest.sha256"
    write_manifest_files(manifest, manifest_path, sha_path)

    verify_manifest_files(manifest, manifest_path, sha_path)
    assert EXPECTED_ANNOTATIONS_MD5 == "3920ee437802cf047a990b2968fa066c"
    assert str(tmp_path).encode() not in manifest_path.read_bytes()
    assert all(record["source_group_id"] is None for record in manifest["records"])
