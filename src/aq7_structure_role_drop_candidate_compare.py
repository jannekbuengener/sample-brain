"""AQ7 structure/role/drop candidate comparison on CALIBRATION (#1028).

Frozen ≤4 thin config adapters over StructureV1 + ArrangementClassifier.
Reuses #1025/#1026 scoring helpers. No production switch / no TEST tuning.
"""

from __future__ import annotations

import argparse
import json
import statistics
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Any, Mapping

from .analysis_eval_artifact import (
    AnalysisEvalArtifactError,
    assert_portable_value,
)
from .aq7_structure_boundary_baseline import (
    DOCUMENT_TYPE as BOUNDARY_BASELINE_DOCUMENT_TYPE,
    CANDIDATE_ID as BOUNDARY_BASELINE_CANDIDATE_ID,
    PLANE_TOKEN as BOUNDARY_PLANE,
    STRUCTURE_SURFACE,
    _predict_fixture as _predict_boundary_fixture,
    aggregate_boundary_splits,
)
from .aq7_structure_role_drop_baseline import (
    ARRANGEMENT_SURFACE,
    BOUNDARY_CONTEXT_CANDIDATE_ID,
    CANDIDATE_ID as ROLE_DROP_BASELINE_CANDIDATE_ID,
    DOCUMENT_TYPE as ROLE_DROP_BASELINE_DOCUMENT_TYPE,
    DROP_PLANE_TOKEN,
    ROLE_PLANE_TOKEN,
    SECTION_SIGNAL_SURFACE,
    _predict_fixture as _predict_role_drop_fixture,
    aggregate_role_drop_splits,
    assert_boundary_geometry_preserved,
    frozen_reference_sections_from_gt,
    reference_boundaries_from_gt,
)
from .aq7_structure_role_drop_corpus import (
    CORPUS_ID,
    CORPUS_VERSION,
    GENERATOR_SEED,
    assert_work_dir_outside_repo,
    generate_aq7_structure_role_drop_corpus,
)
from .aq7_structure_role_drop_schema import load_aq7_corpus_manifest, load_aq7_fixture_gt
from .arrangement_classifier import (
    ArrangementClassifier,
    ArrangementClassifierConfig,
    DEFAULT_ARRANGEMENT_CLASSIFIER_CONFIG,
)
from .measurement.stats import percentile
from .structure_v1 import StructureV1Analyzer, StructureV1Config

DOCUMENT_TYPE = "sample-brain.aq7.structure-role-drop-candidate-compare.v1"
SCHEMA_VERSION = "1.0.0"
BASELINE_CANDIDATE_ID = "aq7.baseline.v1"
EXIT_FROZEN = "AQ7_CANDIDATE_COMPARE_CALIBRATION_FROZEN"
EXIT_KEEP_BASELINE = "AQ7_NO_JUSTIFIED_CANDIDATE_KEEP_BASELINE"
EXIT_INCOMPLETE = "AQ7_CANDIDATE_COMPARE_INCOMPLETE"
FEATURE_TOGGLE = "N/A"
PRODUCTION_DEFAULTS_CHANGED = False
SELECTION_PARTITION = "CALIBRATION"
BOUNDARY_SURFACE_POLICY = "frozen_gt_reference_sections"
RECALL_REGRESSION_TOLERANCE = 0.05

_REPO_ROOT_DEFAULT = Path(__file__).resolve().parents[1]

PARTITION_POLICY = {
    "CALIBRATION": "DEVELOPMENT/CALIBRATION",
    "TEST": "TEST/HOLDOUT",
}

BASELINE_STRUCTURE_CONFIG = StructureV1Config()
BASELINE_ARRANGEMENT_CONFIG = DEFAULT_ARRANGEMENT_CLASSIFIER_CONFIG


class Aq7CandidateCompareError(ValueError):
    """Controlled, fail-closed input or identity error for this compare runner."""


@dataclass(frozen=True)
class Aq7Candidate:
    candidate_id: str
    hypothesis_ids: tuple[str, ...]
    primary_plane: str
    structure_config: StructureV1Config
    arrangement_config: ArrangementClassifierConfig
    description: str
    is_baseline: bool = False


