from __future__ import annotations

from dataclasses import dataclass
import math

from sqlalchemy import text

from .bpm_display import format_bpm_display
from .db import ensure_features_pred_type_column, get_engine, init_db
from .key_signature import key_distance_semitones, parse_key_signature

DEFAULT_LIMIT = 10
DEFAULT_BPM_TOLERANCE = 8.0
HALF_DOUBLE_PENALTY = 0.9
DEFAULT_BPM_WEIGHT = 0.5
DEFAULT_KEY_WEIGHT = 0.3
DEFAULT_TYPE_WEIGHT = 0.2

DIMENSION_OK = "ok"
DIMENSION_NO_RESULT = "no_result"
DIMENSION_NOT_RUN = "not_run"

BPM_RELATION_DIRECT = "direct"
BPM_RELATION_HALF_TIME = "half_time"
BPM_RELATION_DOUBLE_TIME = "double_time"
BPM_RELATION_NO_RESULT = "no_result"


@dataclass(frozen=True)
class MatchProfile:
    target_bpm: float
    target_key: str | None = None
    desired_type: str | None = None
    limit: int | None = DEFAULT_LIMIT
    bpm_tolerance: float = DEFAULT_BPM_TOLERANCE


@dataclass(frozen=True)
class MatchCandidate:
    sample_id: int
    path: str
    bpm: float | None = None
    key: str | None = None
    pred_type: str | None = None


@dataclass(frozen=True)
class MatchDimension:
    name: str
    status: str
    score: float | None
    weight: float
    active: bool
    reason: str
    source_ref: str | None = None


@dataclass(frozen=True)
class MatchResult:
    sample_id: int
    path: str
    bpm: float | None
    key: str | None
    pred_type: str | None
    bpm_score: float
    key_score: float
    type_score: float
    total_score: float
    reasons: tuple[str, ...]
    bpm_relation: str = BPM_RELATION_NO_RESULT
    tempo_multiplier: float | None = None
    semitone_hint: int | None = None
    groove_status: str = DIMENSION_NO_RESULT
    dimensions: tuple[MatchDimension, ...] = ()

    @property
    def active_dimensions(self) -> tuple[str, ...]:
        return tuple(dimension.name for dimension in self.dimensions if dimension.active)


@dataclass(frozen=True)
class MatchRunResult:
    matches: tuple[MatchResult, ...] = ()
    error: str | None = None
    info: str | None = None

    @property
    def ok(self) -> bool:
        return self.error is None


@dataclass(frozen=True)
class _BpmMatchDetails:
    score: float
    reason: str
    status: str
    relation: str = BPM_RELATION_NO_RESULT
    tempo_multiplier: float | None = None


@dataclass(frozen=True)
class _DimensionDetails:
    score: float
    reason: str
    status: str


