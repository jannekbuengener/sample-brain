"""Frozen tests for AQ4 synthetic classification corpus (#1021).

TEST FREEZE: these assertions define the corpus contract. Fix the generator,
not these expectations, when they turn red.
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

import pytest

from src import aq4_classification_corpus as corpus


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_corpus_identity_and_eligible_labels_are_frozen() -> None:
    assert corpus.CORPUS_ID == "sample-brain.aq4.classification.synthetic.v1"
    assert corpus.DOCUMENT_TYPE == "sample-brain.aq4.classification-corpus.v1"
    assert corpus.CORPUS_VERSION == "1.0.0"
    assert corpus.GENERATOR_SEED == 1021001
    assert corpus.SAMPLE_RATE == 44100
    assert corpus.SAMPLE_CLASS_LABELS == (
        "oneshot",
        "loop",
        "ambiguous",
        "unknown",
    )
    assert corpus.PRED_TYPE_LABELS == (
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
        "unknown",
    )
    assert set(corpus.SPLITS) == {"CALIBRATION", "TEST"}


def test_generate_rejects_work_dir_inside_repo(tmp_path: Path) -> None:
    inside = REPO_ROOT / ".pytest_aq4_classification_corpus_should_not_exist"
    with pytest.raises(ValueError, match="outside"):
        corpus.generate_aq4_classification_corpus(inside, repo_root=REPO_ROOT)


def test_generate_writes_deterministic_wav_and_gt_outside_repo(tmp_path: Path) -> None:
    work_a = tmp_path / "corpus-a"
    work_b = tmp_path / "corpus-b"

    manifest_a = corpus.generate_aq4_classification_corpus(work_a, repo_root=REPO_ROOT)
    manifest_b = corpus.generate_aq4_classification_corpus(work_b, repo_root=REPO_ROOT)

    assert manifest_a["document_type"] == corpus.DOCUMENT_TYPE
    assert manifest_a["corpus_id"] == corpus.CORPUS_ID
    assert manifest_a["corpus_version"] == corpus.CORPUS_VERSION
    assert manifest_a["generator_seed"] == corpus.GENERATOR_SEED
    assert manifest_a["sample_class_labels"] == list(corpus.SAMPLE_CLASS_LABELS)
    assert manifest_a["pred_type_labels"] == list(corpus.PRED_TYPE_LABELS)
    assert "support_counts" in manifest_a

    clips_a = {c["clip_id"]: c for c in manifest_a["clips"]}
    clips_b = {c["clip_id"]: c for c in manifest_b["clips"]}
    assert clips_a.keys() == clips_b.keys()
    assert len(clips_a) >= 8

    sample_classes = {clip["sample_class"] for clip in clips_a.values()}
    assert {"oneshot", "loop"}.issubset(sample_classes)
    assert sample_classes & {"ambiguous", "unknown"}

    pred_types = {clip["pred_type"] for clip in clips_a.values()}
    # Thin dual-taxonomy coverage: oneshot-oriented and loop-oriented labels.
    assert {"Kick", "Snare"}.issubset(pred_types) or {"Kick", "HiHat-Closed"}.issubset(
        pred_types
    )
    assert pred_types & {"Loop", "Drum Loop", "Pad", "Drone"}

    splits = {clip["split"] for clip in clips_a.values()}
    assert splits == {"CALIBRATION", "TEST"}

    # No CALIBRATION/TEST leakage by construction: unique clip_ids, disjoint splits.
    cal_ids = {c["clip_id"] for c in clips_a.values() if c["split"] == "CALIBRATION"}
    test_ids = {c["clip_id"] for c in clips_a.values() if c["split"] == "TEST"}
    assert cal_ids.isdisjoint(test_ids)
    assert len(cal_ids) + len(test_ids) == len(clips_a)

    support = manifest_a["support_counts"]
    assert support["sample_class"] == dict(Counter(c["sample_class"] for c in clips_a.values()))
    assert support["pred_type"] == dict(Counter(c["pred_type"] for c in clips_a.values()))
    assert support["split"] == dict(Counter(c["split"] for c in clips_a.values()))

    wav_hashes: dict[str, bytes] = {}
    for clip_id, clip in clips_a.items():
        wav_a = work_a / "audio" / f"{clip_id}.wav"
        wav_b = work_b / "audio" / f"{clip_id}.wav"
        gt_a = work_a / "gt" / f"{clip_id}.json"
        gt_b = work_b / "gt" / f"{clip_id}.json"

        assert wav_a.is_file()
        assert wav_b.is_file()
        assert wav_a.read_bytes() == wav_b.read_bytes()
        assert gt_a.read_text(encoding="utf-8") == gt_b.read_text(encoding="utf-8")
        wav_hashes[clip_id] = wav_a.read_bytes()

        payload = json.loads(gt_a.read_text(encoding="utf-8"))
        assert payload["document_type"] == corpus.DOCUMENT_TYPE
        assert payload["corpus_id"] == corpus.CORPUS_ID
        assert payload["clip_id"] == clip_id
        assert payload["sample_rate"] == corpus.SAMPLE_RATE
        assert payload["sample_class"] in corpus.SAMPLE_CLASS_LABELS
        assert payload["pred_type"] in corpus.PRED_TYPE_LABELS
        assert payload["label_status"] in {"clear", "ambiguous", "unknown"}
        assert payload["split"] in corpus.SPLITS
        assert payload["label_source"] == "synthetic_deterministic"
        assert payload["join_key"]["analysis_eval_record_id"] == clip_id
        # Taxonomies stay separate fields — never a collapsed single label key.
        assert "sample_class" in payload and "pred_type" in payload
        assert "classification_label" not in payload
        for key in ("audio_path", "file_path", "sample_path"):
            assert key not in payload

        assert clip["join_key"]["analysis_eval_record_id"] == clip_id
        assert "audio_path" not in clip
        assert clip["sample_class"] == payload["sample_class"]
        assert clip["pred_type"] == payload["pred_type"]

    # Distinct designed waveforms across the corpus (no cross-split duplicate audio).
    assert len(set(wav_hashes.values())) == len(wav_hashes)


def test_no_committed_audio_binaries_for_aq4_classification_corpus() -> None:
    tracked_audio = []
    for pattern in ("*.wav", "*.aif", "*.aiff", "*.flac", "*.mp3", "*.ogg"):
        tracked_audio.extend(REPO_ROOT.rglob(pattern))
    aq4_named = [
        path
        for path in tracked_audio
        if "aq4" in path.name.lower() and "classif" in str(path).lower()
    ]
    assert aq4_named == []

    for base in (REPO_ROOT / "docs" / "benchmarks", REPO_ROOT / "src"):
        assert list(base.rglob("*.wav")) == []