AQ7_CANDIDATES: tuple[Aq7Candidate, ...] = (
    Aq7Candidate(
        candidate_id=BASELINE_CANDIDATE_ID,
        hypothesis_ids=(),
        primary_plane="multi",
        structure_config=BASELINE_STRUCTURE_CONFIG,
        arrangement_config=BASELINE_ARRANGEMENT_CONFIG,
        description=(
            "Current AQ7 baseline path: StructureV1 defaults + ArrangementClassifier "
            "defaults (matches #1025/#1026 surfaces)."
        ),
        is_baseline=True,
    ),
    Aq7Candidate(
        candidate_id="boundary.min_distance.4",
        hypothesis_ids=("H-AQ7-1027-01",),
        primary_plane=BOUNDARY_PLANE,
        structure_config=replace(BASELINE_STRUCTURE_CONFIG, min_boundary_distance_bars=4),
        arrangement_config=BASELINE_ARRANGEMENT_CONFIG,
        description=(
            "Thin StructureV1 adapter for H-AQ7-1027-01: raise "
            "min_boundary_distance_bars 2→4 to reduce over-segmentation extras "
            "(arrangement knobs unchanged)."
        ),
    ),
    Aq7Candidate(
        candidate_id="role.unknown_margin.0.03",
        hypothesis_ids=("H-AQ7-1027-02",),
        primary_plane=ROLE_PLANE_TOKEN,
        structure_config=BASELINE_STRUCTURE_CONFIG,
        arrangement_config=replace(
            BASELINE_ARRANGEMENT_CONFIG, unknown_min_margin=0.03
        ),
        description=(
            "Thin ArrangementClassifier adapter for H-AQ7-1027-02: relax unknown "
            "score-separation margin 0.05→0.03 to recover intro→unknown abstentions "
            "(StructureV1 + drop threshold unchanged)."
        ),
    ),
    Aq7Candidate(
        candidate_id="drop.onset_thresh.0.80",
        hypothesis_ids=("H-AQ7-1027-05",),
        primary_plane=DROP_PLANE_TOKEN,
        structure_config=BASELINE_STRUCTURE_CONFIG,
        arrangement_config=replace(
            BASELINE_ARRANGEMENT_CONFIG, drop_onset_threshold=0.80
        ),
        description=(
            "Thin ArrangementClassifier adapter for H-AQ7-1027-05: raise "
            "drop_onset_threshold 0.65→0.80 to suppress empty-ref false drops "
            "(StructureV1 + role unknown knobs unchanged)."
        ),
    ),
)

SHORTLIST_NOT_SELECTED = (
    {
        "hypothesis_id": "H-AQ7-1027-03",
        "reason": (
            "CAL support=2 thin; requires role-weight surgery overlapping the "
            "unknown-margin adapter; deferred from this ≤4 bake-off."
        ),
    },
    {
        "hypothesis_id": "H-AQ7-1027-04",
        "reason": (
            "CAL support=2; overlapping unknown-path with H-AQ7-1027-02; not a "
            "separate bake-off identity in this slice."
        ),
    },
)


def list_aq7_candidates() -> list[Aq7Candidate]:
    return list(AQ7_CANDIDATES)


def candidate_by_id(candidate_id: str) -> Aq7Candidate:
    for candidate in AQ7_CANDIDATES:
        if candidate.candidate_id == candidate_id:
            return candidate
    raise Aq7CandidateCompareError(f"unknown aq7 candidate_id: {candidate_id}")


def candidate_public(candidate: Aq7Candidate) -> dict[str, Any]:
    return {
        "candidate_id": candidate.candidate_id,
        "hypothesis_ids": list(candidate.hypothesis_ids),
        "primary_plane": candidate.primary_plane,
        "is_baseline": candidate.is_baseline,
        "structure_config": asdict(candidate.structure_config),
        "arrangement_config": asdict(candidate.arrangement_config),
        "boundary_surface_policy": BOUNDARY_SURFACE_POLICY,
        "description": candidate.description,
    }


def assert_portable_compare_payload(payload: Any) -> None:
    try:
        assert_portable_value(payload, field="aq7.structure_role_drop_candidate_compare")
    except AnalysisEvalArtifactError as exc:
        raise ValueError(str(exc)) from exc


