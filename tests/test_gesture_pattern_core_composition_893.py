"""Frozen acceptance for R&D Slice 6 — Pattern Core composition (#680 / #893).

Docs authority: docs/GESTURE_PATTERN_CORE_COMPOSITION_RND_SLICE6.md

Frozen acceptance for implemented src/gesture_pattern_core_composition.py.
Synthetic fixtures only — no audio, no DB, no private catalogs.
"""

from __future__ import annotations

import ast
import copy
import importlib
import inspect
from fractions import Fraction
from pathlib import Path
from unittest import mock

import pytest

from src.gesture_library_ranking import (
    ClusterRanking,
    LibraryCandidate,
    RankedCandidate,
)
from src.gesture_pattern_binding import (
    GesturePatternBindingPlan,
    PlannedGestureChannelBinding,
    PlannedGestureEventBinding,
    plan_gesture_pattern_binding,
)
from src.gesture_timing_projection import (
    GestureTimingProjection,
    ProjectedGestureEvent,
)
from src.pattern_core import (
    Channel,
    Pattern,
    Trigger,
    require_triggers_reference_known_channels,
)

from src.gesture_pattern_core_composition import (
    GesturePatternCoreComposition,
    compose_gesture_pattern_core,
)

_MODULE_PATH = (
    Path(__file__).resolve().parents[1] / "src" / "gesture_pattern_core_composition.py"
)

_ALLOWED_IMPORT_ROOTS = frozenset(
    {
        "annotations",
        "__future__",
        "dataclasses",
        "fractions",
        "typing",
        "collections",
        "collections.abc",
        "gesture_pattern_binding",
        "src.gesture_pattern_binding",
        "pattern_core",
        "src.pattern_core",
    }
)

_BANNED_IMPORT_ROOTS = frozenset(
    {
        "channel_rack",
        "src.channel_rack",
        "gesture_catalog_adapter",
        "src.gesture_catalog_adapter",
        "gesture_library_ranking",
        "src.gesture_library_ranking",
        "gesture_timing_projection",
        "src.gesture_timing_projection",
        "gesture_analysis",
        "src.gesture_analysis",
        "sqlite3",
        "sqlalchemy",
        "db",
        "src.db",
        "workbench_qml",
        "src.workbench_qml",
        "librosa",
        "soundfile",
        "numpy",
        "torch",
    }
)


# ---------------------------------------------------------------------------
# Derived boundary sets (issue #898)
#
# Forbidden call/field sets are derived from the real upstream authority
# modules and dataclass fields instead of hand-listed name guesses, so a
# renamed or added upstream symbol keeps its guard alive instead of silently
# degrading into a no-op that can never fail.
# ---------------------------------------------------------------------------


def _module_public_api(module_name: str) -> frozenset[str]:
    """Public top-level classes/callables declared by a first-party module."""
    mod = importlib.import_module(module_name)
    tree = ast.parse(Path(mod.__file__).read_text(encoding="utf-8"))
    return frozenset(
        node.name
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
        and not node.name.startswith("_")
    )


_PLAN_TYPE_NAMES = frozenset(
    {
        "PlannedGestureChannelBinding",
        "PlannedGestureEventBinding",
        "GesturePatternBindingPlan",
    }
)
_RANKING_TYPE_NAMES = frozenset({"LibraryCandidate", "RankedCandidate", "ClusterRanking"})
_TIMING_TYPE_NAMES = frozenset({"ProjectedGestureEvent", "GestureTimingProjection"})
_ANALYSIS_TYPE_NAMES = frozenset({"GestureEvent", "GestureAnalysis"})
_PATTERN_CORE_TYPE_NAMES = frozenset({"Channel", "Trigger", "Pattern"})

# Pattern-Core helpers the composer is allowed to use: membership validation
# only. Allocation and live-kit slot mapping stay forbidden.
_PATTERN_CORE_ALLOWED_HELPERS = frozenset(
    {"require_triggers_reference_known_channels"}
)


def _dataclass_fields(*classes: type) -> set[str]:
    names: set[str] = set()
    for cls in classes:
        names |= set(getattr(cls, "__dataclass_fields__", {}))
    return names


# Plan fields the composer may read. Anything else on the #891 plan/ranking
# authority is selection- or ranking-owned and must stay unread, which is what
# keeps rank-dependent auto-selection out of the pure composer.
_COMPOSER_ALLOWED_FIELDS = frozenset(
    {
        "channel_bindings",
        "channel_id",
        "cluster_id",
        "event_bindings",
        "pattern_length_quarters",
        "quarter_position",
        "ready_for_pattern",
        "sample_path",
        "unresolved_cluster_ids",
    }
)

_PLANNER_CALLABLES = sorted(
    _module_public_api("src.gesture_pattern_binding") - _PLAN_TYPE_NAMES
)
_RANKING_CALLABLES = sorted(
    _module_public_api("src.gesture_library_ranking") - _RANKING_TYPE_NAMES
)
_CATALOG_CALLABLES = sorted(_module_public_api("src.gesture_catalog_adapter"))
_DB_CALLABLES = sorted(_module_public_api("src.db"))
_TIMING_CALLABLES = sorted(
    _module_public_api("src.gesture_timing_projection") - _TIMING_TYPE_NAMES
)
_ANALYSIS_CALLABLES = sorted(
    _module_public_api("src.gesture_analysis") - _ANALYSIS_TYPE_NAMES
)
_PATTERN_CORE_MUTATION_CALLABLES = sorted(
    _module_public_api("src.pattern_core")
    - _PATTERN_CORE_TYPE_NAMES
    - _PATTERN_CORE_ALLOWED_HELPERS
)
_CHANNEL_RACK_CALLABLES = sorted(_module_public_api("src.channel_rack"))
_RACK_STATE_NAMES = sorted(
    set(_CHANNEL_RACK_CALLABLES) | {"ChannelRackState", "DEFAULT_ON", "_full_step_triggers"}
)

_RANKING_FIELDS = sorted(
    _dataclass_fields(LibraryCandidate, RankedCandidate, ClusterRanking)
    - _COMPOSER_ALLOWED_FIELDS
)
_SELECTION_FIELDS = sorted(
    _dataclass_fields(PlannedGestureChannelBinding) - _COMPOSER_ALLOWED_FIELDS
)
_TIMING_FIELDS = sorted(
    _dataclass_fields(GestureTimingProjection, ProjectedGestureEvent)
    - _COMPOSER_ALLOWED_FIELDS
)
_TIMING_PROJECTION_FIELDS = sorted(
    _dataclass_fields(GestureTimingProjection) - _COMPOSER_ALLOWED_FIELDS
)
# Length inference is a *recomputation* contract, not a field contract: the
# composer must not re-derive pattern length from timing data. These names are
# the inference operations the original raw-source guard rejected, and they are
# not dataclass fields, so deriving them from the dataclasses alone would drop
# the coverage entirely.
_LENGTH_INFERENCE_NAMES = frozenset(
    {"source_duration", "last_onset", "next_beat", "next_bar"}
)

# Modules that own a forbidden authority API. Used to decide whether a
# qualified reference's leaf name is really that authority or just an unrelated
# receiver method that happens to share the name.
_AUTHORITY_MODULES = (
    "src.gesture_pattern_binding",
    "src.gesture_library_ranking",
    "src.gesture_catalog_adapter",
    "src.db",
    "src.gesture_timing_projection",
    "src.gesture_analysis",
    "src.pattern_core",
    "src.channel_rack",
)


def _authority_owners() -> dict[str, set[str]]:
    """Map each authority symbol name to the module stems that own it."""
    owners: dict[str, set[str]] = {}
    for module in _AUTHORITY_MODULES:
        stem = module.rsplit(".", 1)[-1]
        for name in _module_public_api(module):
            owners.setdefault(name, set()).add(stem)
    return owners


_AUTHORITY_OWNERS = _authority_owners()


def _candidate(sample_id: str, path: str | None = None) -> LibraryCandidate:
    # Align fixture fields with live #882 LibraryCandidate (freeze typo repair).
    return LibraryCandidate(
        sample_id=sample_id,
        path=path if path is not None else f"{sample_id}.wav",
        audio_class="oneshot",
        loudness=0.1,
        brightness=1000.0,
        mfcc13=tuple(float(i) for i in range(13)),
    )


def _ranked(sample_id: str, distance: float, rank: int) -> RankedCandidate:
    return RankedCandidate(sample_id=sample_id, distance=distance, rank=rank)


def _ranking(
    cluster_id: int,
    ranked: tuple[RankedCandidate, ...] | list[RankedCandidate],
) -> ClusterRanking:
    return ClusterRanking(
        cluster_id=cluster_id,
        prototype_aligned=tuple(0.0 for _ in range(15)),
        ranked=tuple(ranked),
    )


def _event(cluster_id: int, quarter: Fraction | int | str) -> ProjectedGestureEvent:
    pos = quarter if isinstance(quarter, Fraction) else Fraction(quarter)
    return ProjectedGestureEvent(
        source_onset_sec=float(pos) * 0.5,
        quarter_position=pos,
        cluster_id=cluster_id,
    )


def _timing(
    events: list[ProjectedGestureEvent] | tuple[ProjectedGestureEvent, ...],
    *,
    duration_quarters: Fraction | None = None,
    bpm: Fraction = Fraction(120, 1),
) -> GestureTimingProjection:
    ev = tuple(events)
    if duration_quarters is None:
        if ev:
            duration_quarters = max(e.quarter_position for e in ev) + Fraction(1, 1)
        else:
            duration_quarters = Fraction(4, 1)
    return GestureTimingProjection(
        events=ev,
        reference_bpm=bpm,
        projected_duration_quarters=duration_quarters,
    )


