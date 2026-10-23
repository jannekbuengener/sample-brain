from __future__ import annotations

import math
import sqlite3
import threading
import time
from pathlib import Path

import pytest

from src.workbench_browser_rows import (
    BACKGROUND_ENRICHMENT,
    CURRENT_VISIBLE,
    BoundedBackgroundWaveformLoader,
    BoundedLazyWaveformCache,
    WaveformCacheResult,
)
from src.workbench_controller import WorkbenchRow
from src.workbench_library import (
    WAVEFORM_ARTIFACT_VERSION,
    WAVEFORM_POINT_BUDGET,
    connect_workbench_library,
    init_workbench_library,
    list_waveform_enrichment_candidates,
    load_valid_waveform_artifacts,
    remove_library_folder,
    store_waveform_artifact,
    upsert_folder,
    upsert_sample,
)
from src.workbench_qml import Screen1QmlViewModel, _hydrate_waveform_rows


@pytest.fixture
def prepared_sample(tmp_path: Path) -> tuple[Path, Path, int, int, int]:
    db_path = tmp_path / "state" / "workbench_library.db"
    source_root = tmp_path / "bank"
    source_root.mkdir()
    sample = source_root / "kick.wav"
    sample.write_bytes(b"synthetic-waveform-source")
    stat = sample.stat()
    size_bytes = int(stat.st_size)
    mtime_ns = int(stat.st_mtime_ns)
    init_workbench_library(db_path)
    folder_id = upsert_folder(source_root, db_path=db_path)
    upsert_sample(
        folder_id,
        WorkbenchRow(
            display_name="kick",
            relative_path="kick.wav",
            path=str(sample),
            bpm=128.0,
            key="Am",
            key_conf=0.9,
            loudness=-10.0,
            brightness=1800.0,
            sample_class="one_shot",
            pred_type="Kick",
            status="ok",
        ),
        size_bytes=size_bytes,
        mtime_ns=mtime_ns,
        db_path=db_path,
    )
    return db_path, sample, folder_id, size_bytes, mtime_ns


def test_valid_persisted_waveform_hit_loads_without_source_decode(prepared_sample):
    db_path, sample, _folder_id, size_bytes, mtime_ns = prepared_sample
    envelope = (0.0, 0.25, 1.0, 0.5)

    assert store_waveform_artifact(
        sample,
        source_size_bytes=size_bytes,
        source_mtime_ns=mtime_ns,
        envelope=envelope,
        db_path=db_path,
    )

    assert load_valid_waveform_artifacts(
        {str(sample.resolve()): (size_bytes, mtime_ns)}, db_path=db_path
    ) == {str(sample.resolve()): envelope}


@pytest.mark.parametrize(
    ("size_delta", "mtime_delta", "version", "point_budget"),
    [
        (1, 0, WAVEFORM_ARTIFACT_VERSION, WAVEFORM_POINT_BUDGET),
        (0, 1, WAVEFORM_ARTIFACT_VERSION, WAVEFORM_POINT_BUDGET),
        (0, 0, "future-renderer", WAVEFORM_POINT_BUDGET),
        (0, 0, WAVEFORM_ARTIFACT_VERSION, WAVEFORM_POINT_BUDGET + 1),
    ],
)
def test_waveform_artifact_identity_mismatch_fails_closed(
    prepared_sample, size_delta, mtime_delta, version, point_budget
):
    db_path, sample, _folder_id, size_bytes, mtime_ns = prepared_sample
    with connect_workbench_library(db_path) as conn:
        sample_id = conn.execute(
            "SELECT id FROM samples WHERE original_path = ?", (str(sample.resolve()),)
        ).fetchone()[0]
        conn.execute(
            """
            INSERT INTO sample_waveform_artifacts (
                sample_id, source_size_bytes, source_mtime_ns, artifact_version,
                point_budget, envelope_json, generated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                sample_id,
                size_bytes + size_delta,
                mtime_ns + mtime_delta,
                version,
                point_budget,
                "[0.0, 1.0]",
                "2026-10-23T00:00:00+00:00",
            ),
        )
        conn.commit()

    assert load_valid_waveform_artifacts(
        {str(sample.resolve()): (size_bytes, mtime_ns)}, db_path=db_path
    ) == {}


@pytest.mark.parametrize(
    "payload",
    [
        "not-json",
        "{}",
        "[]",
        "[NaN]",
        "[Infinity]",
        "[-0.01]",
        "[1.01]",
        "[true]",
        "[" + ",".join("0.1" for _ in range(WAVEFORM_POINT_BUDGET + 1)) + "]",
    ],
)
def test_malformed_or_unbounded_waveform_artifact_never_loads(
    prepared_sample, payload
):
    db_path, sample, _folder_id, size_bytes, mtime_ns = prepared_sample
    with connect_workbench_library(db_path) as conn:
        sample_id = conn.execute(
            "SELECT id FROM samples WHERE original_path = ?", (str(sample.resolve()),)
        ).fetchone()[0]
        conn.execute(
            """
            INSERT INTO sample_waveform_artifacts (
                sample_id, source_size_bytes, source_mtime_ns, artifact_version,
                point_budget, envelope_json, generated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                sample_id,
                size_bytes,
                mtime_ns,
                WAVEFORM_ARTIFACT_VERSION,
                WAVEFORM_POINT_BUDGET,
                payload,
                "2026-10-23T00:00:00+00:00",
            ),
        )
        conn.commit()

    assert load_valid_waveform_artifacts(
        {str(sample.resolve()): (size_bytes, mtime_ns)}, db_path=db_path
    ) == {}


