"""#730 Screen-1 producer-flow end-to-end acceptance.

Thin orchestrator over productive Screen-1 seams only:
Clean Start → Add Source → Analysis → Browser → Audition → Harmonic Match →
Live Kit → Export (#728) → Restart / persistence.

Does not invent a second product path and does not use visual-acceptance
fixture VMs as a substitute for the producer journey.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import time
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf

from src.workbench_live_kit import LIVE_KIT_SLOT_MAPPING
from src.workbench_live_kit_export import LIVE_KIT_EXPORT_DIR_NAME, LIVE_KIT_EXPORT_SCHEMA_VERSION
from src.workbench_qml_startup import WorkspaceMode

PY_SIDE6_AVAILABLE = importlib.util.find_spec("PySide6") is not None
SAMPLE_SOURCES = "container:sample-sources"

pytestmark = pytest.mark.skipif(
    not PY_SIDE6_AVAILABLE,
    reason="PySide6 ist nicht installiert",
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write_key_kick_hybrid(
    path: Path,
    *,
    frequency_hz: float,
    mode: str,
    bpm: float = 120.0,
    duration_sec: float = 4.0,
) -> Path:
    """Synthetic tonal+rhythmic fixture that analysis can resolve to key+BPM."""
    from tests.audio_fixtures import write_key_audio_wav, write_kick_transient_wav

    path.parent.mkdir(parents=True, exist_ok=True)
    keyed = path.with_name(f".{path.stem}_keyed.wav")
    kick = path.with_name(f".{path.stem}_kick.wav")
    write_key_audio_wav(
        keyed,
        frequency_hz=frequency_hz,
        mode=mode,
        duration_sec=duration_sec,
    )
    write_kick_transient_wav(kick, bpm=bpm, duration_sec=duration_sec)
    y1, sr = sf.read(keyed)
    y2, _ = sf.read(kick)
    n = min(len(y1), len(y2))
    mix = np.clip(0.7 * y1[:n] + 0.5 * y2[:n], -1.0, 1.0).astype(np.float32)
    sf.write(path, mix, sr)
    keyed.unlink(missing_ok=True)
    kick.unlink(missing_ok=True)
    return path


def _build_representative_synthetic_bank(root: Path) -> list[Path]:
    from tests.audio_fixtures import write_kick_transient_wav, write_pulse_train_wav

    root.mkdir(parents=True, exist_ok=True)
    written = [
        _write_key_kick_hybrid(root / "cmaj_kick.wav", frequency_hz=261.63, mode="maj"),
        _write_key_kick_hybrid(root / "amin_kick.wav", frequency_hz=220.0, mode="min"),
        _write_key_kick_hybrid(root / "fmaj_kick.wav", frequency_hz=174.61, mode="maj"),
        _write_key_kick_hybrid(root / "gmaj_kick.wav", frequency_hz=196.0, mode="maj"),
        _write_key_kick_hybrid(root / "emaj_kick.wav", frequency_hz=164.81, mode="maj"),
        _write_key_kick_hybrid(root / "dmin_kick.wav", frequency_hz=146.83, mode="min"),
        write_kick_transient_wav(root / "kick_a.wav", bpm=120.0, duration_sec=2.0),
        write_kick_transient_wav(root / "kick_b.wav", bpm=120.0, duration_sec=2.0),
        write_pulse_train_wav(root / "pulse_a.wav", bpm=120.0, duration_sec=2.0),
        write_pulse_train_wav(root / "pulse_b.wav", bpm=120.0, duration_sec=2.0),
        write_kick_transient_wav(root / "kick_c.wav", bpm=128.0, duration_sec=2.0),
        write_pulse_train_wav(root / "pulse_c.wav", bpm=128.0, duration_sec=2.0),
    ]
    return written


def _snapshot_source_hashes(root: Path) -> dict[str, str]:
    return {
        path.relative_to(root).as_posix(): _sha256(path)
        for path in sorted(root.rglob("*"))
        if path.is_file() and not path.name.startswith(".")
    }


def _wait_for_analysis(app, coordinator, folder_id: int, view_model, *, timeout_sec: float = 180.0) -> bool:
    deadline = time.monotonic() + timeout_sec
    while time.monotonic() < deadline:
        app.processEvents()
        token_clear = coordinator._core.current_token(folder_id) is None
        status = str(getattr(view_model, "analysis_status", "") or "")
        if token_clear and view_model.browser_rows and status in {"done", "idle", "error", "cancelled"}:
            return status in {"done", "idle"} and bool(view_model.browser_rows)
        if token_clear and status == "error":
            return False
        time.sleep(0.02)
    return False


def _shutdown_engine(app, engine, window) -> None:
    window.close()
    app.processEvents()
    timer = getattr(engine, "_screen1_waveform_timer", None)
    if timer is not None:
        timer.stop()
    loader = getattr(engine, "_screen1_waveform_loader", None)
    if loader is not None:
        loader.close()
    coordinator = getattr(engine, "_screen1_analysis_coordinator", None)
    if coordinator is not None:
        coordinator.close()
    app.processEvents()


def _boot_screen1(*, db: Path, state_dir: Path):
    from src.workbench_library_navigation import WorkbenchLibraryNavigation
    from src.workbench_qml import (
        Screen1QmlRuntimeComposition,
        Screen1QmlViewModel,
        _qml_engine,
        apply_clean_start_launch,
    )
    from src.workbench_qml_library import WorkbenchLibraryTreeState

    navigation = WorkbenchLibraryNavigation(library_db_path=db)
    composition = Screen1QmlRuntimeComposition(
        library_db_path=db,
        tree_state=WorkbenchLibraryTreeState(navigation),
    )
    view_model = Screen1QmlViewModel(
        state_id="screen1-default-3panel",
        library_labels=(),
        browser_rows=(),
        selected_browser_index=-1,
        harmony_rows=(),
        live_kit_groups=(),
        library_tree=composition.library_tree,
    )
    mode = apply_clean_start_launch(view_model, composition, state_dir=state_dir)
    app, engine, window = _qml_engine(view_model, runtime_composition=composition)
    window.show()
    app.processEvents()
    return mode, composition, view_model, app, engine, window


def _slot_targets() -> list[tuple[str, str]]:
    return [(group, slot) for group, slots in LIVE_KIT_SLOT_MAPPING for slot in slots]


def _collect_relative_tree(root: Path) -> list[str]:
    entries: list[str] = []
    for path in sorted(root.rglob("*")):
        rel = path.relative_to(root).as_posix()
        entries.append(rel + ("/" if path.is_dir() else ""))
    return entries


def test_screen1_producer_flow_e2e_pass(tmp_path: Path):
    from PySide6.QtQuick import QQuickItem

    from src.workbench_library_navigation import LibraryNodeKind

    evidence_root = tmp_path / "evidence"
    evidence_root.mkdir()
    db = tmp_path / "library.db"
    state_dir = tmp_path / "state"
    state_dir.mkdir()
    source = tmp_path / "source-bank"
    export_parent = tmp_path / "exports"
    export_parent.mkdir()

    written = _build_representative_synthetic_bank(source)
    before_hashes = _snapshot_source_hashes(source)
    assert len(written) >= 11

    # --- 1/2 Clean Start -------------------------------------------------
    mode, composition, view_model, app, engine, window = _boot_screen1(
        db=db,
        state_dir=state_dir,
    )
    adapter = engine._screen1_interaction_adapter
    live_kit = engine._screen1_live_kit
    library_bridge = engine._screen1_library_bridge
    library_model = engine._screen1_library_model
    coordinator = engine._screen1_analysis_coordinator

    try:
        assert mode is WorkspaceMode.CLEAN_START
        assert composition.has_active_source is False
        assert view_model.selected_browser_index == -1
        assert adapter.harmonic_match_open is False
        assert adapter.preview_active is False
        assert adapter.pending_live_kit_add == ""
        calm = window.findChild(QQuickItem, "calmCanvas")
        browser = window.findChild(QQuickItem, "browserPane")
        live_kit_pane = window.findChild(QQuickItem, "liveKitPane")
        assert calm is not None and calm.isVisible()
        assert browser is not None and not browser.isVisible()
        assert live_kit_pane is not None and not live_kit_pane.isVisible()

        # --- 3/4/5 Add Source + Analysis ---------------------------------
        library_bridge.registerSourceUrl(str(source))
        app.processEvents()
        # #742: analysis runs before Source/Browser materialization.
        assert composition.has_active_source is False
        folder_id = view_model.analysis_folder_id
        assert folder_id is not None
        assert coordinator is not None
        assert _wait_for_analysis(app, coordinator, folder_id, view_model), (
            f"analysis did not complete (status={view_model.analysis_status!r}, "
            f"rows={len(view_model.browser_rows)})"
        )
        app.processEvents()
        assert composition.has_active_source is True
        selected_id = library_bridge.selectedLibraryNodeId
        assert selected_id == f"root:{folder_id}"
        assert view_model.analysis_status in {"done", "idle"}
        row_count = len(view_model.browser_rows)
        assert row_count >= 11
        assert view_model.selected_browser_index == -1
        assert adapter.preview_active is False
        assert adapter.harmonic_match_open is False
        assert composition.live_kit_revealed is False
        assert browser.isVisible()
        assert not live_kit_pane.isVisible()
        assert not calm.isVisible()

        # --- 6/7 Browser browse + metadata (sanitized) --------------------
        metadata = [
            {
                "name": row.source_row.display_name,
                "bpm": row.source_row.bpm,
                "key": row.source_row.key,
                "status": row.source_row.status,
            }
            for row in view_model.browser_rows[:5]
        ]
        assert all(item["status"] == "ok" for item in metadata)

        # --- 8 Audition ---------------------------------------------------
        first = adapter.preview_row(0)
        assert first is not None
        assert adapter.preview_active is True
        assert adapter.selected_browser_index == 0
        moved = adapter.navigate_browser("next", browser_has_focus=True)
        assert moved is not None
        assert adapter.selected_browser_index == 1
        assert adapter.preview_active is True
        adapter.navigate_browser("previous", browser_has_focus=True)
        assert adapter.selected_browser_index == 0
        assert adapter.stop_preview() is True
        assert adapter.preview_active is False
        assert adapter.stop_preview() is False

        # --- 9/10/11 Harmonic Match --------------------------------------
        anchor_index = next(
            (
                index
                for index, row in enumerate(view_model.browser_rows)
                if row.source_row.bpm is not None
                and isinstance(row.source_row.key, str)
                and ("maj" in row.source_row.key.casefold() or "min" in row.source_row.key.casefold())
            ),
            None,
        )
        assert anchor_index is not None, "No analyzable key+BPM anchor in synthetic bank"
        adapter.select_row(anchor_index)
        assert adapter.toggle_harmonic_match() is True
        assert adapter.harmonic_match_open is True
        first_candidates = [
            (Path(row.source_row.path).name, row.relation, row.fit)
            for row in view_model.harmony_rows
        ]
        assert first_candidates, (
            f"Harmonic Match returned no confident candidates "
            f"(status={adapter.effective_harmony_status!r})"
        )
        assert all(
            "uncertain" not in relation.casefold() and "unknown" not in relation.casefold()
            for _name, relation, _fit in first_candidates
        )
        # Determinism: close/reopen same fingerprint must reuse results.
        candidate_count = len(view_model.harmony_rows)
        assert adapter.toggle_harmonic_match() is False
        assert adapter.toggle_harmonic_match() is True
        second_candidates = [
            (Path(row.source_row.path).name, row.relation, row.fit)
            for row in view_model.harmony_rows
        ]
        assert second_candidates == first_candidates
        assert len(second_candidates) == candidate_count
        harmony_preview = adapter.preview_harmonic_match(0)
        assert harmony_preview is not None
        assert adapter.preview_active is True
        adapter.stop_preview()

        # --- 12 Harmonic Add-to-Kit ---------------------------------------
        slots = _slot_targets()
        assert len(slots) == 11
        assert not live_kit_pane.isVisible()
        harmony_row = adapter.request_add_harmonic_match_to_kit(0)
        assert harmony_row is not None
        engine._screen1_interaction_bridge.refreshState()
        app.processEvents()
        assert composition.live_kit_revealed is True
        assert live_kit_pane.isVisible()
        group0, slot0 = slots[0]
        assert adapter.assign_live_kit_slot(group0, slot0) is True
        assert live_kit.state.assignment_for(group0, slot0) is not None

        # --- 13 Browser add + replace -------------------------------------
        browser_add_index = 0 if anchor_index != 0 else 1
        adapter.request_add_to_kit(browser_add_index)
        group1, slot1 = slots[1]
        assert adapter.assign_live_kit_slot(group1, slot1) is True
        replace_index = 2 if 2 != anchor_index else 3
        replaced = adapter.request_add_to_kit(replace_index)
        assert adapter.assign_live_kit_slot(group1, slot1) is True
        assert live_kit.state.assignment_for(group1, slot1).path == replaced.path

        # --- 14 Complete representative Live Kit --------------------------
        for index, (group, slot) in enumerate(slots):
            if live_kit.state.assignment_for(group, slot) is not None:
                continue
            row_index = index % row_count
            adapter.request_add_to_kit(row_index)
            assert adapter.assign_live_kit_slot(group, slot) is True
        assigned = sum(
            1
            for group, slot in slots
            if live_kit.state.assignment_for(group, slot) is not None
        )
        assert assigned == 11

        # --- 15/16/17/18 Export + source mutation -------------------------
        export_result = adapter.export_live_kit(export_parent)
        assert export_result.ok is True
        assert export_result.export_path is not None
        export_path = export_result.export_path
        assert export_path.name == LIVE_KIT_EXPORT_DIR_NAME
        tree = _collect_relative_tree(export_path)
        assert "manifest.json" in tree
        manifest = json.loads((export_path / "manifest.json").read_text(encoding="utf-8"))
        assert manifest.get("schema_version") == LIVE_KIT_EXPORT_SCHEMA_VERSION
        manifest_text = json.dumps(manifest)
        assert ":\\" not in manifest_text
        assert "/Users/" not in manifest_text
        assert "D:/Dev/" not in manifest_text
        assert str(source).replace("\\", "/") not in manifest_text.replace("\\", "/")

        exported_audio = [
            path for path in export_path.rglob("*") if path.is_file() and path.suffix.lower() == ".wav"
        ]
        assert len(exported_audio) == 11
        for audio in exported_audio:
            data, _sr = sf.read(str(audio))
            assert len(data) > 0
            assert _sha256(audio)

        after_hashes = _snapshot_source_hashes(source)
        assert after_hashes == before_hashes

        # Capture session facts before shutdown (no private absolute paths).
        evidence = {
            "clean_start": "PASS",
            "add_source": "PASS",
            "analysis": {
                "status": view_model.analysis_status,
                "row_count": row_count,
            },
            "browser": {"metadata_sample": metadata, "navigation": "PASS"},
            "audition": "PASS",
            "harmonic_match": {
                "candidate_count": candidate_count,
                "deterministic_reopen": True,
                "audition": "PASS",
            },
            "live_kit": {
                "assigned_count": assigned,
                "groups": [
                    {
                        "group": group,
                        "slots": [
                            slot
                            for slot in slot_names
                            if live_kit.state.assignment_for(group, slot) is not None
                        ],
                    }
                    for group, slot_names in LIVE_KIT_SLOT_MAPPING
                ],
            },
            "export": {
                "ok": True,
                "relative_tree": tree,
                "assigned_count": export_result.assigned_count,
                "empty_count": export_result.empty_count,
            },
            "source_mutation": "NONE",
        }
        exported_audio_paths = list(exported_audio)
        analyzed_row_count = row_count
    finally:
        _shutdown_engine(app, engine, window)

    assert evidence["source_mutation"] == "NONE"

    # --- 19/20/21 Restart + persistence / transient NOT restored ----------
    mode2, composition2, view_model2, app2, engine2, window2 = _boot_screen1(
        db=db,
        state_dir=state_dir,
    )
    adapter2 = engine2._screen1_interaction_adapter
    live_kit2 = engine2._screen1_live_kit
    library_bridge2 = engine2._screen1_library_bridge
    library_model2 = engine2._screen1_library_model
    try:
        assert mode2 is WorkspaceMode.CLEAN_START
        assert composition2.has_active_source is False
        assert view_model2.selected_browser_index == -1
        assert adapter2.harmonic_match_open is False
        assert adapter2.preview_active is False
        assert adapter2.pending_live_kit_add == ""
        assert all(
            live_kit2.state.assignment_for(group, slot) is None
            for group, slot in _slot_targets()
        )
        library_model2.state.fetch_children(SAMPLE_SOURCES)
        from src.workbench_library_navigation import WorkbenchLibraryNavigation

        navigation2 = WorkbenchLibraryNavigation(library_db_path=db)
        roots = [
            node
            for node in navigation2.children(SAMPLE_SOURCES)
            if node.kind is LibraryNodeKind.REGISTERED_ROOT
        ]
        assert len(roots) == 1
        library_bridge2.selectLibraryNode(roots[0].node_id)
        app2.processEvents()
        assert composition2.has_active_source is True
        assert len(view_model2.browser_rows) == analyzed_row_count
        # Fresh/cached load: no analysis job required for unchanged source.
        coordinator2 = engine2._screen1_analysis_coordinator
        assert coordinator2._core.current_token(int(roots[0].node_id.split(":", 1)[1])) is None
        assert view_model2.selected_browser_index == -1
        assert adapter2.harmonic_match_open is False
        assert adapter2.preview_active is False
        evidence["restart"] = {
            "clean_start": "PASS",
            "source_persistence": "PASS",
            "transient_not_restored": True,
            "cached_rows": len(view_model2.browser_rows),
        }
        # Exported files remain usable after app restart.
        for audio in exported_audio_paths:
            data, _sr = sf.read(str(audio))
            assert len(data) > 0
        evidence["export_after_restart"] = "PASS"
        evidence["e2e_result"] = "SCREEN_1_PRODUCER_FLOW_E2E_PASS"
    finally:
        _shutdown_engine(app2, engine2, window2)

    (evidence_root / "producer_flow_e2e.json").write_text(
        json.dumps(evidence, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    assert evidence["e2e_result"] == "SCREEN_1_PRODUCER_FLOW_E2E_PASS"
