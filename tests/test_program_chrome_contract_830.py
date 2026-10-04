"""#830 program chrome contract — docs gate only (no runtime change)."""

from __future__ import annotations

from pathlib import Path


def test_program_chrome_contract_is_canonically_linked() -> None:
    index = Path("docs/CANON_INDEX.md").read_text(encoding="utf-8")
    assert "docs/PROGRAM_CHROME_CONTRACT.md" in index
    assert "#830" in index


def test_program_chrome_contract_names_owner_reference() -> None:
    text = Path("docs/PROGRAM_CHROME_CONTRACT.md").read_text(encoding="utf-8")
    assert "ba928fbe-e27d-4177-8d13-608e9eb2a7e0" in text
    assert "owner_program_chrome_ba928fbe.jpg" in text
    assert "5ae5703a74d02af175d2f47b8802f4a96b3783b8be69ad6be86ef4f832a20183" in text
    assert "Pattern / BARS" in text or "Pattern/Bars" in text
    assert "Navigation is center" in text or "navigation center" in text.lower()


def test_program_chrome_contract_documents_831_test_supersession() -> None:
    text = Path("docs/PROGRAM_CHROME_CONTRACT.md").read_text(encoding="utf-8")
    assert "Implementation test supersession (#831)" in text
    assert "test_workbench_qml_producer_command_zone.py" in text
    assert "test_workbench_qml_screen2_channel_rack.py" in text
