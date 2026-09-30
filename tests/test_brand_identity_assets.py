"""Brand identity reference assets — byte integrity (#771 polish slice)."""

from __future__ import annotations

import hashlib
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
BRAND_DIR = REPO_ROOT / "docs" / "assets" / "portfolio" / "references" / "brand"

EXPECTED = {
    "sample_brain_logo_primary.png": (
        "6e8ba304d216e8f1ba0e819603388dc37ff18491fe1a3e22b985513258882605"
    ),
    "sample_brain_splash_typography.png": (
        "eb130874c65ce8c1e36500b56e3cb1328318d6ac439fd13305547949994a83f6"
    ),
}


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_brand_reference_assets_exist_with_expected_sha256() -> None:
    for name, digest in EXPECTED.items():
        path = BRAND_DIR / name
        assert path.is_file(), f"missing brand asset: {path}"
        assert _sha256(path) == digest


def test_brand_docs_list_repo_paths_without_local_windows_sources() -> None:
    doc = (REPO_ROOT / "docs" / "WORKBENCH_VISUAL_ACCEPTANCE.md").read_text(
        encoding="utf-8"
    )
    assert "## Brand identity references" in doc
    assert "docs/assets/portfolio/references/brand/sample_brain_logo_primary.png" in doc
    assert (
        "docs/assets/portfolio/references/brand/sample_brain_splash_typography.png"
        in doc
    )
    assert EXPECTED["sample_brain_logo_primary.png"] in doc
    assert EXPECTED["sample_brain_splash_typography.png"] in doc
    assert "C:\\Users\\" not in doc
    assert "Desktop\\logos" not in doc
