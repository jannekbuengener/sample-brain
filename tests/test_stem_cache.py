from __future__ import annotations

import hashlib
import json
from pathlib import Path


from src.stem_cache import (
    WEIGHT_USAGE_RESEARCH_ONLY,
    StemModelIdentity,
    build_cache_key,
    build_entry_dict,
    build_separation_fingerprint,
    hash_single_weight_file,
    hash_weight_set,
    known_htdemucs_ft_identity,
    known_htdemucs_identity,
    load_validated_entry,
    publish_entry,
    resolve_cache_dir,
    separate_with_cache,
)

# The debunked fake long hash must never appear anywhere in provenance.
FAKE_HASH = "f7e0c4bcba3fe64a92cfc3b6ef3bcb9c04573f0d"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _synthetic_weight(tmp_path: Path, name: str, seed: bytes) -> Path:
    p = tmp_path / name
    p.write_bytes(seed)
    return p


def _complete_htdemucs(weight_value: str) -> StemModelIdentity:
    return known_htdemucs_identity(
        weight_hash={"algorithm": "sha256", "value": weight_value}
    )


def _make_executor(output_bytes: bytes, backend=None, status="ok"):
    backend = backend or {"name": "python-audio-separator", "version": "0.44.5"}

    def executor(
        *,
        input_path,
        track_ref,
        working_audio_hash,
        model_identity,
        configuration,
        output_dir,
    ):
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        stems = []
        for kind in ("drums", "bass", "vocals", "other"):
            fpath = output_dir / f"{kind}.wav"
            fpath.write_bytes(output_bytes)
            h = hashlib.sha256(output_bytes).hexdigest()
            mpath = output_dir / "stems" / f"stem_{kind}.json"
            mpath.parent.mkdir(parents=True, exist_ok=True)
            mpath.write_text(
                json.dumps(
                    {"document_type": "sample_brain.stem_manifest", "kind": kind}
                ),
                encoding="utf-8",
            )
            stems.append(
                {
                    "stem_kind": kind,
                    "file_path": str(fpath),
                    "hash": {"algorithm": "sha256", "value": h},
                    "status": status,
                    "manifest_path": str(mpath),
                }
            )
        return {"status": status, "backend": backend, "stems": stems}

    return executor


# ---------------------------------------------------------------------------
# A. Deterministic key
# ---------------------------------------------------------------------------


def test_key_is_deterministic_for_identical_inputs():
    fp = build_separation_fingerprint(
        backend_name="python-audio-separator",
        backend_version="0.44.5",
        model_identity=_complete_htdemucs("abc123"),
        configuration={"overlap": 0.25, "segment": 10},
    )
    k1 = build_cache_key(
        track_ref="TRACK1", working_audio_hash="WA1", separation_fingerprint=fp
    )
    k2 = build_cache_key(
        track_ref="TRACK1", working_audio_hash="WA1", separation_fingerprint=fp
    )
    assert k1 == k2
    assert len(k1) == 64


def test_key_is_order_independent_in_config():
    fp_a = build_separation_fingerprint(
        backend_name="python-audio-separator",
        backend_version="0.44.5",
        model_identity=_complete_htdemucs("abc123"),
        configuration={"overlap": 0.25, "segment": 10},
    )
    fp_b = build_separation_fingerprint(
        backend_name="python-audio-separator",
        backend_version="0.44.5",
        model_identity=_complete_htdemucs("abc123"),
        configuration={"segment": 10, "overlap": 0.25},
    )
    assert fp_a == fp_b
    k_a = build_cache_key(
        track_ref="T", working_audio_hash="W", separation_fingerprint=fp_a
    )
    k_b = build_cache_key(
        track_ref="T", working_audio_hash="W", separation_fingerprint=fp_b
    )
    assert k_a == k_b


# ---------------------------------------------------------------------------
# B. Invalidation matrix
# ---------------------------------------------------------------------------