def test_store_rejects_changed_fingerprint_and_invalid_envelope(prepared_sample):
    db_path, sample, _folder_id, size_bytes, mtime_ns = prepared_sample

    assert not store_waveform_artifact(
        sample,
        source_size_bytes=size_bytes + 1,
        source_mtime_ns=mtime_ns,
        envelope=(0.0, 1.0),
        db_path=db_path,
    )
    assert not store_waveform_artifact(
        sample,
        source_size_bytes=size_bytes,
        source_mtime_ns=mtime_ns,
        envelope=(0.0, math.nan),
        db_path=db_path,
    )


def test_removing_sample_metadata_cascades_waveform_artifact(prepared_sample):
    db_path, sample, folder_id, size_bytes, mtime_ns = prepared_sample
    assert store_waveform_artifact(
        sample,
        source_size_bytes=size_bytes,
        source_mtime_ns=mtime_ns,
        envelope=(0.0, 1.0),
        db_path=db_path,
    )

    assert remove_library_folder(folder_id, db_path=db_path)

    with connect_workbench_library(db_path) as conn:
        assert conn.execute("SELECT COUNT(*) FROM sample_waveform_artifacts").fetchone()[0] == 0


def test_wave2_candidates_are_bounded_and_exclude_valid_artifacts(prepared_sample):
    db_path, sample, _folder_id, size_bytes, mtime_ns = prepared_sample
    assert [item.path for item in list_waveform_enrichment_candidates(db_path=db_path, limit=1)] == [
        str(sample.resolve())
    ]
    assert store_waveform_artifact(
        sample,
        source_size_bytes=size_bytes,
        source_mtime_ns=mtime_ns,
        envelope=(0.0, 1.0),
        db_path=db_path,
    )
    assert list_waveform_enrichment_candidates(db_path=db_path, limit=1) == []


def test_memory_cache_hit_touches_access_lru_without_decode():
    decode_calls: list[str] = []
    cache = BoundedLazyWaveformCache(
        capacity=2, loader=lambda path: decode_calls.append(path) or (1.0,)
    )
    cache.put_result("a.wav", WaveformCacheResult("ready", (0.25,)))
    cache.put_result("b.wav", WaveformCacheResult("ready", (0.5,)))

    assert cache.get("a.wav", touch=True).envelope == (0.25,)
    cache.put_result("c.wav", WaveformCacheResult("ready", (0.75,)))

    assert cache.paths() == ("a.wav", "c.wav")
    assert decode_calls == []


def test_rebuilt_qml_rows_hydrate_from_memory_without_decode(prepared_sample):
    db_path, sample, _folder_id, size_bytes, mtime_ns = prepared_sample
    decode_calls: list[str] = []
    cache = BoundedLazyWaveformCache(
        capacity=8, loader=lambda path: decode_calls.append(path) or (1.0,)
    )
    cache.put_result(
        str(sample.resolve()),
        WaveformCacheResult("ready", (0.2, 0.8)),
        source_size_bytes=size_bytes,
        source_mtime_ns=mtime_ns,
    )
    view_model = Screen1QmlViewModel.baseline("screen1-default-3panel")
    view_model.set_browser_state(
        rows=(
            WorkbenchRow(
                display_name="kick",
                relative_path="kick.wav",
                path=str(sample.resolve()),
                bpm=128.0,
                key="Am",
                key_conf=0.9,
                loudness=-10.0,
                brightness=1800.0,
                sample_class="one_shot",
                pred_type="Kick",
                status="ok",
                details={"source_size_bytes": size_bytes, "source_mtime_ns": mtime_ns},
            ),
        ),
        selected_index=0,
        browser_context="Bank",
        error=None,
    )

    assert _hydrate_waveform_rows(
        view_model,
        view_model.browser_rows,
        waveform_cache=cache,
        library_db_path=db_path,
    ) == {str(sample.resolve())}
    assert view_model.browser_rows[0].waveform_envelope == (0.2, 0.8)
    assert decode_calls == []


