from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import numpy as np

from src.key_mode_evaluation import (
    LibrarySample,
    ReferenceSample,
    best_bpm_relation,
    evaluate_reference_library,
    format_ab_handoff,
    normalize_open_key,
    resolve_reference_samples,
    run_local_evaluation,
    sanitize_report,
    select_references,
)
from src.key_profile_analysis import MAJOR_KEY_PROFILE
from src.key_profile_audio_calibration import HarmonicChromaEvidence


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
        chroma_mean = np.asarray(MAJOR_KEY_PROFILE, dtype=np.float32).tobytes()
        chroma_std = (np.asarray(MAJOR_KEY_PROFILE, dtype=np.float32) * 0.01).tobytes()

    monkeypatch.setattr("src.key_mode_evaluation.extract_features", lambda *_, **__: Features())

    report = evaluate_reference_library([reference], library)
    record = report["records"][0]

    assert record["bpm"]["sample_brain_bpm"] == 200.0
    assert record["bpm"]["traktor_bpm"] == 100.0
    assert record["bpm"]["relation"] == "double_time"
    assert record["sample_brain"]["canonical_key"] == "C"
    assert record["baseline"] == record["sample_brain"]
    assert record["sample_brain"]["abstained"] is True
    assert record["comparison"]["root_match"] is True
    assert record["comparison"]["mode_match"] is None
    assert record["comparison"]["full_key_match"] is False
    assert record["candidate"]["status"] == "ranked_only"
    assert record["candidate"]["canonical_key"] == "Cmaj"
    assert record["candidate_profile"] == record["candidate"]
    assert record["candidate_gated"]["status"] == "resolved"
    assert record["candidate_gated"]["canonical_key"] == "Cmaj"
    assert record["candidate_gated"]["gate_evidence"]["gate_version"]
    assert record["candidate_comparison"]["root_match"] is True
    assert record["candidate_comparison"]["full_key_match"] is True
    assert report["ab_comparison"]["overall"]["candidate"]["status_counts"]["ranked_only"] == 1


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
    handoff_path = tmp_path / "handoff.txt"

    class Features:
        bpm = 100.0
        key = "Cmaj"
        key_conf = 0.42
        key_mode_evidence = {"kind": "third_contrast", "contrast": 0.4}
        chroma_mean = np.asarray(MAJOR_KEY_PROFILE, dtype=np.float32).tobytes()
        chroma_std = (np.asarray(MAJOR_KEY_PROFILE, dtype=np.float32) * 0.01).tobytes()

    monkeypatch.setattr("src.key_mode_evaluation.extract_features", lambda *_, **__: Features())
    report = run_local_evaluation(
        reference_json=reference_path,
        workbench_db=db_path,
        output_json=output_path,
        handoff_text=handoff_path,
        tier_a_only=True,
    )

    assert report["selection"] == {"tier_a_only": True, "reference_names": []}
    assert report["summary"]["reference_count"] == 1
    saved = output_path.read_text(encoding="utf-8")
    assert str(tmp_path) not in saved
    handoff = handoff_path.read_text(encoding="utf-8")
    assert "KEY_PROFILE_AB_HANDOFF_V1" in handoff
    assert "Tier A" not in handoff


def test_sanitized_report_has_aliases_but_no_private_names_or_paths(monkeypatch) -> None:
    reference = ReferenceSample(name="Private Sample", traktor_bpm=100.0, open_key="1d", tier="A")
    library = [LibrarySample(path=Path("C:/private/Private Sample.wav"), display_name="Private Sample")]

    class Features:
        bpm = 100.0
        key = "Cmaj"
        key_conf = 0.42
        key_mode_evidence = {"kind": "third_contrast", "contrast": 0.4}
        chroma_mean = np.asarray(MAJOR_KEY_PROFILE, dtype=np.float32).tobytes()
        chroma_std = (np.asarray(MAJOR_KEY_PROFILE, dtype=np.float32) * 0.01).tobytes()

    monkeypatch.setattr("src.key_mode_evaluation.extract_features", lambda *_, **__: Features())
    sanitized = sanitize_report(evaluate_reference_library([reference], library))
    record = sanitized["records"][0]

    assert record["sample_alias"] == "sample_001"
    assert "name" not in record["reference"]
    assert "file_identity" not in record
    assert record["candidate"]["canonical_key"] == "Cmaj"
    assert record["candidate_profile"] == record["candidate"]
    assert record["candidate_gated"]["status"] == "resolved"
    assert "gate_evidence" in record["candidate_gated"]
    assert "ab_comparison" in sanitized
    assert "Private" not in json.dumps(sanitized)


