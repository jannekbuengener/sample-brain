#!/usr/bin/env python3
"""Generate a local Sample Brain validation report from ``catalog.db``.

The report is intentionally local-only. It summarizes catalog consistency,
BPM/key plausibility, and Autotype quality against weak labels derived from
filenames/folder names without writing raw sample paths to the report.
"""

from __future__ import annotations

import argparse
import math
import re
import sqlite3
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path
from statistics import median

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.bpm_display import format_bpm_display
from src.key_signature import parse_key_signature

BPM_HINT_RE = re.compile(r"(?<!\d)(\d{2,3})\s*[-_ ]?\s*bpm(?![A-Za-z0-9])", re.IGNORECASE)
KEY_HINT_RE = re.compile(
    r"\b([A-Ga-g])([#b]?)(?:\s*)(maj(?:or)?|min(?:or)?|m)\b",
    re.IGNORECASE,
)

_TYPE_PATTERNS = {
    "oneshot": re.compile(r"\b(?:one\s*shot|oneshot|one-shot)\b", re.IGNORECASE),
    "loop": re.compile(r"\bloops?\b", re.IGNORECASE),
}

_INSTRUMENT_PATTERNS = (
    ("kick", re.compile(r"\bkicks?\b", re.IGNORECASE)),
    ("snare", re.compile(r"\bsnares?\b", re.IGNORECASE)),
    ("clap", re.compile(r"\bclaps?\b", re.IGNORECASE)),
    ("hihat", re.compile(r"\b(?:hi\s*hat|hihat|hats?)\b", re.IGNORECASE)),
    ("impact", re.compile(r"\bimpacts?\b", re.IGNORECASE)),
    ("drone", re.compile(r"\bdrones?\b", re.IGNORECASE)),
    ("pad", re.compile(r"\bpads?\b", re.IGNORECASE)),
    ("fx", re.compile(r"\b(?:fx|sfx)\b", re.IGNORECASE)),
)


def _normalized_ref(text: str | None) -> str:
    return re.sub(r"[_./\\()\[\]-]+", " ", text or "").strip()


def extract_bpm_hint(text: str | None) -> float | None:
    if not text:
        return None
    match = BPM_HINT_RE.search(text)
    if match is None:
        return None
    return float(match.group(1))


def classify_bpm_match(
    predicted: float | None,
    hint: float | None,
    tolerance: float = 2.0,
) -> str:
    if predicted is None or hint is None:
        return "no_hint"
    if abs(predicted - hint) <= tolerance:
        return "match"
    if abs(predicted * 2.0 - hint) <= tolerance:
        return "half_time"
    if abs(predicted / 2.0 - hint) <= tolerance:
        return "double_time"
    return "mismatch"


def extract_key_hint(text: str | None) -> str | None:
    normalized = _normalized_ref(text)
    match = KEY_HINT_RE.search(normalized)
    if match is None:
        return None
    raw = f"{match.group(1)}{match.group(2)}{match.group(3)}"
    parsed = parse_key_signature(raw)
    if parsed is None or parsed.mode is None:
        return None
    return f"{parsed.root}{parsed.mode}"


def extract_type_hint(text: str | None) -> str | None:
    normalized = _normalized_ref(text)
    for label in ("oneshot", "loop"):
        if _TYPE_PATTERNS[label].search(normalized):
            return label
    return None


def extract_instrument_hint(text: str | None) -> str | None:
    normalized = _normalized_ref(text)
    for label, pattern in _INSTRUMENT_PATTERNS:
        if pattern.search(normalized):
            return label
    return None


def _normalize_class(value: str | None) -> str | None:
    normalized = (value or "").strip().casefold().replace("-", "").replace("_", "")
    if normalized in {"oneshot", "oneshots"}:
        return "oneshot"
    if normalized in {"loop", "loops"}:
        return "loop"
    return None


def _normalize_pred_type(value: str | None) -> str | None:
    normalized = (value or "").strip().casefold().replace("-", "").replace("_", "")
    if not normalized:
        return None
    if "kick" in normalized:
        return "kick"
    if "snare" in normalized:
        return "snare"
    if "clap" in normalized:
        return "clap"
    if "hihat" in normalized or normalized in {"hat", "hats"}:
        return "hihat"
    if "impact" in normalized:
        return "impact"
    if "drone" in normalized:
        return "drone"
    if "pad" in normalized:
        return "pad"
    if normalized in {"fx", "sfx"}:
        return "fx"
    return None


def _pct(count: int, total: int) -> float:
    return 0.0 if total == 0 else 100.0 * count / total


