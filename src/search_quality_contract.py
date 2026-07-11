"""Golden search-quality suite contract validation (ADR-0005 Tier A/B)."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

TIER_B_QUERY_CLASSES: frozenset[str] = frozenset(
    {
        "kick_snare_perc",
        "pad_texture",
        "riser_impact",
        "dry_wet",
        "vocal_no_vocal",
        "genre_mood",
    }
)

TIER_B_QUERY_MODES: frozenset[str] = frozenset({"text", "audio"})

TIER_A_QUERY_MODES: frozenset[str] = frozenset({"vector"})

PORTABLE_GOLDEN_PATH_PREFIX = "/golden/"

_WINDOWS_DRIVE_PATH = re.compile(r"^[A-Za-z]:[/\\]")
_UNIX_PRIVATE_PREFIXES = ("/Users/", "/home/", "/var/", "/private/")


class SearchQualityContractError(ValueError):
    """Raised when a golden suite violates the search-quality contract."""

    def __init__(self, message: str, *, query_id: str | None = None) -> None:
        self.query_id = query_id
        if query_id:
            super().__init__(f"query '{query_id}': {message}")
        else:
            super().__init__(message)


@dataclass(frozen=True)
class ValidatedQuery:
    id: str
    mode: str
    query_class: str | None
    relevant_sample_ids: tuple[int, ...]
    negative_sample_ids: tuple[int, ...]
    eval_excluded: bool


@dataclass(frozen=True)
class ValidatedSuite:
    version: int
    tier: str
    queries: tuple[ValidatedQuery, ...]
    sample_ids: frozenset[int]
    fixture_names: frozenset[str]


def is_private_absolute_path(path: str) -> bool:
    """Return True when *path* looks like a machine-local absolute reference."""
    normalized = str(path).strip().replace("\\", "/")
    if not normalized:
        return False
    if normalized.startswith(PORTABLE_GOLDEN_PATH_PREFIX):
        return False
    if _WINDOWS_DRIVE_PATH.match(normalized):
        return True
    if normalized.startswith("//"):
        return True
    if normalized.startswith("/") and not normalized.startswith(
        PORTABLE_GOLDEN_PATH_PREFIX
    ):
        return True
    for prefix in _UNIX_PRIVATE_PREFIXES:
        if normalized.startswith(prefix):
            return True
    return False


def validate_search_quality_suite(suite: dict[str, Any]) -> ValidatedSuite:
    """Validate a loaded golden suite dict and return normalized contract view."""
    if not isinstance(suite, dict):
        raise SearchQualityContractError("suite must be a mapping")

    version = int(suite.get("version", 0))
    if version < 1:
        raise SearchQualityContractError("version must be >= 1")

    tier = str(suite.get("tier", "")).strip().upper()
    if tier not in {"A", "B"}:
        raise SearchQualityContractError(f"unsupported tier: {tier!r}")

    catalog = suite.get("catalog") or {}
    samples = catalog.get("samples") or []
    sample_ids: set[int] = set()
    fixture_names: set[str] = set()
    for sample in samples:
        if not isinstance(sample, dict):
            raise SearchQualityContractError("catalog sample entries must be mappings")
        sample_ids.add(int(sample["id"]))
        fixture_name = sample.get("fixture_name")
        if fixture_name:
            fixture_names.add(str(fixture_name))
        sample_path = sample.get("path")
        if sample_path and is_private_absolute_path(str(sample_path)):
            raise SearchQualityContractError(
                f"catalog sample {sample.get('id')} uses private absolute path"
            )

    raw_queries = suite.get("queries") or []
    if not raw_queries:
        raise SearchQualityContractError("queries must not be empty")

    if tier == "A":
        return _validate_tier_a(version, raw_queries, sample_ids, fixture_names)
    return _validate_tier_b(version, raw_queries, sample_ids, fixture_names)


def _validate_tier_a(
    version: int,
    raw_queries: list[Any],
    sample_ids: set[int],
    fixture_names: set[str],
) -> ValidatedSuite:
    seen_ids: set[str] = set()
    validated: list[ValidatedQuery] = []

    for raw_query in raw_queries:
        if not isinstance(raw_query, dict):
            raise SearchQualityContractError("query entries must be mappings")
        query_id = str(raw_query.get("id", "")).strip()
        if not query_id:
            raise SearchQualityContractError("query id is required")
        if query_id in seen_ids:
            raise SearchQualityContractError("duplicate query id", query_id=query_id)
        seen_ids.add(query_id)

        mode = str(raw_query.get("mode", "")).strip()
        if mode not in TIER_A_QUERY_MODES:
            raise SearchQualityContractError(
                f"invalid query mode {mode!r}; expected one of {sorted(TIER_A_QUERY_MODES)}",
                query_id=query_id,
            )
        if "query_vector" not in raw_query:
            raise SearchQualityContractError(
                "vector mode requires query_vector", query_id=query_id
            )

        relevant = _parse_sample_id_list(
            raw_query.get("relevant_sample_ids"),
            field_name="relevant_sample_ids",
            query_id=query_id,
            sample_ids=sample_ids,
            allow_empty=False,
        )
        negatives = _parse_sample_id_list(
            raw_query.get("negative_sample_ids"),
            field_name="negative_sample_ids",
            query_id=query_id,
            sample_ids=sample_ids,
            allow_empty=True,
        )
        _reject_overlap(relevant, negatives, query_id)

        validated.append(
            ValidatedQuery(
                id=query_id,
                mode=mode,
                query_class=None,
                relevant_sample_ids=relevant,
                negative_sample_ids=negatives,
                eval_excluded=False,
            )
        )

    return ValidatedSuite(
        version=version,
        tier="A",
        queries=tuple(validated),
        sample_ids=frozenset(sample_ids),
        fixture_names=frozenset(fixture_names),
    )


def _validate_tier_b(
    version: int,
    raw_queries: list[Any],
    sample_ids: set[int],
    fixture_names: set[str],
) -> ValidatedSuite:
    seen_ids: set[str] = set()
    validated: list[ValidatedQuery] = []

    for raw_query in raw_queries:
        if not isinstance(raw_query, dict):
            raise SearchQualityContractError("query entries must be mappings")
        query_id = str(raw_query.get("id", "")).strip()
        if not query_id:
            raise SearchQualityContractError("query id is required")
        if query_id in seen_ids:
            raise SearchQualityContractError("duplicate query id", query_id=query_id)
        seen_ids.add(query_id)

        mode = str(raw_query.get("mode", "")).strip()
        if mode not in TIER_B_QUERY_MODES:
            raise SearchQualityContractError(
                f"invalid query mode {mode!r}; expected one of {sorted(TIER_B_QUERY_MODES)}",
                query_id=query_id,
            )

        query_class = raw_query.get("query_class")
        if not query_class:
            raise SearchQualityContractError(
                "query_class is required", query_id=query_id
            )
        query_class = str(query_class).strip()
        if query_class not in TIER_B_QUERY_CLASSES:
            raise SearchQualityContractError(
                f"unknown query_class {query_class!r}; "
                f"expected one of {sorted(TIER_B_QUERY_CLASSES)}",
                query_id=query_id,
            )

        text = raw_query.get("text")
        query_audio = raw_query.get("query_audio")
        query_audio_fixture = raw_query.get("query_audio_fixture")
        eval_excluded = bool(raw_query.get("eval_excluded", False))

        if mode == "text":
            if not text or not str(text).strip():
                raise SearchQualityContractError(
                    "text mode requires non-empty text", query_id=query_id
                )
            if query_audio:
                raise SearchQualityContractError(
                    "text mode must not set query_audio", query_id=query_id
                )
            if query_audio_fixture:
                raise SearchQualityContractError(
                    "text mode must not set query_audio_fixture", query_id=query_id
                )
        else:
            if text:
                raise SearchQualityContractError(
                    "audio mode must not set text", query_id=query_id
                )
            if query_audio:
                raise SearchQualityContractError(
                    "audio mode must use query_audio_fixture, not query_audio path",
                    query_id=query_id,
                )
            if not query_audio_fixture or not str(query_audio_fixture).strip():
                raise SearchQualityContractError(
                    "audio mode requires query_audio_fixture", query_id=query_id
                )
            fixture_name = str(query_audio_fixture).strip()
            if fixture_name not in fixture_names:
                raise SearchQualityContractError(
                    f"unknown query_audio_fixture {fixture_name!r}", query_id=query_id
                )

        relevant = _parse_sample_id_list(
            raw_query.get("relevant_sample_ids"),
            field_name="relevant_sample_ids",
            query_id=query_id,
            sample_ids=sample_ids,
            allow_empty=eval_excluded,
        )
        negatives = _parse_sample_id_list(
            raw_query.get("negative_sample_ids"),
            field_name="negative_sample_ids",
            query_id=query_id,
            sample_ids=sample_ids,
            allow_empty=True,
        )
        if not eval_excluded and not relevant:
            raise SearchQualityContractError(
                "relevant_sample_ids must not be empty", query_id=query_id
            )
        _reject_overlap(relevant, negatives, query_id)

        validated.append(
            ValidatedQuery(
                id=query_id,
                mode=mode,
                query_class=query_class,
                relevant_sample_ids=relevant,
                negative_sample_ids=negatives,
                eval_excluded=eval_excluded,
            )
        )

    return ValidatedSuite(
        version=version,
        tier="B",
        queries=tuple(validated),
        sample_ids=frozenset(sample_ids),
        fixture_names=frozenset(fixture_names),
    )


def _parse_sample_id_list(
    raw: Any,
    *,
    field_name: str,
    query_id: str,
    sample_ids: set[int],
    allow_empty: bool,
) -> tuple[int, ...]:
    if raw is None:
        if allow_empty:
            return ()
        raise SearchQualityContractError(f"{field_name} is required", query_id=query_id)
    if not isinstance(raw, list):
        raise SearchQualityContractError(
            f"{field_name} must be a list", query_id=query_id
        )
    if not raw and not allow_empty:
        raise SearchQualityContractError(
            f"{field_name} must not be empty", query_id=query_id
        )

    parsed: list[int] = []
    for value in raw:
        sample_id = int(value)
        if sample_ids and sample_id not in sample_ids:
            raise SearchQualityContractError(
                f"{field_name} references unknown sample id {sample_id}",
                query_id=query_id,
            )
        parsed.append(sample_id)
    return tuple(parsed)


def _reject_overlap(
    relevant: tuple[int, ...],
    negatives: tuple[int, ...],
    query_id: str,
) -> None:
    overlap = set(relevant) & set(negatives)
    if overlap:
        raise SearchQualityContractError(
            f"relevant_sample_ids and negative_sample_ids overlap: {sorted(overlap)}",
            query_id=query_id,
        )
