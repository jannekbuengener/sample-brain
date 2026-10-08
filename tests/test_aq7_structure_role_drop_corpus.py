"""Frozen tests for AQ7 synthetic structure/role/drop corpus (#1024).

TEST FREEZE — fix generator/schema, not these expectations.
These assertions encode the Task-1 corpus contract
(``docs/benchmarks/AQ7_STRUCTURE_ROLE_DROP_CORPUS.md``). Do not weaken them
to match a soft implementation.
"""

from __future__ import annotations

import ast
import copy
import importlib
import json
import re
from pathlib import Path
from typing import Any

import pytest


class _LazyModule:
    """Import public surfaces on first attribute access.

    Modules are intentionally absent until Tasks 3/4 — each test should fail
    RED at use-site rather than aborting collection.
    """

    def __init__(self, module_name: str) -> None:
        self._module_name = module_name
        self._module: Any | None = None

    def _load(self) -> Any:
        if self._module is None:
            self._module = importlib.import_module(self._module_name)
        return self._module

    def __getattr__(self, name: str) -> Any:
        return getattr(self._load(), name)


# Public surfaces under test (planned modules; RED until implemented).
schema = _LazyModule("src.aq7_structure_role_drop_schema")
corpus = _LazyModule("src.aq7_structure_role_drop_corpus")


REPO_ROOT = Path(__file__).resolve().parents[1]

CORPUS_ID = "sample-brain.aq7.structure-role-drop.synthetic.v1"
DOCUMENT_TYPE = "sample-brain.aq7.structure-role-drop-corpus.v1"
CORPUS_VERSION = "1.0.0"
GENERATOR_ID = "sample-brain.aq7.structure-role-drop.generator.v1"
GENERATOR_SEED = 1024001
SAMPLE_RATE = 44100
LABEL_SOURCE = "synthetic_deterministic"

ROLE_VOCABULARY = (
    "intro",
    "groove",
    "build",
    "drop",
    "breakdown",
    "outro",
    "unknown",
)
SPLITS = frozenset({"CALIBRATION", "TEST"})
ANNOTATION_STATUSES = frozenset(
    {"adjudicated", "single_source", "ambiguous", "unavailable"}
)
BEATGRID_PROVENANCE_STATUSES = frozenset(
    {"authored_synthetic", "missing", "insufficient"}
)
PLANE_TOKENS = ("aq7.boundary", "aq7.role", "aq7.drop_event")

CALIBRATION_FIXTURES: tuple[tuple[str, str], ...] = (
    ("simple_clean", "aq7-synth-simple-clean-cal-001"),
    ("repeated_structure", "aq7-synth-repeated-structure-cal-001"),
    ("near_boundary_tolerance", "aq7-synth-near-boundary-tolerance-cal-001"),
    ("role_ambiguity_unknown", "aq7-synth-role-ambiguity-unknown-cal-001"),
    ("annotation_disagreement", "aq7-synth-annotation-disagreement-cal-001"),
    ("over_segmentation_challenge", "aq7-synth-over-segmentation-challenge-cal-001"),
)
TEST_FIXTURES: tuple[tuple[str, str], ...] = (
    ("drop_at_boundary", "aq7-synth-drop-at-boundary-test-001"),
    ("drop_not_boundary_owner", "aq7-synth-drop-not-boundary-owner-test-001"),
    ("under_segmentation_challenge", "aq7-synth-under-segmentation-challenge-test-001"),
    ("beatgrid_hold", "aq7-synth-beatgrid-hold-test-001"),
)
ALL_FIXTURE_IDS = tuple(fid for _, fid in CALIBRATION_FIXTURES + TEST_FIXTURES)
FIXTURE_ID_RE = re.compile(
    r"^aq7-synth-[a-z0-9-]+-(cal|test)-\d{3}$"
)

_FORBIDDEN_ANALYZER_MODULES = frozenset(
    {
        "structure_v1",
        "arrangement_classifier",
        "section_signals",
        "src.structure_v1",
        "src.arrangement_classifier",
        "src.section_signals",
    }
)


def _matrix_rows() -> list[dict[str, Any]]:
    rows = list(getattr(corpus, "FIXTURE_MATRIX"))
    assert isinstance(rows, (list, tuple))
    return [dict(row) for row in rows]


def _fixture_ids_from_matrix() -> list[str]:
    return [str(row["fixture_id"]) for row in _matrix_rows()]


