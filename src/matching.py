from __future__ import annotations

from dataclasses import dataclass
import math
import re

from sqlalchemy import text

from .db import ensure_features_pred_type_column, get_engine, init_db

DEFAULT_LIMIT = 10
DEFAULT_BPM_TOLERANCE = 8.0
HALF_DOUBLE_PENALTY = 0.9
DEFAULT_BPM_WEIGHT = 0.5
DEFAULT_KEY_WEIGHT = 0.3
DEFAULT_TYPE_WEIGHT = 0.2

_KEY_RE = re.compile(r"^\s*([A-Ga-g])([#b]?)(?:\s*(maj(?:or)?|min(?:or)?|m))?\s*$")
_FLAT_TO_SHARP = {
    "CB": "B",
    "DB": "C#",
    "EB": "D#",
    "FB": "E",
    "GB": "F#",
    "AB": "G#",
    "BB": "A#",
}


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


@dataclass(frozen=True)
class MatchRunResult:
    matches: tuple[MatchResult, ...] = ()
    error: str | None = None
    info: str | None = None

    @property
    def ok(self) -> bool:
        return self.error is None


@dataclass(frozen=True)
class _ParsedKey:
    root: str
    mode: str | None = None


@dataclass(frozen=True)
class _BpmMatchDetails:
    score: float
    reason: str


def _normalize_text(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip().casefold()
    return normalized or None


def _normalize_note(root: str, accidental: str) -> str:
    note = f"{root.upper()}{accidental}"
    return _FLAT_TO_SHARP.get(note, note)


def _parse_key(value: str | None) -> _ParsedKey | None:
    normalized = _normalize_text(value)
    if normalized is None:
        return None

    match = _KEY_RE.match(normalized)
    if match is None:
        return None

    root = _normalize_note(match.group(1), match.group(2) or "")
    mode_token = match.group(3)
    if mode_token is None:
        mode = None
    elif mode_token.startswith("maj"):
        mode = "maj"
    else:
        mode = "min"

    return _ParsedKey(root=root, mode=mode)


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
        return _BpmMatchDetails(score=0.0, reason="bpm missing")

    if not math.isfinite(sample_bpm) or not math.isfinite(target_bpm):
        return _BpmMatchDetails(score=0.0, reason="bpm invalid")

    if sample_bpm <= 0 or target_bpm <= 0:
        return _BpmMatchDetails(score=0.0, reason="bpm invalid")

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
            f"bpm direct match: {sample_bpm:.1f} vs {target_bpm:.1f}",
        ),
        (
            half_time_score,
            f"bpm half-time fit: {sample_bpm:.1f} -> {sample_bpm * 2.0:.1f}",
        ),
        (
            double_time_score,
            f"bpm double-time fit: {sample_bpm:.1f} -> {sample_bpm / 2.0:.1f}",
        ),
    ]
    best_score, best_reason = max(candidates, key=lambda item: item[0])
    if best_score > 0.0:
        return _BpmMatchDetails(score=best_score, reason=best_reason)

    return _BpmMatchDetails(
        score=0.0,
        reason=f"bpm mismatch: {sample_bpm:.1f} vs {target_bpm:.1f}",
    )


def score_bpm_match(
    sample_bpm: float | None,
    target_bpm: float | None,
    tolerance: float,
) -> float:
    return _score_bpm_details(sample_bpm, target_bpm, tolerance).score


def score_key_match(sample_key: str | None, target_key: str | None) -> float:
    sample = _parse_key(sample_key)
    target = _parse_key(target_key)
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


def _score_key_details(
    sample_key: str | None, target_key: str | None
) -> tuple[float, str] | None:
    if target_key is None:
        return None
    if sample_key is None:
        return 0.0, "key missing"

    score = score_key_match(sample_key, target_key)
    if score > 0.0:
        sample = _parse_key(sample_key)
        target = _parse_key(target_key)
        if sample is not None and target is not None and sample.mode != target.mode:
            return score, f"key pitch-class match: {sample.root}"
        return score, f"key match: {sample_key}"
    return 0.0, f"key mismatch: {sample_key} vs {target_key}"


def _score_type_details(
    sample_type: str | None, target_type: str | None
) -> tuple[float, str] | None:
    if target_type is None:
        return None
    if sample_type is None:
        return 0.0, "type missing"

    score = score_type_match(sample_type, target_type)
    if score > 0.0:
        return score, f"type match: {sample_type}"
    return 0.0, f"type mismatch: {sample_type} vs {target_type}"


def _compute_total_score(
    profile: MatchProfile,
    bpm_score: float,
    key_score: float,
    type_score: float,
) -> float:
    weighted_components = [(DEFAULT_BPM_WEIGHT, bpm_score)]
    if profile.target_key is not None:
        weighted_components.append((DEFAULT_KEY_WEIGHT, key_score))
    if profile.desired_type is not None:
        weighted_components.append((DEFAULT_TYPE_WEIGHT, type_score))

    weight_sum = sum(weight for weight, _ in weighted_components)
    if weight_sum <= 0:
        return 0.0

    weighted_total = sum(weight * score for weight, score in weighted_components)
    return weighted_total / weight_sum


def score_candidate(candidate: MatchCandidate, profile: MatchProfile) -> MatchResult:
    bpm_details = _score_bpm_details(
        candidate.bpm, profile.target_bpm, profile.bpm_tolerance
    )
    bpm_score = bpm_details.score
    key_details = _score_key_details(candidate.key, profile.target_key)
    type_details = _score_type_details(candidate.pred_type, profile.desired_type)
    key_score = key_details[0] if key_details is not None else 0.0
    type_score = type_details[0] if type_details is not None else 0.0

    reasons = [bpm_details.reason]
    if key_details is not None:
        reasons.append(key_details[1])
    if type_details is not None:
        reasons.append(type_details[1])

    total_score = _compute_total_score(profile, bpm_score, key_score, type_score)
    return MatchResult(
        sample_id=candidate.sample_id,
        path=candidate.path,
        bpm=candidate.bpm,
        key=candidate.key,
        pred_type=candidate.pred_type,
        bpm_score=bpm_score,
        key_score=key_score,
        type_score=type_score,
        total_score=total_score,
        reasons=tuple(reasons),
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
        print(
            " ".join(
                [
                    f"rank={rank}",
                    f"sample_id={match.sample_id}",
                    f"total_score={match.total_score:.4f}",
                    f"bpm_score={match.bpm_score:.4f}",
                    f"key_score={match.key_score:.4f}",
                    f"type_score={match.type_score:.4f}",
                    f"path={match.path}",
                    f"bpm={'' if match.bpm is None else match.bpm}",
                    f"key={'' if match.key is None else match.key}",
                    f"pred_type={'' if match.pred_type is None else match.pred_type}",
                    f"reasons={'; '.join(match.reasons)}",
                ]
            )
        )
