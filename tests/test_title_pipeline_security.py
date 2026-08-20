from __future__ import annotations

from pathlib import Path

import pytest

from tools.title_pipeline import emit_rename_ps1


@pytest.mark.parametrize(
    "relpath",
    [
        "safe.wav\nWrite-Output INJECTED",
        "safe.wav\rWrite-Output INJECTED",
        "safe.wav\r\nWrite-Output INJECTED",
        "safe.wav\x00Write-Output INJECTED",
        "safe.wav\x1fWrite-Output INJECTED",
    ],
)
def test_rename_preview_does_not_emit_untrusted_relpath_as_powershell(
    tmp_path: Path, relpath: str
) -> None:
    output = tmp_path / "rename.ps1"
    emit_rename_ps1(
        [
            {
                "relpath": relpath,
                "abs_path": r"C:\Samples\safe.wav",
                "new_abs_path": r"C:\Samples\renamed.wav",
            }
        ],
        output,
    )

    script = output.read_text(encoding="utf-8")

    assert "Write-Output INJECTED" not in script
    assert relpath not in script
    assert "$src = 'C:\\Samples\\safe.wav'" in script
    assert "$dst = 'C:\\Samples\\renamed.wav'" in script


def test_rename_preview_still_escapes_single_quotes_in_paths(tmp_path: Path) -> None:
    output = tmp_path / "rename.ps1"
    emit_rename_ps1(
        [
            {
                "relpath": "safe.wav",
                "abs_path": r"C:\Samples\O'Brien.wav",
                "new_abs_path": r"C:\Samples\O'Brien renamed.wav",
            }
        ],
        output,
    )

    script = output.read_text(encoding="utf-8")

    assert "$src = 'C:\\Samples\\O''Brien.wav'" in script
    assert "$dst = 'C:\\Samples\\O''Brien renamed.wav'" in script