@pytest.fixture(scope="module")
def aq7_generated_corpus(tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, dict[str, Any]]:
    """Generate the frozen corpus once per module for read-only assertions."""
    work = tmp_path_factory.mktemp("aq7-corpus-shared")
    manifest = corpus.generate_aq7_structure_role_drop_corpus(work, repo_root=REPO_ROOT)
    return work, manifest


def _minimal_valid_gt(*, fixture_id: str = "aq7-synth-simple-clean-cal-001") -> dict[str, Any]:
    """Minimal schema-valid GT payload for negative mutation cases."""
    return {
        "document_type": DOCUMENT_TYPE,
        "corpus_id": CORPUS_ID,
        "corpus_version": CORPUS_VERSION,
        "generator_id": GENERATOR_ID,
        "generator_seed": GENERATOR_SEED,
        "fixture_id": fixture_id,
        "sample_rate": SAMPLE_RATE,
        "split": "CALIBRATION",
        "label_source": LABEL_SOURCE,
        "family": "simple_clean",
        "beatgrid_provenance": {
            "status": "authored_synthetic",
            "note": "generator-authored synthetic grid; analyzer BeatGrid is never GT",
        },
        "boundaries": [
            {
                "boundary_id": "b1",
                "bar_index": 16,
                "time_sec": None,
                "annotation_status": "single_source",
            }
        ],
        "sections": [
            {
                "section_id": "s0",
                "start_bar": 0,
                "end_bar": 16,
                "role": "intro",
                "annotation_status": "single_source",
            },
            {
                "section_id": "s1",
                "start_bar": 16,
                "end_bar": 32,
                "role": "groove",
                "annotation_status": "single_source",
            },
        ],
        "drop_events": [],
        "drop_events_complete": True,
        "plane_status": {
            "aq7.boundary": "single_source",
            "aq7.role": "single_source",
            "aq7.drop_event": "single_source",
        },
        "join_key": {
            "analysis_eval_record_id": fixture_id,
            "note": "fixture_id is the portable #956 record_id join key; no host paths",
        },
    }


def _minimal_valid_manifest() -> dict[str, Any]:
    fixtures = []
    for family, fixture_id in CALIBRATION_FIXTURES:
        fixtures.append(
            {
                "fixture_id": fixture_id,
                "family": family,
                "split": "CALIBRATION",
                "join_key": {"analysis_eval_record_id": fixture_id},
            }
        )
    for family, fixture_id in TEST_FIXTURES:
        fixtures.append(
            {
                "fixture_id": fixture_id,
                "family": family,
                "split": "TEST",
                "join_key": {"analysis_eval_record_id": fixture_id},
            }
        )
    return {
        "document_type": DOCUMENT_TYPE,
        "corpus_id": CORPUS_ID,
        "corpus_version": CORPUS_VERSION,
        "generator_id": GENERATOR_ID,
        "generator_seed": GENERATOR_SEED,
        "fixtures": fixtures,
        "support_counts": {
            "split": {"CALIBRATION": 6, "TEST": 4},
            "plane": {
                "aq7.boundary": 10,
                "aq7.role": 10,
                "aq7.drop_event": 10,
            },
        },
    }


def _imported_module_names(module: Any) -> set[str]:
    loaded = module._load() if isinstance(module, _LazyModule) else module
    path = Path(loaded.__file__)
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                names.add(alias.name)
                names.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                names.add(node.module)
                names.add(node.module.split(".")[0])
                if node.module.startswith("src."):
                    names.add(node.module.removeprefix("src."))
            for alias in node.names:
                names.add(alias.name)
    return names


def _load_generated_gt(work_dir: Path, fixture_id: str) -> dict[str, Any]:
    path = work_dir / "gt" / f"{fixture_id}.json"
    assert path.is_file(), f"missing GT sidecar for {fixture_id}"
    return json.loads(path.read_text(encoding="utf-8"))


def _assert_no_private_or_absolute_paths(payload: Any) -> None:
    blob = json.dumps(payload, ensure_ascii=False)
    assert ":" not in blob or not re.search(r"[A-Za-z]:\\\\|[A-Za-z]:/", blob)
    assert "/Users/" not in blob
    assert "/home/" not in blob
    assert "C:\\\\" not in blob
    assert "C:/" not in blob
    for key in ("audio_path", "file_path", "sample_path", "host_path"):
        if isinstance(payload, dict):
            assert key not in payload


# ---------------------------------------------------------------------------
# Proof matrix 1–4 — identity, version, seed/fixture IDs, split membership
# ---------------------------------------------------------------------------


