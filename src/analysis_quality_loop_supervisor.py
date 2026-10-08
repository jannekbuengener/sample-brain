"""Sample Brain analysis quality-loop supervisor composition v1 (#1097).

Import scaffold only — composition is implemented in the supervisor task.
"""

from __future__ import annotations

from typing import Any, Mapping


class AnalysisQualityLoopSupervisorError(ValueError):
    """Raised when supervisor composition violates the v1 contract."""


def run_supervisor_step(**_kwargs: Any) -> dict[str, Any]:
    """Placeholder until supervisor composition is implemented."""
    raise AnalysisQualityLoopSupervisorError(
        "supervisor composition not implemented"
    )


# Re-export seam name expected by infrastructure-failure tests.
def run_orchestration(*_args: Any, **_kwargs: Any) -> Mapping[str, Any]:
    raise AnalysisQualityLoopSupervisorError(
        "supervisor composition not implemented"
    )


__all__ = [
    "AnalysisQualityLoopSupervisorError",
    "run_orchestration",
    "run_supervisor_step",
]