def _assert_output_outside_repo(out: Path, root: Path) -> None:
    assert_work_dir_outside_repo(out.parent if out.parent != out else out, root)
    try:
        out.resolve().relative_to(root.resolve())
    except ValueError:
        return
    raise ValueError(f"output path must be outside repo: {out.resolve()}")


def _safe_num(value: Any) -> float | None:
    if value is None:
        return None
    return float(value)


def _improved(new: float | None, old: float | None, *, eps: float = 1e-12) -> bool:
    if new is None or old is None:
        return False
    return new > old + eps


def _reduced(new: float | None, old: float | None, *, eps: float = 1e-12) -> bool:
    if new is None or old is None:
        return False
    return new < old - eps


def _not_regressed(
    new: float | None,
    old: float | None,
    *,
    tolerance: float = RECALL_REGRESSION_TOLERANCE,
) -> bool:
    if old is None:
        return True
    if new is None:
        return False
    return new >= old - tolerance


def hard_case_deltas(
    *,
    baseline_cal: Mapping[str, Any],
    candidate_cal: Mapping[str, Any],
) -> dict[str, Any]:
    """Portable CALIBRATION hard-case deltas across separate planes."""
    b_bound = ((baseline_cal.get(BOUNDARY_PLANE) or {}).get("metrics")) or {}
    c_bound = ((candidate_cal.get(BOUNDARY_PLANE) or {}).get("metrics")) or {}
    b_role = baseline_cal.get(ROLE_PLANE_TOKEN) or {}
    c_role = candidate_cal.get(ROLE_PLANE_TOKEN) or {}
    b_drop = baseline_cal.get(DROP_PLANE_TOKEN) or {}
    c_drop = candidate_cal.get(DROP_PLANE_TOKEN) or {}
    b_intro = ((b_role.get("per_role") or {}).get("intro")) or {}
    c_intro = ((c_role.get("per_role") or {}).get("intro")) or {}
    return {
        "partition": SELECTION_PARTITION,
        "aq7.boundary": {
            "precision_1bar_delta": _delta(
                c_bound.get("precision_1bar"), b_bound.get("precision_1bar")
            ),
            "recall_1bar_delta": _delta(
                c_bound.get("recall_1bar"), b_bound.get("recall_1bar")
            ),
            "extra_rate_delta": _delta(
                c_bound.get("extra_rate"), b_bound.get("extra_rate")
            ),
            "over_segmentation_rate_delta": _delta(
                c_bound.get("over_segmentation_rate"),
                b_bound.get("over_segmentation_rate"),
            ),
            "false_positive_count_delta": _int_delta(
                c_bound.get("false_positive_count"), b_bound.get("false_positive_count")
            ),
        },
        "aq7.role": {
            "macro_f1_delta": _delta(c_role.get("macro_f1"), b_role.get("macro_f1")),
            "unknown_rate_delta": _delta(
                c_role.get("unknown_rate"), b_role.get("unknown_rate")
            ),
            "intro_recall_delta": _delta(c_intro.get("recall"), b_intro.get("recall")),
            "intro_f1_delta": _delta(c_intro.get("f1"), b_intro.get("f1")),
        },
        "aq7.drop_event": {
            "f1_1bar_delta": _delta(c_drop.get("f1_1bar"), b_drop.get("f1_1bar")),
            "matched_count_delta": _int_delta(
                c_drop.get("matched_count"), b_drop.get("matched_count")
            ),
            "false_positive_count_delta": _int_delta(
                c_drop.get("false_positive_count"), b_drop.get("false_positive_count")
            ),
            "missed_count_delta": _int_delta(
                c_drop.get("missed_count"), b_drop.get("missed_count")
            ),
        },
    }


def _delta(new: Any, old: Any) -> float | None:
    n = _safe_num(new)
    o = _safe_num(old)
    if n is None or o is None:
        return None
    return n - o


def _int_delta(new: Any, old: Any) -> int | None:
    if new is None or old is None:
        return None
    return int(new) - int(old)