def _plan_from_891(
    timing: GestureTimingProjection,
    rankings: list[ClusterRanking] | tuple[ClusterRanking, ...],
    candidates: list[LibraryCandidate] | tuple[LibraryCandidate, ...],
    selections: dict[int, str],
    existing: list[str] | tuple[str, ...] = (),
    *,
    length: Fraction = Fraction(4, 1),
) -> GesturePatternBindingPlan:
    return plan_gesture_pattern_binding(
        timing,
        rankings,
        candidates,
        selections,
        existing,
        pattern_length_quarters=length,
    )


def _channel_binding(
    cluster_id: int,
    channel_id: str,
    *,
    sample_id: str = "a",
    sample_path: str = "a.wav",
    selected_rank: int = 1,
    distance: float = 0.1,
) -> PlannedGestureChannelBinding:
    return PlannedGestureChannelBinding(
        cluster_id=cluster_id,
        channel_id=channel_id,
        sample_id=sample_id,
        sample_path=sample_path,
        selected_rank=selected_rank,
        distance=distance,
    )


def _event_binding(
    cluster_id: int,
    channel_id: str,
    quarter: Fraction,
) -> PlannedGestureEventBinding:
    return PlannedGestureEventBinding(
        cluster_id=cluster_id,
        channel_id=channel_id,
        quarter_position=quarter,
    )


def _ready_plan(
    *,
    channels: tuple[PlannedGestureChannelBinding, ...] = (),
    events: tuple[PlannedGestureEventBinding, ...] = (),
    length: Fraction = Fraction(4, 1),
    unresolved: tuple[int, ...] = (),
    ready: bool = True,
) -> GesturePatternBindingPlan:
    return GesturePatternBindingPlan(
        channel_bindings=channels,
        event_bindings=events,
        unresolved_cluster_ids=unresolved,
        pattern_length_quarters=length,
        ready_for_pattern=ready,
    )


def _simple_ready_plan() -> GesturePatternBindingPlan:
    return _ready_plan(
        channels=(_channel_binding(0, "ch_user_1", sample_path="kick.wav"),),
        events=(_event_binding(0, "ch_user_1", Fraction(1, 4)),),
        length=Fraction(4, 1),
    )


def _source_text() -> str:
    return _MODULE_PATH.read_text(encoding="utf-8")


def _is_submodule(name: str) -> bool:
    """True when ``name`` is a real module/package inside ``src/``.

    Lets ``from src import db`` be recognised as importing the ``src.db``
    module without guessing from a hand-listed set of names.
    """
    src_dir = _MODULE_PATH.resolve().parents[1]
    candidate = src_dir / name
    return candidate.with_suffix(".py").is_file() or (candidate / "__init__.py").is_file()


def _imported_module_names(mod) -> set[str]:
    """Module paths imported by a module, including package-relative forms.

    ``from . import db`` has ``ImportFrom.module is None``: the imported module
    is named only by the alias, and the relative ``level`` is what makes it a
    package-local import. Both plain and relative from-imports are recorded so
    a banned root cannot hide behind ``from . import db``.
    """
    path = Path(mod.__file__)
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                names.add(alias.name.split(".")[0])
                names.add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            module = node.module
            if module:
                names.add(module.split(".")[0])
                names.add(module)
                # An alias may itself name a submodule (`from src import db`).
                # Detect that from the real package layout so plain symbols
                # imported from a module are not mistaken for module paths.
                for alias in node.names:
                    if _is_submodule(alias.name):
                        names.add(f"{module}.{alias.name}")
            else:
                # `from . import db` / `from .. import x`: module is None and
                # the alias itself is the imported module name.
                for alias in node.names:
                    names.add(alias.name.split(".")[0])
                    names.add(alias.name)
    return names


def _parse_module_src(src: str) -> ast.Module:
    """Parse module source for a guard, failing closed on unparsable input.

    A ``SyntaxError`` must never be swallowed into an empty result: that would
    turn a boundary guard into a silent pass.
    """
    try:
        return ast.parse(src)
    except SyntaxError as exc:  # fail closed — never silently skip a guard
        raise AssertionError(f"cannot audit module source: {exc}") from exc


def _dotted_name(node: ast.AST) -> str | None:
    """Render a ``a.b.c`` reference; return None when the root is not a name."""
    parts: list[str] = []
    current: ast.AST | None = node
    while isinstance(current, ast.Attribute):
        parts.append(current.attr)
        current = current.value
    if not isinstance(current, ast.Name):
        return None
    parts.append(current.id)
    parts.reverse()
    return ".".join(parts)


def _imported_bindings(tree: ast.Module) -> dict[str, str]:
    """Map each locally bound name to the symbol path it was imported from.

    ``import a.b``, ``import a.b as ab``, ``from m import x`` and
    ``from m import x as y`` all resolve, so aliasing a forbidden import cannot
    hide it from the call/reference guards. Package-relative ``from . import db``
    binds ``db`` to ``db`` because the alias is the module name itself.
    """
    bindings: dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                local = alias.asname or alias.name.split(".")[0]
                bindings[local] = alias.name
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            for alias in node.names:
                local = alias.asname or alias.name
                if module:
                    bindings[local] = f"{module}.{alias.name}"
                elif node.level:
                    # `from . import db` — module is None, alias is the module.
                    bindings[local] = alias.name
                else:
                    bindings[local] = alias.name
    return bindings


def _bound_name_targets(args: ast.arguments) -> list[str]:
    """Parameter names of a ``def`` or ``lambda`` signature."""
    names = [arg.arg for arg in (*args.posonlyargs, *args.args, *args.kwonlyargs)]
    if args.vararg is not None:
        names.append(args.vararg.arg)
    if args.kwarg is not None:
        names.append(args.kwarg.arg)
    return names


def _local_name_bindings(tree: ast.Module) -> set[str]:
    """Names the module binds itself, so a bare spelling is not an import.

    A bare ``get_engine()`` with no visible origin has no other explanation than
    an injected or runtime-supplied authority symbol, so the call guard treats
    it as a reference. But when the module itself binds that name — a ``def``, a
    class, an assignment, a parameter, or a loop target — the composer has
    shadowed the authority, and the bare call is its own helper rather than
    upstream authority. The derived API sets contain several generic names
    (``get_engine``, ``init_db``, ``add_user_channel``), which is exactly why the
    two cases have to be told apart.

    ``global``/``nonlocal`` declarations are excluded, because those names are
    looked up in an enclosing scope rather than bound locally.
    """
    declared_outer: set[str] = set()
    bound: set[str] = set()

    def add(target: ast.AST | None) -> None:
        if isinstance(target, ast.Name):
            bound.add(target.id)
        elif isinstance(target, (ast.Tuple, ast.List)):
            for element in target.elts:
                add(element)
        elif isinstance(target, ast.Starred):
            add(target.value)

    for node in ast.walk(tree):
        if isinstance(node, (ast.Global, ast.Nonlocal)):
            declared_outer.update(node.names)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            bound.add(node.name)
            bound.update(_bound_name_targets(node.args))
        elif isinstance(node, ast.Lambda):
            bound.update(_bound_name_targets(node.args))
        elif isinstance(node, ast.ClassDef):
            bound.add(node.name)
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                add(target)
        elif isinstance(node, (ast.AnnAssign, ast.AugAssign)):
            add(node.target)
        elif isinstance(node, ast.NamedExpr):
            add(node.target)
        elif isinstance(node, ast.For):
            add(node.target)
        elif isinstance(node, (ast.With, ast.AsyncWith)):
            for item in node.items:
                add(item.optional_vars)
        elif isinstance(node, ast.ExceptHandler):
            if node.name:
                bound.add(node.name)
        elif isinstance(node, ast.comprehension):
            add(node.target)
        elif isinstance(node, ast.MatchAs):
            if node.name:
                bound.add(node.name)
        elif isinstance(node, ast.MatchStar):
            if node.name:
                bound.add(node.name)
        elif isinstance(node, ast.MatchMapping):
            if node.rest:
                bound.add(node.rest)
    return bound - declared_outer


def _authority_reference_nodes(tree: ast.Module) -> list[ast.AST]:
    """Every AST node that *references* a forbidden symbol's origin.

    The composer boundary is about capturing or using an upstream authority, not
    about proving a call happens. Once a forbidden callable is referenced at
    all — imported, bound, captured, or invoked — the boundary is broken, so
    later rebinding or an indirect invocation cannot launder it.

    This deliberately yields every load context in the tree rather than trying
    to model dataflow: no scope engine, no SSA, no control-flow graph. The
    reference itself is the evidence.

    ``ast.alias`` is included because a bare ``from x import forbidden`` binds
    the authority without ever emitting a ``Name`` node — the import alone
    already crosses the boundary.
    """
    return [
        node
        for node in ast.walk(tree)
        if isinstance(node, (ast.Name, ast.Attribute, ast.alias))
    ]