def test_ab_handoff_is_aggregate_only(monkeypatch) -> None:
    reference = ReferenceSample(name="Private Sample", traktor_bpm=100.0, open_key="1d", tier="A")
    library = [LibrarySample(path=Path("C:/private/Private Sample.wav"), display_name="Private Sample")]

    class Features:
        bpm = 100.0
        key = "Cmaj"
        key_conf = 0.42
        key_mode_evidence = {"kind": "third_contrast", "contrast": 0.4}
        chroma_mean = np.asarray(MAJOR_KEY_PROFILE, dtype=np.float32).tobytes()
        chroma_std = (np.asarray(MAJOR_KEY_PROFILE, dtype=np.float32) * 0.01).tobytes()

    monkeypatch.setattr("src.key_mode_evaluation.extract_features", lambda *_, **__: Features())
    handoff = format_ab_handoff(evaluate_reference_library([reference], library))

    assert "Private" not in handoff
    assert "C:/private" not in handoff
    assert "candidate_is_evaluation_only" in handoff


def test_harmonic_evaluator_metrics_transitions_and_negative_controls_are_reported(monkeypatch) -> None:
    references = [
        ReferenceSample(name="Tonal Anchor", traktor_bpm=100.0, open_key="1d", tier="A"),
        ReferenceSample(name="No Key Control", traktor_bpm=100.0, open_key=None, tier="B"),
    ]
    library = [
        LibrarySample(path=Path("C:/private/Tonal Anchor.wav"), display_name="Tonal Anchor"),
        LibrarySample(path=Path("C:/private/No Key Control.wav"), display_name="No Key Control"),
    ]

    class Features:
        bpm = 100.0
        key = "Cmaj"
        key_conf = 0.42
        key_mode_evidence = {"kind": "third_contrast", "contrast": 0.4}
        chroma_mean = np.asarray(MAJOR_KEY_PROFILE, dtype=np.float32).tobytes()
        chroma_std = (np.asarray(MAJOR_KEY_PROFILE, dtype=np.float32) * 0.01).tobytes()

    evidence = HarmonicChromaEvidence(
        chroma_mean=np.asarray(MAJOR_KEY_PROFILE, dtype=np.float32),
        chroma_std=np.zeros(12, dtype=np.float32),
        harmonic_rms=0.2,
        percussive_rms=0.1,
        harmonic_energy_fraction=0.8,
    )
    monkeypatch.setattr("src.key_mode_evaluation.extract_features", lambda *_, **__: Features())
    monkeypatch.setattr("src.key_mode_evaluation.extract_harmonic_chroma_evidence", lambda *_: evidence)

    report = evaluate_reference_library(references, library)
    overall = report["ab_comparison"]["overall"]
    tier_a = report["ab_comparison"]["tier_a"]

    assert overall["candidate_harmonic_profile"]["root_agreement_ranked"] == {
        "agreement_count": 1, "comparable_count": 1,
    }
    assert tier_a["candidate_harmonic_profile"]["full_key_agreement_ranked"] == {
        "agreement_count": 1, "comparable_count": 1,
    }
    transitions = overall["delta"]
    assert transitions["full_correct_to_harmonic_correct_root"] == 1
    assert sum(transitions[key] for key in (
        "full_correct_to_harmonic_correct_root", "full_correct_to_harmonic_wrong_root",
        "full_wrong_to_harmonic_correct_root", "full_wrong_to_harmonic_wrong_root",
    )) == 1
    negative_controls = overall["negative_controls"]
    assert negative_controls["full_profile_margin_distribution"]["count"] == 1
    assert negative_controls["harmonic_profile_margin_distribution"]["count"] == 1
    assert negative_controls["harmonic_energy_fraction_distribution"]["count"] == 1
    assert sanitize_report(report)["records"][0]["candidate_harmonic_profile"]["canonical_key"] == "Cmaj"