def _base_fp(weight_value="abc123", backend_version="0.44.5", model=None, config=None):
    model = model or _complete_htdemucs(weight_value)
    config = config or {"overlap": 0.25}
    return build_separation_fingerprint(
        backend_name="python-audio-separator",
        backend_version=backend_version,
        model_identity=model,
        configuration=config,
    )


def test_track_ref_change_invalidates():
    fp = _base_fp()
    k1 = build_cache_key(
        track_ref="T1", working_audio_hash="W", separation_fingerprint=fp
    )
    k2 = build_cache_key(
        track_ref="T2", working_audio_hash="W", separation_fingerprint=fp
    )
    assert k1 != k2


def test_working_audio_hash_change_invalidates():
    fp = _base_fp()
    k1 = build_cache_key(
        track_ref="T", working_audio_hash="W1", separation_fingerprint=fp
    )
    k2 = build_cache_key(
        track_ref="T", working_audio_hash="W2", separation_fingerprint=fp
    )
    assert k1 != k2


def test_backend_version_change_invalidates():
    fp1 = _base_fp(backend_version="0.44.5")
    fp2 = _base_fp(backend_version="0.44.6")
    k1 = build_cache_key(
        track_ref="T", working_audio_hash="W", separation_fingerprint=fp1
    )
    k2 = build_cache_key(
        track_ref="T", working_audio_hash="W", separation_fingerprint=fp2
    )
    assert k1 != k2


def test_model_change_htdemucs_to_ft_invalidates():
    fp1 = _base_fp(model=_complete_htdemucs("abc"))
    fp2 = _base_fp(
        model=known_htdemucs_ft_identity(
            weight_hash={"algorithm": "sha256", "value": "abc"}
        )
    )
    k1 = build_cache_key(
        track_ref="T", working_audio_hash="W", separation_fingerprint=fp1
    )
    k2 = build_cache_key(
        track_ref="T", working_audio_hash="W", separation_fingerprint=fp2
    )
    assert k1 != k2


def test_checkpoint_change_invalidates():
    m1 = StemModelIdentity(
        family="htdemucs",
        name="htdemucs",
        checkpoint="955717e8",
        weight_hash={"algorithm": "sha256", "value": "x"},
        code_license="MIT",
        weight_license=WEIGHT_USAGE_RESEARCH_ONLY,
    )
    m2 = StemModelIdentity(
        family="htdemucs",
        name="htdemucs",
        checkpoint="99999999",
        weight_hash={"algorithm": "sha256", "value": "x"},
        code_license="MIT",
        weight_license=WEIGHT_USAGE_RESEARCH_ONLY,
    )
    fp1 = _base_fp(model=m1)
    fp2 = _base_fp(model=m2)
    k1 = build_cache_key(
        track_ref="T", working_audio_hash="W", separation_fingerprint=fp1
    )
    k2 = build_cache_key(
        track_ref="T", working_audio_hash="W", separation_fingerprint=fp2
    )
    assert k1 != k2


def test_weight_hash_change_invalidates():
    fp1 = _base_fp(weight_value="aaa")
    fp2 = _base_fp(weight_value="bbb")
    k1 = build_cache_key(
        track_ref="T", working_audio_hash="W", separation_fingerprint=fp1
    )
    k2 = build_cache_key(
        track_ref="T", working_audio_hash="W", separation_fingerprint=fp2
    )
    assert k1 != k2


def test_config_change_invalidates():
    fp1 = _base_fp(config={"overlap": 0.25})
    fp2 = _base_fp(config={"overlap": 0.50})
    k1 = build_cache_key(
        track_ref="T", working_audio_hash="W", separation_fingerprint=fp1
    )
    k2 = build_cache_key(
        track_ref="T", working_audio_hash="W", separation_fingerprint=fp2
    )
    assert k1 != k2


