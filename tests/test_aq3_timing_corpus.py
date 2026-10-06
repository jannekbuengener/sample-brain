"""Frozen tests for AQ3 synthetic timing corpus (#993).

TEST FREEZE: these assertions define the corpus contract. Fix the generator,
not these expectations, when they turn red.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src import aq3_timing_corpus as corpus


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_corpus_identity_and_tolerance_candidates_are_frozen() -> None:
    assert corpus.CORPUS_ID == "sample-brain.aq3.timing.synthetic.v1"
    assert corpus.DOCUMENT_TYPE == "sample-brain.aq3.timing-corpus.v1"
    assert corpus.CORPUS_VERSION == "1.0.0"
    assert corpus.GENERATOR_SEED == 993001
    assert corpus.SAMPLE_RATE == 44100
    assert corpus.TOLERANCE_CANDIDATES_MS == (20, 50)
    assert corpus.ACTIVE_BUCKETS == (
        "soft_attack",
        "silence_leading",
        "short_clip",
        "simple_multi_onset",
    )
    assert corpus.HOLD_BUCKETS == ("layered_transient_dense", "noisy")
    assert set(corpus.SPLITS) == {"CALIBRATION", "TEST"}


def test_generate_rejects_work_dir_inside_repo(tmp_path: Path) -> None:
    inside = REPO_ROOT / ".pytest_aq3_timing_corpus_should_not_exist"
    with pytest.raises(ValueError, match="outside"):
        corpus.generate_aq3_timing_corpus(inside, repo_root=REPO_ROOT)


def test_generate_writes_deterministic_wav_and_gt_outside_repo(tmp_path: Path) -> None:
    work_a = tmp_path / "corpus-a"
    work_b = tmp_path / "corpus-b"

    manifest_a = corpus.generate_aq3_timing_corpus(work_a, repo_root=REPO_ROOT)
    manifest_b = corpus.generate_aq3_timing_corpus(work_b, repo_root=REPO_ROOT)

    assert manifest_a["document_type"] == corpus.DOCUMENT_TYPE
    assert manifest_a["corpus_id"] == corpus.CORPUS_ID
    assert manifest_a["corpus_version"] == corpus.CORPUS_VERSION
    assert manifest_a["generator_seed"] == corpus.GENERATOR_SEED
    assert manifest_a["tolerance_candidates_ms"] == list(corpus.TOLERANCE_CANDIDATES_MS)
    assert manifest_a["hold_buckets"] == list(corpus.HOLD_BUCKETS)

    clips_a = {c["clip_id"]: c for c in manifest_a["clips"]}
    clips_b = {c["clip_id"]: c for c in manifest_b["clips"]}
    assert clips_a.keys() == clips_b.keys()
    assert len(clips_a) >= 4

    covered = {bucket for clip in clips_a.values() for bucket in clip["buckets"]}
    assert set(corpus.ACTIVE_BUCKETS).issubset(covered)
    assert set(corpus.HOLD_BUCKETS).isdisjoint(covered)

    splits = {clip["split"] for clip in clips_a.values()}
    assert splits == {"CALIBRATION", "TEST"}

    for clip_id, clip in clips_a.items():
        wav_a = work_a / "audio" / f"{clip_id}.wav"
        wav_b = work_b / "audio" / f"{clip_id}.wav"
        gt_a = work_a / "gt" / f"{clip_id}.json"
        gt_b = work_b / "gt" / f"{clip_id}.json"

        assert wav_a.is_file()
        assert wav_b.is_file()
        assert wav_a.read_bytes() == wav_b.read_bytes()
        assert gt_a.read_text(encoding="utf-8") == gt_b.read_text(encoding="utf-8")

        payload = json.loads(gt_a.read_text(encoding="utf-8"))
        assert payload["document_type"] == corpus.DOCUMENT_TYPE
        assert payload["corpus_id"] == corpus.CORPUS_ID
        assert payload["clip_id"] == clip_id
        assert payload["sample_rate"] == corpus.SAMPLE_RATE
        assert isinstance(payload["onset_times_ms"], list)
        assert payload["onset_times_ms"] == sorted(payload["onset_times_ms"])
        assert payload["buckets"]
        assert payload["split"] in corpus.SPLITS
        assert payload["label_source"] == "synthetic_deterministic"
        assert payload["join_key"]["analysis_eval_record_id"] == clip_id
        assert ":" not in json.dumps(payload.get("audio_path", ""))
        for key in ("audio_path", "file_path", "sample_path"):
            assert key not in payload

        # Optional attack marker must be null or a finite number.
        attack = payload.get("attack_marker_ms")
        assert attack is None or isinstance(attack, (int, float))

        # Manifest clip row stays path-free and join-key compatible.
        assert clip["join_key"]["analysis_eval_record_id"] == clip_id
        assert "audio_path" not in clip


def test_no_committed_audio_binaries_for_aq3_timing_corpus() -> None:
    tracked_audio = []
    for pattern in ("*.wav", "*.aif", "*.aiff", "*.flac", "*.mp3", "*.ogg"):
        tracked_audio.extend(REPO_ROOT.rglob(pattern))
    # Generator must not leave corpus audio under repo; also assert no
    # aq3-timing named wav slipped into the tree from this feature.
    aq3_named = [
        path
        for path in tracked_audio
        if "aq3" in path.name.lower() and "timing" in str(path).lower()
    ]
    assert aq3_named == []

    # Hard guard: no wav under docs/benchmarks or src from this corpus.
    for base in (REPO_ROOT / "docs" / "benchmarks", REPO_ROOT / "src"):
        assert list(base.rglob("*.wav")) == []