def _normalize_text(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip().casefold()
    return normalized or None


def _linear_decay(diff: float, tolerance: float) -> float:
    if tolerance <= 0:
        return 0.0
    if diff >= tolerance:
        return 0.0
    if diff == 0:
        return 1.0
    return 1.0 - (diff / tolerance)


def _score_bpm_details(
    sample_bpm: float | None,
    target_bpm: float | None,
    tolerance: float,
) -> _BpmMatchDetails:
    if sample_bpm is None or target_bpm is None:
        return _BpmMatchDetails(
            score=0.0,
            reason="bpm missing",
            status=DIMENSION_NO_RESULT,
        )

    if not math.isfinite(sample_bpm) or not math.isfinite(target_bpm):
        return _BpmMatchDetails(
            score=0.0,
            reason="bpm invalid",
            status=DIMENSION_NO_RESULT,
        )

    if sample_bpm <= 0 or target_bpm <= 0:
        return _BpmMatchDetails(
            score=0.0,
            reason="bpm invalid",
            status=DIMENSION_NO_RESULT,
        )

    direct_score = _linear_decay(abs(sample_bpm - target_bpm), tolerance)
    half_time_score = (
        _linear_decay(abs((sample_bpm * 2.0) - target_bpm), tolerance)
        * HALF_DOUBLE_PENALTY
    )
    double_time_score = (
        _linear_decay(abs((sample_bpm / 2.0) - target_bpm), tolerance)
        * HALF_DOUBLE_PENALTY
    )

    candidates = [
        (
            direct_score,
            BPM_RELATION_DIRECT,
            1.0,
            f"bpm direct match: {format_bpm_display(sample_bpm)} vs {format_bpm_display(target_bpm)}",
        ),
        (
            half_time_score,
            BPM_RELATION_HALF_TIME,
            2.0,
            f"bpm half-time fit: {format_bpm_display(sample_bpm)} -> {format_bpm_display(sample_bpm * 2.0)}",
        ),
        (
            double_time_score,
            BPM_RELATION_DOUBLE_TIME,
            0.5,
            f"bpm double-time fit: {format_bpm_display(sample_bpm)} -> {format_bpm_display(sample_bpm / 2.0)}",
        ),
    ]
    best_score, relation, tempo_multiplier, best_reason = max(
        candidates, key=lambda item: item[0]
    )
    if best_score > 0.0:
        return _BpmMatchDetails(
            score=best_score,
            reason=best_reason,
            status=DIMENSION_OK,
            relation=relation,
            tempo_multiplier=tempo_multiplier,
        )

    return _BpmMatchDetails(
        score=0.0,
        reason=f"bpm mismatch: {format_bpm_display(sample_bpm)} vs {format_bpm_display(target_bpm)}",
        status=DIMENSION_OK,
    )


def score_bpm_match(
    sample_bpm: float | None,
    target_bpm: float | None,
    tolerance: float,
) -> float:
    return _score_bpm_details(sample_bpm, target_bpm, tolerance).score


def score_key_match(sample_key: str | None, target_key: str | None) -> float:
    sample = parse_key_signature(sample_key)
    target = parse_key_signature(target_key)
    if sample is None or target is None:
        return 0.0
    if sample.root != target.root:
        return 0.0
    if (
        sample.mode is not None
        and target.mode is not None
        and sample.mode != target.mode
    ):
        return 0.0
    return 1.0


def score_type_match(sample_type: str | None, target_type: str | None) -> float:
    normalized_sample = _normalize_text(sample_type)
    normalized_target = _normalize_text(target_type)
    if normalized_sample is None or normalized_target is None:
        return 0.0
    return 1.0 if normalized_sample == normalized_target else 0.0


def semitone_hint(sample_key: str | None, target_key: str | None) -> int | None:
    """Return the smallest deterministic pitch-class shift from sample to target.

    The v1 hint is intentionally conservative: missing/unparseable keys and a known
    major/minor mismatch return no hint because pitch shifting cannot repair mode.
    The signed range is -5..+6; the tritone tie is always represented as +6.
    """
    sample = parse_key_signature(sample_key)
    target = parse_key_signature(target_key)
    if sample is None or target is None:
        return None
    if (
        sample.mode is not None
        and target.mode is not None
        and sample.mode != target.mode
    ):
        return None

    distance = key_distance_semitones(sample, target)
    if distance > 6:
        return distance - 12
    return distance


def _score_key_details(
    sample_key: str | None, target_key: str | None
) -> _DimensionDetails | None:
    if target_key is None:
        return None

    target = parse_key_signature(target_key)
    if target is None:
        return _DimensionDetails(
            score=0.0,
            reason="target key invalid",
            status=DIMENSION_NO_RESULT,
        )
    if sample_key is None:
        return _DimensionDetails(
            score=0.0,
            reason="key missing",
            status=DIMENSION_NO_RESULT,
        )

    sample = parse_key_signature(sample_key)
    if sample is None:
        return _DimensionDetails(
            score=0.0,
            reason="key invalid",
            status=DIMENSION_NO_RESULT,
        )

    score = score_key_match(sample_key, target_key)
    if score > 0.0:
        if sample.mode != target.mode:
            return _DimensionDetails(
                score=score,
                reason=f"key pitch-class match: {sample.root}",
                status=DIMENSION_OK,
            )
        return _DimensionDetails(
            score=score,
            reason=f"key match: {sample_key}",
            status=DIMENSION_OK,
        )
    if (
        sample.mode is not None
        and target.mode is not None
        and sample.mode != target.mode
    ):
        return _DimensionDetails(
            score=0.0,
            reason=f"key mode mismatch: {sample_key} vs {target_key}",
            status=DIMENSION_OK,
        )
    return _DimensionDetails(
        score=0.0,
        reason=f"key mismatch: {sample_key} vs {target_key}",
        status=DIMENSION_OK,
    )


def _score_type_details(
    sample_type: str | None, target_type: str | None
) -> _DimensionDetails | None:
    if target_type is None:
        return None
    if _normalize_text(target_type) is None:
        return _DimensionDetails(
            score=0.0,
            reason="target type invalid",
            status=DIMENSION_NO_RESULT,
        )
    if sample_type is None or _normalize_text(sample_type) is None:
        return _DimensionDetails(
            score=0.0,
            reason="type missing",
            status=DIMENSION_NO_RESULT,
        )

    score = score_type_match(sample_type, target_type)
    if score > 0.0:
        return _DimensionDetails(
            score=score,
            reason=f"type match: {sample_type}",
            status=DIMENSION_OK,
        )
    return _DimensionDetails(
        score=0.0,
        reason=f"type mismatch: {sample_type} vs {target_type}",
        status=DIMENSION_OK,
    )


def _match_dimension(
    name: str,
    details: _DimensionDetails | _BpmMatchDetails | None,
    weight: float,
    source_ref: str,
) -> MatchDimension:
    if details is None:
        return MatchDimension(
            name=name,
            status=DIMENSION_NOT_RUN,
            score=None,
            weight=weight,
            active=False,
            reason=f"{name} target not provided",
            source_ref=source_ref,
        )
    return MatchDimension(
        name=name,
        status=details.status,
        score=details.score,
        weight=weight,
        active=details.status == DIMENSION_OK,
        reason=details.reason,
        source_ref=source_ref,
    )


def _compute_total_score(dimensions: tuple[MatchDimension, ...]) -> float:
    weighted_components = [
        (dimension.weight, dimension.score or 0.0)
        for dimension in dimensions
        if dimension.active and dimension.weight > 0.0
    ]
    weight_sum = sum(weight for weight, _ in weighted_components)
    if weight_sum <= 0:
        return 0.0

    weighted_total = sum(weight * score for weight, score in weighted_components)
    return min(1.0, max(0.0, weighted_total / weight_sum))


def score_candidate(candidate: MatchCandidate, profile: MatchProfile) -> MatchResult:
    bpm_details = _score_bpm_details(
        candidate.bpm, profile.target_bpm, profile.bpm_tolerance
    )
    key_details = _score_key_details(candidate.key, profile.target_key)
    type_details = _score_type_details(candidate.pred_type, profile.desired_type)

    bpm_dimension = _match_dimension(
        "bpm", bpm_details, DEFAULT_BPM_WEIGHT, "candidate.bpm"
    )
    key_dimension = _match_dimension(
        "key", key_details, DEFAULT_KEY_WEIGHT, "candidate.key"
    )
    type_dimension = _match_dimension(
        "type", type_details, DEFAULT_TYPE_WEIGHT, "candidate.pred_type"
    )
    groove_dimension = MatchDimension(
        name="groove",
        status=DIMENSION_NO_RESULT,
        score=None,
        weight=0.0,
        active=False,
        reason="GROOVE_EVIDENCE_UNAVAILABLE",
        source_ref=None,
    )
    dimensions = (
        bpm_dimension,
        key_dimension,
        type_dimension,
        groove_dimension,
    )

    reasons = [bpm_details.reason]
    if key_details is not None:
        reasons.append(key_details.reason)
    if type_details is not None:
        reasons.append(type_details.reason)

    key_score = key_details.score if key_details is not None else 0.0
    type_score = type_details.score if type_details is not None else 0.0
    total_score = _compute_total_score(dimensions)

    return MatchResult(
        sample_id=candidate.sample_id,
        path=candidate.path,
        bpm=candidate.bpm,
        key=candidate.key,
        pred_type=candidate.pred_type,
        bpm_score=bpm_details.score,
        key_score=key_score,
        type_score=type_score,
        total_score=total_score,
        reasons=tuple(reasons),
        bpm_relation=bpm_details.relation,
        tempo_multiplier=bpm_details.tempo_multiplier,
        semitone_hint=semitone_hint(candidate.key, profile.target_key),
        groove_status=groove_dimension.status,
        dimensions=dimensions,
    )


def match_candidates(
    candidates: list[MatchCandidate],
    profile: MatchProfile,
) -> list[MatchResult]:
    results = [score_candidate(candidate, profile) for candidate in candidates]
    results.sort(
        key=lambda item: (
            -item.total_score,
            -item.bpm_score,
            -item.key_score,
            -item.type_score,
            item.sample_id,
            item.path,
        )
    )
    if profile.limit is None:
        return results
    return results[: profile.limit]


def load_match_candidates() -> list[MatchCandidate]:
    init_db()
    ensure_features_pred_type_column()
    engine = get_engine()
    query = """
        SELECT s.id, s.path, f.bpm, f.key, f.pred_type
        FROM samples s
        INNER JOIN features f ON f.sample_id = s.id
        ORDER BY s.id
    """
    with engine.begin() as conn:
        rows = conn.execute(text(query)).fetchall()

    return [
        MatchCandidate(
            sample_id=row[0],
            path=row[1],
            bpm=row[2],
            key=row[3],
            pred_type=row[4],
        )
        for row in rows
    ]


def collect_matches(profile: MatchProfile) -> MatchRunResult:
    if not math.isfinite(profile.target_bpm) or profile.target_bpm <= 0:
        return MatchRunResult(error="match requires a positive --target-bpm.")
    if profile.limit is not None and profile.limit <= 0:
        return MatchRunResult(error="match requires --limit > 0 when provided.")
    if profile.bpm_tolerance <= 0:
        return MatchRunResult(error="match requires bpm_tolerance > 0.")

    candidates = load_match_candidates()
    if not candidates:
        return MatchRunResult(info="No analyzed samples available for matching.")

    matches = match_candidates(candidates, profile)
    return MatchRunResult(matches=tuple(matches))


def run_match(
    target_bpm: float,
    target_key: str | None = None,
    desired_type: str | None = None,
    limit: int | None = DEFAULT_LIMIT,
) -> None:
    result = collect_matches(
        MatchProfile(
            target_bpm=target_bpm,
            target_key=target_key,
            desired_type=desired_type,
            limit=limit,
        )
    )

    if result.error:
        print(f"[ERROR] {result.error}")
        return

    if result.info:
        print(f"[INFO] {result.info}")
        return

    for rank, match in enumerate(result.matches, start=1):
        statuses = ",".join(
            f"{dimension.name}:{dimension.status}"
            for dimension in match.dimensions
        )
        weights = ",".join(
            f"{dimension.name}:{dimension.weight:.1f}"
            for dimension in match.dimensions
            if dimension.active
        )
        print(
            " ".join(
                [
                    f"rank={rank}",
                    f"sample_id={match.sample_id}",
                    f"total_score={match.total_score:.4f}",
                    f"bpm_score={match.bpm_score:.4f}",
                    f"key_score={match.key_score:.4f}",
                    f"type_score={match.type_score:.4f}",
                    f"bpm_relation={match.bpm_relation}",
                    f"tempo_multiplier={'' if match.tempo_multiplier is None else match.tempo_multiplier}",
                    f"semitone_hint={'' if match.semitone_hint is None else match.semitone_hint}",
                    f"active_dimensions={','.join(match.active_dimensions)}",
                    f"dimension_statuses={statuses}",
                    f"used_weights={weights}",
                    f"path={match.path}",
                    f"bpm={format_bpm_display(match.bpm, placeholder='')}",
                    f"key={'' if match.key is None else match.key}",
                    f"pred_type={'' if match.pred_type is None else match.pred_type}",
                    f"reasons={'; '.join(match.reasons)}",
                ]
            )
        )
