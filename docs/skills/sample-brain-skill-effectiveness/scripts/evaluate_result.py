#!/usr/bin/env python3
"""Deterministic helpers for sample-brain-skill-effectiveness results.

Validates evaluation result documents, rejects incomplete comparisons, and
computes verdicts for structured observation records. Agent judgment remains
outside this script; this only enforces the result contract.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

VERDICTS = frozenset({"EFFECTIVE", "INEFFECTIVE", "UNNECESSARY", "INCOMPLETE"})
SKILL_TYPES = frozenset({"discipline", "technique", "pattern", "reference"})
OUTCOMES = frozenset({"pass", "fail", "partial", "not_run"})
ACTIVATION_POS = frozenset({"used", "not_used", "unknown"})
ACTIVATION_NEG = frozenset({"correctly_idle", "false_positive", "unknown"})

REQUIRED_TOP = (
    "target_skill",
    "target_revision",
    "skill_type",
    "scenario_id",
    "baseline",
    "skill_enabled",
    "delta",
    "activation",
    "transfer",
    "verdict",
)

INCOMPLETE_REASONS = frozenset(
    {
        "missing_baseline",
        "inequivalent_inputs",
        "skill_not_loaded",
        "structural_only",
        "missing_required_fields",
        "invalid_skill_type",
        "missing_delta",
        "agent_run_unavailable",
    }
)


def _as_dict(value: Any, label: str, problems: list[str]) -> dict[str, Any]:
    if not isinstance(value, dict):
        problems.append(f"{label} must be a mapping")
        return {}
    return value


def parse_simple_yaml(text: str) -> dict[str, Any]:
    """Parse a restricted YAML-like subset used by evaluation evidence.

    Supports nested maps via indentation (2 spaces), scalars, booleans, null,
    integers, and inline lists of scalars. Not a general YAML parser.
    """
    lines: list[str] = []
    for raw in text.splitlines():
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        lines.append(raw.rstrip())

    root: dict[str, Any] = {}
    stack: list[tuple[int, dict[str, Any]]] = [(-1, root)]

    def parse_scalar(raw: str) -> Any:
        value = raw.strip()
        if value in {"true", "True"}:
            return True
        if value in {"false", "False"}:
            return False
        if value in {"null", "Null", "~", ""}:
            return None
        if re.fullmatch(r"-?\d+", value):
            return int(value)
        if value.startswith("[") and value.endswith("]"):
            inner = value[1:-1].strip()
            if not inner:
                return []
            return [parse_scalar(part) for part in inner.split(",")]
        if (value.startswith('"') and value.endswith('"')) or (
            value.startswith("'") and value.endswith("'")
        ):
            return value[1:-1]
        return value

    i = 0
    while i < len(lines):
        line = lines[i]
        indent = len(line) - len(line.lstrip(" "))
        if ":" not in line:
            raise ValueError(f"unsupported line (missing ':'): {line}")
        key, _, rest = line.lstrip(" ").partition(":")
        key = key.strip()
        rest = rest.strip()

        while stack and indent <= stack[-1][0]:
            stack.pop()
        if not stack:
            raise ValueError(f"invalid indentation near: {line}")
        parent = stack[-1][1]

        if rest in {">", ">-", "|", "|-"}:
            block_lines: list[str] = []
            i += 1
            while i < len(lines):
                nxt = lines[i]
                nxt_indent = len(nxt) - len(nxt.lstrip(" "))
                if nxt_indent <= indent:
                    break
                block_lines.append(nxt[indent + 2 :] if nxt_indent >= indent + 2 else nxt.lstrip(" "))
                i += 1
            # folded (>) joins with spaces; literal (|) keeps newlines
            if rest.startswith(">"):
                parent[key] = " ".join(part.strip() for part in block_lines if part.strip())
            else:
                parent[key] = "\n".join(block_lines).rstrip("\n")
            continue

        if rest == "":
            # Peek: sequence of "- item" lines => list; else nested mapping.
            if i + 1 < len(lines):
                peek = lines[i + 1]
                peek_indent = len(peek) - len(peek.lstrip(" "))
                if peek_indent > indent and peek.lstrip(" ").startswith("- "):
                    items: list[Any] = []
                    i += 1
                    while i < len(lines):
                        nxt = lines[i]
                        nxt_indent = len(nxt) - len(nxt.lstrip(" "))
                        if nxt_indent <= indent or not nxt.lstrip(" ").startswith("- "):
                            break
                        item_raw = nxt.lstrip(" ")[2:].strip()
                        if item_raw.endswith(":") or (":" in item_raw and not item_raw.startswith('"')):
                            # mapping list item: "- id: value" (+ optional indented keys)
                            item_map: dict[str, Any] = {}
                            if ":" in item_raw:
                                ik, _, iv = item_raw.partition(":")
                                item_map[ik.strip()] = parse_scalar(iv.strip()) if iv.strip() else None
                            i += 1
                            while i < len(lines):
                                nested = lines[i]
                                nested_indent = len(nested) - len(nested.lstrip(" "))
                                if nested_indent <= nxt_indent or nested.lstrip(" ").startswith("- "):
                                    break
                                if ":" not in nested:
                                    raise ValueError(f"unsupported list map line: {nested}")
                                nk, _, nv = nested.lstrip(" ").partition(":")
                                item_map[nk.strip()] = parse_scalar(nv.strip())
                                i += 1
                            items.append(item_map)
                            continue
                        items.append(parse_scalar(item_raw))
                        i += 1
                    parent[key] = items
                    continue
            child: dict[str, Any] = {}
            parent[key] = child
            stack.append((indent, child))
        else:
            parent[key] = parse_scalar(rest)
        i += 1

    return root


def load_result(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    if path.suffix.lower() == ".json":
        data = json.loads(text)
        if not isinstance(data, dict):
            raise ValueError("JSON result must be an object")
        return data
    return parse_simple_yaml(text)


def validate_result(data: dict[str, Any]) -> list[str]:
    problems: list[str] = []
    for key in REQUIRED_TOP:
        if key not in data:
            problems.append(f"missing required field: {key}")

    skill_type = data.get("skill_type")
    if skill_type is not None and skill_type not in SKILL_TYPES:
        problems.append(f"invalid skill_type: {skill_type}")

    verdict = data.get("verdict")
    if verdict is not None and verdict not in VERDICTS:
        problems.append(f"invalid verdict: {verdict}")

    baseline = _as_dict(data.get("baseline"), "baseline", problems)
    skill_enabled = _as_dict(data.get("skill_enabled"), "skill_enabled", problems)
    delta = _as_dict(data.get("delta"), "delta", problems)
    activation = _as_dict(data.get("activation"), "activation", problems)
    transfer = _as_dict(data.get("transfer"), "transfer", problems)

    for label, block in (("baseline", baseline), ("skill_enabled", skill_enabled)):
        if not block:
            continue
        outcome = block.get("outcome")
        if outcome is not None and outcome not in OUTCOMES:
            problems.append(f"{label}.outcome invalid: {outcome}")
        if "ran" in block and not isinstance(block["ran"], bool):
            problems.append(f"{label}.ran must be bool")

    if skill_enabled and "skill_loaded" in skill_enabled:
        if not isinstance(skill_enabled["skill_loaded"], bool):
            problems.append("skill_enabled.skill_loaded must be bool")

    if activation:
        pos = activation.get("positive")
        neg = activation.get("negative")
        if pos is not None and pos not in ACTIVATION_POS:
            problems.append(f"activation.positive invalid: {pos}")
        if neg is not None and neg not in ACTIVATION_NEG:
            problems.append(f"activation.negative invalid: {neg}")

    if transfer:
        for key in ("variants_passed", "counterexamples_passed"):
            if key in transfer and not isinstance(transfer[key], int):
                problems.append(f"transfer.{key} must be int")

    if delta and "improved" in delta and not isinstance(delta["improved"], bool):
        problems.append("delta.improved must be bool")

    if data.get("verdict") == "INCOMPLETE":
        reason = data.get("incomplete_reason")
        if not reason:
            problems.append("INCOMPLETE requires incomplete_reason")
        elif reason not in INCOMPLETE_REASONS:
            problems.append(f"unknown incomplete_reason: {reason}")

    if "confidence" in data or "confidence_percent" in data:
        problems.append("confidence percentages are forbidden")

    return problems


def detect_incomplete(data: dict[str, Any]) -> str | None:
    """Return incomplete_reason if evaluation cannot produce a closed verdict."""
    if data.get("structural_only") is True:
        return "structural_only"
    if data.get("inputs_comparable") is False:
        return "inequivalent_inputs"
    baseline = data.get("baseline") or {}
    skill_enabled = data.get("skill_enabled") or {}
    if not isinstance(baseline, dict) or baseline.get("ran") is not True:
        return "missing_baseline"
    if baseline.get("outcome") == "not_run":
        return "missing_baseline"
    if not isinstance(skill_enabled, dict):
        return "skill_not_loaded"
    if skill_enabled.get("skill_loaded") is False:
        return "skill_not_loaded"
    if skill_enabled.get("ran") is not True:
        return "agent_run_unavailable"
    if data.get("skill_type") not in SKILL_TYPES:
        return "invalid_skill_type"
    if not isinstance(data.get("delta"), dict):
        return "missing_delta"
    return None


def compute_verdict(data: dict[str, Any]) -> str:
    """Compute closed or incomplete verdict from structured observations."""
    incomplete = detect_incomplete(data)
    if incomplete:
        return "INCOMPLETE"

    baseline = data["baseline"]
    skill_enabled = data["skill_enabled"]
    delta = data["delta"]
    activation = data.get("activation") or {}
    transfer = data.get("transfer") or {}

    base_outcome = baseline.get("outcome")
    skill_outcome = skill_enabled.get("outcome")
    improved = bool(delta.get("improved"))
    material = bool(delta.get("material_change", improved))
    positive = activation.get("positive")
    negative = activation.get("negative")
    overconstraint = transfer.get("overconstraint")

    # Baseline already satisfied the success criteria without the skill.
    if base_outcome == "pass" and skill_outcome == "pass" and not material:
        return "UNNECESSARY"

    if (
        base_outcome == "fail"
        and skill_outcome == "pass"
        and improved
        and material
        and positive == "used"
        and negative in {"correctly_idle", "unknown"}
        and overconstraint is not True
    ):
        return "EFFECTIVE"

    if base_outcome == "fail" and skill_outcome in {"fail", "partial"}:
        return "INEFFECTIVE"

    if skill_outcome == "fail" and improved is False:
        return "INEFFECTIVE"

    if overconstraint is True and not improved:
        return "INEFFECTIVE"

    # Ambiguous partial improvements stay incomplete rather than forced closed.
    if skill_outcome == "partial" or positive == "unknown":
        return "INCOMPLETE"

    if improved and material and positive == "used":
        return "EFFECTIVE"

    return "INEFFECTIVE"


def finalize_result(data: dict[str, Any]) -> dict[str, Any]:
    """Validate/normalize and attach computed verdict when possible."""
    out = dict(data)
    incomplete = detect_incomplete(out)
    if incomplete:
        out["verdict"] = "INCOMPLETE"
        out["incomplete_reason"] = incomplete
        return out

    out["verdict"] = compute_verdict(out)
    if out["verdict"] != "INCOMPLETE":
        out.pop("incomplete_reason", None)
    elif "incomplete_reason" not in out:
        out["incomplete_reason"] = "missing_required_fields"
    return out


def score_activation_markers(
    text: str,
    *,
    positive_markers: list[str],
    negative_markers: list[str] | None = None,
) -> dict[str, Any]:
    """Deterministic activation fixture helper for recorded agent outputs."""
    lowered = text.lower()
    pos_hits = [m for m in positive_markers if m.lower() in lowered]
    neg_hits = [m for m in (negative_markers or []) if m.lower() in lowered]
    return {
        "positive_hits": pos_hits,
        "negative_hits": neg_hits,
        "activated": bool(pos_hits),
        "overconstraint_signal": bool(neg_hits) and not bool(pos_hits),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Validate and/or compute sample-brain-skill-effectiveness results"
    )
    parser.add_argument("path", type=Path, help="Path to result .yml/.yaml/.json")
    parser.add_argument(
        "--compute",
        action="store_true",
        help="Recompute verdict from observations and print finalized result JSON",
    )
    parser.add_argument(
        "--check-only",
        action="store_true",
        help="Validate schema only; do not recompute verdict",
    )
    args = parser.parse_args(argv)

    data = load_result(args.path)
    problems = validate_result(data)

    if args.compute:
        finalized = finalize_result(data)
        # Re-validate after finalize so INCOMPLETE shape is checked.
        problems = validate_result(finalized)
        print(json.dumps(finalized, indent=2, sort_keys=True))
        if problems:
            for problem in problems:
                print(f"ERROR: {problem}", file=sys.stderr)
            return 1
        return 0

    if problems:
        for problem in problems:
            print(f"ERROR: {problem}", file=sys.stderr)
        return 1

    if not args.check_only:
        expected = compute_verdict(data) if detect_incomplete(data) is None else "INCOMPLETE"
        if data.get("verdict") != expected and data.get("verdict") != "INCOMPLETE":
            # Allow explicit INCOMPLETE overrides only when incomplete_reason set.
            if not (data.get("verdict") == "INCOMPLETE" and data.get("incomplete_reason")):
                print(
                    f"ERROR: recorded verdict {data.get('verdict')!r} != computed {expected!r}",
                    file=sys.stderr,
                )
                return 1
        incomplete = detect_incomplete(data)
        if incomplete and data.get("verdict") != "INCOMPLETE":
            print(
                f"ERROR: result must be INCOMPLETE ({incomplete}), got {data.get('verdict')!r}",
                file=sys.stderr,
            )
            return 1

    print("OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
