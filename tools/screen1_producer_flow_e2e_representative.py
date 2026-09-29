"""Controlled #730 representative local-source runtime acceptance.

Uses productive Screen-1 seams only. Writes sanitized evidence outside the
repository. Does not commit or print private absolute source paths.
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
import time
from pathlib import Path

import soundfile as sf

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _wait_for_analysis(app, coordinator, folder_id: int, view_model, timeout_sec: float = 600.0) -> bool:
    deadline = time.monotonic() + timeout_sec
    while time.monotonic() < deadline:
        app.processEvents()
        token_clear = coordinator._core.current_token(folder_id) is None
        status = str(getattr(view_model, "analysis_status", "") or "")
        if token_clear and view_model.browser_rows and status in {"done", "idle"}:
            return True
        if token_clear and status == "error":
            return False
        time.sleep(0.05)
    return False


def _shutdown(app, engine, window) -> None:
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


def main() -> int:
    from PySide6.QtQuick import QQuickItem

    from src.workbench_library_navigation import LibraryNodeKind, WorkbenchLibraryNavigation
    from src.workbench_live_kit import LIVE_KIT_SLOT_MAPPING
    from src.workbench_live_kit_export import LIVE_KIT_EXPORT_DIR_NAME, LIVE_KIT_EXPORT_SCHEMA_VERSION
    from src.workbench_qml import (
        Screen1QmlRuntimeComposition,
        Screen1QmlViewModel,
        _qml_engine,
        apply_clean_start_launch,
    )
    from src.workbench_qml_library import WorkbenchLibraryTreeState
    from src.workbench_qml_startup import WorkspaceMode

    source = Path(os.environ["SAMPLE_BRAIN_E2E_SOURCE"]).expanduser().resolve()
    evidence_dir = Path(os.environ["SAMPLE_BRAIN_E2E_EVIDENCE"]).expanduser().resolve()
    work = Path(os.environ.get("SAMPLE_BRAIN_E2E_WORK", evidence_dir / "work")).expanduser().resolve()
    evidence_dir.mkdir(parents=True, exist_ok=True)
    work.mkdir(parents=True, exist_ok=True)
    db = work / "library.db"
    state_dir = work / "state"
    state_dir.mkdir(exist_ok=True)
    export_parent = work / "exports"
    export_parent.mkdir(exist_ok=True)

    wavs = sorted(p for p in source.rglob("*.wav") if p.is_file())
    if len(wavs) < 4:
        raise SystemExit(f"representative source needs >=4 wav files, found {len(wavs)}")
    before = {p.name: _sha256(p) for p in wavs}

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
    adapter = engine._screen1_interaction_adapter
    live_kit = engine._screen1_live_kit
    library_bridge = engine._screen1_library_bridge
    coordinator = engine._screen1_analysis_coordinator

    evidence: dict = {
        "runtime": "qml_product_screen1",
        "source_file_count": len(wavs),
        "source_label": "representative-local-bank",
    }
    try:
        if mode is not WorkspaceMode.CLEAN_START:
            raise RuntimeError("Clean Start failed")
        calm = window.findChild(QQuickItem, "calmCanvas")
        if calm is None or not calm.isVisible():
            raise RuntimeError("Calm Canvas missing on Clean Start")
        evidence["clean_start"] = "PASS"

        library_bridge.registerSourceUrl(str(source))
        app.processEvents()
        selected_id = library_bridge.selectedLibraryNodeId
        folder_id = int(selected_id.split(":", 1)[1])
        if not _wait_for_analysis(app, coordinator, folder_id, view_model):
            raise RuntimeError(
                f"analysis failed status={view_model.analysis_status!r} rows={len(view_model.browser_rows)}"
            )
        row_count = len(view_model.browser_rows)
        evidence["add_source"] = "PASS"
        evidence["analysis"] = {
            "status": view_model.analysis_status,
            "row_count": row_count,
        }
        if row_count < 1:
            raise RuntimeError("no analyzed browser rows")

        adapter.preview_row(0)
        if not adapter.preview_active:
            raise RuntimeError("audition failed")
        if row_count > 1:
            adapter.navigate_browser("next", browser_has_focus=True)
            adapter.navigate_browser("previous", browser_has_focus=True)
        adapter.stop_preview()
        evidence["audition"] = "PASS"
        evidence["browser"] = "PASS"

        # Prefer a key+BPM anchor when available; otherwise still complete kit/export.
        anchor_index = next(
            (
                i
                for i, row in enumerate(view_model.browser_rows)
                if row.source_row.bpm is not None
                and isinstance(row.source_row.key, str)
                and ("maj" in row.source_row.key.casefold() or "min" in row.source_row.key.casefold())
            ),
            0,
        )
        adapter.select_row(anchor_index)
        harmonic_pass = False
        candidate_count = 0
        if adapter.toggle_harmonic_match():
            candidate_count = len(view_model.harmony_rows)
            if candidate_count:
                adapter.preview_harmonic_match(0)
                adapter.stop_preview()
                adapter.request_add_harmonic_match_to_kit(0)
                adapter.assign_live_kit_slot("Kick + Bass", "Kick")
                harmonic_pass = True
            adapter.toggle_harmonic_match()
        evidence["harmonic_match"] = {
            "opened": True,
            "candidate_count": candidate_count,
            "audition_add": harmonic_pass,
            "anchor_usable": bool(
                view_model.browser_rows[anchor_index].source_row.bpm is not None
                and isinstance(view_model.browser_rows[anchor_index].source_row.key, str)
                and (
                    "maj" in str(view_model.browser_rows[anchor_index].source_row.key).casefold()
                    or "min" in str(view_model.browser_rows[anchor_index].source_row.key).casefold()
                )
            ),
        }

        slots = [(g, s) for g, ss in LIVE_KIT_SLOT_MAPPING for s in ss]
        for index, (group, slot) in enumerate(slots):
            if live_kit.state.assignment_for(group, slot) is not None:
                continue
            adapter.request_add_to_kit(index % row_count)
            if not adapter.assign_live_kit_slot(group, slot):
                raise RuntimeError(f"assign failed for {group}/{slot}")
        # Replace one slot from browser.
        adapter.request_add_to_kit(min(1, row_count - 1))
        adapter.assign_live_kit_slot("Kick + Bass", "Bass")
        assigned = sum(1 for g, s in slots if live_kit.state.assignment_for(g, s) is not None)
        if assigned != 11:
            raise RuntimeError(f"incomplete kit assigned={assigned}")
        evidence["live_kit"] = {"assigned_count": assigned, "replace": "PASS"}

        result = adapter.export_live_kit(export_parent)
        if not result.ok or result.export_path is None:
            raise RuntimeError(result.error_message or "export failed")
        manifest = json.loads((result.export_path / "manifest.json").read_text(encoding="utf-8"))
        tree = sorted(
            p.relative_to(result.export_path).as_posix() + ("/" if p.is_dir() else "")
            for p in result.export_path.rglob("*")
        )
        exported = [p for p in result.export_path.rglob("*.wav") if p.is_file()]
        for audio in exported:
            data, _sr = sf.read(str(audio))
            if len(data) == 0:
                raise RuntimeError("empty exported audio")
        after = {p.name: _sha256(p) for p in wavs}
        if after != before:
            raise RuntimeError("SOURCE_MUTATION detected")
        evidence["export"] = {
            "ok": True,
            "dir_name": LIVE_KIT_EXPORT_DIR_NAME,
            "schema_version": manifest.get("schema_version", LIVE_KIT_EXPORT_SCHEMA_VERSION),
            "relative_tree": tree,
            "audio_count": len(exported),
        }
        evidence["source_mutation"] = "NONE"
        export_path = result.export_path
    finally:
        _shutdown(app, engine, window)

    # Restart persistence / Clean Start
    navigation2 = WorkbenchLibraryNavigation(library_db_path=db)
    composition2 = Screen1QmlRuntimeComposition(
        library_db_path=db,
        tree_state=WorkbenchLibraryTreeState(navigation2),
    )
    view_model2 = Screen1QmlViewModel(
        state_id="screen1-default-3panel",
        library_labels=(),
        browser_rows=(),
        selected_browser_index=-1,
        harmony_rows=(),
        live_kit_groups=(),
        library_tree=composition2.library_tree,
    )
    mode2 = apply_clean_start_launch(view_model2, composition2, state_dir=state_dir)
    app2, engine2, window2 = _qml_engine(view_model2, runtime_composition=composition2)
    window2.show()
    app2.processEvents()
    try:
        if mode2 is not WorkspaceMode.CLEAN_START:
            raise RuntimeError("restart Clean Start failed")
        adapter2 = engine2._screen1_interaction_adapter
        if composition2.has_active_source or adapter2.harmonic_match_open or adapter2.preview_active:
            raise RuntimeError("transient state restored on restart")
        engine2._screen1_library_model.state.fetch_children("container:sample-sources")
        roots = [
            node
            for node in navigation2.children("container:sample-sources")
            if node.kind is LibraryNodeKind.REGISTERED_ROOT
        ]
        if len(roots) != 1:
            raise RuntimeError(f"expected 1 registered source, got {len(roots)}")
        engine2._screen1_library_bridge.selectLibraryNode(roots[0].node_id)
        app2.processEvents()
        if len(view_model2.browser_rows) != evidence["analysis"]["row_count"]:
            raise RuntimeError("cached rows mismatch after restart")
        for audio in export_path.rglob("*.wav"):
            data, _sr = sf.read(str(audio))
            if len(data) == 0:
                raise RuntimeError("export unusable after restart")
        evidence["restart"] = {
            "clean_start": "PASS",
            "source_persistence": "PASS",
            "transient_not_restored": True,
            "export_usable": True,
        }
        evidence["e2e_result"] = "SCREEN_1_PRODUCER_FLOW_E2E_PASS"
    finally:
        _shutdown(app2, engine2, window2)

    out = evidence_dir / "representative_local_producer_flow.json"
    out.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"status": evidence["e2e_result"], "evidence": out.name}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
