from __future__ import annotations

import json
import re
from copy import deepcopy
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
FIXTURE_PATH = REPO_ROOT / "docs" / "performance_pack_layout_v1_examples.json"
DOC_PATH = REPO_ROOT / "docs" / "PERFORMANCE_PACK_LAYOUT_V1.md"

# Cross-validate every example against the #257 manifest contract as well.
try:
    from test_performance_pack_manifest_contract import validate_pack as validate_manifest_v1
except Exception:  # pragma: no cover - import shield
    validate_manifest_v1 = None  # type: ignore[assignment]


# ---------------------------------------------------------------------------
# Reference implementation of the #258 naming / layout algorithm.
# This is the canonical behavior the pack assembler (#259) must match.
# ---------------------------------------------------------------------------

_FORBIDDEN_FILENAME_CHARS = set('<>:"/\\|?*')

_ALLOWED_REF_PREFIXES = ("analysis/", "loops/", "sections/", "stems/")
_ALLOWED_REF_EXACT = ("manifest.json",)


def sanitize_component(value: str) -> str:
    """Sanitize a portable id/label into a safe, case-insensitive filename component.

    - keeps only [A-Za-z0-9._-]
    - lowercases so names are case-insensitive-safe
    - collapses runs of '_' and strips leading/trailing '_'
    - rejects empty results
    """
    if not isinstance(value, str) or value == "":
        raise ValueError("sanitize_component requires a non-empty string")
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", value)
    cleaned = cleaned.lower()
    cleaned = re.sub(r"_+", "_", cleaned).strip("_").strip(".")
    if not cleaned:
        raise ValueError("sanitize_component collapsed to empty")
    return cleaned


def asset_file_name(asset_kind: str, asset_id: str, ext: str) -> str:
    """Return the canonical asset file name (no directory)."""
    if asset_kind not in ("loop", "section"):
        raise ValueError(f"asset_kind must be loop|section, got {asset_kind!r}")
    return f"{asset_kind}_{sanitize_component(asset_id)}.{ext}"


def asset_relative_path(asset_kind: str, asset_id: str, ext: str) -> str:
    """Return the pack-relative path of an asset file inside its kind directory."""
    kind_dir = "loops" if asset_kind == "loop" else "sections"
    return f"{kind_dir}/{asset_file_name(asset_kind, asset_id, ext)}"


def stem_relative_path(stem_id: str) -> str:
    return f"stems/{sanitize_component(stem_id)}.json"


def track_map_relative_path() -> str:
    return "analysis/track_map.json"


def arrangement_relative_path() -> str:
    return "analysis/arrangement_map.json"


def resolve_asset_names(assets: list[dict]) -> dict[str, str]:
    """Deterministically assign final json paths for a list of assets.

    Keyed by asset_id. Uses the unique portable asset_id; if two distinct
    asset_ids sanitize to the same base within the same kind directory, the
    colliding group is ordered by full asset_id (lexicographic) and all but the
    first receive a numeric suffix. No random UUID is ever used.
    """
    by_dir: dict[str, list[tuple[str, str]]] = {}
    for a in assets:
        kind_dir = "loops" if a["asset_kind"] == "loop" else "sections"
        base = f"{a['asset_kind']}_{sanitize_component(a['asset_id'])}"
        by_dir.setdefault(kind_dir, []).append((a["asset_id"], base))

    result: dict[str, str] = {}
    for kind_dir, items in by_dir.items():
        groups: dict[str, list[str]] = {}
        for aid, base in items:
            groups.setdefault(base, []).append(aid)
        for base, aids in groups.items():
            ordered = sorted(aids)
            for i, aid in enumerate(ordered):
                suffix = "" if i == 0 else f"_{i + 1}"
                result[aid] = f"{kind_dir}/{base}{suffix}.json"
    return result


def is_portable_ref(value: str) -> bool:
    if not isinstance(value, str) or not value:
        return False
    if ".." in value:
        return False
    if "file://" in value:
        return False
    if "\\" in value:
        return False
    if value.startswith("/"):
        return False
    if any(c.isalpha() and value[i + 1] == ":" for i, c in enumerate(value[:-1])):
        return False
    return True