def test_license_usage_change_invalidates():
    m1 = StemModelIdentity(
        family="htdemucs",
        name="htdemucs",
        checkpoint="955717e8",
        weight_hash={"algorithm": "sha256", "value": "x"},
        code_license="MIT",
        weight_license=WEIGHT_USAGE_RESEARCH_ONLY,
    )
    m2 = StemModelIdentity(
        family="htdemucs",
        name="htdemucs",
        checkpoint="955717e8",
        weight_hash={"algorithm": "sha256", "value": "x"},
        code_license="MIT",
        weight_license="COMMERCIAL_USE_GRANTED",
    )
    fp1 = _base_fp(model=m1)
    fp2 = _base_fp(model=m2)
    k1 = build_cache_key(
        track_ref="T", working_audio_hash="W", separation_fingerprint=fp1
    )
    k2 = build_cache_key(
        track_ref="T", working_audio_hash="W", separation_fingerprint=fp2
    )
    assert k1 != k2


# ---------------------------------------------------------------------------
# C. Model identity
# ---------------------------------------------------------------------------


def test_htdemucs_checkpoint_is_955717e8():
    assert known_htdemucs_identity().checkpoint == "955717e8"


def test_htdemucs_ft_bag_has_four_canonical_sigs():
    bag = known_htdemucs_ft_identity().checkpoint
    parts = bag.split(",")
    assert parts == ["f7e0c4bc", "d12395a8", "92cfc3b6", "04573f0d"]
    assert len(parts) == 4


def test_fake_long_hash_never_appears():
    haystack = (
        Path(__file__)
        .parent.parent.joinpath("src", "stem_cache.py")
        .read_text(encoding="utf-8")
    )
    assert FAKE_HASH not in haystack


def test_incomplete_weight_identity_cannot_be_reusable():
    incomplete = known_htdemucs_identity(weight_hash=None)
    assert not incomplete.is_complete()
    fp = build_separation_fingerprint(
        backend_name="python-audio-separator",
        backend_version="0.44.5",
        model_identity=incomplete,
        configuration={"overlap": 0.25},
    )
    assert fp is not None
    assert '"weight_hash": null' in fp or '"weight_hash":null' in fp


def test_weight_hash_uses_real_sha256_of_files(tmp_path):
    w1 = _synthetic_weight(tmp_path, "w1.bin", b"model-weights-a")
    w2 = _synthetic_weight(tmp_path, "w2.bin", b"model-weights-b")
    h1 = hash_single_weight_file(w1)
    h2 = hash_single_weight_file(w2)
    assert h1 != h2
    assert h1 == hashlib.sha256(b"model-weights-a").hexdigest()

    agg = hash_weight_set(
        checkpoint="955717e8",
        component_hashes={"vocals": h1, "drums": h2},
    )
    assert agg["algorithm"] == "sha256-set-v1"
    assert len(agg["value"]) == 64
    agg2 = hash_weight_set(
        checkpoint="955717e8",
        component_hashes={"drums": h2, "vocals": h1},
    )
    assert agg2["value"] == agg["value"]


# ---------------------------------------------------------------------------
# D. Cache location
# ---------------------------------------------------------------------------


def test_explicit_cache_dir_wins(tmp_path, monkeypatch):
    monkeypatch.delenv("SAMPLE_BRAIN_STEM_CACHE_DIR", raising=False)
    explicit = tmp_path / "explicit"
    assert resolve_cache_dir(explicit=explicit) == explicit


def test_env_cache_dir_overrides_platform_default(tmp_path, monkeypatch):
    monkeypatch.setenv("SAMPLE_BRAIN_STEM_CACHE_DIR", str(tmp_path / "from_env"))
    assert resolve_cache_dir() == tmp_path / "from_env"


def test_platform_default_stays_outside_repo(monkeypatch):
    monkeypatch.delenv("SAMPLE_BRAIN_STEM_CACHE_DIR", raising=False)
    resolved = resolve_cache_dir()
    assert resolved.name == "stems"
    assert "sample-brain" in resolved.parts