def test_corpus_identity_deterministic() -> None:
    """Proof 1: Corpus identity deterministic."""
    assert schema.CORPUS_ID == CORPUS_ID
    assert schema.DOCUMENT_TYPE == DOCUMENT_TYPE
    assert schema.GENERATOR_ID == GENERATOR_ID
    assert schema.GENERATOR_SEED == GENERATOR_SEED
    assert corpus.CORPUS_ID == CORPUS_ID
    assert corpus.DOCUMENT_TYPE == DOCUMENT_TYPE
    assert corpus.GENERATOR_ID == GENERATOR_ID
    assert corpus.GENERATOR_SEED == GENERATOR_SEED


def test_corpus_version_explicit() -> None:
    """Proof 2: Corpus version explicit."""
    assert schema.CORPUS_VERSION == CORPUS_VERSION
    assert corpus.CORPUS_VERSION == CORPUS_VERSION
    assert isinstance(schema.CORPUS_VERSION, str)
    assert schema.CORPUS_VERSION.count(".") == 2


def test_same_seed_config_yields_same_fixture_ids() -> None:
    """Proof 3: same seed/config → same fixture IDs."""
    assert schema.GENERATOR_SEED == GENERATOR_SEED
    matrix_ids = _fixture_ids_from_matrix()
    assert matrix_ids == list(ALL_FIXTURE_IDS)
    assert len(matrix_ids) == len(set(matrix_ids))
    for fixture_id in matrix_ids:
        assert FIXTURE_ID_RE.match(fixture_id)


def test_calibration_test_membership_deterministic() -> None:
    """Proof 4: CALIBRATION/TEST membership deterministic."""
    assert set(schema.SPLITS) == SPLITS
    assert set(corpus.SPLITS) == SPLITS
    rows = _matrix_rows()
    assert len(rows) == 10
    cal = [r for r in rows if r["split"] == "CALIBRATION"]
    test = [r for r in rows if r["split"] == "TEST"]
    assert len(cal) == 6
    assert len(test) == 4
    assert {r["fixture_id"] for r in cal} == {fid for _, fid in CALIBRATION_FIXTURES}
    assert {r["fixture_id"] for r in test} == {fid for _, fid in TEST_FIXTURES}
    for family, fixture_id in CALIBRATION_FIXTURES + TEST_FIXTURES:
        row = next(r for r in rows if r["fixture_id"] == fixture_id)
        assert row["family"] == family


# ---------------------------------------------------------------------------
# Proof matrix 5 — leakage
# ---------------------------------------------------------------------------


def test_no_fixture_leakage_across_splits(tmp_path: Path) -> None:
    """Proof 5: no fixture leakage."""
    rows = _matrix_rows()
    cal_ids = {r["fixture_id"] for r in rows if r["split"] == "CALIBRATION"}
    test_ids = {r["fixture_id"] for r in rows if r["split"] == "TEST"}
    assert cal_ids.isdisjoint(test_ids)
    assert cal_ids | test_ids == set(ALL_FIXTURE_IDS)

    work_a = tmp_path / "corpus-a"
    work_b = tmp_path / "corpus-b"
    manifest_a = corpus.generate_aq7_structure_role_drop_corpus(work_a, repo_root=REPO_ROOT)
    manifest_b = corpus.generate_aq7_structure_role_drop_corpus(work_b, repo_root=REPO_ROOT)

    clips_a = {c["fixture_id"]: c for c in manifest_a["fixtures"]}
    clips_b = {c["fixture_id"]: c for c in manifest_b["fixtures"]}
    assert clips_a.keys() == clips_b.keys() == set(ALL_FIXTURE_IDS)
    cal_gen = {fid for fid, c in clips_a.items() if c["split"] == "CALIBRATION"}
    test_gen = {fid for fid, c in clips_a.items() if c["split"] == "TEST"}
    assert cal_gen.isdisjoint(test_gen)

    # No copy-with-offset / seed-twin leakage: WAV bytes unique across fixtures.
    wav_hashes = {
        fid: (work_a / "audio" / f"{fid}.wav").read_bytes() for fid in clips_a
    }
    assert len(set(wav_hashes.values())) == len(wav_hashes)

    # Structural topology uniqueness (independent of fixture_id dither).
    structural = []
    for row in rows:
        gt = _load_generated_gt(work_a, str(row["fixture_id"]))
        structural.append(
            (
                gt["family"],
                gt["split"],
                tuple((b["bar_index"], b["boundary_id"]) for b in gt["boundaries"]),
                tuple(
                    (s["start_bar"], s["end_bar"], s["role"]) for s in gt["sections"]
                ),
                tuple(
                    (e["boundary_id"], e["bar_index"]) for e in gt["drop_events"]
                ),
            )
        )
    assert len(set(structural)) == len(structural)