def is_allowed_pack_ref(value: str) -> bool:
    if not is_portable_ref(value):
        return False
    if value in _ALLOWED_REF_EXACT:
        return True
    return any(value.startswith(p) for p in _ALLOWED_REF_PREFIXES)


def validate_layout(pack: dict) -> list[str]:
    """Validate that a #257 manifest uses only #258-allowed pack-relative refs."""
    errors: list[str] = []

    st = pack.get("source_track") or {}
    tm_ref = st.get("track_ref") or ""
    if not is_allowed_pack_ref(tm_ref):
        errors.append(f"source_track.track_ref not an allowed pack ref: {tm_ref!r}")
    elif tm_ref != track_map_relative_path():
        errors.append(f"source_track.track_ref must be {track_map_relative_path()!r}, got {tm_ref!r}")

    docs = pack.get("documents") or {}
    tm = docs.get("track_map") or {}
    tmr = tm.get("ref") or ""
    if not is_allowed_pack_ref(tmr):
        errors.append(f"documents.track_map.ref not allowed: {tmr!r}")
    elif tmr != track_map_relative_path():
        errors.append(f"documents.track_map.ref must be {track_map_relative_path()!r}")

    arr = docs.get("arrangement")
    if isinstance(arr, dict):
        ar = arr.get("ref") or ""
        if not is_allowed_pack_ref(ar):
            errors.append(f"documents.arrangement.ref not allowed: {ar!r}")
        elif ar != arrangement_relative_path():
            errors.append(f"documents.arrangement.ref must be {arrangement_relative_path()!r}")

    assets = pack.get("assets") or []
    expected = resolve_asset_names(assets)
    for a in assets:
        ref = a.get("asset_ref") or ""
        if not is_allowed_pack_ref(ref):
            errors.append(f"asset {a.get('asset_id')} asset_ref not allowed: {ref!r}")
            continue
        exp = expected.get(a["asset_id"])
        if exp is not None and ref != exp:
            errors.append(f"asset {a.get('asset_id')} asset_ref {ref!r} != expected {exp!r}")

    for sm in pack.get("stems") or []:
        sref = sm.get("stem_ref") or ""
        if not is_allowed_pack_ref(sref):
            errors.append(f"stem {sm.get('stem_id')} stem_ref not allowed: {sref!r}")
        elif sref != stem_relative_path(sm["stem_id"]):
            errors.append(f"stem {sm.get('stem_id')} stem_ref must be {stem_relative_path(sm['stem_id'])!r}")

    return errors


# ---------------------------------------------------------------------------
# Fixture loading
# ---------------------------------------------------------------------------

def _load_examples() -> dict:
    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


def _example(name: str) -> dict:
    return deepcopy(_load_examples()["examples"][name])


# ---------------------------------------------------------------------------
# Doc / fixture existence
# ---------------------------------------------------------------------------

def test_doc_and_fixture_exist():
    assert DOC_PATH.exists()
    assert FIXTURE_PATH.exists()


def test_doc_declares_layout_contract():
    text = DOC_PATH.read_text(encoding="utf-8")
    assert "PERFORMANCE_PACK_LAYOUT_V1.md" in text or "Performance Pack Layout v1" in text
    for token in ("analysis/", "loops/", "sections/", "stems/", "manifest.json"):
        assert token in text, f"layout token missing: {token}"


# ---------------------------------------------------------------------------
# Determinism
# ---------------------------------------------------------------------------

def test_same_input_yields_same_path():
    p1 = asset_relative_path("loop", "asset_loop_8bar_master_01a2b3c4", "wav")
    p2 = asset_relative_path("loop", "asset_loop_8bar_master_01a2b3c4", "wav")
    assert p1 == p2
    assert p1 == "loops/loop_asset_loop_8bar_master_01a2b3c4.wav"