def test_absolute_cache_root_never_serialized_in_entry(tmp_path):
    entry = build_entry_dict(
        cache_key="deadbeef",
        track_ref="TRACK1",
        working_audio_hash="WA1",
        separation_fingerprint="fp",
        backend={"name": "python-audio-separator", "version": "0.44.5"},
        model_identity=_complete_htdemucs("abc"),
        configuration={"overlap": 0.25},
        aggregate_status="ok",
        stems=[],
    )
    text = json.dumps(entry)
    assert str(tmp_path) not in text
    assert "/abs/source.wav" not in text
    assert "model_cache" not in text


# ---------------------------------------------------------------------------
# E. Read / write
# ---------------------------------------------------------------------------


def _publish_ok_entry(
    cache_root, tmp_path, key, track_ref="T", wa="W", model=None, config=None
):
    model = model or _complete_htdemucs("abc")
    config = config or {"overlap": 0.25}
    fp = build_separation_fingerprint(
        backend_name="python-audio-separator",
        backend_version="0.44.5",
        model_identity=model,
        configuration=config,
    )
    out_bytes = b"rendered-stem-bytes"
    out_dir = tmp_path / "out"
    out_dir.mkdir(exist_ok=True)
    stems = []
    outputs = {}
    for kind in ("drums", "bass", "vocals", "other"):
        fpath = out_dir / f"{kind}.wav"
        fpath.write_bytes(out_bytes)
        h = hashlib.sha256(out_bytes).hexdigest()
        stems.append(
            {
                "stem_kind": kind,
                "file_ref": f"{kind}.wav",
                "hash": {"algorithm": "sha256", "value": h},
                "status": "ok",
                "manifest_ref": f"stem_{kind}.json",
            }
        )
        outputs[kind] = (f"{kind}.wav", fpath)
        (tmp_path / "manifests").mkdir(exist_ok=True)
        (tmp_path / "manifests" / f"stem_{kind}.json").write_text(
            json.dumps({"document_type": "sample_brain.stem_manifest"}),
            encoding="utf-8",
        )
    entry = build_entry_dict(
        cache_key=key,
        track_ref=track_ref,
        working_audio_hash=wa,
        separation_fingerprint=fp,
        backend={"name": "python-audio-separator", "version": "0.44.5"},
        model_identity=model,
        configuration=config,
        aggregate_status="ok",
        stems=stems,
    )
    publish_entry(
        cache_root=cache_root,
        entry_dict=entry,
        outputs=outputs,
        manifests={
            k: (f"stem_{k}.json", tmp_path / "manifests" / f"stem_{k}.json")
            for k in outputs
        },
    )
    return fp


def test_entry_round_trip_and_hit(tmp_path):
    cache_root = tmp_path / "cache"
    key = build_cache_key(
        track_ref="T", working_audio_hash="W", separation_fingerprint="fp-X"
    )
    fp = _publish_ok_entry(cache_root, tmp_path, key)
    loaded = load_validated_entry(
        cache_root=cache_root,
        expected_key=key,
        expected_track_ref="T",
        expected_working_audio_hash="W",
        expected_fingerprint=fp,
    )
    assert loaded is not None
    assert loaded["track_ref"] == "T"
    assert loaded["aggregate_status"] == "ok"
    assert len(loaded["stems"]) == 4


def test_malformed_json_is_miss(tmp_path):
    cache_root = tmp_path / "cache"
    key = "abc"
    (cache_root / key).mkdir(parents=True)
    (cache_root / key / "entry.json").write_text("{not valid json", encoding="utf-8")
    assert (
        load_validated_entry(
            cache_root=cache_root,
            expected_key=key,
            expected_track_ref="T",
            expected_working_audio_hash="W",
            expected_fingerprint="fp",
        )
        is None
    )