# ---------------------------------------------------------------------------
# Proof matrix 6–9 — three-plane structural separation
# ---------------------------------------------------------------------------


def test_boundary_plane_structurally_separate() -> None:
    """Proof 6: boundary plane structurally separate."""
    payload = _minimal_valid_gt()
    schema.validate_aq7_fixture_gt(payload)
    assert "boundaries" in payload
    assert "sections" in payload
    assert "drop_events" in payload
    assert set(payload["plane_status"]) == set(PLANE_TOKENS)
    # Boundary plane owns bar identities; roles/events reference, not redefine.
    boundary_ids = {b["boundary_id"] for b in payload["boundaries"]}
    assert boundary_ids == {"b1"}
    assert all("role" not in b for b in payload["boundaries"])
    assert all("event_type" not in b for b in payload["boundaries"])


def test_roles_cannot_add_boundaries() -> None:
    """Proof 7: roles cannot add boundaries."""
    payload = _minimal_valid_gt()
    # Section extents must align to existing boundary-derived cuts only.
    schema.validate_aq7_fixture_gt(payload)
    poisoned = copy.deepcopy(payload)
    poisoned["sections"].append(
        {
            "section_id": "s_role_boundary",
            "start_bar": 0,
            "end_bar": 8,
            "role": "build",
            "annotation_status": "single_source",
            "boundaries": [{"boundary_id": "role-made", "bar_index": 8}],
        }
    )
    with pytest.raises(ValueError, match="role|boundary"):
        schema.validate_aq7_fixture_gt(poisoned)


def test_drop_plane_structurally_separate() -> None:
    """Proof 8: drop plane structurally separate."""
    payload = _minimal_valid_gt()
    payload["drop_events"] = [
        {
            "event_id": "e1",
            "event_type": "drop_onset",
            "boundary_id": "b1",
            "bar_index": 16,
            "annotation_status": "single_source",
        }
    ]
    payload["drop_events_complete"] = True
    schema.validate_aq7_fixture_gt(payload)
    assert payload["drop_events"][0]["event_type"] == "drop_onset"
    assert "boundaries" not in payload["drop_events"][0]
    assert payload["plane_status"]["aq7.drop_event"] in ANNOTATION_STATUSES


def test_drop_event_cannot_add_boundary() -> None:
    """Proof 9: drop event cannot add boundary."""
    payload = _minimal_valid_gt()
    poisoned = copy.deepcopy(payload)
    poisoned["drop_events"] = [
        {
            "event_id": "e_bad",
            "event_type": "drop_onset",
            "boundary_id": "invented",
            "bar_index": 24,
            "annotation_status": "single_source",
            "boundary": {"boundary_id": "invented", "bar_index": 24},
        }
    ]
    poisoned["drop_events_complete"] = True
    with pytest.raises(ValueError, match="drop|boundary"):
        schema.validate_aq7_fixture_gt(poisoned)


# ---------------------------------------------------------------------------
# Proof matrix 10–14 — fixture family coverage
# ---------------------------------------------------------------------------


def test_unknown_role_valid(aq7_generated_corpus: tuple[Path, dict[str, Any]]) -> None:
    """Proof 10: unknown role valid."""
    assert set(schema.ROLE_VOCABULARY) == set(ROLE_VOCABULARY)
    assert "unknown" in schema.ROLE_VOCABULARY
    payload = _minimal_valid_gt(
        fixture_id="aq7-synth-role-ambiguity-unknown-cal-001"
    )
    payload["family"] = "role_ambiguity_unknown"
    payload["sections"][1]["role"] = "unknown"
    schema.validate_aq7_fixture_gt(payload)

    work, manifest = aq7_generated_corpus
    unknown_id = "aq7-synth-role-ambiguity-unknown-cal-001"
    assert unknown_id in {f["fixture_id"] for f in manifest["fixtures"]}
    gt = _load_generated_gt(work, unknown_id)
    roles = {s["role"] for s in gt["sections"]}
    assert "unknown" in roles