def _percentile(values: list[float], quantile: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    position = (len(ordered) - 1) * quantile
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    weight = position - lower
    return ordered[lower] * (1.0 - weight) + ordered[upper] * weight


def _key_match(predicted: str | None, hint: str | None) -> tuple[bool, bool]:
    predicted_key = parse_key_signature(predicted)
    hint_key = parse_key_signature(hint)
    if predicted_key is None or hint_key is None:
        return False, False
    root_match = predicted_key.root == hint_key.root
    signature_match = root_match and predicted_key.mode == hint_key.mode
    return root_match, signature_match


def generate_report(db_path: Path, out_path: Path) -> dict[str, int | bool]:
    """Generate the Markdown report and return compact machine-readable metrics."""

    db_path = Path(db_path)
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    if not db_path.exists():
        out_path.write_text(
            "# Sample Brain Validation Report\n\n"
            f"Generated: {datetime.now().isoformat(timespec='seconds')}\n\n"
            f"ERROR: Database not found at `{db_path.name}`.\n",
            encoding="utf-8",
        )
        raise FileNotFoundError(db_path)

    connection = sqlite3.connect(db_path)
    connection.row_factory = sqlite3.Row
    try:
        feature_columns = {
            row["name"] for row in connection.execute("PRAGMA table_info(features)").fetchall()
        }
        pred_type_expr = "f.pred_type" if "pred_type" in feature_columns else "NULL"
        rows = connection.execute(
            f"""
            SELECT
                s.id,
                COALESCE(s.relpath, s.path) AS ref,
                s.duration,
                f.sample_id AS feature_sample_id,
                f.bpm,
                f.key,
                f.key_conf,
                f.loudness,
                f.brightness,
                f."class" AS class_name,
                {pred_type_expr} AS pred_type
            FROM samples AS s
            LEFT JOIN features AS f ON f.sample_id = s.id
            ORDER BY s.id
            """
        ).fetchall()
        feature_rows = int(connection.execute("SELECT COUNT(*) FROM features").fetchone()[0])
        orphan_features = int(
            connection.execute(
                """
                SELECT COUNT(*)
                FROM features AS f
                LEFT JOIN samples AS s ON s.id = f.sample_id
                WHERE s.id IS NULL
                """
            ).fetchone()[0]
        )
    finally:
        connection.close()

    sample_count = len(rows)
    missing_features = sum(1 for row in rows if row["feature_sample_id"] is None)
    catalog_consistent = (
        sample_count == feature_rows and missing_features == 0 and orphan_features == 0
    )

    bpm_values = [float(row["bpm"]) for row in rows if row["bpm"] is not None]
    key_conf_values = [
        float(row["key_conf"]) for row in rows if row["key_conf"] is not None
    ]

    bpm_results: Counter[str] = Counter()
    key_hint_count = 0
    key_root_matches = 0
    key_signature_matches = 0
    class_hint_count = 0
    class_matches = 0
    instrument_hint_count = 0
    instrument_matches = 0

    class_counts: Counter[str] = Counter()
    pred_type_counts: Counter[str] = Counter()

    for row in rows:
        ref = row["ref"] or ""

        bpm_hint = extract_bpm_hint(ref)
        bpm_result = classify_bpm_match(
            float(row["bpm"]) if row["bpm"] is not None else None,
            bpm_hint,
        )
        if bpm_result != "no_hint":
            bpm_results[bpm_result] += 1

        key_hint = extract_key_hint(ref)
        if key_hint is not None:
            key_hint_count += 1
            root_match, signature_match = _key_match(row["key"], key_hint)
            key_root_matches += int(root_match)
            key_signature_matches += int(signature_match)

        type_hint = extract_type_hint(ref)
        if type_hint is not None:
            class_hint_count += 1
            class_matches += int(_normalize_class(row["class_name"]) == type_hint)

        instrument_hint = extract_instrument_hint(ref)
        if instrument_hint is not None:
            instrument_hint_count += 1
            instrument_matches += int(
                _normalize_pred_type(row["pred_type"]) == instrument_hint
            )

        class_counts[str(row["class_name"] or "unknown")] += 1
        pred_type_counts[str(row["pred_type"] or "unknown")] += 1

    bpm_hint_count = sum(bpm_results.values())
    with_bpm = len(bpm_values)
    with_key = sum(1 for row in rows if row["key"] is not None)
    with_key_conf = len(key_conf_values)
    with_class = sum(1 for row in rows if row["class_name"] is not None)

    lines: list[str] = [
        "# Sample Brain Validation Report\n\n",
        f"Generated: {datetime.now().isoformat(timespec='seconds')}\n\n",
        "This report uses only aggregate metrics. Raw sample paths are not emitted.\n\n",
        "## Catalog consistency\n",
        f"- Samples: **{sample_count}**\n",
        f"- Feature rows: **{feature_rows}**\n",
        f"- Samples without features: **{missing_features}**\n",
        f"- Orphan feature rows: **{orphan_features}**\n",
        f"- Catalog consistent: **{'YES' if catalog_consistent else 'NO'}**\n\n",
        "## Feature coverage\n",
        f"- With BPM: **{with_bpm}** ({_pct(with_bpm, sample_count):.1f}%)\n",
        f"- With Key: **{with_key}** ({_pct(with_key, sample_count):.1f}%)\n",
        f"- With Key confidence: **{with_key_conf}** ({_pct(with_key_conf, sample_count):.1f}%)\n",
        f"- With Loop/OneShot class: **{with_class}** ({_pct(with_class, sample_count):.1f}%)\n\n",
        "## BPM plausibility — filename weak labels\n",
        f"- Weak BPM labels: **{bpm_hint_count}**\n",
    ]

    for label in ("match", "half_time", "double_time", "mismatch"):
        count = bpm_results[label]
        lines.append(f"- {label}: **{count}** ({_pct(count, bpm_hint_count):.1f}%)\n")

    if bpm_values:
        p10 = _percentile(bpm_values, 0.10)
        p90 = _percentile(bpm_values, 0.90)
        lines.extend(
            [
                "\n## BPM distribution\n",
                "- min / median / max: "
                f"**{format_bpm_display(min(bpm_values))} / "
                f"{format_bpm_display(median(bpm_values))} / "
                f"{format_bpm_display(max(bpm_values))}**\n",
                "- 10th / 90th percentile: "
                f"**{format_bpm_display(p10)} / {format_bpm_display(p90)}**\n",
            ]
        )

    lines.extend(
        [
            "\n## Key plausibility — filename weak labels\n",
            f"- Weak key labels: **{key_hint_count}**\n",
            f"- Root matches: **{key_root_matches}/{key_hint_count}** "
            f"({_pct(key_root_matches, key_hint_count):.1f}%)\n",
            f"- Exact signature matches: **{key_signature_matches}/{key_hint_count}** "
            f"({_pct(key_signature_matches, key_hint_count):.1f}%)\n",
        ]
    )

    if key_conf_values:
        low_key_conf = sum(1 for value in key_conf_values if value < 0.55)
        lines.extend(
            [
                f"- key_conf min / median / max: **{min(key_conf_values):.3f} / "
                f"{median(key_conf_values):.3f} / {max(key_conf_values):.3f}**\n",
                f"- key_conf below FL export gate 0.55: **{low_key_conf}/{len(key_conf_values)}** "
                f"({_pct(low_key_conf, len(key_conf_values)):.1f}%)\n",
            ]
        )

    lines.extend(
        [
            "\n## Autotype quality — path/filename weak labels\n",
            f"- Loop/one-shot weak labels: **{class_hint_count}**\n",
            f"- Loop/one-shot matches: **{class_matches}/{class_hint_count}** "
            f"({_pct(class_matches, class_hint_count):.1f}%)\n",
            f"- Instrument weak labels: **{instrument_hint_count}**\n",
            f"- Instrument matches: **{instrument_matches}/{instrument_hint_count}** "
            f"({_pct(instrument_matches, instrument_hint_count):.1f}%)\n",
            "\nTop classes:\n",
        ]
    )

    for label, count in class_counts.most_common(10):
        lines.append(f"- {label}: {count}\n")

    lines.append("\nTop pred_type values:\n")
    for label, count in pred_type_counts.most_common(10):
        lines.append(f"- {label}: {count}\n")

    lines.extend(
        [
            "\n## Decision notes\n",
            "- Weak labels come only from explicit filename/folder tokens; missing hints are not treated as failures.\n",
            "- `half_time` / `double_time` are reported separately from true BPM mismatches.\n",
            "- Key confidence uses the current 0–1 analyzer scale; the FL export gate is 0.55.\n",
            "- Private catalogs and generated reports remain local and are gitignored.\n",
        ]
    )

    out_path.write_text("".join(lines), encoding="utf-8")

    return {
        "samples": sample_count,
        "feature_rows": feature_rows,
        "catalog_consistent": catalog_consistent,
        "bpm_weak_labels": bpm_hint_count,
        "key_weak_labels": key_hint_count,
        "class_weak_labels": class_hint_count,
        "instrument_weak_labels": instrument_hint_count,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", default="data/catalog.db")
    parser.add_argument("--out", default="reports/VALIDATION_REPORT.md")
    args = parser.parse_args()

    try:
        metrics = generate_report(Path(args.db), Path(args.out))
    except FileNotFoundError:
        print(f"Database not found: {Path(args.db)}", file=sys.stderr)
        raise SystemExit(2)

    print(
        "Wrote validation report: "
        f"samples={metrics['samples']} features={metrics['feature_rows']} "
        f"consistent={metrics['catalog_consistent']}"
    )


if __name__ == "__main__":
    main()