def test_wrong_schema_major_is_miss(tmp_path):
    cache_root = tmp_path / "cache"
    key = "abc"
    d = build_entry_dict(
        cache_key=key,
        track_ref="T",
        working_audio_hash="W",
        separation_fingerprint="fp",
        backend={"name": "x", "version": "1"},
        model_identity=_complete_htdemucs("abc"),
        configuration={},
        aggregate_status="ok",
        stems=[],
    )
    d["schema_version"] = "2.0.0"
    (cache_root / key).mkdir(parents=True)
    (cache_root / key / "entry.json").write_text(json.dumps(d), encoding="utf-8")
    assert (
        load_validated_entry(
            cache_root=cache_root,
            expected_key=key,
            expected_track_ref="T",
            expected_working_audio_hash="W",
            expected_fingerprint="fp",
        )
        is None
    )


def test_wrong_document_type_is_miss(tmp_path):
    cache_root = tmp_path / "cache"
    key = "abc"
    d = build_entry_dict(
        cache_key=key,
        track_ref="T",
        working_audio_hash="W",
        separation_fingerprint="fp",
        backend={"name": "x", "version": "1"},
        model_identity=_complete_htdemucs("abc"),
        configuration={},
        aggregate_status="ok",
        stems=[],
    )
    d["document_type"] = "sample_brain.something_else"
    (cache_root / key).mkdir(parents=True)
    (cache_root / key / "entry.json").write_text(json.dumps(d), encoding="utf-8")
    assert (
        load_validated_entry(
            cache_root=cache_root,
            expected_key=key,
            expected_track_ref="T",
            expected_working_audio_hash="W",
            expected_fingerprint="fp",
        )
        is None
    )


def test_wrong_cache_key_is_miss(tmp_path):
    cache_root = tmp_path / "cache"
    key = "realkey"
    fp = _publish_ok_entry(cache_root, tmp_path, key)
    assert (
        load_validated_entry(
            cache_root=cache_root,
            expected_key="otherkey",
            expected_track_ref="T",
            expected_working_audio_hash="W",
            expected_fingerprint=fp,
        )
        is None
    )


# ---------------------------------------------------------------------------
# F. Output validation
# ---------------------------------------------------------------------------


def test_missing_output_is_miss(tmp_path):
    cache_root = tmp_path / "cache"
    key = build_cache_key(
        track_ref="T", working_audio_hash="W", separation_fingerprint="fp-Y"
    )
    fp = _publish_ok_entry(cache_root, tmp_path, key)
    (cache_root / key / "outputs" / "drums.wav").unlink()
    assert (
        load_validated_entry(
            cache_root=cache_root,
            expected_key=key,
            expected_track_ref="T",
            expected_working_audio_hash="W",
            expected_fingerprint=fp,
        )
        is None
    )


def test_mutated_output_is_miss(tmp_path):
    cache_root = tmp_path / "cache"
    key = build_cache_key(
        track_ref="T", working_audio_hash="W", separation_fingerprint="fp-Z"
    )
    fp = _publish_ok_entry(cache_root, tmp_path, key)
    (cache_root / key / "outputs" / "drums.wav").write_bytes(b"mutated-bytes")
    assert (
        load_validated_entry(
            cache_root=cache_root,
            expected_key=key,
            expected_track_ref="T",
            expected_working_audio_hash="W",
            expected_fingerprint=fp,
        )
        is None
    )


def test_traversal_path_rejected(tmp_path):
    cache_root = tmp_path / "cache"
    key = "trav"
    (cache_root / key / "outputs").mkdir(parents=True)
    entry = build_entry_dict(
        cache_key=key,
        track_ref="T",
        working_audio_hash="W",
        separation_fingerprint="fp",
        backend={"name": "x", "version": "1"},
        model_identity=_complete_htdemucs("abc"),
        configuration={},
        aggregate_status="ok",
        stems=[
            {
                "stem_kind": "drums",
                "file_ref": "../escape.wav",
                "hash": {"algorithm": "sha256", "value": "x"},
                "status": "ok",
                "manifest_ref": None,
            }
        ],
    )
    (cache_root / key / "entry.json").write_text(json.dumps(entry), encoding="utf-8")
    assert (
        load_validated_entry(
            cache_root=cache_root,
            expected_key=key,
            expected_track_ref="T",
            expected_working_audio_hash="W",
            expected_fingerprint="fp",
        )
        is None
    )


