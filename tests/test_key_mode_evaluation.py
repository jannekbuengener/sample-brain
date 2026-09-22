from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from src.key_mode_evaluation import (
    LibrarySample,
    ReferenceSample,
    best_bpm_relation,
    evaluate_reference_library,
    normalize_open_key,
    resolve_reference_samples,
    run_local_evaluation,
    sanitize_report,
    select_references,
)


def test_normalize_open_key_uses_canonical_parser_enharmonics() -> None:
    assert normalize_open_key("1d") == "Cmaj"
    assert normalize_open_key("11m") == "Gmin"
    assert normalize_open_key("8d") == "C#maj"
    assert normalize_open_key(None) is None


def test_best_bpm_relation_preserves_half_and_double_time() -> None:
    assert best_bpm_relation(156.605, 77.5)["relation"] == "double_time"
    assert best_bpm_relation(62.0, 123.047)["relation"] == "half_time"
    assert best_bpm_relation(None, 120.0)["relation"] == "no_result"


def test_resolver_refuses_ambiguous_normalized_names() -> None:
    references = [ReferenceSample(name="Bass-Loop", traktor_bpm=120.0, open_key="5m")]
    library = [
        LibrarySample(path=Path("/private/a/Bass Loop.wav"), display_name="Bass Loop"),
        LibrarySample(path=Path("/private/b/Bass_Loop.wav"), display_name="Bass_Loop"),
    ]

    resolved = resolve_reference_samples(references, library)

    assert resolved[0].library_sample is None
    assert resolved[0].reason == "AMBIGUOUS_NAME_MATCH"


def test_select_references_supports_tier_a_and_explicit_names() -> None:
    references = [
        ReferenceSample(name="Anchor A", traktor_bpm=100.0, open_key="1d", tier="A"),
        ReferenceSample(name="Anchor B", traktor_bpm=100.0, open_key="2d", tier="B"),
    ]

    assert select_references(references, tier_a_only=True) == [references[0]]
    assert select_references(references, reference_names=["anchor b"]) == [references[1]]


def test_evaluation_reports_mode_abstention_without_claiming_key_match(monkeypatch) -> None:
    reference = ReferenceSample(name="Tonal Anchor", traktor_bpm=100.0, open_key="1d", tier="A")
    library = [LibrarySample(path=Path("/private/Tonal Anchor.wav"), display_name="Tonal Anchor")]

    class Features:
        bpm = 200.0
        key = "C"
        key_conf = 0.24
        key_mode = None
        key_mode_evidence = {"kind": "third_contrast", "contrast": 0.12}

    monkeypatch.setattr("src.key_mode_evaluation.extract_features", lambda *_, **__: Features())

    report = evaluate_reference_library([reference], library)
    record = report["records"][0]

    assert record["bpm"]["sample_brain_bpm"] == 200.0
    assert record["bpm"]["traktor_bpm"] == 100.0
    assert record["bpm"]["relation"] == "double_time"
    assert record["sample_brain"]["canonical_key"] == "C"
    assert record["sample_brain"]["abstained"] is True
    assert record["comparison"]["root_match"] is True
    assert record["comparison"]["mode_match"] is None
    assert record["comparison"]["full_key_match"] is False


def test_run_local_evaluation_uses_explicit_external_inputs_and_writes_no_paths(
    tmp_path: Path, monkeypatch
) -> None:
    audio_path = tmp_path / "Tier A.wav"
    audio_path.touch()
    db_path = tmp_path / "workbench.db"
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            "CREATE TABLE samples (original_path TEXT, display_name TEXT, size_bytes INTEGER)"
        )
        conn.execute(
            "INSERT INTO samples VALUES (?, ?, ?)", (str(audio_path), "Tier A", 0)
        )

    reference_path = tmp_path / "oracle.json"
    reference_path.write_text(
        json.dumps([
            {"name": "Tier A", "traktor_bpm": 100.0, "open_key": "1d", "tier": "A"},
            {"name": "Tier B", "traktor_bpm": 100.0, "open_key": "2d", "tier": "B"},
        ]),
        encoding="utf-8",
    )
    output_path = tmp_path / "report.json"

    class Features:
        bpm = 100.0
        key = "Cmaj"
        key_conf = 0.42
        key_mode_evidence = {"kind": "third_contrast", "contrast": 0.4}

    monkeypatch.setattr("src.key_mode_evaluation.extract_features", lambda *_, **__: Features())
    report = run_local_evaluation(
        reference_json=reference_path,
        workbench_db=db_path,
        output_json=output_path,
        tier_a_only=True,
    )

    assert report["selection"] == {"tier_a_only": True, "reference_names": []}
    assert report["summary"]["reference_count"] == 1
    saved = output_path.read_text(encoding="utf-8")
    assert str(tmp_path) not in saved


def test_sanitized_report_has_aliases_but_no_private_names_or_paths(monkeypatch) -> None:
    reference = ReferenceSample(name="Private Sample", traktor_bpm=100.0, open_key="1d", tier="A")
    library = [LibrarySample(path=Path("C:/private/Private Sample.wav"), display_name="Private Sample")]

    class Features:
        bpm = 100.0
        key = "Cmaj"
        key_conf = 0.42
        key_mode_evidence = {"kind": "third_contrast", "contrast": 0.4}

    monkeypatch.setattr("src.key_mode_evaluation.extract_features", lambda *_, **__: Features())
    sanitized = sanitize_report(evaluate_reference_library([reference], library))
    record = sanitized["records"][0]

    assert record["sample_alias"] == "sample_001"
    assert "name" not in record["reference"]
    assert "file_identity" not in record
    assert "Private" not in json.dumps(sanitized)
