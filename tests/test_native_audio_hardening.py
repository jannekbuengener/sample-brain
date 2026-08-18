"""
Focused tests for native audio library load hardening (#421).
"""

import ctypes
import os
import platform
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from src import native_audio


def test_platform_lib_filename():
    """Verify platform filename selection per OS contract."""
    with patch("platform.system", return_value="Windows"):
        assert native_audio._get_platform_lib_filename() == "samplebrain_audio.dll"

    with patch("platform.system", return_value="Linux"):
        assert native_audio._get_platform_lib_filename() == "libsamplebrain_audio.so"

    with patch("platform.system", return_value="Darwin"):
        assert native_audio._get_platform_lib_filename() == "libsamplebrain_audio.dylib"


def test_trusted_candidates_absolute_no_bare_fallback():
    """Verify candidate search paths are absolute and derived from package/repo checkout without bare name."""
    candidates = native_audio._get_trusted_candidates()
    assert len(candidates) > 0
    for cand in candidates:
        assert cand.is_absolute()
        assert not cand.name.startswith("samplebrain_audio") or cand.parent != Path(".")
        assert "samplebrain_audio" in cand.name


def test_missing_library_returns_unavailable_without_crash(tmp_path):
    """Verify missing library gracefully yields None without crashing or raising exceptions."""
    with patch("src.native_audio._get_trusted_candidates", return_value=[tmp_path / "libsamplebrain_audio.so"]):
        lib, path = native_audio._load_native_library()
        assert lib is None
        assert path is None


def test_fake_library_missing_symbol_fails_closed(tmp_path):
    """Verify library missing required sb_* symbol fails closed and degrades to unavailable."""
    fake_lib_path = tmp_path / "libsamplebrain_audio.so"
    fake_lib_path.write_bytes(b"fake library content")

    mock_cdll = MagicMock(spec=ctypes.CDLL)
    # Simulate missing sb_engine_open symbol
    del mock_cdll.sb_engine_open

    with patch("src.native_audio._get_trusted_candidates", return_value=[fake_lib_path]):
        with patch("ctypes.CDLL", return_value=mock_cdll):
            lib, path = native_audio._load_native_library()
            assert lib is None
            assert path is None


def test_valid_library_loads_and_verifies_symbols(tmp_path):
    """Verify valid library with all required symbols loads successfully."""
    fake_lib_path = tmp_path / "libsamplebrain_audio.so"
    fake_lib_path.write_bytes(b"fake library content")

    mock_cdll = MagicMock(spec=ctypes.CDLL)
    for sym in native_audio._REQUIRED_SB_SYMBOLS:
        setattr(mock_cdll, sym, MagicMock())

    with patch("src.native_audio._get_trusted_candidates", return_value=[fake_lib_path]):
        with patch("src.native_audio._get_trusted_roots", return_value=[tmp_path]):
            with patch("ctypes.CDLL", return_value=mock_cdll):
                lib, path = native_audio._load_native_library()
                assert lib is mock_cdll
                assert path == fake_lib_path


def test_escaped_symlink_candidate_rejected_and_cdll_not_called(tmp_path):
    """Verify symlink pointing outside trusted roots is rejected and ctypes.CDLL is never called."""
    allowed_dir = tmp_path / "allowed"
    allowed_dir.mkdir()
    outside_dir = tmp_path / "outside"
    outside_dir.mkdir()

    outside_target = outside_dir / "libsamplebrain_audio.so"
    outside_target.write_bytes(b"outside binary content")

    escaped_candidate = allowed_dir / "libsamplebrain_audio.so"

    if hasattr(os, "symlink"):
        try:
            os.symlink(outside_target, escaped_candidate)
        except OSError:
            pytest.skip("Symlinks not supported on this platform/permission level")
    else:
        pytest.skip("Symlinks not supported on this platform")

    with patch("src.native_audio._get_trusted_candidates", return_value=[escaped_candidate]):
        with patch("src.native_audio._get_trusted_roots", return_value=[allowed_dir]):
            with patch("ctypes.CDLL") as mock_cdll:
                lib, path = native_audio._load_native_library()
                assert lib is None
                assert path is None
                mock_cdll.assert_not_called()