def test_empty_favorites_do_not_resolve_each_browser_path(monkeypatch):
    view_model = Screen1QmlViewModel.baseline("screen1-default-3panel")
    row = view_model.browser_rows[0].source_row

    def fail_resolve(*_args, **_kwargs):
        raise AssertionError("empty favorites must not resolve row paths")

    monkeypatch.setattr(Path, "resolve", fail_resolve)
    view_model.set_browser_state(
        rows=(row,),
        selected_index=0,
        browser_context="Library",
        error=None,
        favorite_paths=set(),
    )

    assert len(view_model.browser_rows) == 1


def test_current_generation_drops_stale_queued_viewport_work():
    started = threading.Event()
    release = threading.Event()
    calls: list[str] = []
    cache = BoundedLazyWaveformCache(capacity=8, loader=lambda _path: ())

    def decoder(path: str):
        calls.append(path)
        if path == "old-running.wav":
            started.set()
            assert release.wait(timeout=2)
        return (1.0,)

    loader = BoundedBackgroundWaveformLoader(cache=cache, loader=decoder, max_pending=4)
    try:
        old_generation = loader.current_generation
        assert loader.schedule("old-running.wav", generation=old_generation)
        assert started.wait(timeout=1)
        assert loader.schedule("old-queued-a.wav", generation=old_generation)
        assert loader.schedule("old-queued-b.wav", generation=old_generation)

        current_generation = loader.advance_generation()
        assert loader.schedule("new-visible.wav", generation=current_generation)
        release.set()
        deadline = time.monotonic() + 2
        while loader.pending_count and time.monotonic() < deadline:
            assert loader.wait_for_result(timeout=1)
            loader.drain_results()

        assert calls == ["old-running.wav", "new-visible.wav"]
        assert loader.pending_count == 0
    finally:
        release.set()
        loader.close()


def test_current_visible_outranks_background_enrichment():
    started = threading.Event()
    release = threading.Event()
    calls: list[str] = []
    cache = BoundedLazyWaveformCache(capacity=8, loader=lambda _path: ())

    def decoder(path: str):
        calls.append(path)
        if path == "background-running.wav":
            started.set()
            assert release.wait(timeout=2)
        return (1.0,)

    loader = BoundedBackgroundWaveformLoader(cache=cache, loader=decoder, max_pending=4)
    try:
        assert loader.schedule("background-running.wav", priority=BACKGROUND_ENRICHMENT)
        assert started.wait(timeout=1)
        assert loader.schedule("background-queued.wav", priority=BACKGROUND_ENRICHMENT)
        assert loader.schedule("visible.wav", priority=CURRENT_VISIBLE)
        release.set()
        deadline = time.monotonic() + 2
        while loader.pending_count and time.monotonic() < deadline:
            assert loader.wait_for_result(timeout=1)
            loader.drain_results()
        assert calls == ["background-running.wav", "visible.wav", "background-queued.wav"]
        assert loader.pending_count == 0
    finally:
        release.set()
        loader.close()


def test_visible_request_promotes_same_queued_background_identity():
    started = threading.Event()
    release = threading.Event()
    calls: list[str] = []
    cache = BoundedLazyWaveformCache(capacity=8, loader=lambda _path: ())

    def decoder(path: str):
        calls.append(path)
        if path == "background-running.wav":
            started.set()
            assert release.wait(timeout=2)
        return (1.0,)

    loader = BoundedBackgroundWaveformLoader(cache=cache, loader=decoder, max_pending=4)
    try:
        assert loader.schedule("background-running.wav", priority=BACKGROUND_ENRICHMENT)
        assert started.wait(timeout=1)
        assert loader.schedule("shared.wav", priority=BACKGROUND_ENRICHMENT)
        assert loader.schedule("other-background.wav", priority=BACKGROUND_ENRICHMENT)
        assert loader.schedule("shared.wav", priority=CURRENT_VISIBLE)
        release.set()
        deadline = time.monotonic() + 2
        while loader.pending_count and time.monotonic() < deadline:
            assert loader.wait_for_result(timeout=1)
            loader.drain_results()
        assert calls == [
            "background-running.wav",
            "shared.wav",
            "other-background.wav",
        ]
    finally:
        release.set()
        loader.close()


def test_stale_completion_retains_its_identity_for_fail_closed_persistence():
    started = threading.Event()
    release = threading.Event()
    completed = []
    cache = BoundedLazyWaveformCache(capacity=8, loader=lambda _path: ())

    def decoder(_path: str):
        started.set()
        assert release.wait(timeout=2)
        return (0.5,)

    loader = BoundedBackgroundWaveformLoader(
        cache=cache, loader=decoder, max_pending=2, on_result=completed.append
    )
    try:
        generation = loader.current_generation
        assert loader.schedule(
            "same.wav",
            generation=generation,
            source_size_bytes=10,
            source_mtime_ns=20,
        )
        assert started.wait(timeout=1)
        loader.advance_generation()
        release.set()
        assert loader.wait_for_result(timeout=1)
        assert loader.drain_results() == 1
        assert completed[0].generation == generation
        assert completed[0].source_size_bytes == 10
        assert completed[0].source_mtime_ns == 20
    finally:
        release.set()
        loader.close()