def test_near_boundary_tolerance_fixture_exists(
    aq7_generated_corpus: tuple[Path, dict[str, Any]],
) -> None:
    """Proof 11: near-boundary tolerance fixture exists."""
    assert ("near_boundary_tolerance", "aq7-synth-near-boundary-tolerance-cal-001") in (
        CALIBRATION_FIXTURES
    )
    work, manifest = aq7_generated_corpus
    fid = "aq7-synth-near-boundary-tolerance-cal-001"
    row = next(f for f in manifest["fixtures"] if f["fixture_id"] == fid)
    assert row["family"] == "near_boundary_tolerance"
    assert row["split"] == "CALIBRATION"
    gt = _load_generated_gt(work, fid)
    assert gt["family"] == "near_boundary_tolerance"
    assert gt["boundaries"]


def test_annotation_disagreement_fixture_exists(
    aq7_generated_corpus: tuple[Path, dict[str, Any]],
) -> None:
    """Proof 12: annotation-disagreement fixture exists."""
    work, manifest = aq7_generated_corpus
    fid = "aq7-synth-annotation-disagreement-cal-001"
    row = next(f for f in manifest["fixtures"] if f["fixture_id"] == fid)
    assert row["family"] == "annotation_disagreement"
    gt = _load_generated_gt(work, fid)
    statuses = {gt["plane_status"][p] for p in PLANE_TOKENS}
    locus_statuses = {
        *(b.get("annotation_status") for b in gt["boundaries"]),
        *(s.get("annotation_status") for s in gt["sections"]),
        *(e.get("annotation_status") for e in gt.get("drop_events", [])),
    }
    assert "ambiguous" in statuses | locus_statuses


def test_over_segmentation_challenge_exists(
    aq7_generated_corpus: tuple[Path, dict[str, Any]],
) -> None:
    """Proof 13: over-segmentation challenge exists."""
    work, manifest = aq7_generated_corpus
    fid = "aq7-synth-over-segmentation-challenge-cal-001"
    row = next(f for f in manifest["fixtures"] if f["fixture_id"] == fid)
    assert row["family"] == "over_segmentation_challenge"
    assert row["split"] == "CALIBRATION"
    gt = _load_generated_gt(work, fid)
    assert gt["family"] == "over_segmentation_challenge"
    assert len(gt["boundaries"]) >= 1


def test_under_segmentation_challenge_exists(
    aq7_generated_corpus: tuple[Path, dict[str, Any]],
) -> None:
    """Proof 14: under-segmentation challenge exists."""
    work, manifest = aq7_generated_corpus
    fid = "aq7-synth-under-segmentation-challenge-test-001"
    row = next(f for f in manifest["fixtures"] if f["fixture_id"] == fid)
    assert row["family"] == "under_segmentation_challenge"
    assert row["split"] == "TEST"
    gt = _load_generated_gt(work, fid)
    assert gt["family"] == "under_segmentation_challenge"
    assert isinstance(gt["boundaries"], list)
    # Dense reference so a coarse one-/two-cut prediction under-segments.
    assert len(gt["boundaries"]) >= 3


# ---------------------------------------------------------------------------
# Proof matrix 15–16 — BeatGrid provenance / HOLD
# ---------------------------------------------------------------------------


def test_beatgrid_provenance_present(
    aq7_generated_corpus: tuple[Path, dict[str, Any]],
) -> None:
    """Proof 15: BeatGrid provenance present."""
    work, manifest = aq7_generated_corpus
    for fixture in manifest["fixtures"]:
        gt = _load_generated_gt(work, fixture["fixture_id"])
        prov = gt["beatgrid_provenance"]
        assert isinstance(prov, dict)
        assert prov["status"] in BEATGRID_PROVENANCE_STATUSES
        schema.validate_aq7_fixture_gt(gt)


def test_missing_beatgrid_hold_case_representable(
    aq7_generated_corpus: tuple[Path, dict[str, Any]],
) -> None:
    """Proof 16: missing BeatGrid/HOLD case representable."""
    work, manifest = aq7_generated_corpus
    fid = "aq7-synth-beatgrid-hold-test-001"
    row = next(f for f in manifest["fixtures"] if f["fixture_id"] == fid)
    assert row["family"] == "beatgrid_hold"
    assert row["split"] == "TEST"
    gt = _load_generated_gt(work, fid)
    assert gt["beatgrid_provenance"]["status"] in {"missing", "insufficient"}
    # HOLD path must not fabricate trustworthy seconds.
    for boundary in gt["boundaries"]:
        assert boundary.get("time_sec") is None


