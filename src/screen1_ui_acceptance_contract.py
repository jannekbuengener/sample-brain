"""Screen-1 UI acceptance contract — result model and case definitions.

No Windows-MCP dependency. Desktop automation backends are host-local.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any


SCHEMA_VERSION = 1


class CaseResult(str, Enum):
    PASS = "pass"
    FAIL = "fail"
    PARTIAL = "partial"
    BLOCKED = "blocked"


class DiscoveryMethod(str, Enum):
    UIA = "uia"
    VISUAL_FALLBACK = "visual_fallback"
    NOT_AVAILABLE = "not_available"


class RunPhase(str, Enum):
    PRECHECK = "precheck"
    START_APP = "start_app"
    FOCUS_APP = "focus_app"
    SNAPSHOT_INITIAL = "snapshot_initial"
    RUN_CASES = "run_cases"
    RESTORE = "restore"
    CAPTURE_EVIDENCE = "capture_evidence"
    FINAL_RESULT = "final_result"


CASE_APP_START = "app_start"
CASE_DISPLAY_PREFERENCES = "display_preferences"
CASE_HARMONIC_MATCH = "harmonic_match"

DISPLAY_PREFERENCES_NAME = "Display preferences"
HARMONIC_MATCH_NAME = "Harmonic Match"
APP_WINDOW_TITLE = "Sample Brain"

DISPLAY_PREFERENCES_OPEN_MARKERS: tuple[str, ...] = (
    "Reset Layout",
    "Save Workspace Preset",
    "Set Preset as Startup",
    "Return to Clean Start",
    "Density",
    "Motion",
)

V1_CASES: tuple[str, ...] = (
    CASE_APP_START,
    CASE_DISPLAY_PREFERENCES,
    CASE_HARMONIC_MATCH,
)


@dataclass
class CaseReport:
    schema_version: int = SCHEMA_VERSION
    case: str = ""
    result: str = CaseResult.BLOCKED.value
    discovery: str = DiscoveryMethod.NOT_AVAILABLE.value
    verification: list[str] = field(default_factory=list)
    evidence: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class RunReport:
    schema_version: int = SCHEMA_VERSION
    run_id: str = ""
    result: str = CaseResult.BLOCKED.value
    phases: list[str] = field(default_factory=list)
    cases: list[dict[str, Any]] = field(default_factory=list)
    evidence_dir: str = ""
    accessibility_followups: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def aggregate_run_result(case_results: list[CaseResult]) -> CaseResult:
    """Fail-closed aggregate: FAIL > BLOCKED > PARTIAL > PASS."""
    if not case_results:
        return CaseResult.BLOCKED
    if any(r is CaseResult.FAIL for r in case_results):
        return CaseResult.FAIL
    if any(r is CaseResult.BLOCKED for r in case_results):
        return CaseResult.BLOCKED
    if any(r is CaseResult.PARTIAL for r in case_results):
        return CaseResult.PARTIAL
    return CaseResult.PASS


def exit_code_for(result: CaseResult) -> int:
    """Non-zero for real acceptance failure; PARTIAL is non-zero to stay fail-closed for CI."""
    if result is CaseResult.PASS:
        return 0
    if result is CaseResult.PARTIAL:
        return 2
    if result is CaseResult.BLOCKED:
        return 3
    return 1


def parse_case_result(value: str) -> CaseResult:
    normalized = str(value or "").strip().lower()
    try:
        return CaseResult(normalized)
    except ValueError as exc:
        raise ValueError(f"unknown case result: {value!r}") from exc


def parse_discovery(value: str) -> DiscoveryMethod:
    normalized = str(value or "").strip().lower()
    try:
        return DiscoveryMethod(normalized)
    except ValueError as exc:
        raise ValueError(f"unknown discovery method: {value!r}") from exc


def validate_case_report_dict(payload: dict[str, Any]) -> list[str]:
    """Return validation errors for a case JSON payload (empty == ok)."""
    errors: list[str] = []
    if int(payload.get("schema_version", -1)) != SCHEMA_VERSION:
        errors.append("schema_version must be 1")
    case = str(payload.get("case", ""))
    if case not in V1_CASES:
        errors.append(f"case must be one of {V1_CASES}")
    try:
        parse_case_result(str(payload.get("result", "")))
    except ValueError as exc:
        errors.append(str(exc))
    try:
        parse_discovery(str(payload.get("discovery", "")))
    except ValueError as exc:
        errors.append(str(exc))
    if not isinstance(payload.get("verification", []), list):
        errors.append("verification must be a list")
    if not isinstance(payload.get("evidence", []), list):
        errors.append("evidence must be a list")
    result = str(payload.get("result", "")).lower()
    discovery = str(payload.get("discovery", "")).lower()
    if result == CaseResult.PASS.value and discovery == DiscoveryMethod.NOT_AVAILABLE.value:
        errors.append("PASS requires discovery other than not_available")
    if (
        case == CASE_DISPLAY_PREFERENCES
        and result == CaseResult.PASS.value
        and discovery != DiscoveryMethod.UIA.value
    ):
        errors.append("display_preferences PASS requires discovery=uia")
    return errors


ACCESSIBILITY_FOLLOWUPS_V1: tuple[str, ...] = (
    "Browser ListView rows are not exposed in the Windows UIA tree; sample selection needs Accessible metadata or a dedicated AutomationId.",
    "Harmonic Match pane open-state / 'Harmonic Matches' title is not reliably exposed in UIA; prefer Accessible.name on the pane root.",
    "harmonicMatchButton currently relies on Button.text for UIA Name; add Accessible.name: \"Harmonic Match\" for stability.",
)