def candidate_justified_on_calibration(
    candidate: Aq7Candidate,
    *,
    baseline_cal: Mapping[str, Any],
    candidate_cal: Mapping[str, Any],
) -> dict[str, Any]:
    """CALIBRATION-only justification against #1027 falsifiers (no TEST feedback)."""
    if candidate.is_baseline:
        return {
            "justified": False,
            "reason": "baseline is the retention anchor, not a competing candidate",
            "primary_plane": candidate.primary_plane,
        }

    if candidate.primary_plane == BOUNDARY_PLANE:
        bm = ((baseline_cal.get(BOUNDARY_PLANE) or {}).get("metrics")) or {}
        cm = ((candidate_cal.get(BOUNDARY_PLANE) or {}).get("metrics")) or {}
        recall_ok = _not_regressed(cm.get("recall_1bar"), bm.get("recall_1bar"))
        target_hit = (
            _improved(cm.get("precision_1bar"), bm.get("precision_1bar"))
            or _reduced(cm.get("extra_rate"), bm.get("extra_rate"))
            or _reduced(
                cm.get("over_segmentation_rate"), bm.get("over_segmentation_rate")
            )
            or (
                (cm.get("false_positive_count") is not None)
                and (bm.get("false_positive_count") is not None)
                and int(cm["false_positive_count"]) < int(bm["false_positive_count"])
            )
        )
        justified = bool(recall_ok and target_hit)
        return {
            "justified": justified,
            "reason": (
                "boundary P@1bar / extra / over-seg improved without unacceptable "
                "recall regression"
                if justified
                else "no CAL boundary target improvement (or recall regressed)"
            ),
            "primary_plane": BOUNDARY_PLANE,
            "recall_ok": recall_ok,
            "target_hit": target_hit,
        }

    if candidate.primary_plane == ROLE_PLANE_TOKEN:
        br = baseline_cal.get(ROLE_PLANE_TOKEN) or {}
        cr = candidate_cal.get(ROLE_PLANE_TOKEN) or {}
        b_intro = ((br.get("per_role") or {}).get("intro")) or {}
        c_intro = ((cr.get("per_role") or {}).get("intro")) or {}
        target_hit = (
            _improved(cr.get("macro_f1"), br.get("macro_f1"))
            or _improved(c_intro.get("recall"), b_intro.get("recall"))
            or _improved(c_intro.get("f1"), b_intro.get("f1"))
        )
        unknown_ok = _not_regressed(
            # unknown_reference_recall should not collapse; higher is better
            cr.get("unknown_reference_recall"),
            br.get("unknown_reference_recall"),
            tolerance=0.25,
        )
        justified = bool(target_hit and unknown_ok)
        return {
            "justified": justified,
            "reason": (
                "role macro-F1 / intro recall improved without unknown-honesty collapse"
                if justified
                else "no CAL role target improvement (or unknown honesty regressed)"
            ),
            "primary_plane": ROLE_PLANE_TOKEN,
            "target_hit": target_hit,
            "unknown_ok": unknown_ok,
        }

    if candidate.primary_plane == DROP_PLANE_TOKEN:
        bd = baseline_cal.get(DROP_PLANE_TOKEN) or {}
        cd = candidate_cal.get(DROP_PLANE_TOKEN) or {}
        # #1027 falsifier: FP reduction alone with F1 still 0 is NOT acceptance.
        f1_up = _improved(cd.get("f1_1bar"), bd.get("f1_1bar"))
        tp_up = (
            cd.get("matched_count") is not None
            and bd.get("matched_count") is not None
            and int(cd["matched_count"]) > int(bd["matched_count"])
        )
        justified = bool(f1_up or tp_up)
        return {
            "justified": justified,
            "reason": (
                "drop F1 or TP improved on CALIBRATION"
                if justified
                else (
                    "no CAL drop F1/TP gain (FP-only reduction is insufficient per "
                    "H-AQ7-1027-05 falsifier)"
                )
            ),
            "primary_plane": DROP_PLANE_TOKEN,
            "f1_up": f1_up,
            "tp_up": tp_up,
            "false_positive_reduced": (
                cd.get("false_positive_count") is not None
                and bd.get("false_positive_count") is not None
                and int(cd["false_positive_count"]) < int(bd["false_positive_count"])
            ),
        }

    return {
        "justified": False,
        "reason": f"unsupported primary_plane: {candidate.primary_plane}",
        "primary_plane": candidate.primary_plane,
    }