def test_same_input_yields_same_json_path():
    p1 = asset_relative_path("section", "asset_section_drop_master_a1b2c3", "json")
    p2 = asset_relative_path("section", "asset_section_drop_master_a1b2c3", "json")
    assert p1 == p2 == "sections/section_asset_section_drop_master_a1b2c3.json"


# ---------------------------------------------------------------------------
# Collisions
# ---------------------------------------------------------------------------

def test_multiple_drops_do_not_collide():
    drops = [
        {"asset_id": "asset_section_drop_master_a1b2c3", "asset_kind": "section"},
        {"asset_id": "asset_section_drop_master_d4e5f6", "asset_kind": "section"},
    ]
    paths = resolve_asset_names(drops)
    assert len(set(paths.values())) == 2


def test_multiple_builds_do_not_collide():
    builds = [
        {"asset_id": "asset_section_build_master_c3d4e5", "asset_kind": "section"},
        {"asset_id": "asset_section_build_master_f6a7b8", "asset_kind": "section"},
    ]
    paths = resolve_asset_names(builds)
    assert len(set(paths.values())) == 2


def test_multiple_loops_same_section_do_not_collide():
    loops = [
        {"asset_id": "asset_loop_4bar_master_11aabb", "asset_kind": "loop"},
        {"asset_id": "asset_loop_8bar_master_22bbcc", "asset_kind": "loop"},
        {"asset_id": "asset_loop_16bar_master_33ccdd", "asset_kind": "loop"},
    ]
    paths = resolve_asset_names(loops)
    assert len(set(paths.values())) == 3


def test_case_insensitive_collisions_are_prevented():
    # Two distinct asset_ids differing only by case sanitize to the same base.
    assets = [
        {"asset_id": "AssetLoop_XyZ", "asset_kind": "loop"},
        {"asset_id": "assetloop_xyz", "asset_kind": "loop"},
    ]
    paths = resolve_asset_names(assets)
    assert len(set(paths.values())) == 2
    # Both bases are identical and lowercased; the tiebreaker uses full asset_id.
    assert paths["AssetLoop_XyZ"] == "loops/loop_assetloop_xyz.json"
    assert paths["assetloop_xyz"] == "loops/loop_assetloop_xyz_2.json"


def test_sanitized_collision_gets_deterministic_suffix():
    # These three sanitize to the same base "loop_a" and must be disambiguated
    # deterministically by full asset_id order (no random suffix).
    assets = [
        {"asset_id": "loop a", "asset_kind": "loop"},
        {"asset_id": "loop_a", "asset_kind": "loop"},
        {"asset_id": "loop__a", "asset_kind": "loop"},
    ]
    paths = resolve_asset_names(assets)
    bases = sorted(paths.values())
    assert bases[0] == "loops/loop_loop_a.json"
    assert bases[1] == "loops/loop_loop_a_2.json"
    assert bases[2] == "loops/loop_loop_a_3.json"


# ---------------------------------------------------------------------------
# Portability / forbidden characters
# ---------------------------------------------------------------------------

def test_windows_dangerous_characters_are_not_produced():
    nasty = [
        'a<b>c:d"e/f\\g|h?i*j',
        "leading dot.name",
        "trailing dot.",
        " space start",
        "tab\tinside",
        "NEWLINE\nhere",
    ]
    for n in nasty:
        comp = sanitize_component(n)
        for ch in _FORBIDDEN_FILENAME_CHARS:
            assert ch not in comp, f"forbidden char {ch!r} in {comp!r} from {n!r}"
        assert not comp.startswith(".")
        assert not comp.endswith(".")
        assert not comp.startswith(" ")
        assert not comp.endswith(" ")
        # control characters
        assert not any(ord(c) < 32 for c in comp)


def test_absolute_paths_are_rejected():
    for bad in ("C:/Users/x/demo.wav", "D:\\x\\y.wav", "/abs/path.json", "\\\\host\\share\\f", "file:///x/y"):
        assert not is_portable_ref(bad)


