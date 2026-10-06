"""Frozen Screen-1 brand-asset packaging contract tests.

Proves the PyInstaller onedir spec carries exactly the assets the distributable
Screen-1 runtime actually consumes, and that the packaged destinations line up
with what the runtime resolvers expect inside a frozen build.

Frozen-path mechanics (proven against PyInstaller 6.17.0 onedir):
- ``datas`` entries land under ``<bundle>/_internal/<dest>``,
- FrozenImporter sets bundled-module ``__file__`` to
  ``<_internal>/<module>.pyc``, so ``Path(__file__).resolve().parents[1]``
  for a ``src/``-layout module equals ``<bundle>/_internal`` — the same root
  the resolvers use (``_repo_root()``) and the same root PyInstaller fills
  with ``datas``.

The spec is parsed statically (ast) — no PyInstaller build and no PyInstaller
dependency is required to prove the contract.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from src.workbench_brand_motion import resolve_brand_slots

REPO_ROOT = Path(__file__).resolve().parents[1]
SPEC_PATH = REPO_ROOT / "tools" / "windows" / "sample_brain_screen1.spec"

INTERNAL = "_internal"
LOGO_RELATIVE = Path("docs/assets/portfolio/references/brand/sample_brain_logo_primary.png")
BACKGROUND_RELATIVE = Path(
    "docs/assets/portfolio/references/screen1_background_reference.png"
)


def _spec_source() -> str:
    return SPEC_PATH.read_text(encoding="utf-8")


def _spec_tree() -> ast.Module:
    return ast.parse(_spec_source(), filename=str(SPEC_PATH))


def _spec_env(tree: ast.Module) -> dict[str, ast.AST]:
    """Module-level single-assignment names -> value nodes (for Name lookup)."""
    env: dict[str, ast.AST] = {}
    for node in tree.body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1:
            target = node.targets[0]
            if isinstance(target, ast.Name):
                env[target.id] = node.value
    return env


def _literal(
    node: ast.AST, env: dict[str, ast.AST], depth: int = 0
) -> str | None:
    """Evaluate simple string/join expressions from the spec AST to posix text."""
    if depth > 16:
        return None
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value.replace("\\", "/")
    if isinstance(node, ast.Name):
        assigned = env.get(node.id)
        return None if assigned is None else _literal(assigned, env, depth + 1)
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
        if node.func.id == "str" and len(node.args) == 1:
            return _literal(node.args[0], env, depth + 1)
        if node.func.id == "Path":
            parts = [_literal(arg, env, depth + 1) for arg in node.args]
            if any(part is None for part in parts):
                return None
            return "/".join(part for part in parts if part)
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Div):
        left = _literal(node.left, env, depth + 1)
        right = _literal(node.right, env, depth + 1)
        if left is None or right is None:
            return None
        return f"{left}/{right}"
    return None


def _logo_entry(entries: list[tuple[str, str]]) -> tuple[str, str]:
    logo = [entry for entry in entries if entry[0].endswith(LOGO_RELATIVE.name)]
    assert len(logo) == 1, f"expected exactly one logo datas entry, got {logo}"
    return logo[0]


def _literal_or_tail(
    node: ast.AST, env: dict[str, ast.AST], depth: int = 0
) -> str | None:
    """Full literal, or the resolvable right-hand tail of a path-join chain.

    Spec sources start with ``REPO`` (``Path(SPECPATH).resolve().parents[1]``),
    which is not statically resolvable; the meaningful static part of a datas
    source is the asset filename tail.
    """
    value = _literal(node, env, depth)
    if value is not None:
        return value
    if isinstance(node, ast.Name):
        assigned = env.get(node.id)
        if assigned is not None:
            return _literal_or_tail(assigned, env, depth + 1)
        return None
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
        if node.func.id == "str" and len(node.args) == 1:
            return _literal_or_tail(node.args[0], env, depth + 1)
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Div):
        return _literal_or_tail(node.right, env, depth + 1)
    return None


def _spec_datas(tree: ast.Module) -> list[tuple[str, str]]:
    """Extract the static (source, dest) pairs appended to the spec datas list."""
    env = _spec_env(tree)
    entries: list[tuple[str, str]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if not (isinstance(func, ast.Attribute) and func.attr == "append"):
            continue
        target = func.value
        if not (isinstance(target, ast.Name) and target.id == "datas"):
            continue
        pair_args: list[ast.AST]
        if (
            len(node.args) == 1
            and isinstance(node.args[0], (ast.Tuple, ast.List))
            and len(node.args[0].elts) == 2
        ):
            pair_args = list(node.args[0].elts)
        elif len(node.args) == 2:
            pair_args = list(node.args)
        else:
            continue
        src, dest = _literal_or_tail(pair_args[0], env), _literal(pair_args[1], env)
        if src is None or dest is None:
            continue
        entries.append((src, dest))
    return entries


def test_required_brand_logo_is_packed_for_the_distributable_runtime() -> None:
    """analysisBrandBrain consumes the primary logo; the spec must pack it."""
    _logo_entry(_spec_datas(_spec_tree()))

    # Runtime truth: the slot relative path owns the filename and directory.
    slots = resolve_brand_slots()
    assert slots["brain_symbol"].relative_path == LOGO_RELATIVE.as_posix()
    assert slots["brain_symbol"].path.is_file()
    assert slots["brain_symbol"].sha256 == (
        "6e8ba304d216e8f1ba0e819603388dc37ff18491fe1a3e22b985513258882605"
    )


def test_packaged_logo_destination_matches_frozen_resolver_root() -> None:
    """dest + _internal root == the path resolve_brand_slots() expects frozen."""
    logo = _logo_entry(_spec_datas(_spec_tree()))
    assert logo[1] == LOGO_RELATIVE.parent.as_posix(), (
        "datas dest must equal the slot relative dir so the frozen "
        "_repo_root() (== _internal) resolves the bundled file"
    )


def test_spec_does_not_hard_require_the_historical_background_reference() -> None:
    """The hidden historical seam is not a required frozen runtime asset."""
    source = _spec_source()
    assert "REQUIRED Screen-1 background missing" not in source
    entries = _spec_datas(_spec_tree())
    assert not [e for e in entries if e[0].endswith(BACKGROUND_RELATIVE.name)], (
        "background reference PNG is V7-rejected historical evidence; the "
        "distributable must not pack or require it"
    )


def test_spec_gate_targets_the_real_required_asset() -> None:
    """A fail-closed gate stays — but only for the consumed brand asset."""
    source = _spec_source()
    assert "REQUIRED Screen-1 brand asset missing" in source


def test_splash_typography_is_not_packed_without_a_runtime_consumer() -> None:
    """The splash slot has no QML binding in the distributable path."""
    entries = _spec_datas(_spec_tree())
    assert not [e for e in entries if "sample_brain_splash_typography" in e[0]]


def test_qml_binds_the_primary_logo_from_the_brand_runtime_payload() -> None:
    """Runtime-consumer proof: the bundled logo URL feeds analysisBrandBrain."""
    from src import workbench_qml

    assert "source: window.screenData.brandBrainUrl" in workbench_qml.QML_SOURCE
    assert 'objectName: "analysisBrandBrain"' in workbench_qml.QML_SOURCE


def test_frozen_repo_root_semantics_align_with_datas_root(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Simulate the frozen layout: __file__ inside _internal, datas beside it."""
    import src.workbench_brand_motion as brand_motion

    internal = tmp_path / INTERNAL
    fake_module = internal / "src" / "workbench_brand_motion.py"
    fake_module.parent.mkdir(parents=True)
    fake_module.write_text("", encoding="utf-8")

    bundled_logo = internal / LOGO_RELATIVE
    bundled_logo.parent.mkdir(parents=True)
    bundled_logo.write_bytes((REPO_ROOT / LOGO_RELATIVE).read_bytes())

    monkeypatch.setattr(brand_motion, "__file__", str(fake_module), raising=False)
    slots = resolve_brand_slots()
    assert slots["brain_symbol"].path == bundled_logo.resolve()
    assert slots["brain_symbol"].path.is_file()