# ---------------------------------------------------------------------------
# Proof matrix 17 — analyzer independence
# ---------------------------------------------------------------------------


def test_gt_does_not_require_current_analyzer(
    aq7_generated_corpus: tuple[Path, dict[str, Any]],
) -> None:
    """Proof 17: GT does not require current analyzer."""
    for mod in (schema, corpus):
        imported = _imported_module_names(mod)
        assert imported.isdisjoint(_FORBIDDEN_ANALYZER_MODULES), (
            f"{mod.__name__} imports analyzer modules: "
            f"{sorted(imported & _FORBIDDEN_ANALYZER_MODULES)}"
        )

    work, manifest = aq7_generated_corpus
    for fixture in manifest["fixtures"]:
        gt = _load_generated_gt(work, fixture["fixture_id"])
        assert gt["label_source"] == LABEL_SOURCE
        assert gt.get("analyzer_source") is None
        assert "structure_v1" not in json.dumps(gt)
        assert "arrangement_classifier" not in json.dumps(gt)


def test_corpus_modules_do_not_import_structure_analyzers() -> None:
    """Analyzer independence: schema/corpus must not import StructureV1 stack."""
    for mod in (schema, corpus):
        imported = _imported_module_names(mod)
        for forbidden in (
            "structure_v1",
            "arrangement_classifier",
            "section_signals",
        ):
            assert forbidden not in imported
            assert f"src.{forbidden}" not in imported


# ---------------------------------------------------------------------------
# Proof matrix 18–19 — privacy / no committed WAV
# ---------------------------------------------------------------------------


def test_no_private_or_absolute_paths_in_artifacts(
    aq7_generated_corpus: tuple[Path, dict[str, Any]],
) -> None:
    """Proof 18: no private/absolute paths."""
    work, manifest = aq7_generated_corpus
    _assert_no_private_or_absolute_paths(manifest)
    for fixture in manifest["fixtures"]:
        _assert_no_private_or_absolute_paths(fixture)
        gt = _load_generated_gt(work, fixture["fixture_id"])
        _assert_no_private_or_absolute_paths(gt)
        schema.validate_aq7_fixture_gt(gt)


def test_no_committed_wav_dependency() -> None:
    """Proof 19: no committed WAV dependency."""
    tracked_audio: list[Path] = []
    for pattern in ("*.wav", "*.aif", "*.aiff", "*.flac", "*.mp3", "*.ogg"):
        tracked_audio.extend(REPO_ROOT.rglob(pattern))
    aq7_named = [
        path
        for path in tracked_audio
        if "aq7" in path.name.lower()
        or "structure-role-drop" in str(path).lower().replace("\\", "/")
        or "structure_role_drop" in str(path).lower().replace("\\", "/")
    ]
    assert aq7_named == []
    for base in (REPO_ROOT / "docs" / "benchmarks", REPO_ROOT / "src"):
        assert list(base.rglob("*.wav")) == []


# ---------------------------------------------------------------------------
# Proof matrix 20 — consumer schema readiness + determinism/layout
# ---------------------------------------------------------------------------


def test_schema_sufficient_for_later_aq7_baseline_consumer(
    aq7_generated_corpus: tuple[Path, dict[str, Any]],
) -> None:
    """Proof 20: schema sufficient for later AQ7 baseline consumer."""
    assert schema.BOUNDARY_MATCH_TOLERANCE_BARS == 1
    assert schema.SAMPLE_RATE == SAMPLE_RATE
    assert set(schema.ROLE_VOCABULARY) == set(ROLE_VOCABULARY)

    work, manifest = aq7_generated_corpus
    schema.validate_aq7_manifest(manifest)

    required_manifest = {
        "document_type",
        "corpus_id",
        "corpus_version",
        "generator_id",
        "generator_seed",
        "fixtures",
    }
    assert required_manifest.issubset(manifest)

    required_gt = {
        "document_type",
        "corpus_id",
        "corpus_version",
        "generator_id",
        "generator_seed",
        "fixture_id",
        "sample_rate",
        "split",
        "label_source",
        "family",
        "beatgrid_provenance",
        "boundaries",
        "sections",
        "drop_events",
        "drop_events_complete",
        "plane_status",
        "join_key",
    }
    for fixture in manifest["fixtures"]:
        gt = _load_generated_gt(work, fixture["fixture_id"])
        assert required_gt.issubset(gt)
        assert gt["join_key"]["analysis_eval_record_id"] == gt["fixture_id"]
        assert set(gt["plane_status"]) == set(PLANE_TOKENS)
        assert gt["drop_events_complete"] is True
        assert isinstance(gt["drop_events"], list)
        for section in gt["sections"]:
            assert section["role"] in ROLE_VOCABULARY
            assert section["end_bar"] > section["start_bar"]
        for event in gt["drop_events"]:
            assert event["event_type"] == "drop_onset"
            assert event["boundary_id"] in {
                b["boundary_id"] for b in gt["boundaries"]
            }
        schema.validate_aq7_fixture_gt(gt)
        # Runtime audio exists outside repo for later baseline consumers.
        assert (work / "audio" / f"{gt['fixture_id']}.wav").is_file()


