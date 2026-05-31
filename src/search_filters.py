from __future__ import annotations

from dataclasses import dataclass

from .db import get_engine, text


@dataclass(frozen=True)
class SearchFilters:
    tags: tuple[str, ...] = ()
    min_bpm: float | None = None
    max_bpm: float | None = None
    key: str | None = None
    scale: str | None = None
    min_duration: float | None = None
    max_duration: float | None = None
    pred_type: str | None = None

    def active(self) -> bool:
        return bool(
            self.tags
            or self.min_bpm is not None
            or self.max_bpm is not None
            or self.key is not None
            or self.scale is not None
            or self.min_duration is not None
            or self.max_duration is not None
            or self.pred_type is not None
        )


def _normalize(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    return normalized or None


def _normalize_casefold(value: str | None) -> str | None:
    normalized = _normalize(value)
    return normalized.casefold() if normalized is not None else None


def key_matches_scale(key: str | None, scale: str | None) -> bool:
    if scale is None:
        return True
    if key is None:
        return False

    normalized_key = key.strip()
    normalized_scale = scale.strip().casefold()
    if normalized_scale in {"minor", "min"}:
        return normalized_key.endswith("m") or normalized_key.endswith("min")
    if normalized_scale in {"major", "maj"}:
        return not (
            normalized_key.endswith("m")
            or normalized_key.endswith("min")
            or normalized_key.endswith("min.")
        )
    return normalized_scale in normalized_key.casefold()


def resolve_filtered_sample_ids(filters: SearchFilters | None) -> set[int] | None:
    if filters is None or not filters.active():
        return None

    clauses: list[str] = []
    params: dict[str, object] = {}

    if filters.min_bpm is not None:
        clauses.append("f.bpm >= :min_bpm")
        params["min_bpm"] = filters.min_bpm
    if filters.max_bpm is not None:
        clauses.append("f.bpm <= :max_bpm")
        params["max_bpm"] = filters.max_bpm
    if filters.key is not None:
        clauses.append("LOWER(f.key) = :key")
        params["key"] = filters.key.strip().casefold()
    if filters.pred_type is not None:
        clauses.append("LOWER(f.pred_type) = :pred_type")
        params["pred_type"] = filters.pred_type.strip().casefold()
    if filters.min_duration is not None:
        clauses.append("s.duration >= :min_duration")
        params["min_duration"] = filters.min_duration
    if filters.max_duration is not None:
        clauses.append("s.duration <= :max_duration")
        params["max_duration"] = filters.max_duration

    tag_join = ""
    if filters.tags:
        tag_join = """
            JOIN sample_tags st ON st.sample_id = s.id
        """
        tag_clauses = []
        for index, tag in enumerate(filters.tags):
            param_name = f"tag_{index}"
            tag_clauses.append(f"LOWER(st.tag) = :{param_name}")
            params[param_name] = tag.strip().casefold()
        clauses.append("(" + " OR ".join(tag_clauses) + ")")

    where_sql = ""
    if clauses:
        where_sql = "WHERE " + " AND ".join(clauses)

    query = f"""
        SELECT DISTINCT s.id, f.key
        FROM samples s
        LEFT JOIN features f ON f.sample_id = s.id
        {tag_join}
        {where_sql}
    """
    engine = get_engine()
    with engine.begin() as conn:
        rows = conn.execute(text(query), params).fetchall()

    if filters.scale is not None:
        rows = [
            row for row in rows if key_matches_scale(row[1], filters.scale)
        ]

    return {int(row[0]) for row in rows}


def sync_pred_type_tags() -> int:
    """Copy features.pred_type values into sample_tags (source=pred_type)."""
    engine = get_engine()
    with engine.begin() as conn:
        rows = conn.execute(
            text("""
            SELECT sample_id, pred_type
            FROM features
            WHERE pred_type IS NOT NULL AND TRIM(pred_type) != ''
            """)
        ).fetchall()
        synced = 0
        for sample_id, pred_type in rows:
            result = conn.execute(
                text("""
                INSERT OR IGNORE INTO sample_tags (sample_id, tag, source)
                VALUES (:sample_id, :tag, 'pred_type')
                """),
                {"sample_id": sample_id, "tag": pred_type.strip()},
            )
            synced += result.rowcount or 0
    return synced


def search_filters_from_cli_args(args) -> SearchFilters | None:
    tags = tuple(tag.strip() for tag in getattr(args, "tag", []) or [] if tag.strip())
    filters = SearchFilters(
        tags=tags,
        min_bpm=getattr(args, "min_bpm", None),
        max_bpm=getattr(args, "max_bpm", None),
        key=getattr(args, "filter_key", None),
        scale=getattr(args, "scale", None),
        min_duration=getattr(args, "min_duration", None),
        max_duration=getattr(args, "max_duration", None),
        pred_type=getattr(args, "pred_type", None),
    )
    if not filters.active():
        return None
    return filters
