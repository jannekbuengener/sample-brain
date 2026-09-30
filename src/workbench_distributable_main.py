"""Double-click GUI entry for the Screen-1 Windows distributable (#729).

Starts only the production QML Screen-1 path. Sets Windows pilot state defaults
when no explicit environment overrides are present; does not change Linux/dev
defaults for non-distributable launches.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path


_STATE_ENV = "SAMPLE_BRAIN_WORKBENCH_STATE_DIR"
_DB_ENV = "SAMPLE_BRAIN_DB_PATH"


def apply_windows_distributable_defaults(*, env: dict[str, str] | None = None) -> Path | None:
    """Apply LocalAppData state defaults for the Windows distributable launcher.

    Returns the resolved state directory when defaults were applied or an
    existing override was present on Windows; otherwise None.
    """
    env_map = os.environ if env is None else env
    if sys.platform != "win32":
        return None

    existing = (env_map.get(_STATE_ENV) or "").strip()
    if existing:
        state = Path(existing).expanduser()
    else:
        local = (env_map.get("LOCALAPPDATA") or "").strip()
        if not local:
            return None
        state = Path(local) / "SampleBrain" / "state"
        env_map[_STATE_ENV] = str(state)

    if not (env_map.get(_DB_ENV) or "").strip():
        env_map[_DB_ENV] = str(state / "catalog.db")

    state.mkdir(parents=True, exist_ok=True)
    return state


def main() -> int:
    # Marks this process as the Windows distributable so native audio may load
    # samplebrain_audio.dll from the executable directory (trusted packaging path).
    os.environ.setdefault("SAMPLE_BRAIN_DISTRIBUTABLE", "1")
    apply_windows_distributable_defaults()
    # #region agent log
    def _dbg760(message: str, data: dict, hypothesis_id: str) -> None:
        import json
        import time
        from pathlib import Path

        payload = {
            "sessionId": "676a9f",
            "runId": "post-fix",
            "hypothesisId": hypothesis_id,
            "location": "workbench_distributable_main.py:main",
            "message": message,
            "data": data,
            "timestamp": int(time.time() * 1000),
        }
        try:
            log_path = Path(__file__).resolve().parents[1] / "debug-676a9f.log"
            with log_path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(payload, ensure_ascii=True) + "\n")
        except Exception:
            pass

    _dbg760("distributable_main_before_qml_import", {"platform": sys.platform}, "D")
    # #endregion
    try:
        from .workbench_qml import run_qml_screen1
    except Exception as exc:
        # #region agent log
        _dbg760(
            "distributable_main_qml_import_failed",
            {"type": type(exc).__name__, "msg": str(exc)[:300]},
            "D",
        )
        # #endregion
        raise
    # #region agent log
    _dbg760("distributable_main_qml_imported", {}, "D")
    # #endregion

    result = run_qml_screen1()
    return int(result or 0)


if __name__ == "__main__":
    raise SystemExit(main())