def _primary_score(
    candidate: Aq7Candidate, *, baseline_cal: Mapping[str, Any], candidate_cal: Mapping[str, Any]
) -> float:
    """Deterministic ranking key among justified candidates (higher is better)."""
    if candidate.primary_plane == BOUNDARY_PLANE:
        bm = ((baseline_cal.get(BOUNDARY_PLANE) or {}).get("metrics")) or {}
        cm = ((candidate_cal.get(BOUNDARY_PLANE) or {}).get("metrics")) or {}
        return float(
            (_delta(cm.get("precision_1bar"), bm.get("precision_1bar")) or 0.0)
            + (-(_delta(cm.get("extra_rate"), bm.get("extra_rate")) or 0.0))
        )
    if candidate.primary_plane == ROLE_PLANE_TOKEN:
        br = baseline_cal.get(ROLE_PLANE_TOKEN) or {}
        cr = candidate_cal.get(ROLE_PLANE_TOKEN) or {}
        return float(_delta(cr.get("macro_f1"), br.get("macro_f1")) or 0.0)
    if candidate.primary_plane == DROP_PLANE_TOKEN:
        bd = baseline_cal.get(DROP_PLANE_TOKEN) or {}
        cd = candidate_cal.get(DROP_PLANE_TOKEN) or {}
        return float(_delta(cd.get("f1_1bar"), bd.get("f1_1bar")) or 0.0)
    return 0.0