def _import_alias_spellings(tree: ast.Module) -> list[tuple[str, str | None]]:
    """``(imported_name, module)`` for every import alias in ``tree``.

    The module context lets a guard recognise that ``from m import f`` binds the
    symbol path ``m.f``, so ``import f`` is judged as the authority it came
    from rather than as an unrelated local name.
    """
    spellings: list[tuple[str, str | None]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                spellings.append((alias.name, None))
        elif isinstance(node, ast.ImportFrom):
            module = node.module
            for alias in node.names:
                spellings.append((alias.name, module))
    return spellings


def _forbidden_calls_in_src(src: str, forbidden: list[str]) -> set[str]:
    """Forbidden authority symbols referenced anywhere in ``src``.

    The pure composer may not use, capture, or re-export a forbidden upstream,
    mutation, rack, ranking, or DB authority. A reference is a violation on its
    own, so this is a *reference* guard, not a call/dataflow analysis: it holds
    regardless of how the value is later invoked.

    Detects, all semantically (never by text):
      - forbidden from-imports, including ``as`` aliases and module aliases,
      - qualified module members (``pattern_core.allocate_user_channel_id``),
      - bare and qualified direct calls,
      - assignment, container, conditional, and loop captures.

    Because it keys on semantic reference rather than call shape, rebinding
    (``op = helper`` ... ``op = safe``), subscript calls (``ops[0](...)``),
    list/tuple captures, ``x if c else y`` bindings, and ``for`` targets are
    all caught at the capture site.

    Comments, docstrings, and string literals are not code and are ignored by
    ``ast.parse()``, so they can never trip this guard.
    """
    tree = _parse_module_src(src)
    imported = _imported_bindings(tree)
    local = _local_name_bindings(tree)
    lower = {name.lower() for name in forbidden}
    found: set[str] = set()

    # An import binds the authority by name: `from m import f as g` still
    # imports `f`, so both the bare and the module-qualified spelling count.
    for name, module in _import_alias_spellings(tree):
        spellings = {name}
        if module:
            spellings.add(f"{module}.{name}")
        for spelling in spellings:
            for candidate in _resolved_names(spelling, imported, _AUTHORITY_OWNERS, local):
                if candidate.lower() in lower:
                    found.add(candidate)

    for node in _authority_reference_nodes(tree):
        if isinstance(node, ast.alias):
            continue
        qualified = _dotted_name(node)
        if qualified is None:
            continue
        for candidate in _resolved_names(qualified, imported, _AUTHORITY_OWNERS, local):
            if candidate.lower() in lower:
                found.add(candidate)

    # `getattr(mod, "f")` / `mod.__dict__["f"]` capture the authority by name
    # at import time, before any later patch could intercept it.
    for name in _dynamic_member_lookups(tree):
        if name.lower() in lower:
            found.add(name)
    return found


def _resolved_names(
    qualified: str,
    imported: dict[str, str],
    owners: dict[str, set[str]] | None = None,
    local_bindings: set[str] | None = None,
) -> set[str]:
    """Candidate spellings of a reference, including its import resolution.

    Covers the written form, the bare attribute/name form, and — when the
    reference is an imported alias — both the resolved dotted symbol and its
    final component, so a ban on either the bare or the qualified symbol hits.

    A qualified leaf is only offered as a bare-name candidate when the receiver
    actually resolves to the owning authority: either it is an imported module
    alias, or it *is* the authority module. Without that check any unrelated
    receiver method sharing a generic API name (``validator.get_engine()``)
    would be reported as a database authority reference.

    A bare name that the module itself binds is likewise dropped, because the
    composer shadowed the authority rather than referencing it. That suppression
    applies to the authority call guard only; the name-ban guards deliberately
    keep matching bare names.
    """
    owners = owners or {}
    local_bindings = local_bindings or set()
    candidates = {qualified}
    if "." in qualified:
        head, _, tail = qualified.rpartition(".")
        if owners:
            # Scoped mode: a leaf only counts when the receiver resolves to the
            # owning authority, so `validator.get_engine()` is not a DB call.
            if head in imported:
                resolved = f"{imported[head]}.{tail}"
                candidates.add(resolved)
                candidates.add(resolved.rpartition(".")[2])
            elif head in owners.get(tail, ()):
                candidates.add(tail)
        else:
            # Unscoped mode (field/state guards): the receiver is an arbitrary
            # instance, so the attribute leaf itself is the reference.
            candidates.add(tail)
            if head in imported:
                resolved = f"{imported[head]}.{tail}"
                candidates.add(resolved)
                candidates.add(resolved.rpartition(".")[2])
    elif qualified in imported:
        resolved = imported[qualified]
        candidates.add(resolved)
        candidates.add(resolved.rpartition(".")[2])
    elif qualified in local_bindings:
        return set()
    return candidates


_MAPPING_LOOKUP_METHODS = frozenset({"get", "getdefault", "pop", "setdefault", "popitem"})


def _is_mapping_access(target: ast.AST) -> bool:
    """True when ``target`` reads an object's ``__dict__`` by name.

    Covers the direct attribute form (``obj.__dict__``) and the builtin
    ``vars(obj)`` form, whose ``func`` is a ``Name`` rather than an
    ``Attribute``.
    """
    leaf = (_dotted_name(target) or "").rpartition(".")[2]
    if leaf == "__dict__":
        return True
    if leaf == "vars":
        return True
    return isinstance(target, ast.Call) and (
        (_dotted_name(target.func) or "").rpartition(".")[2] == "vars"
    )


def _dynamic_member_lookups(tree: ast.Module) -> list[str]:
    """Member names resolved at runtime through a string literal.

    ``getattr(mod, "f")``, ``mod.__dict__["f"]``, ``mod.__dict__.get("f")``,
    ``vars(mod)["f"]``, ``vars(mod).get("f")`` and ``operator.attrgetter("f")``
    all fetch a member *by name*, so the AST holds the forbidden symbol as a
    ``Constant`` rather than as a ``Name``. The guard cannot see it by walking
    names alone, but it is still a real reference to the authority — the capture
    happens at import time, before any later module patch can intercept it.

    Only string literals in a member-lookup *position* are returned, so an
    ordinary string that merely spells a forbidden word is not affected.
    """
    found: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func = _dotted_name(node.func) or ""
            leaf = func.rpartition(".")[2]
            if leaf == "getattr" and len(node.args) >= 2:
                name = node.args[1]
            elif leaf == "attrgetter" and node.args:
                name = node.args[0]
            elif (
                isinstance(node.func, ast.Attribute)
                and node.func.attr in _MAPPING_LOOKUP_METHODS
                and node.args
                # A mapping method is only a named member read when the mapping
                # itself is an object's `__dict__`; any other receiver is
                # ordinary application data.
                and _is_mapping_access(node.func.value)
            ):
                # The method name comes from `func.attr`, not from
                # `_dotted_name`: `vars(obj).get(...)` has a Call receiver, so
                # the dotted spelling is empty.
                name = node.args[0]
            else:
                continue
            if isinstance(name, ast.Constant) and isinstance(name.value, str):
                found.append(name.value)
        elif isinstance(node, ast.Subscript):
            if _is_mapping_access(node.value):
                key = node.slice
                if isinstance(key, ast.Constant) and isinstance(key.value, str):
                    found.append(key.value)
    return found


def _forbidden_dynamic_lookups_in_src(src: str, forbidden: list[str]) -> set[str]:
    """Forbidden authority members fetched by name through a string literal."""
    tree = _parse_module_src(src)
    lower = {name.lower() for name in forbidden}
    return {name for name in _dynamic_member_lookups(tree) if name.lower() in lower}


def _forbidden_name_refs_in_src(
    src: str,
    forbidden: list[str],
    *,
    attributes_only: bool = False,
) -> set[str]:
    """Forbidden symbols referenced by name in ``src`` (alias-aware).

    ``attributes_only`` restricts the match to attribute reads (``x.field``),
    which is the correct shape when banning upstream *fields*: the composer
    legitimately uses local variables that share those field names.
    """
    tree = _parse_module_src(src)
    imported = _imported_bindings(tree)
    lower = {name.lower() for name in forbidden}
    found: set[str] = set()
    for node in _authority_reference_nodes(tree):
        if isinstance(node, ast.Name):
            if attributes_only:
                continue
            candidates = _resolved_names(node.id, imported)
        else:
            qualified = _dotted_name(node)
            if qualified is None:
                continue
            # Field and state guards read through arbitrary instances
            # (`binding.selected_rank`, `rack_state.DEFAULT_ON`), so the leaf
            # must match here; owner scoping applies to module APIs only.
            candidates = _resolved_names(qualified, imported)
        for candidate in candidates:
            if candidate.lower() in lower:
                found.add(candidate)
    # A protected field read dynamically (`getattr(binding, "selected_rank")`,
    # `binding.__dict__["selected_rank"]`) is still an attribute read by name,
    # so the field guard must see it too.
    for name in _dynamic_member_lookups(tree):
        if name.lower() in lower:
            found.add(name)
    return found


def _compose(plan: GesturePatternBindingPlan, pattern_id: str = "gesture-pat-1"):
    return compose_gesture_pattern_core(plan, pattern_id=pattern_id)


# ---------------------------------------------------------------------------
# Semantic checker proof tests (false-positive / true-positive)
# ---------------------------------------------------------------------------


def test__semantic_checker_false_positive_comments_docstrings_strings() -> None:
    """Checker must NOT flag forbidden words in comments, docstrings, or string literals."""
    src = '''
"""Module docstring with quantize and allocate_user_channel_id."""

# Comment with add_user_channel and DEFAULT_ON
def foo():
    """Docstring with project_gesture_timing and rank_1."""
    msg = "String literal with auto-select and INSERT"
    return msg
'''
    # No actual calls or refs to forbidden names
    calls = _forbidden_calls_in_src(src, [
        "quantize",
        "allocate_user_channel_id",
        "add_user_channel",
        "project_gesture_timing",
    ])
    refs = _forbidden_name_refs_in_src(src, [
        "quantize",
        "allocate_user_channel_id",
        "add_user_channel",
        "DEFAULT_ON",
        "project_gesture_timing",
        "auto_select",
        "rank_1",
        "INSERT",
    ])
    assert calls == set()
    assert refs == set()


def test__semantic_checker_true_positive_calls() -> None:
    """Checker MUST detect actual forbidden CALLS."""
    src = '''
def func():
    quantize(1, 2)
    pattern_core.allocate_user_channel_id()
    add_user_channel("x")
'''
    calls = _forbidden_calls_in_src(src, [
        "quantize",
        "allocate_user_channel_id",
        "add_user_channel",
    ])
    assert "quantize" in calls
    assert "allocate_user_channel_id" in calls
    assert "add_user_channel" in calls


def test__semantic_checker_ignores_unrelated_receiver_leaf() -> None:
    """An unrelated receiver method sharing an API name is not a violation.

    Regression proof for matching an attribute's leaf unconditionally: the DB
    and rack APIs contain generic names such as `get_engine`, so a harmless
    `validator.get_engine()` was reported as database authority access.
    """
    src = """
class Validator:
    def get_engine(self):
        return object()

def compose():
    return Validator().get_engine()
"""
    assert _forbidden_calls_in_src(src, _DB_CALLABLES) == set()
    assert _forbidden_calls_in_src(src, _CHANNEL_RACK_CALLABLES) == set()
    # The same names still fail when they really come from the authority.
    assert _forbidden_calls_in_src(
        "import db\ndef compose():\n    return db.get_engine()\n", _DB_CALLABLES
    ) == {"get_engine"}
    assert _forbidden_calls_in_src(
        "import channel_rack\ndef compose():\n    return channel_rack.add_user_channel(c)\n",
        _CHANNEL_RACK_CALLABLES,
    ) == {"add_user_channel"}


def test__semantic_checker_ignores_locally_bound_bare_helper() -> None:
    """A local helper sharing an authority API name is not that authority.

    Regression proof for keeping a bare spelling unconditionally: because the
    derived DB and rack sets contain generic names such as `get_engine`, an
    unrelated local `def get_engine()` was reported as database authority
    access even though no DB module is referenced at all.
    """
    locals_ = {
        "local def": "def get_engine():\n    return object()\n\ndef compose():\n"
        "    return get_engine()\n",
        "local assignment": "def compose(obj):\n    get_engine = obj.engine\n"
        "    return get_engine()\n",
        "local parameter": "def compose(get_engine):\n    return get_engine()\n",
        "local loop target": "def compose(rows):\n    for get_engine in rows:\n"
        "        return get_engine()\n",
    }
    for label, src in locals_.items():
        assert _forbidden_calls_in_src(src, _DB_CALLABLES) == set(), label

    # A bare spelling with no local binding has no other possible origin, so it
    # stays a reference; so does an import of the authority.
    assert _forbidden_calls_in_src(
        "def compose():\n    return get_engine()\n", _DB_CALLABLES
    ) == {"get_engine"}
    assert _forbidden_calls_in_src(
        "from db import get_engine\ndef compose():\n    return get_engine()\n", _DB_CALLABLES
    ) == {"get_engine"}

    # Shadowing the name does not launder a captured authority: the reference
    # is still caught at the point where the authority is actually touched.
    assert _forbidden_calls_in_src(
        "import db\ndef get_engine():\n    return db.get_engine()\n", _DB_CALLABLES
    ) == {"get_engine"}
    assert _forbidden_calls_in_src(
        "import db\ndef compose():\n    get_engine = db.get_engine\n"
        "    return get_engine()\n",
        _DB_CALLABLES,
    ) == {"get_engine"}

    # The frozen composer itself must stay clean.
    assert _forbidden_calls_in_src(_source_text(), _DB_CALLABLES) == set()


def test__field_guard_rejects_dynamic_protected_field_read() -> None:
    """A protected field read by name must fail the field guard.

    Regression proof for `attributes_only` guards seeing only real `Attribute`
    nodes: `getattr(binding, "selected_rank")` and the `__dict__` subscript form
    both bypassed test 39.
    """
    for src in (
        'def compose(binding):\n    return getattr(binding, "selected_rank")\n',
        'def compose(binding):\n    return binding.__dict__["selected_rank"]\n',
        'def compose(binding):\n    return binding.__dict__.get("selected_rank")\n',
        'def compose(binding):\n    return vars(binding).get("selected_rank")\n',
        'def compose(binding):\n    return binding.__dict__.getdefault("selected_rank", 0)\n',
    ):
        assert _forbidden_name_refs_in_src(
            src, _SELECTION_FIELDS, attributes_only=True
        ) == {"selected_rank"}, src
    # A plain string that merely spells the field name is not a field read.
    assert _forbidden_name_refs_in_src(
        'def compose():\n    label = "selected_rank"\n',
        _SELECTION_FIELDS,
        attributes_only=True,
    ) == set()
    # The frozen composer itself must stay clean.
    assert _forbidden_name_refs_in_src(
        _source_text(), _SELECTION_FIELDS, attributes_only=True
    ) == set()


def test__semantic_checker_true_positive_name_refs() -> None:
    """Checker MUST detect actual forbidden NAME/ATTRIBUTE references."""
    src = '''
DEFAULT_ON = True
x = _full_step_triggers
y = ChannelRackState()
'''
    refs = _forbidden_name_refs_in_src(src, [
        "DEFAULT_ON",
        "_full_step_triggers",
        "ChannelRackState",
    ])
    assert "DEFAULT_ON" in refs
    assert "_full_step_triggers" in refs
    assert "ChannelRackState" in refs


def test__semantic_checker_true_positive_qualified_attribute() -> None:
    """Checker MUST detect qualified references such as ``module.DEFAULT_ON``."""
    src = "flag = rack_state.DEFAULT_ON\n"
    # A qualified ban matches the full dotted reference.
    assert _forbidden_name_refs_in_src(
        src, ["rack_state.DEFAULT_ON"]
    ) == {"rack_state.DEFAULT_ON"}
    # The bare attribute form matches too, so a field-only ban also hits.
    assert _forbidden_name_refs_in_src(src, ["DEFAULT_ON"]) == {"DEFAULT_ON"}
    # An attribute-only ban hits the read as well.
    assert _forbidden_name_refs_in_src(
        src, ["DEFAULT_ON"], attributes_only=True
    ) == {"DEFAULT_ON"}


def test__semantic_checker_resolves_import_aliases() -> None:
    """Aliased from-imports must not hide a forbidden call from the checker."""
    src = '''
from .pattern_core import allocate_user_channel_id as allocate

def compose():
    allocate("ch_user_1")
'''
    # A bare-symbol ban still catches the aliased call.
    assert _forbidden_calls_in_src(src, ["allocate_user_channel_id"]) == {
        "allocate_user_channel_id"
    }
    # A qualified ban is matched against the resolved import path.
    assert _forbidden_calls_in_src(
        src, ["pattern_core.allocate_user_channel_id"]
    ) == {"pattern_core.allocate_user_channel_id"}


def test__semantic_checker_resolves_module_aliases() -> None:
    """``import x as y`` module aliases must resolve to the banned symbol."""
    src = '''
import pattern_core as pc

def compose():
    pc.allocate_user_channel_id()
'''
    assert _forbidden_calls_in_src(src, ["allocate_user_channel_id"]) == {
        "allocate_user_channel_id"
    }
    assert _forbidden_calls_in_src(
        src, ["pattern_core.allocate_user_channel_id"]
    ) == {"pattern_core.allocate_user_channel_id"}


def test__semantic_checker_fails_closed_on_unparsable_source() -> None:
    """Unparsable source must raise, never silently pass the boundary guard."""
    broken = "def compose(:\n    pass\n"
    with pytest.raises(AssertionError):
        _forbidden_calls_in_src(broken, ["allocate_user_channel_id"])
    with pytest.raises(AssertionError):
        _forbidden_name_refs_in_src(broken, ["DEFAULT_ON"])


def test__semantic_checker_attributes_only_ignores_bare_locals() -> None:
    """Field bans must ignore bare locals that share the field name."""
    src = '''
def compose(events, plan):
    events = tuple(events)
    return plan.pattern_length_quarters, len(events)
'''
    # A field ban matches the attribute read...
    assert "projected_duration_quarters" in _forbidden_name_refs_in_src(
        "value = timing.projected_duration_quarters\n",
        ["projected_duration_quarters"],
        attributes_only=True,
    )
    # ...but not the identically named local variable.
    assert _forbidden_name_refs_in_src(
        src, ["events"], attributes_only=True
    ) == set()
    assert _forbidden_name_refs_in_src(src, ["pattern_length_quarters"]) == {
        "pattern_length_quarters"
    }


def test__semantic_checker_import_binding_resolution() -> None:
    """Import/ImportFrom forms (incl. aliases) resolve to their symbol paths."""
    src = '''
import sqlite3
import gesture_catalog_adapter as catalog
from db import connect
from .pattern_core import allocate_user_channel_id as allocate
'''
    bindings = _imported_bindings(ast.parse(src))
    assert bindings["sqlite3"] == "sqlite3"
    assert bindings["catalog"] == "gesture_catalog_adapter"
    assert bindings["connect"] == "db.connect"
    assert bindings["allocate"] == "pattern_core.allocate_user_channel_id"


def test__semantic_checker_import_boundary_detects_banned_roots(tmp_path: Path) -> None:
    """Import boundary rejects banned roots and accepts the frozen allow-list."""
    banned_src = '''
import sqlite3
from db import connect
import gesture_catalog_adapter
'''
    banned_path = tmp_path / "banned_module.py"
    banned_path.write_text(banned_src, encoding="utf-8")
    banned = _imported_module_names(_FakeModule(banned_path))
    assert {"sqlite3", "db", "gesture_catalog_adapter"} <= banned
    assert not banned <= _ALLOWED_IMPORT_ROOTS
    allowed_src = '''
from __future__ import annotations
from dataclasses import dataclass
from fractions import Fraction
from .pattern_core import Channel, Pattern, Trigger
'''
    allowed_path = tmp_path / "allowed_module.py"
    allowed_path.write_text(allowed_src, encoding="utf-8")
    allowed = _imported_module_names(_FakeModule(allowed_path))
    assert allowed <= _ALLOWED_IMPORT_ROOTS


class _FakeModule:
    """Minimal module stand-in exposing ``__file__`` for source-based helpers."""

    def __init__(self, path: Path) -> None:
        self.__file__ = str(path)


def _write_source(tmp_path: Path, src: str, name: str = "candidate.py") -> Path:
    path = tmp_path / name
    path.write_text(src, encoding="utf-8")
    return path


@pytest.mark.parametrize(
    ("guard", "forbidden", "violating_src"),
    [
        (
            "planner_call",
            _PLANNER_CALLABLES,
            "def compose(plan):\n    return plan_gesture_pattern_binding(plan)\n",
        ),
        (
            "ranking_call",
            _RANKING_CALLABLES,
            "def compose():\n    return rank_gesture_library_candidates([], [])\n",
        ),
        (
            "catalog_call",
            _CATALOG_CALLABLES,
            "def compose():\n    return load_gesture_library_candidates(path)\n",
        ),
        (
            "timing_call",
            _TIMING_CALLABLES,
            "def compose():\n    return project_gesture_timing(events)\n",
        ),
        (
            "analysis_call",
            _ANALYSIS_CALLABLES,
            "def compose():\n    return analyze_gesture_audio(path)\n",
        ),
        (
            "pattern_core_mutation",
            _PATTERN_CORE_MUTATION_CALLABLES,
            "def compose():\n    return allocate_user_channel_id(existing)\n",
        ),
        (
            "channel_rack_call",
            _CHANNEL_RACK_CALLABLES,
            "def compose():\n    return add_user_channel(channel)\n",
        ),
        (
            "aliased_import_call",
            _PATTERN_CORE_MUTATION_CALLABLES,
            "from .pattern_core import allocate_user_channel_id as allocate\n"
            "\n"
            "def compose():\n"
            "    return allocate(existing)\n",
        ),
    ],
)
def test__derived_call_guards_are_live(guard, forbidden, violating_src) -> None:
    """Every derived call guard must flag a violating module (no dead guards)."""
    assert forbidden, f"{guard}: derived forbidden set must not be empty"
    assert _forbidden_calls_in_src(violating_src, forbidden), (
        f"{guard}: guard failed to flag a real violating call"
    )


@pytest.mark.parametrize(
    ("guard", "forbidden", "violating_src"),
    [
        (
            "ranking_field",
            _RANKING_FIELDS,
            "def compose(cluster):\n    return cluster.ranked\n",
        ),
        (
            "selection_field",
            _SELECTION_FIELDS,
            "def compose(binding):\n    return binding.selected_rank\n",
        ),
        (
            "timing_field",
            _TIMING_FIELDS,
            "def compose(timing):\n    return timing.projected_duration_quarters\n",
        ),
        (
            "timing_projection_field",
            _TIMING_PROJECTION_FIELDS,
            "def compose(timing):\n    return timing.reference_bpm\n",
        ),
    ],
)
def test__derived_field_guards_are_live(guard, forbidden, violating_src) -> None:
    """Every derived field guard must flag a violating read (no dead guards)."""
    assert forbidden, f"{guard}: derived forbidden set must not be empty"
    assert _forbidden_name_refs_in_src(
        violating_src, forbidden, attributes_only=True
    ), f"{guard}: guard failed to flag a real forbidden field read"


def test__semantic_checker_follows_callable_assignment_alias() -> None:
    """``allocator = helper; allocator(...)`` must not evade the boundary guard."""
    src = """
from .pattern_core import allocate_user_channel_id

allocator = allocate_user_channel_id

def compose():
    return allocator("ch_user_1")
"""
    assert _forbidden_calls_in_src(src, _PATTERN_CORE_MUTATION_CALLABLES) == {
        "allocate_user_channel_id"
    }


def test__semantic_checker_follows_chained_assignment_alias() -> None:
    """Aliases of aliases must still resolve to the forbidden symbol."""
    src = """
import channel_rack

first = channel_rack.add_user_channel
second = first
third = second

def compose():
    return third(channel)
"""
    assert _forbidden_calls_in_src(src, _CHANNEL_RACK_CALLABLES) == {
        "add_user_channel"
    }


def test__semantic_checker_reference_guard_terminates_on_self_reference() -> None:
    """Self-referential local names must terminate instead of hanging the guard."""
    src = """
loop_a = loop_b
loop_b = loop_a

def compose():
    return loop_a()
"""
    assert _forbidden_calls_in_src(src, ["nonexistent_forbidden"]) == set()


def test__semantic_checker_flags_reference_not_only_invocations() -> None:
    """The guard is reference-based: capture alone is a violation."""
    src = """
from .pattern_core import allocate_user_channel_id

captured = allocate_user_channel_id
"""
    assert _forbidden_calls_in_src(src, _PATTERN_CORE_MUTATION_CALLABLES) == {
        "allocate_user_channel_id"
    }


def test__semantic_checker_rejects_rebound_authority_capture() -> None:
    """A forbidden capture is a violation even when the local name is rebound later."""
    src = """
from .pattern_core import allocate_user_channel_id

def compose(existing, safe):
    op = allocate_user_channel_id
    op(existing)
    op = safe
"""
    assert _forbidden_calls_in_src(src, _PATTERN_CORE_MUTATION_CALLABLES) == {
        "allocate_user_channel_id"
    }


def test__semantic_checker_rejects_container_capture() -> None:
    """Storing a forbidden callable in a container and calling it by subscript is a capture."""
    src = """
from .pattern_core import allocate_user_channel_id

def compose(existing):
    ops = [allocate_user_channel_id]
    ops[0](existing)
"""
    assert _forbidden_calls_in_src(src, _PATTERN_CORE_MUTATION_CALLABLES) == {
        "allocate_user_channel_id"
    }


def test__semantic_checker_rejects_qualified_capture() -> None:
    """Capturing a forbidden qualified module member is a violation."""
    src = """
import pattern_core

def compose():
    op = pattern_core.allocate_user_channel_id
    return op
"""
    assert _forbidden_calls_in_src(src, _PATTERN_CORE_MUTATION_CALLABLES) == {
        "allocate_user_channel_id"
    }


def test__semantic_checker_rejects_module_alias_capture() -> None:
    """A forbidden member reached through an aliased module is a capture."""
    src = """
import pattern_core as pc

def compose():
    op = pc.allocate_user_channel_id
    return op
"""
    assert _forbidden_calls_in_src(src, _PATTERN_CORE_MUTATION_CALLABLES) == {
        "allocate_user_channel_id"
    }


def test__semantic_checker_rejects_conditional_capture() -> None:
    """A conditional expression that may yield a forbidden callable is a capture."""
    src = """
from .pattern_core import allocate_user_channel_id

def compose(condition, safe):
    op = allocate_user_channel_id if condition else safe
    return op
"""
    assert _forbidden_calls_in_src(src, _PATTERN_CORE_MUTATION_CALLABLES) == {
        "allocate_user_channel_id"
    }


def test__semantic_checker_rejects_loop_bound_capture() -> None:
    """A loop binding a forbidden callable as its iteration value is a capture."""
    src = """
from .pattern_core import allocate_user_channel_id

def compose(existing):
    for op in [allocate_user_channel_id]:
        op(existing)
"""
    assert _forbidden_calls_in_src(src, _PATTERN_CORE_MUTATION_CALLABLES) == {
        "allocate_user_channel_id"
    }


def test__semantic_checker_rejects_unused_forbidden_import() -> None:
    """Importing a forbidden authority is itself a boundary violation."""
    src = """
from src.pattern_core import allocate_user_channel_id
from src.pattern_core import allocate_user_channel_id as allocator
"""
    assert _forbidden_calls_in_src(src, _PATTERN_CORE_MUTATION_CALLABLES) == {
        "allocate_user_channel_id"
    }


def test__import_guard_rejects_package_relative_db_import(tmp_path: Path) -> None:
    """``from . import db`` must be recorded, not skipped as module=None."""
    src = """
from . import db
"""
    names = _imported_module_names(_FakeModule(_write_source(tmp_path, src)))
    assert "db" in names
    assert "db" in _BANNED_IMPORT_ROOTS


def test__import_guard_rejects_relative_db_call() -> None:
    """DB operations via ``from . import db`` stay flagged by the call guard."""
    src = """
from . import db

def compose():
    return db.init_db()
"""
    assert _forbidden_calls_in_src(src, _DB_CALLABLES) == {"init_db"}
    # The frozen module itself must stay clean.
    assert _forbidden_calls_in_src(_source_text(), _DB_CALLABLES) == set()


def test__db_callable_set_is_live() -> None:
    """The derived DB set must actually flag DB operations."""
    assert _DB_CALLABLES
    assert _forbidden_calls_in_src(
        "def compose():\n    return db.init_db()\n", _DB_CALLABLES
    ) == {"init_db"}


def test__rank_based_auto_select_branch_is_rejected() -> None:
    """Rank-1 auto-select branching in the composer must fail test 39's guard.

    Regression proof for the case where a raw text guard was replaced by
    identifier bans that never matched the actual selection field.
    """
    violating = """
def compose(binding):
    if binding.selected_rank == 1:
        return auto_select(binding)
    return binding
"""
    assert _forbidden_name_refs_in_src(
        violating, _SELECTION_FIELDS, attributes_only=True
    ) == {"selected_rank"}
    # The frozen module itself must stay clean.
    assert _forbidden_name_refs_in_src(
        _source_text(), _SELECTION_FIELDS, attributes_only=True
    ) == set()


# ---------------------------------------------------------------------------
# Happy path / object identity / preservation
# ---------------------------------------------------------------------------


def test_01_one_ready_binding_event_one_channel_trigger_pattern() -> None:
    """1. one ready binding/event → one Channel + one Trigger + one Pattern."""
    plan = _simple_ready_plan()
    result = _compose(plan, "pat-1")
    assert isinstance(result, GesturePatternCoreComposition)
    assert len(result.channels) == 1
    assert len(result.pattern.triggers) == 1
    assert result.pattern.pattern_id == "pat-1"


def test_02_result_uses_actual_pattern_core_channel() -> None:
    """2. result uses actual pattern_core.Channel."""
    result = _compose(_simple_ready_plan())
    assert len(result.channels) == 1
    assert type(result.channels[0]) is Channel
    assert isinstance(result.channels[0], Channel)


def test_03_result_uses_actual_pattern_core_trigger() -> None:
    """3. result uses actual pattern_core.Trigger."""
    result = _compose(_simple_ready_plan())
    assert len(result.pattern.triggers) == 1
    assert type(result.pattern.triggers[0]) is Trigger
    assert isinstance(result.pattern.triggers[0], Trigger)


def test_04_result_uses_actual_pattern_core_pattern() -> None:
    """4. result uses actual pattern_core.Pattern."""
    result = _compose(_simple_ready_plan())
    assert type(result.pattern) is Pattern
    assert isinstance(result.pattern, Pattern)


def test_05_channel_id_preserved_exactly() -> None:
    """5. channel_id preserved exactly."""
    plan = _ready_plan(
        channels=(_channel_binding(7, "ch_user_42"),),
        events=(_event_binding(7, "ch_user_42", Fraction(0, 1)),),
    )
    result = _compose(plan)
    assert result.channels[0].channel_id == "ch_user_42"
    assert result.pattern.triggers[0].channel_id == "ch_user_42"


def test_06_sample_path_preserved_exactly() -> None:
    """6. sample_path preserved exactly."""
    plan = _ready_plan(
        channels=(_channel_binding(0, "ch_user_1", sample_path="samples/exact/path.wav"),),
        events=(_event_binding(0, "ch_user_1", Fraction(0, 1)),),
    )
    result = _compose(plan)
    assert result.channels[0].sample_path == "samples/exact/path.wav"


def test_07_user_provenance_none_none() -> None:
    """7. user provenance = None / None."""
    result = _compose(_simple_ready_plan())
    ch = result.channels[0]
    assert ch.live_kit_group is None
    assert ch.live_kit_slot is None


def test_08_repeated_events_one_channel_n_triggers() -> None:
    """8. repeated events → one Channel + N Triggers."""
    positions = (Fraction(0, 1), Fraction(1, 2), Fraction(3, 2))
    plan = _ready_plan(
        channels=(_channel_binding(3, "ch_user_1"),),
        events=tuple(_event_binding(3, "ch_user_1", p) for p in positions),
    )
    result = _compose(plan)
    assert len(result.channels) == 1
    assert len(result.pattern.triggers) == 3
    assert [t.position for t in result.pattern.triggers] == list(positions)


def test_09_two_clusters_two_channels() -> None:
    """9. two clusters → two Channels."""
    plan = _ready_plan(
        channels=(
            _channel_binding(1, "ch_user_1", sample_id="a", sample_path="a.wav"),
            _channel_binding(2, "ch_user_2", sample_id="b", sample_path="b.wav"),
        ),
        events=(
            _event_binding(1, "ch_user_1", Fraction(0, 1)),
            _event_binding(2, "ch_user_2", Fraction(1, 1)),
        ),
    )
    result = _compose(plan)
    assert len(result.channels) == 2
    assert [c.channel_id for c in result.channels] == ["ch_user_1", "ch_user_2"]


def test_10_same_path_across_clusters_separate_channels() -> None:
    """10. same path across clusters → separate Channels."""
    plan = _ready_plan(
        channels=(
            _channel_binding(1, "ch_user_1", sample_id="42", sample_path="shared.wav"),
            _channel_binding(2, "ch_user_2", sample_id="42", sample_path="shared.wav"),
        ),
        events=(
            _event_binding(1, "ch_user_1", Fraction(0, 1)),
            _event_binding(2, "ch_user_2", Fraction(1, 1)),
        ),
    )
    result = _compose(plan)
    assert len(result.channels) == 2
    assert result.channels[0].channel_id != result.channels[1].channel_id
    assert result.channels[0].sample_path == result.channels[1].sample_path == "shared.wav"


def test_11_quarter_fractions_preserved_exactly() -> None:
    """11. quarter Fractions preserved exactly."""
    pos = Fraction(3, 10)
    plan = _ready_plan(
        channels=(_channel_binding(0, "ch_user_1"),),
        events=(_event_binding(0, "ch_user_1", pos),),
    )
    result = _compose(plan)
    trigger = result.pattern.triggers[0]
    assert trigger.position == pos
    assert type(trigger.position) is Fraction


def test_12_no_quantization() -> None:
    """12. no quantization."""
    # Unquantized position that is not on a 16th grid.
    pos = Fraction(1, 7)
    plan = _ready_plan(
        channels=(_channel_binding(0, "ch_user_1"),),
        events=(_event_binding(0, "ch_user_1", pos),),
        length=Fraction(4, 1),
    )
    result = _compose(plan)
    assert result.pattern.triggers[0].position == Fraction(1, 7)
    src = _source_text()
    # Semantic check: no actual CALLS to quantization functions
    forbidden_calls = _forbidden_calls_in_src(src, [
        "quantize", "snap", "swing", "groove", "round"
    ])
    assert forbidden_calls == set(), f"Found forbidden quantization calls: {forbidden_calls}"


def test_13_plan_pattern_length_preserved_exactly() -> None:
    """13. plan Pattern length preserved exactly."""
    length = Fraction(17, 4)
    plan = _ready_plan(
        channels=(_channel_binding(0, "ch_user_1"),),
        events=(_event_binding(0, "ch_user_1", Fraction(0, 1)),),
        length=length,
    )
    result = _compose(plan)
    assert result.pattern.length_quarter_notes == length
    assert type(result.pattern.length_quarter_notes) is Fraction


def test_14_explicit_pattern_id_preserved() -> None:
    """14. explicit pattern_id preserved."""
    result = _compose(_simple_ready_plan(), pattern_id="explicit-gesture-42")
    assert result.pattern.pattern_id == "explicit-gesture-42"


# ---------------------------------------------------------------------------
# Fail-closed gates
# ---------------------------------------------------------------------------


def test_15_empty_pattern_id_rejected() -> None:
    """15. empty pattern_id rejected."""
    with pytest.raises((TypeError, ValueError)):
        _compose(_simple_ready_plan(), pattern_id="")


def test_16_non_string_pattern_id_rejected() -> None:
    """16. non-string pattern_id rejected."""
    with pytest.raises((TypeError, ValueError)):
        compose_gesture_pattern_core(_simple_ready_plan(), pattern_id=123)  # type: ignore[arg-type]


def test_17_non_ready_plan_rejected() -> None:
    """17. non-ready plan rejected."""
    plan = _ready_plan(
        channels=(_channel_binding(0, "ch_user_1"),),
        events=(_event_binding(0, "ch_user_1", Fraction(0, 1)),),
        unresolved=(1,),
        ready=False,
    )
    with pytest.raises((TypeError, ValueError)):
        _compose(plan)


def test_18_unresolved_plan_rejected() -> None:
    """18. unresolved plan rejected."""
    plan = _ready_plan(
        channels=(_channel_binding(0, "ch_user_1"),),
        events=(_event_binding(0, "ch_user_1", Fraction(0, 1)),),
        unresolved=(9,),
        ready=False,
    )
    assert plan.unresolved_cluster_ids == (9,)
    with pytest.raises((TypeError, ValueError)):
        _compose(plan)


def test_19_spoofed_ready_with_unresolved_ids_rejected() -> None:
    """19. spoofed ready=True + unresolved IDs rejected."""
    plan = _ready_plan(
        channels=(_channel_binding(0, "ch_user_1"),),
        events=(_event_binding(0, "ch_user_1", Fraction(0, 1)),),
        unresolved=(3,),
        ready=True,
    )
    with pytest.raises((TypeError, ValueError)):
        _compose(plan)


def test_20_duplicate_planned_channel_ids_rejected() -> None:
    """20. duplicate planned channel IDs rejected."""
    plan = _ready_plan(
        channels=(
            _channel_binding(1, "ch_user_1"),
            _channel_binding(2, "ch_user_1"),
        ),
        events=(
            _event_binding(1, "ch_user_1", Fraction(0, 1)),
            _event_binding(2, "ch_user_1", Fraction(1, 1)),
        ),
    )
    with pytest.raises((TypeError, ValueError)):
        _compose(plan)


def test_21_duplicate_planned_cluster_ids_rejected() -> None:
    """21. duplicate planned cluster IDs rejected."""
    plan = _ready_plan(
        channels=(
            _channel_binding(1, "ch_user_1"),
            _channel_binding(1, "ch_user_2"),
        ),
        events=(
            _event_binding(1, "ch_user_1", Fraction(0, 1)),
            _event_binding(1, "ch_user_2", Fraction(1, 1)),
        ),
    )
    with pytest.raises((TypeError, ValueError)):
        _compose(plan)


def test_22_empty_sample_path_rejected() -> None:
    """22. empty sample_path rejected."""
    plan = _ready_plan(
        channels=(_channel_binding(0, "ch_user_1", sample_path=""),),
        events=(_event_binding(0, "ch_user_1", Fraction(0, 1)),),
    )
    with pytest.raises((TypeError, ValueError)):
        _compose(plan)


def test_23_event_unknown_channel_rejected() -> None:
    """23. event unknown channel rejected."""
    plan = _ready_plan(
        channels=(_channel_binding(0, "ch_user_1"),),
        events=(_event_binding(0, "ch_user_99", Fraction(0, 1)),),
    )
    with pytest.raises((TypeError, ValueError)):
        _compose(plan)


def test_24_event_cluster_channel_mismatch_rejected() -> None:
    """24. event cluster/channel mismatch rejected."""
    plan = _ready_plan(
        channels=(
            _channel_binding(1, "ch_user_1"),
            _channel_binding(2, "ch_user_2"),
        ),
        events=(
            # cluster 1 must map to ch_user_1, not ch_user_2
            _event_binding(1, "ch_user_2", Fraction(0, 1)),
            _event_binding(2, "ch_user_2", Fraction(1, 1)),
        ),
    )
    with pytest.raises((TypeError, ValueError)):
        _compose(plan)


def test_25_event_non_fraction_position_rejected() -> None:
    """25. event non-Fraction position rejected."""
    # Bypass dataclass construction by object.__setattr__ on a copy-like path:
    # PlannedGestureEventBinding validates nothing on Fraction type, so craft via
    # object mutation after replace is not available — build with Fraction then
    # overwrite using object.__setattr__ on a frozen instance is blocked.
    # Use a hand-built instance via GesturePatternBindingPlan with a mock-like
    # event object that has the right attributes but wrong position type.
    bad_event = PlannedGestureEventBinding(
        cluster_id=0,
        channel_id="ch_user_1",
        quarter_position=Fraction(1, 4),
    )
    object.__setattr__(bad_event, "quarter_position", 0.25)
    plan = _ready_plan(
        channels=(_channel_binding(0, "ch_user_1"),),
        events=(bad_event,),
    )
    with pytest.raises((TypeError, ValueError)):
        _compose(plan)


def test_26_event_position_equal_length_rejected() -> None:
    """26. event position == length rejected."""
    length = Fraction(4, 1)
    plan = _ready_plan(
        channels=(_channel_binding(0, "ch_user_1"),),
        events=(_event_binding(0, "ch_user_1", length),),
        length=length,
    )
    with pytest.raises((TypeError, ValueError)):
        _compose(plan)


def test_27_event_position_greater_than_length_rejected() -> None:
    """27. event position > length rejected."""
    plan = _ready_plan(
        channels=(_channel_binding(0, "ch_user_1"),),
        events=(_event_binding(0, "ch_user_1", Fraction(5, 1)),),
        length=Fraction(4, 1),
    )
    with pytest.raises((TypeError, ValueError)):
        _compose(plan)


def test_28_valid_exclusive_end_position_accepted() -> None:
    """28. valid exclusive-end position accepted."""
    length = Fraction(4, 1)
    just_before = length - Fraction(1, 16)
    plan = _ready_plan(
        channels=(_channel_binding(0, "ch_user_1"),),
        events=(_event_binding(0, "ch_user_1", just_before),),
        length=length,
    )
    result = _compose(plan)
    assert result.pattern.triggers[0].position == just_before
    assert result.pattern.triggers[0].position < result.pattern.length_quarter_notes


def test_29_non_monotonic_ready_plan_not_silently_reordered() -> None:
    """29. malformed non-monotonic ready plan does not get silently reordered."""
    plan = _ready_plan(
        channels=(
            _channel_binding(1, "ch_user_1"),
            _channel_binding(2, "ch_user_2"),
        ),
        events=(
            _event_binding(2, "ch_user_2", Fraction(1, 1)),
            _event_binding(1, "ch_user_1", Fraction(0, 1)),  # earlier position later
            _event_binding(2, "ch_user_2", Fraction(2, 1)),
        ),
    )
    with pytest.raises((TypeError, ValueError)):
        _compose(plan)


def test_30_valid_event_order_unchanged_after_pattern_creation() -> None:
    """30. valid event order remains unchanged after Pattern creation."""
    positions = [Fraction(0, 1), Fraction(1, 3), Fraction(2, 3), Fraction(5, 2)]
    plan = _ready_plan(
        channels=(_channel_binding(0, "ch_user_1"),),
        events=tuple(_event_binding(0, "ch_user_1", p) for p in positions),
        length=Fraction(4, 1),
    )
    result = _compose(plan)
    assert [t.position for t in result.pattern.triggers] == positions
    assert [t.channel_id for t in result.pattern.triggers] == ["ch_user_1"] * 4


# ---------------------------------------------------------------------------
# Boundary: no reallocation / rack / DEFAULT_ON / recomputation
# ---------------------------------------------------------------------------


def test_31_no_channel_reallocation() -> None:
    """31. no channel reallocation."""
    plan = _ready_plan(
        channels=(_channel_binding(0, "ch_user_7"),),
        events=(_event_binding(0, "ch_user_7", Fraction(0, 1)),),
    )
    result = _compose(plan)
    assert result.channels[0].channel_id == "ch_user_7"
    assert result.pattern.triggers[0].channel_id == "ch_user_7"


def test_32_no_allocate_user_channel_id_call() -> None:
    """32. no allocate_user_channel_id call."""
    # Behavioral authority: the exploding mock forbids the call at runtime.
    with mock.patch(
        "src.pattern_core.allocate_user_channel_id",
        side_effect=AssertionError("allocate_user_channel_id must not be called"),
    ):
        result = _compose(_simple_ready_plan())
    assert result.channels[0].channel_id == "ch_user_1"


def test_33_no_add_user_channel_call() -> None:
    """33. no add_user_channel call."""
    src = _source_text()
    forbidden_calls = _forbidden_calls_in_src(src, ["add_user_channel"])
    assert forbidden_calls == set()


def test_34_no_default_on() -> None:
    """34. no DEFAULT_ON."""
    src = _source_text()
    # Semantic check: no references to DEFAULT_ON or _full_step_triggers in code
    forbidden_refs = _forbidden_name_refs_in_src(src, ["DEFAULT_ON", "_full_step_triggers"])
    assert forbidden_refs == set()
    plan = _ready_plan(
        channels=(_channel_binding(0, "ch_user_1"),),
        events=(_event_binding(0, "ch_user_1", Fraction(1, 3)),),
    )
    result = _compose(plan)
    # Only the one planned event — not 16 DEFAULT_ON steps.
    assert len(result.pattern.triggers) == 1


def test_35_trigger_count_equals_event_binding_count() -> None:
    """35. Trigger count == event binding count."""
    events = (
        _event_binding(0, "ch_user_1", Fraction(0, 1)),
        _event_binding(0, "ch_user_1", Fraction(1, 2)),
        _event_binding(0, "ch_user_1", Fraction(5, 4)),
    )
    plan = _ready_plan(
        channels=(_channel_binding(0, "ch_user_1"),),
        events=events,
    )
    result = _compose(plan)
    assert len(result.pattern.triggers) == len(plan.event_bindings) == 3


def test_36_no_ranking_recomputation() -> None:
    """36. no ranking recomputation."""
    src = _source_text()
    # Derived from the real ranking authority (#882): its callables plus every
    # ranking-owned field of ClusterRanking/RankedCandidate/LibraryCandidate.
    assert _forbidden_calls_in_src(src, _RANKING_CALLABLES) == set()
    assert _forbidden_name_refs_in_src(src, _RANKING_FIELDS, attributes_only=True) == set()


def test_37_no_timing_recomputation() -> None:
    """37. no timing recomputation."""
    src = _source_text()
    assert _forbidden_calls_in_src(src, _TIMING_CALLABLES) == set()
    # Attribute reads only: the composer legitimately owns a local `events`.
    assert _forbidden_name_refs_in_src(src, _TIMING_FIELDS, attributes_only=True) == set()


def test_38_no_catalog_db_access() -> None:
    """38. no catalog/DB access."""
    mod = importlib.import_module("src.gesture_pattern_core_composition")
    imported = _imported_module_names(mod)
    for banned in (
        "sqlite3",
        "sqlalchemy",
        "db",
        "src.db",
        "gesture_catalog_adapter",
        "src.gesture_catalog_adapter",
    ):
        assert banned not in imported
    src = _source_text()
    # DB operations stay covered by a derived set, not a guessed name list, so
    # `db.init_db()` (also via `from . import db`) is rejected.
    forbidden = sorted(set(_CATALOG_CALLABLES) | set(_DB_CALLABLES))
    assert _forbidden_calls_in_src(src, forbidden) == set()


def test_39_no_selection_recomputation() -> None:
    """39. no selection recomputation."""
    src = _source_text()
    # The planner is the only selection authority; it must never be re-run.
    assert _forbidden_calls_in_src(src, _PLANNER_CALLABLES) == set()
    # Reading any selection-owned plan field (notably `selected_rank`) would
    # make the composer re-select instead of consuming the ready plan.
    assert _forbidden_name_refs_in_src(src, _SELECTION_FIELDS, attributes_only=True) == set()


def test_40_no_pattern_length_recomputation() -> None:
    """40. no Pattern-length recomputation."""
    src = _source_text()
    # Pattern length is plan authority; timing projection must not feed it.
    assert (
        _forbidden_name_refs_in_src(
            src, _TIMING_PROJECTION_FIELDS, attributes_only=True
        )
        == set()
    )
    # Dataclass fields alone cannot express length inference, so the inference
    # operations are banned by name as well. Without this a local
    # `next_bar(last_onset)` helper would pass while recomputing length.
    assert _forbidden_name_refs_in_src(src, _LENGTH_INFERENCE_NAMES) == set()
    length = Fraction(11, 3)
    plan = _ready_plan(
        channels=(_channel_binding(0, "ch_user_1"),),
        events=(_event_binding(0, "ch_user_1", Fraction(0, 1)),),
        length=length,
    )
    assert _compose(plan).pattern.length_quarter_notes == length


def test__semantic_checker_rejects_dynamic_member_lookup() -> None:
    """``getattr(mod, "forbidden")`` captures the authority by string name."""
    variants = [
        'import pattern_core\nallocator = getattr(pattern_core, "allocate_user_channel_id")\n',
        'import builtins, pattern_core\nallocator = builtins.getattr(pattern_core, "allocate_user_channel_id")\n',
        'import operator, pattern_core\nallocator = operator.attrgetter("allocate_user_channel_id")(pattern_core)\n',
        'import pattern_core\nallocator = pattern_core.__dict__["allocate_user_channel_id"]\n',
        'import pattern_core\nallocator = vars(pattern_core)["allocate_user_channel_id"]\n',
    ]
    for src in variants:
        assert _forbidden_calls_in_src(
            src, _PATTERN_CORE_MUTATION_CALLABLES
        ) == {"allocate_user_channel_id"}, src


def test__semantic_checker_ignores_ordinary_string_literal() -> None:
    """A string that merely spells a forbidden name is still not a reference."""
    src = """
import pattern_core

message = "allocate_user_channel_id"
lookup = getattr(pattern_core, "some_safe_name")
"""
    assert _forbidden_calls_in_src(src, _PATTERN_CORE_MUTATION_CALLABLES) == set()


def test__length_inference_guard_rejects_local_inference_helpers() -> None:
    """A local length-inference helper must not pass test 40's guard.

    Regression proof for replacing the inference ban with dataclass-derived
    fields only: those fields do not include the inference operations, so
    `next_bar(last_onset)` slipped through.
    """
    violating = """
def compose(timing):
    return next_bar(timing.last_onset)
"""
    assert _forbidden_name_refs_in_src(
        violating, _LENGTH_INFERENCE_NAMES
    ) == {"next_bar", "last_onset"}
    # The frozen composer itself must stay clean.
    assert _forbidden_name_refs_in_src(_source_text(), _LENGTH_INFERENCE_NAMES) == set()


def test__length_inference_guard_is_live() -> None:
    """The inference ban must actually flag each guarded operation."""
    for name in _LENGTH_INFERENCE_NAMES:
        assert _forbidden_name_refs_in_src(
            f"def compose():\n    return {name}(value)\n", _LENGTH_INFERENCE_NAMES
        ) == {name}, name


def test_40_length_preservation_rejects_integral_only_branch() -> None:
    """Length preservation must not be satisfiable by an integral-only branch.

    A four-quarter fixture coincidentally matches a truncated computation, so
    the preservation proof alone cannot show that non-integral lengths survive.
    The guard is bound to the real composer call here.
    """
    for length in (Fraction(11, 3), Fraction(7, 2), Fraction(5, 4)):
        plan = _ready_plan(
            channels=(_channel_binding(0, "ch_user_1"),),
            events=(_event_binding(0, "ch_user_1", Fraction(0, 1)),),
            length=length,
        )
        assert _compose(plan).pattern.length_quarter_notes == length


def test_41_no_channel_rack_state() -> None:
    """41. no ChannelRackState."""
    src = _source_text()
    # Derived from the real Channel Rack authority: no rack helper is called
    # and no rack state symbol is referenced.
    assert _forbidden_calls_in_src(src, _CHANNEL_RACK_CALLABLES) == set()
    assert _forbidden_name_refs_in_src(src, _RACK_STATE_NAMES) == set()
    result = _compose(_simple_ready_plan())
    assert not hasattr(result, "rack")
    assert not hasattr(result, "channel_rack")
    assert set(getattr(result, "__dataclass_fields__", {})) <= {"channels", "pattern"} or (
        hasattr(result, "channels") and hasattr(result, "pattern")
    )


def test_42_input_plan_unchanged() -> None:
    """42. input plan unchanged."""
    plan = _simple_ready_plan()
    before = copy.deepcopy(plan)
    _compose(plan)
    assert plan == before
    assert plan.channel_bindings == before.channel_bindings
    assert plan.event_bindings == before.event_bindings


def test_43_identical_input_twice_equal_composition() -> None:
    """43. identical input twice → equal composition."""
    plan = _simple_ready_plan()
    a = _compose(plan, "same-id")
    b = _compose(plan, "same-id")
    assert a == b
    assert a.channels == b.channels
    assert a.pattern == b.pattern


def test_44_every_trigger_references_composed_channel() -> None:
    """44. every trigger references a composed channel."""
    plan = _ready_plan(
        channels=(
            _channel_binding(1, "ch_user_1"),
            _channel_binding(2, "ch_user_2"),
        ),
        events=(
            _event_binding(1, "ch_user_1", Fraction(0, 1)),
            _event_binding(2, "ch_user_2", Fraction(1, 2)),
            _event_binding(1, "ch_user_1", Fraction(1, 1)),
        ),
    )
    result = _compose(plan)
    known = {c.channel_id for c in result.channels}
    assert known == {"ch_user_1", "ch_user_2"}
    for trigger in result.pattern.triggers:
        assert trigger.channel_id in known


def test_45_pattern_core_membership_helper_accepts_graph() -> None:
    """45. Pattern-Core membership helper accepts graph."""
    result = _compose(_simple_ready_plan())
    require_triggers_reference_known_channels(
        result.pattern.triggers,
        known_channel_ids=[c.channel_id for c in result.channels],
    )


def test_46_valid_891_generated_plan_composes_directly() -> None:
    """46. valid #891-generated plan composes directly."""
    timing = _timing(
        [
            _event(0, Fraction(0, 1)),
            _event(0, Fraction(1, 2)),
            _event(1, Fraction(5, 4)),
        ]
    )
    rankings = [
        _ranking(0, [_ranked("a", 0.1, 1)]),
        _ranking(1, [_ranked("b", 0.2, 1)]),
    ]
    plan = _plan_from_891(
        timing,
        rankings,
        [_candidate("a"), _candidate("b")],
        {0: "a", 1: "b"},
        length=Fraction(4, 1),
    )
    assert plan.ready_for_pattern is True
    assert plan.unresolved_cluster_ids == ()
    result = _compose(plan, "from-891")
    assert len(result.channels) == len(plan.channel_bindings) == 2
    assert len(result.pattern.triggers) == len(plan.event_bindings) == 3
    assert result.pattern.pattern_id == "from-891"
    assert result.pattern.length_quarter_notes == plan.pattern_length_quarters
    assert [c.channel_id for c in result.channels] == [
        b.channel_id for b in plan.channel_bindings
    ]
    assert [t.position for t in result.pattern.triggers] == [
        e.quarter_position for e in plan.event_bindings
    ]


def test_47_empty_ready_plan_follows_docs_gate() -> None:
    """47. empty ready plan behavior exactly follows frozen DOCS_GATE decision."""
    # Live #891: empty timing → ready_for_pattern=True, empty bindings.
    empty_timing = _timing(())
    plan = _plan_from_891(empty_timing, [], [], {}, length=Fraction(8, 1))
    assert plan.ready_for_pattern is True
    assert plan.channel_bindings == ()
    assert plan.event_bindings == ()
    assert plan.unresolved_cluster_ids == ()

    result = _compose(plan, "empty-gesture")
    assert result.channels == ()
    assert result.pattern.triggers == ()
    assert result.pattern.pattern_id == "empty-gesture"
    assert result.pattern.length_quarter_notes == Fraction(8, 1)

    # Orphan planned channel (not producible by #891) must fail closed.
    orphan = _ready_plan(
        channels=(_channel_binding(0, "ch_user_1"),),
        events=(),
    )
    with pytest.raises((TypeError, ValueError)):
        _compose(orphan)


# ---------------------------------------------------------------------------
# Protected suites / module boundary (items 48-52 are runner-level;
# module AST/import guards freeze the composition boundary here too)
# ---------------------------------------------------------------------------


def test_48_module_import_boundary_allows_only_declared_roots() -> None:
    """48. module import boundary aligned with docs (supports protected #891 GREEN)."""
    mod = importlib.import_module("src.gesture_pattern_core_composition")
    imported = _imported_module_names(mod)
    assert imported <= _ALLOWED_IMPORT_ROOTS
    for banned in _BANNED_IMPORT_ROOTS:
        assert banned not in imported


def test_49_module_does_not_call_upstream_planner_or_timing() -> None:
    """49. no upstream planner/timing/analysis calls (supports #888 suite independence)."""
    src = _source_text()
    forbidden = sorted(set(_PLANNER_CALLABLES) | set(_TIMING_CALLABLES) | set(_ANALYSIS_CALLABLES))
    assert _forbidden_calls_in_src(src, forbidden) == set()


def test_50_module_does_not_call_ranking_or_catalog() -> None:
    """50. no ranking/catalog calls (supports #882/#886 suite independence)."""
    src = _source_text()
    forbidden = sorted(set(_RANKING_CALLABLES) | set(_CATALOG_CALLABLES))
    assert _forbidden_calls_in_src(src, forbidden) == set()


def test_51_module_does_not_mutate_pattern_core_or_rack_helpers() -> None:
    """51. no Pattern Core mutation / Channel Rack DEFAULT_ON helpers."""
    src = _source_text()
    forbidden = sorted(
        set(_PATTERN_CORE_MUTATION_CALLABLES) | set(_CHANNEL_RACK_CALLABLES)
    )
    assert _forbidden_calls_in_src(src, forbidden) == set()
    assert _forbidden_name_refs_in_src(src, ["DEFAULT_ON"]) == set()
    # Membership helper is allowed / expected — proven as a real call, not as
    # a text match that a comment or docstring could satisfy.
    assert _forbidden_calls_in_src(
        src, ["require_triggers_reference_known_channels"]
    ) == {"require_triggers_reference_known_channels"}


def test_52_public_seam_signature_frozen() -> None:
    """52. public seam signature frozen for sequencer-compatible composition delta."""
    sig = inspect.signature(compose_gesture_pattern_core)
    params = list(sig.parameters.values())
    assert params[0].name == "plan"
    assert params[0].kind in (
        inspect.Parameter.POSITIONAL_ONLY,
        inspect.Parameter.POSITIONAL_OR_KEYWORD,
    )
    assert "pattern_id" in sig.parameters
    assert sig.parameters["pattern_id"].kind == inspect.Parameter.KEYWORD_ONLY
    # Result type exposes channels + pattern only (composition delta).
    result = _compose(_simple_ready_plan(), "sig-check")
    assert hasattr(result, "channels")
    assert hasattr(result, "pattern")
    assert isinstance(result.pattern, Pattern)