# ---------------------------------------------------------------------------
# G. Status / failure behavior
# ---------------------------------------------------------------------------


def test_ok_is_reusable_hit(tmp_path):
    cache_root = tmp_path / "cache"
    key = build_cache_key(
        track_ref="T", working_audio_hash="W", separation_fingerprint="fp-ok"
    )
    fp = _publish_ok_entry(cache_root, tmp_path, key)
    loaded = load_validated_entry(
        cache_root=cache_root,
        expected_key=key,
        expected_track_ref="T",
        expected_working_audio_hash="W",
        expected_fingerprint=fp,
    )
    assert loaded["aggregate_status"] == "ok"


def test_partial_retains_partial_status(tmp_path):
    cache_root = tmp_path / "cache"
    key = "partialkey"
    fp = _publish_ok_entry(cache_root, tmp_path, key)
    entry_path = cache_root / key / "entry.json"
    data = json.loads(entry_path.read_text(encoding="utf-8"))
    data["aggregate_status"] = "partial"
    data["stems"][0]["status"] = "partial"
    entry_path.write_text(json.dumps(data), encoding="utf-8")
    loaded = load_validated_entry(
        cache_root=cache_root,
        expected_key=key,
        expected_track_ref="T",
        expected_working_audio_hash="W",
        expected_fingerprint=fp,
    )
    assert loaded["aggregate_status"] == "partial"


def test_failed_not_reused_as_success(tmp_path):
    cache_root = tmp_path / "cache"
    key = "failedkey"
    entry = build_entry_dict(
        cache_key=key,
        track_ref="T",
        working_audio_hash="W",
        separation_fingerprint="fp",
        backend={"name": "x", "version": "1"},
        model_identity=_complete_htdemucs("abc"),
        configuration={},
        aggregate_status="failed",
        stems=[],
    )
    (cache_root / key).mkdir(parents=True)
    (cache_root / key / "entry.json").write_text(json.dumps(entry), encoding="utf-8")
    assert (
        load_validated_entry(
            cache_root=cache_root,
            expected_key=key,
            expected_track_ref="T",
            expected_working_audio_hash="W",
            expected_fingerprint="fp",
        )
        is None
    )


def test_not_run_not_reused_as_success(tmp_path):
    cache_root = tmp_path / "cache"
    key = "notrunkey"
    entry = build_entry_dict(
        cache_key=key,
        track_ref="T",
        working_audio_hash="W",
        separation_fingerprint="fp",
        backend={"name": "x", "version": "1"},
        model_identity=_complete_htdemucs("abc"),
        configuration={},
        aggregate_status="not_run",
        stems=[],
    )
    (cache_root / key).mkdir(parents=True)
    (cache_root / key / "entry.json").write_text(json.dumps(entry), encoding="utf-8")
    assert (
        load_validated_entry(
            cache_root=cache_root,
            expected_key=key,
            expected_track_ref="T",
            expected_working_audio_hash="W",
            expected_fingerprint="fp",
        )
        is None
    )


# ---------------------------------------------------------------------------
# H. Privacy
# ---------------------------------------------------------------------------


def test_entry_contains_no_private_paths(tmp_path):
    cache_root = tmp_path / "cache"
    key = "privkey"
    _publish_ok_entry(cache_root, tmp_path, key)
    entry_text = Path(cache_root / key / "entry.json").read_text(encoding="utf-8")
    assert "C:\\" not in entry_text
    assert "/Users/" not in entry_text
    assert "/home/" not in entry_text
    assert "model_cache" not in entry_text
    assert "SAMPLE_BRAIN_STEM_CACHE_DIR" not in entry_text


# ---------------------------------------------------------------------------
# I. End-to-end wrapper cache hit / miss
# ---------------------------------------------------------------------------