def test_generate_rejects_work_dir_inside_repo() -> None:
    inside = REPO_ROOT / ".pytest_aq7_structure_role_drop_corpus_should_not_exist"
    with pytest.raises(ValueError, match="outside"):
        corpus.generate_aq7_structure_role_drop_corpus(inside, repo_root=REPO_ROOT)


def test_generate_is_deterministic_across_work_dirs(tmp_path: Path) -> None:
    work_a = tmp_path / "corpus-a"
    work_b = tmp_path / "corpus-b"
    manifest_a = corpus.generate_aq7_structure_role_drop_corpus(work_a, repo_root=REPO_ROOT)
    manifest_b = corpus.generate_aq7_structure_role_drop_corpus(work_b, repo_root=REPO_ROOT)

    assert manifest_a["corpus_id"] == CORPUS_ID
    assert manifest_a["document_type"] == DOCUMENT_TYPE
    assert manifest_a["corpus_version"] == CORPUS_VERSION
    assert manifest_a["generator_id"] == GENERATOR_ID
    assert manifest_a["generator_seed"] == GENERATOR_SEED
    assert {f["fixture_id"] for f in manifest_a["fixtures"]} == {
        f["fixture_id"] for f in manifest_b["fixtures"]
    }

    for fixture_id in ALL_FIXTURE_IDS:
        wav_a = work_a / "audio" / f"{fixture_id}.wav"
        wav_b = work_b / "audio" / f"{fixture_id}.wav"
        gt_a = work_a / "gt" / f"{fixture_id}.json"
        gt_b = work_b / "gt" / f"{fixture_id}.json"
        assert wav_a.read_bytes() == wav_b.read_bytes()
        assert gt_a.read_text(encoding="utf-8") == gt_b.read_text(encoding="utf-8")


def test_load_manifest_helper_roundtrip(
    aq7_generated_corpus: tuple[Path, dict[str, Any]],
) -> None:
    work, generated = aq7_generated_corpus
    loaded = schema.load_aq7_corpus_manifest(work / "manifest.json")
    assert loaded["corpus_id"] == generated["corpus_id"]
    assert {f["fixture_id"] for f in loaded["fixtures"]} == set(ALL_FIXTURE_IDS)
    schema.validate_aq7_manifest(loaded)


def test_reject_fixture_id_outside_frozen_membership() -> None:
    payload = _minimal_valid_gt(fixture_id="aq7-synth-made-up-cal-001")
    payload["family"] = "simple_clean"
    with pytest.raises(ValueError, match="outside frozen corpus membership"):
        schema.validate_aq7_fixture_gt(payload)


# ---------------------------------------------------------------------------
# Additional negative validation cases
# ---------------------------------------------------------------------------


def test_reject_role_refs_nonexistent_section() -> None:
    payload = _minimal_valid_gt()
    poisoned = copy.deepcopy(payload)
    # Role on a section that is not derived from the reference boundary set.
    poisoned["sections"].append(
        {
            "section_id": "s_nonexistent",
            "start_bar": 64,
            "end_bar": 80,
            "role": "outro",
            "annotation_status": "single_source",
        }
    )
    with pytest.raises(ValueError, match="section|boundary"):
        schema.validate_aq7_fixture_gt(poisoned)


def test_reject_drop_refs_nonexistent_boundary() -> None:
    payload = _minimal_valid_gt()
    poisoned = copy.deepcopy(payload)
    poisoned["drop_events"] = [
        {
            "event_id": "e1",
            "event_type": "drop_onset",
            "boundary_id": "does-not-exist",
            "bar_index": 16,
            "annotation_status": "single_source",
        }
    ]
    poisoned["drop_events_complete"] = True
    with pytest.raises(ValueError, match="boundary"):
        schema.validate_aq7_fixture_gt(poisoned)


