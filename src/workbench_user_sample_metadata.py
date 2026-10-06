"""Session-owned user-channel classification metadata (#952).

Canonical authority: ``docs/USER_CHANNEL_CLASSIFICATION_AUTHORITY.md`` §1-§3.

This module is the only I/O owner for user-channel sample classification. It
reads the Workbench library through the existing read-only seams so that no
second normalizer, SQL surface, or path store exists:

- :class:`UserSampleMetadata` — one resolved library row: ``sample_class`` plus
  the ``source_bpm`` that comes from the *same* already-read row (needed for
  SYNC-on user loop channels without a second seam).
- :class:`UserSampleMetadataBinding` — immutable ``Mapping`` keyed by the exact
  durable ``Channel.sample_path`` string. A missing key means "no evidence",
  which the classifier treats as ``ambiguous`` (fail-closed).
- :class:`UserSampleMetadataResolver` — the injected protocol
  (``resolve`` / ``resolve_one``) the Rack controller depends on.
- :class:`WorkbenchLibraryUserSampleMetadataResolver` — the concrete resolver
  over :func:`workbench_library.workbench_library_readonly_connection` and
  :func:`workbench_library.query_sample_by_path_on_readonly_connection`.

Lookup canonicalization (``str(Path(p).expanduser().resolve())``) and the
analyzer/fingerprint gate stay private to ``workbench_library``; this module
passes raw durable strings in and keys the binding by the same raw strings.

The binding is derived, in-memory, and never serialized: session JSON stays
path-only. ``pred_type`` is never read.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterable, Iterator, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from .workbench_library import (
    query_sample_by_path_on_readonly_connection,
    workbench_library_readonly_connection,
)


@dataclass(frozen=True)
class UserSampleMetadata:
    """One resolved library row for a user-channel sample path.

    ``sample_class`` is the raw library value. ``None`` (or any non-explicit
    value) means "resolved but unclassifiable" and therefore fails closed to
    ``ambiguous`` at every consumption point.
    """

    sample_class: str | None = None
    source_bpm: float | None = None


class UserSampleMetadataBinding(Mapping[str, UserSampleMetadata]):
    """Immutable path-keyed metadata binding.

    Deliberately not a ``MutableMapping``: the binding is derived state owned by
    the Rack controller, and a mutable mapping would let a consumer silently
    edit classification authority.
    """

    __slots__ = ("_entries",)

    def __init__(self, entries: Mapping[str, UserSampleMetadata] | None = None) -> None:
        self._entries: dict[str, UserSampleMetadata] = dict(entries or {})

    def __getitem__(self, key: str) -> UserSampleMetadata:
        return self._entries[key]

    def __iter__(self) -> Iterator[str]:
        return iter(self._entries)

    def __len__(self) -> int:
        return len(self._entries)

    def __eq__(self, other: object) -> bool:
        if isinstance(other, UserSampleMetadataBinding):
            return self._entries == other._entries
        if isinstance(other, Mapping):
            return self._entries == dict(other)
        return NotImplemented

    def __ne__(self, other: object) -> bool:
        result = self.__eq__(other)
        if result is NotImplemented:
            return result
        return not result

    def __repr__(self) -> str:
        return f"UserSampleMetadataBinding({len(self._entries)} entries)"


EMPTY_USER_SAMPLE_METADATA_BINDING = UserSampleMetadataBinding()


@runtime_checkable
class UserSampleMetadataResolver(Protocol):
    """Injected seam the Rack controller may call only at B1-B4 boundaries."""

    def resolve(self, paths: Iterable[str]) -> UserSampleMetadataBinding:
        """Resolve a batch of raw durable paths in one bounded read.

        Keys are the raw durable strings, byte for byte: no normalizer runs
        here, so lookup by ``Channel.sample_path`` cannot miss.
        """

    def resolve_one(self, path: str) -> UserSampleMetadata | None:
        """Resolve one raw durable path, or ``None`` when there is no evidence."""


def _coerce_source_bpm(value: Any) -> float | None:
    """Return a finite float BPM, or ``None`` for missing/unusable values."""
    if value is None:
        return None
    try:
        bpm = float(value)
    except (TypeError, ValueError):
        return None
    if bpm != bpm or bpm in (float("inf"), float("-inf")):
        return None
    return bpm


def _coerce_sample_class(value: Any) -> str | None:
    """Return the raw library class string, or ``None`` when unusable."""
    if value is None:
        return None
    text = str(value).strip()
    return text or None


class WorkbenchLibraryUserSampleMetadataResolver:
    """The only I/O owner: resolve user-sample metadata from the library.

    Every batch opens at most one read-only snapshot connection and performs no
    writes, no schema DDL, and no database creation. A missing, unreadable,
    stale-fingerprint, or catalog-miss path yields *no binding entry*, which is
    the fail-closed ``ambiguous`` case for all consumers.
    """

    __slots__ = ("_library_db_path",)

    def __init__(self, *, library_db_path: Path | None = None) -> None:
        self._library_db_path = (
            Path(library_db_path) if library_db_path is not None else None
        )

    @property
    def library_db_path(self) -> Path | None:
        return self._library_db_path

    def resolve(self, paths: Iterable[str]) -> UserSampleMetadataBinding:
        """Resolve a batch of raw durable paths in one bounded read.

        The binding is keyed by the *raw durable* strings handed in, byte for
        byte. No normalizer runs here: canonicalization stays private to
        ``workbench_library.query_sample_by_path_on_readonly_connection``, so a
        lookup by ``Channel.sample_path`` can never miss a present entry.
        """
        ordered = tuple(
            dict.fromkeys(
                raw
                for raw in (str(path) for path in paths if path is not None)
                if raw
            )
        )
        if not ordered:
            return EMPTY_USER_SAMPLE_METADATA_BINDING

        entries: dict[str, UserSampleMetadata] = {}
        try:
            with workbench_library_readonly_connection(
                self._library_db_path
            ) as conn:
                if conn is None:
                    return EMPTY_USER_SAMPLE_METADATA_BINDING
                for raw_path in ordered:
                    row = query_sample_by_path_on_readonly_connection(conn, raw_path)
                    if row is None:
                        # Catalog miss, stale fingerprint, or analyzer-version
                        # mismatch: no entry, so consumers fail closed.
                        continue
                    entries[raw_path] = UserSampleMetadata(
                        sample_class=_coerce_sample_class(row.sample_class),
                        source_bpm=_coerce_source_bpm(row.bpm),
                    )
        except (OSError, sqlite3.Error):
            # Unreadable library degrades the whole batch to ambiguous rather
            # than breaking playback or mutating anything.
            return EMPTY_USER_SAMPLE_METADATA_BINDING
        return UserSampleMetadataBinding(entries)

    def resolve_one(self, path: str) -> UserSampleMetadata | None:
        return self.resolve((path,)).get(str(path))


__all__ = [
    "EMPTY_USER_SAMPLE_METADATA_BINDING",
    "UserSampleMetadata",
    "UserSampleMetadataBinding",
    "UserSampleMetadataResolver",
    "WorkbenchLibraryUserSampleMetadataResolver",
]