def decide_calibration_freeze(
    *,
    candidates: list[Aq7Candidate],
    calibration_by_id: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    """Freeze winner or baseline retention using CALIBRATION evidence only."""
    baseline = next(c for c in candidates if c.is_baseline)
    baseline_cal = calibration_by_id[baseline.candidate_id]
    justified_rows: list[dict[str, Any]] = []
    for candidate in candidates:
        verdict = candidate_justified_on_calibration(
            candidate,
            baseline_cal=baseline_cal,
            candidate_cal=calibration_by_id[candidate.candidate_id],
        )
        row = {
            "candidate_id": candidate.candidate_id,
            **verdict,
            "primary_score": (
                None
                if candidate.is_baseline
                else _primary_score(
                    candidate,
                    baseline_cal=baseline_cal,
                    candidate_cal=calibration_by_id[candidate.candidate_id],
                )
            ),
        }
        justified_rows.append(row)

    winners = [r for r in justified_rows if r.get("justified")]
    if not winners:
        return {
            "exit_token": EXIT_KEEP_BASELINE,
            "selection_partition": SELECTION_PARTITION,
            "test_used_for_selection": False,
            "frozen_outcome": "baseline_retention",
            "frozen_candidate_id": baseline.candidate_id,
            "frozen_config": candidate_public(baseline),
            "justification_rows": justified_rows,
            "decision_note": (
                "No non-baseline candidate met CALIBRATION justification rules; "
                "retain aq7.baseline.v1 before TEST/HOLDOUT (#1030)."
            ),
        }

    winners.sort(
        key=lambda r: (
            -float(r["primary_score"] or 0.0),
            str(r["candidate_id"]),
        )
    )
    winner_id = str(winners[0]["candidate_id"])
    winner = candidate_by_id(winner_id)
    return {
        "exit_token": EXIT_FROZEN,
        "selection_partition": SELECTION_PARTITION,
        "test_used_for_selection": False,
        "frozen_outcome": "candidate_frozen",
        "frozen_candidate_id": winner.candidate_id,
        "frozen_config": candidate_public(winner),
        "justification_rows": justified_rows,
        "decision_note": (
            f"Frozen {winner.candidate_id} from CALIBRATION-only justification "
            f"for plane {winner.primary_plane}; TEST/HOLDOUT unused for selection."
        ),
    }


def predict_fixture_for_candidate(
    *,
    audio_path: Path,
    gt: Mapping[str, Any],
    candidate: Aq7Candidate,
) -> dict[str, Any]:
    """Score one fixture on all three planes for a declared candidate."""
    boundary_analyzer = StructureV1Analyzer(candidate.structure_config)
    boundary_row = _predict_boundary_fixture(
        audio_path=audio_path, gt=gt, analyzer=boundary_analyzer
    )

    # Role/drop consume frozen GT geometry (#1026). Structure defaults supply
    # bar_features only so role/drop knobs are not confounded by boundary config.
    feature_analyzer = StructureV1Analyzer(BASELINE_STRUCTURE_CONFIG)
    classifier = ArrangementClassifier(candidate.arrangement_config)
    role_drop_row = _predict_role_drop_fixture(
        audio_path=audio_path,
        gt=gt,
        analyzer=feature_analyzer,
        classifier=classifier,
    )

    # Boundary-ownership guard: role/drop path must not invent/move geometry.
    if role_drop_row.get("hold_kind") is None:
        refs_b = reference_boundaries_from_gt(gt)
        refs_s = frozen_reference_sections_from_gt(gt)
        out_b = [
            {"boundary_id": b["boundary_id"], "bar_index": int(b["bar_index"])}
            for b in refs_b
        ]
        out_s = [
            {
                "section_id": s["section_id"],
                "start_bar": int(s["start_bar"]),
                "end_bar": int(s["end_bar"]),
            }
            for s in refs_s
        ]
        assert_boundary_geometry_preserved(refs_b, out_b, refs_s, out_s)

    return {
        "candidate_id": candidate.candidate_id,
        "fixture_id": gt["fixture_id"],
        "split": gt["split"],
        "family": gt.get("family"),
        "boundary": boundary_row,
        "role_drop": role_drop_row,
        "boundary_surface_policy": BOUNDARY_SURFACE_POLICY,
    }


def _runtime_block(boundary_rows: list[dict[str, Any]], role_rows: list[dict[str, Any]]) -> dict[str, Any]:
    times = [
        float(r["runtime_sec"])
        for r in boundary_rows + role_rows
        if r.get("runtime_sec") is not None
    ]
    return {
        "methodology": "docs/benchmarks/ANALYZER_RUNTIME_METHODOLOGY_V1.md",
        "by_reference": True,
        "methodology_v1_compliant": False,
        "diagnostic_only": True,
        "status": "diagnostic" if times else "unknown",
        "track_length_buckets": "HOLD",
        "n_timed_observations": len(times),
        "runtime_sec_median_diagnostic": (
            float(statistics.median(times)) if times else None
        ),
        "runtime_sec_p95_diagnostic": percentile(times, 95) if times else None,
    }


def run_aq7_structure_role_drop_candidate_compare(
    *,
    work_dir: Path | str,
    output_path: Path | str,
    repo_root: Path | str | None = None,
    regenerate_corpus: bool = True,
) -> dict[str, Any]:
    """Generate corpus, score frozen candidates, freeze CALIBRATION decision."""
    root = Path(repo_root) if repo_root is not None else _REPO_ROOT_DEFAULT
    work = Path(work_dir)
    out = Path(output_path)
    assert_work_dir_outside_repo(work, root)
    _assert_output_outside_repo(out, root)

    _ = regenerate_corpus
    generate_aq7_structure_role_drop_corpus(work, repo_root=root)
    manifest = load_aq7_corpus_manifest(work / "manifest.json")
    if manifest.get("corpus_id") != CORPUS_ID:
        raise Aq7CandidateCompareError("corpus_id mismatch against frozen #1024 identity")
    if manifest.get("corpus_version") != CORPUS_VERSION:
        raise Aq7CandidateCompareError(
            "corpus_version mismatch against frozen #1024 identity"
        )

    candidates = list_aq7_candidates()
    if not (3 <= len(candidates) <= 4):
        raise Aq7CandidateCompareError("candidate registry must contain 3–4 identities")

    candidate_entries: list[dict[str, Any]] = []
    fixture_join_rows: list[dict[str, Any]] = []
    calibration_by_id: dict[str, dict[str, Any]] = {}
    measured_ok = True

    for candidate in candidates:
        boundary_rows: list[dict[str, Any]] = []
        role_drop_rows: list[dict[str, Any]] = []
        for item in manifest["fixtures"]:
            fixture_id = str(item["fixture_id"])
            gt = load_aq7_fixture_gt(work / "gt" / f"{fixture_id}.json")
            audio = work / "audio" / f"{fixture_id}.wav"
            row = predict_fixture_for_candidate(
                audio_path=audio, gt=gt, candidate=candidate
            )
            boundary_rows.append(row["boundary"])
            role_drop_rows.append(row["role_drop"])
            fixture_join_rows.append(
                {
                    "candidate_id": candidate.candidate_id,
                    "fixture_id": fixture_id,
                    "split": gt["split"],
                    "family": gt.get("family"),
                    "boundary_hold_kind": row["boundary"].get("hold_kind"),
                    "role_drop_hold_kind": row["role_drop"].get("hold_kind"),
                    "boundary_precision_1bar": row["boundary"].get("precision_1bar"),
                    "boundary_recall_1bar": row["boundary"].get("recall_1bar"),
                    "boundary_false_positive_count": row["boundary"].get(
                        "false_positive_count"
                    ),
                    "role_macro_f1": (row["role_drop"].get("role") or {}).get(
                        "macro_f1"
                    ),
                    "drop_f1_1bar": (row["role_drop"].get("drop_event") or {}).get(
                        "f1_1bar"
                    ),
                    "drop_false_positive_count": (
                        row["role_drop"].get("drop_event") or {}
                    ).get("false_positive_count"),
                }
            )

        boundary_splits = aggregate_boundary_splits(boundary_rows)
        role_drop_splits = aggregate_role_drop_splits(role_drop_rows)
        splits: dict[str, Any] = {}
        for split_name in ("CALIBRATION", "TEST"):
            splits[split_name] = {
                BOUNDARY_PLANE: (boundary_splits.get(split_name) or {}).get(
                    BOUNDARY_PLANE
                ),
                ROLE_PLANE_TOKEN: (role_drop_splits.get(split_name) or {}).get(
                    ROLE_PLANE_TOKEN
                ),
                DROP_PLANE_TOKEN: (role_drop_splits.get(split_name) or {}).get(
                    DROP_PLANE_TOKEN
                ),
                "n_fixtures": (role_drop_splits.get(split_name) or {}).get(
                    "n_fixtures"
                ),
                "n_beatgrid_hold": (role_drop_splits.get(split_name) or {}).get(
                    "n_beatgrid_hold"
                ),
            }
        calibration_by_id[candidate.candidate_id] = splits["CALIBRATION"]
        if int(splits["CALIBRATION"].get("n_fixtures") or 0) < 1:
            measured_ok = False
        if int(
            ((splits["CALIBRATION"].get(BOUNDARY_PLANE) or {}).get("n_usable") or 0)
        ) < 1:
            measured_ok = False

        baseline_cal = calibration_by_id.get(BASELINE_CANDIDATE_ID)
        deltas = (
            hard_case_deltas(
                baseline_cal=baseline_cal, candidate_cal=splits["CALIBRATION"]
            )
            if baseline_cal is not None
            else None
        )
        candidate_entries.append(
            {
                **candidate_public(candidate),
                "splits": splits,
                "calibration_hard_case_deltas_vs_baseline": deltas,
                "runtime": _runtime_block(boundary_rows, role_drop_rows),
            }
        )

    if not measured_ok:
        decision = {
            "exit_token": EXIT_INCOMPLETE,
            "selection_partition": SELECTION_PARTITION,
            "test_used_for_selection": False,
            "frozen_outcome": "incomplete",
            "frozen_candidate_id": None,
            "frozen_config": None,
            "justification_rows": [],
            "decision_note": "CALIBRATION measurement incomplete; no freeze.",
        }
        exit_token = EXIT_INCOMPLETE
    else:
        decision = decide_calibration_freeze(
            candidates=candidates, calibration_by_id=calibration_by_id
        )
        exit_token = str(decision["exit_token"])

    result: dict[str, Any] = {
        "document_type": DOCUMENT_TYPE,
        "schema_version": SCHEMA_VERSION,
        "corpus_id": CORPUS_ID,
        "corpus_version": CORPUS_VERSION,
        "generator_seed": GENERATOR_SEED,
        "baseline_candidate_id": BASELINE_CANDIDATE_ID,
        "boundary_baseline_candidate_id": BOUNDARY_BASELINE_CANDIDATE_ID,
        "role_drop_baseline_candidate_id": ROLE_DROP_BASELINE_CANDIDATE_ID,
        "boundary_baseline_document_type": BOUNDARY_BASELINE_DOCUMENT_TYPE,
        "role_drop_baseline_document_type": ROLE_DROP_BASELINE_DOCUMENT_TYPE,
        "boundary_reference": BOUNDARY_CONTEXT_CANDIDATE_ID,
        "boundary_surface_policy": BOUNDARY_SURFACE_POLICY,
        "surfaces": {
            BOUNDARY_PLANE: STRUCTURE_SURFACE,
            ROLE_PLANE_TOKEN: ARRANGEMENT_SURFACE,
            DROP_PLANE_TOKEN: ARRANGEMENT_SURFACE,
            "section_signals": SECTION_SIGNAL_SURFACE,
        },
        "partition_policy": dict(PARTITION_POLICY),
        "selection_partition": SELECTION_PARTITION,
        "no_tuning_on_test": True,
        "test_used_for_selection": False,
        "feature_toggle": FEATURE_TOGGLE,
        "production_defaults_changed": PRODUCTION_DEFAULTS_CHANGED,
        "algorithm_changed": False,
        "shortlist_not_selected": list(SHORTLIST_NOT_SELECTED),
        "candidate_count": len(candidate_entries),
        "candidates": candidate_entries,
        "fixtures": fixture_join_rows,
        "decision": decision,
        "exit_status": exit_token,
        "exit_token": exit_token,
        "determinism": {
            "methodology": "docs/ANALYZER_SEMANTIC_DETERMINISM_V1.md",
            "by_reference": True,
            "status": "unknown",
            "note": (
                "Harness is deterministic for identical candidate configs; "
                "repeat-run equality is validated in tests, not claimed from a "
                "single CLI invocation."
            ),
        },
    }
    assert_portable_compare_payload(result)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Compare frozen AQ7 StructureV1/ArrangementClassifier candidates on "
            "CALIBRATION and freeze winner or baseline retention."
        )
    )
    parser.add_argument("--work-dir", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--repo-root", default=None)
    parser.add_argument(
        "--no-regenerate",
        action="store_true",
        help="Ignored: corpus is always rewritten for identity proof.",
    )
    args = parser.parse_args(argv)
    result = run_aq7_structure_role_drop_candidate_compare(
        work_dir=args.work_dir,
        output_path=args.output,
        repo_root=args.repo_root,
        regenerate_corpus=not args.no_regenerate,
    )
    print(
        json.dumps(
            {
                "exit_status": result["exit_status"],
                "exit_token": result["exit_token"],
                "frozen_candidate_id": (result.get("decision") or {}).get(
                    "frozen_candidate_id"
                ),
                "candidate_count": result["candidate_count"],
                "selection_partition": result["selection_partition"],
                "test_used_for_selection": result["test_used_for_selection"],
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0 if result["exit_status"] in {EXIT_FROZEN, EXIT_KEEP_BASELINE} else 1


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "AQ7_CANDIDATES",
    "BASELINE_CANDIDATE_ID",
    "BOUNDARY_SURFACE_POLICY",
    "CORPUS_ID",
    "CORPUS_VERSION",
    "DOCUMENT_TYPE",
    "EXIT_FROZEN",
    "EXIT_INCOMPLETE",
    "EXIT_KEEP_BASELINE",
    "FEATURE_TOGGLE",
    "GENERATOR_SEED",
    "PRODUCTION_DEFAULTS_CHANGED",
    "SCHEMA_VERSION",
    "SELECTION_PARTITION",
    "SHORTLIST_NOT_SELECTED",
    "Aq7Candidate",
    "Aq7CandidateCompareError",
    "candidate_by_id",
    "candidate_justified_on_calibration",
    "candidate_public",
    "decide_calibration_freeze",
    "hard_case_deltas",
    "list_aq7_candidates",
    "predict_fixture_for_candidate",
    "run_aq7_structure_role_drop_candidate_compare",
]
