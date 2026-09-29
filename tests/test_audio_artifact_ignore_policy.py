from __future__ import annotations

from pathlib import Path

from src.config import AUDIO_EXTS

ROOT = Path(__file__).resolve().parents[1]


def test_gitignore_covers_all_supported_data_audio_extensions() -> None:
    patterns = {
        line.strip()
        for line in (ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    }

    missing = sorted(
        ext for ext in AUDIO_EXTS if f"data/**/*{ext.lower()}" not in patterns
    )
    assert not missing, f"supported sample extensions missing from .gitignore: {missing}"


def test_artifact_policy_names_all_supported_sample_audio_extensions() -> None:
    policy = (ROOT / "docs" / "DATA_AND_ARTIFACT_POLICY.md").read_text(
        encoding="utf-8"
    ).lower()

    missing = sorted(ext for ext in AUDIO_EXTS if `\`${ext.lower()}\`` not in policy)
    assert not missing, f"supported sample extensions missing from artifact policy: {missing}"
