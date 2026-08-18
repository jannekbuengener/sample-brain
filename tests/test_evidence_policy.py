from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

EVIDENCE_DIR = Path(__file__).resolve().parents[1] / "evidence"
MAX_EVIDENCE_BYTES = 100_000

_SENSITIVE_KEYS = {
    "api_key",
    "audio_path",
    "device_id",
    "device_name",
    "file_path",
    "host",
    "hostname",
    "machine",
    "machine_name",
    "sample_path",
    "secret",
    "token",
    "user",
    "user_name",
    "username",
}

_PRIVATE_PATH = re.compile(
    r"(?:^[A-Za-z]:[\\/]|^\\\\|^/(?:home|Users|root|mnt|Volumes|tmp)/)",
    re.IGNORECASE,
)
_SECRET_VALUE = re.compile(
    r"(?i)(?:api[_-]?key|token|secret)\s*[:=]\s*\S+"
)


def _walk(value: Any):
    if isinstance(value, dict):
        for key, child in value.items():
            yield str(key), child
            yield from _walk(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk(child)


def test_curated_evidence_is_small_valid_json_without_private_identity() -> None:
    files = sorted(EVIDENCE_DIR.glob("*.json"))
    assert files, "curated evidence directory must contain validation JSON"

    for path in files:
        assert path.stat().st_size <= MAX_EVIDENCE_BYTES, f"oversized evidence: {path.name}"
        payload = json.loads(path.read_text(encoding="utf-8"))
        assert isinstance(payload, dict), f"evidence must be a JSON object: {path.name}"
        assert payload.get("suite"), f"evidence must identify its validation suite: {path.name}"

        for key, child in _walk(payload):
            assert key.lower() not in _SENSITIVE_KEYS, (
                f"private identity/path field is forbidden in curated evidence: {path.name}:{key}"
            )
            if isinstance(child, str):
                assert not _PRIVATE_PATH.search(child), (
                    f"absolute/private path is forbidden in curated evidence: {path.name}"
                )
                assert not _SECRET_VALUE.search(child), (
                    f"secret-like value is forbidden in curated evidence: {path.name}"
                )