def test_separate_with_cache_miss_then_hit(tmp_path):
    cache_root = tmp_path / "cache"
    out1 = tmp_path / "out1"
    out2 = tmp_path / "out2"
    model = _complete_htdemucs("abc")
    executor = _make_executor(b"stem-data-bytes")

    r1 = separate_with_cache(
        input_path=tmp_path / "track.wav",
        track_ref="TRACK1",
        working_audio_hash="WA1",
        model_identity=model,
        configuration={"overlap": 0.25},
        output_dir=out1,
        cache_dir=cache_root,
        backend_name="python-audio-separator",
        backend_version="0.44.5",
        executor=executor,
    )
    assert r1["cache_status"] == "miss"
    assert r1["status"] == "ok"
    assert (out1 / "drums.wav").exists()

    r2 = separate_with_cache(
        input_path=tmp_path / "track.wav",
        track_ref="TRACK1",
        working_audio_hash="WA1",
        model_identity=model,
        configuration={"overlap": 0.25},
        output_dir=out2,
        cache_dir=cache_root,
        backend_name="python-audio-separator",
        backend_version="0.44.5",
        executor=executor,
    )
    assert r2["cache_status"] == "hit"
    assert r2["status"] == "ok"
    assert (out2 / "drums.wav").exists()


def test_incomplete_model_identity_never_hits(tmp_path):
    cache_root = tmp_path / "cache"
    out1 = tmp_path / "out1"
    out2 = tmp_path / "out2"
    incomplete = known_htdemucs_identity(weight_hash=None)
    executor = _make_executor(b"stem-data")
    r1 = separate_with_cache(
        input_path=tmp_path / "t.wav",
        track_ref="T",
        working_audio_hash="W",
        model_identity=incomplete,
        configuration={"overlap": 0.25},
        output_dir=out1,
        cache_dir=cache_root,
        backend_name="python-audio-separator",
        backend_version="0.44.5",
        executor=executor,
    )
    assert r1["cache_status"] == "miss"
    r2 = separate_with_cache(
        input_path=tmp_path / "t.wav",
        track_ref="T",
        working_audio_hash="W",
        model_identity=incomplete,
        configuration={"overlap": 0.25},
        output_dir=out2,
        cache_dir=cache_root,
        backend_name="python-audio-separator",
        backend_version="0.44.5",
        executor=executor,
    )
    assert r2["cache_status"] == "miss"


def test_working_audio_change_invalidates_cache(tmp_path):
    cache_root = tmp_path / "cache"
    model = _complete_htdemucs("abc")
    executor = _make_executor(b"stem-data")
    separate_with_cache(
        input_path=tmp_path / "t.wav",
        track_ref="T",
        working_audio_hash="W1",
        model_identity=model,
        configuration={"overlap": 0.25},
        output_dir=tmp_path / "o1",
        cache_dir=cache_root,
        backend_name="python-audio-separator",
        backend_version="0.44.5",
        executor=executor,
    )
    r2 = separate_with_cache(
        input_path=tmp_path / "t.wav",
        track_ref="T",
        working_audio_hash="W2",
        model_identity=model,
        configuration={"overlap": 0.25},
        output_dir=tmp_path / "o2",
        cache_dir=cache_root,
        backend_name="python-audio-separator",
        backend_version="0.44.5",
        executor=executor,
    )
    assert r2["cache_status"] == "miss"


def test_cache_disabled_runs_but_never_hits(tmp_path):
    cache_root = tmp_path / "cache"
    model = _complete_htdemucs("abc")
    executor = _make_executor(b"stem-data")
    r = separate_with_cache(
        input_path=tmp_path / "t.wav",
        track_ref="T",
        working_audio_hash="W",
        model_identity=model,
        configuration={"overlap": 0.25},
        output_dir=tmp_path / "o",
        cache_dir=cache_root,
        cache_enabled=False,
        backend_name="python-audio-separator",
        backend_version="0.44.5",
        executor=executor,
    )
    assert r["cache_status"] == "disabled"
    assert not cache_root.exists() or len(list(cache_root.iterdir())) == 0