def test_parent_traversal_is_rejected():
    for bad in ("../escape.json", "analysis/../../etc/passwd", "loops/../track_map.json"):
        assert not is_portable_ref(bad)
        assert not is_allowed_pack_ref(bad)


def test_asset_ref_must_be_pack_relative():
    pack = _example("pack_without_stems")
    pack["assets"][0]["asset_ref"] = "C:/private/loop.wav"
    errors = validate_layout(pack)
    assert any("not allowed" in e for e in errors), errors


def test_dots_in_asset_ref_are_rejected():
    pack = _example("pack_without_stems")
    pack["assets"][0]["asset_ref"] = "../loops/leak.json"
    errors = validate_layout(pack)
    assert any("not allowed" in e for e in errors), errors


# ---------------------------------------------------------------------------
# Layout validity of example packs
# ---------------------------------------------------------------------------

def test_all_examples_are_valid_layout_and_manifest():
    examples = _load_examples()["examples"]
    for name, pack in examples.items():
        layout_errors = validate_layout(pack)
        assert layout_errors == [], f"{name}: {layout_errors}"
        if validate_manifest_v1 is not None:
            manifest_errors = validate_manifest_v1(deepcopy(pack))
            assert manifest_errors == [], f"{name}: {manifest_errors}"


def test_pack_without_stems_is_valid_and_has_no_stems_dir_ref():
    pack = _example("pack_without_stems")
    assert "stems" not in pack
    assert validate_layout(pack) == []
    if validate_manifest_v1 is not None:
        assert validate_manifest_v1(deepcopy(pack)) == []


def test_multiple_loops_example_unique_paths():
    pack = _example("pack_multiple_loops")
    loops = [a for a in pack["assets"] if a["asset_kind"] == "loop"]
    paths = [a["asset_ref"] for a in loops]
    assert len(paths) == len(set(paths)) == 3
    for a in loops:
        assert a["asset_ref"].startswith("loops/")


def test_two_drops_example_unique_paths():
    pack = _example("pack_two_drops")
    sections = [a for a in pack["assets"] if a["asset_kind"] == "section"]
    paths = [a["asset_ref"] for a in sections]
    assert len(paths) == len(set(paths)) == 2
    for a in sections:
        assert a["asset_ref"].startswith("sections/")


def test_two_builds_example_unique_paths():
    pack = _example("pack_two_builds")
    sections = [a for a in pack["assets"] if a["asset_kind"] == "section"]
    paths = [a["asset_ref"] for a in sections]
    assert len(paths) == len(set(paths)) == 2


def test_master_only_example_uses_master_source():
    pack = _example("pack_master_only")
    for a in pack["assets"]:
        assert a["source_kind"] == "master"
        assert a.get("stem_id") is None
        assert a.get("producer_group_id") is None


def test_manifest_refs_point_to_allowed_pack_areas():
    pack = _example("pack_without_stems")
    refs = [
        pack["source_track"]["track_ref"],
        pack["documents"]["track_map"]["ref"],
        *[a["asset_ref"] for a in pack["assets"]],
    ]
    for r in refs:
        assert is_allowed_pack_ref(r), r


def test_asset_identity_is_portable_id_not_sqlite():
    # Filename is derived purely from the portable asset_id; no numeric/row id leaks in.
    aid = "asset_loop_8bar_master_01a2b3c4"
    name = asset_file_name("loop", aid, "wav")
    assert aid in name
    # A different ordering/scenario with a different id yields a different name
    # without any database row dependency.
    other = asset_file_name("loop", "asset_loop_8bar_master_ffeedd", "wav")
    assert other != name
    assert "asset_loop_8bar_master_ffeedd" in other


def test_asset_audio_file_name_is_kind_prefixed():
    assert asset_file_name("loop", "8bar_master_01", "wav") == "loop_8bar_master_01.wav"
    assert asset_file_name("section", "drop_master_a1", "wav") == "section_drop_master_a1.wav"


def test_stem_ref_layout():
    assert stem_relative_path("stem_drums_01") == "stems/stem_drums_01.json"