def test_reject_duplicate_drop_boundary_anchor() -> None:
    payload = _minimal_valid_gt()
    poisoned = copy.deepcopy(payload)
    poisoned["drop_events"] = [
        {
            "event_id": "e1",
            "event_type": "drop_onset",
            "boundary_id": "b1",
            "bar_index": 16,
            "annotation_status": "single_source",
        },
        {
            "event_id": "e2",
            "event_type": "drop_onset",
            "boundary_id": "b1",
            "bar_index": 16,
            "annotation_status": "single_source",
        },
    ]
    poisoned["drop_events_complete"] = True
    with pytest.raises(ValueError, match="duplicate drop event boundary anchor"):
        schema.validate_aq7_fixture_gt(poisoned)


def test_reject_role_tries_to_define_boundary() -> None:
    payload = _minimal_valid_gt()
    poisoned = copy.deepcopy(payload)
    poisoned["sections"][0]["boundary_id"] = "role-created"
    poisoned["sections"][0]["bar_index"] = 8
    with pytest.raises(ValueError, match="role|boundary"):
        schema.validate_aq7_fixture_gt(poisoned)


def test_reject_drop_tries_to_define_boundary() -> None:
    payload = _minimal_valid_gt()
    poisoned = copy.deepcopy(payload)
    poisoned["drop_events"] = [
        {
            "event_id": "e1",
            "event_type": "drop_onset",
            "boundary_id": "b1",
            "bar_index": 16,
            "annotation_status": "single_source",
            "creates_boundary": True,
        }
    ]
    poisoned["drop_events_complete"] = True
    with pytest.raises(ValueError, match="drop|boundary"):
        schema.validate_aq7_fixture_gt(poisoned)


def test_reject_invalid_role() -> None:
    payload = _minimal_valid_gt()
    poisoned = copy.deepcopy(payload)
    poisoned["sections"][0]["role"] = "verse"
    with pytest.raises(ValueError, match="role"):
        schema.validate_aq7_fixture_gt(poisoned)


def test_reject_wrong_split() -> None:
    payload = _minimal_valid_gt()
    poisoned = copy.deepcopy(payload)
    poisoned["split"] = "HOLDOUT"
    with pytest.raises(ValueError, match="split"):
        schema.validate_aq7_fixture_gt(poisoned)


def test_reject_malformed_manifest() -> None:
    good = _minimal_valid_manifest()
    schema.validate_aq7_manifest(good)

    missing_id = copy.deepcopy(good)
    del missing_id["corpus_id"]
    with pytest.raises(ValueError, match="corpus_id|malformed|manifest"):
        schema.validate_aq7_manifest(missing_id)

    bad_count = copy.deepcopy(good)
    bad_count["fixtures"] = bad_count["fixtures"][:3]
    with pytest.raises(ValueError, match="fixture|split|manifest"):
        schema.validate_aq7_manifest(bad_count)

    leaked = copy.deepcopy(good)
    leaked["fixtures"][0]["split"] = "TEST"
    leaked["fixtures"][0]["fixture_id"] = "aq7-synth-simple-clean-cal-001"
    with pytest.raises(ValueError, match="split|leak|fixture"):
        schema.validate_aq7_manifest(leaked)


def test_reject_private_or_absolute_path_in_gt_and_manifest() -> None:
    payload = _minimal_valid_gt()
    poisoned = copy.deepcopy(payload)
    poisoned["audio_path"] = "C:/Users/private/track.wav"
    with pytest.raises(ValueError, match="path|absolute|private"):
        schema.validate_aq7_fixture_gt(poisoned)

    poisoned2 = copy.deepcopy(payload)
    poisoned2["join_key"]["note"] = "/home/owner/secret/sample.wav"
    with pytest.raises(ValueError, match="path|absolute|private"):
        schema.validate_aq7_fixture_gt(poisoned2)

    manifest = _minimal_valid_manifest()
    poisoned_m = copy.deepcopy(manifest)
    poisoned_m["fixtures"][0]["file_path"] = "D:/Libraries/private/loop.wav"
    with pytest.raises(ValueError, match="path|absolute|private"):
        schema.validate_aq7_manifest(poisoned_m)


def test_assert_work_dir_outside_repo_helper() -> None:
    inside = REPO_ROOT / "data"
    with pytest.raises(ValueError, match="outside"):
        corpus.assert_work_dir_outside_repo(inside, REPO_ROOT)
