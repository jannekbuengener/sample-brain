"""Fail-closed Library scope evidence capture helpers for #837.

Capture is only allowed after observable presentation state matches the
expected scope. Click-only or mislabeled captures must raise.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Mapping


SCOPE_SOURCES = "sources"
SCOPE_ALL = "all"
SCOPE_FAVORITES = "favorites"
SCOPE_RECORDINGS = "recordings"
SCOPE_COLLECTIONS = "collections"

EVIDENCE_FILENAMES = {
    SCOPE_SOURCES: "01_sources_scope.png",
    SCOPE_ALL: "02_all_samples_scope.png",
    SCOPE_FAVORITES: "03_favorites_scope.png",
    SCOPE_RECORDINGS: "04_recordings_scope.png",
    SCOPE_COLLECTIONS: "05_collections_scope.png",
}


@dataclass(frozen=True)
class LibraryScopePresentation:
    """Observable UI seams for one Library scope capture."""

    mode: str
    browser_title: str
    tree_visible: bool
    collections_visible: bool
    scope_bar_y: float
    header_bottom_y: float
    selected_node_id: str | None = None


class ScopeCaptureError(RuntimeError):
    """Raised when a capture would mislabel or fail integrity checks."""


def expected_presentation(
    scope: str,
    *,
    browser_title: str,
    tree_visible: bool,
    collections_visible: bool,
    scope_bar_y: float,
    header_bottom_y: float,
    selected_node_id: str | None = None,
) -> LibraryScopePresentation:
    return LibraryScopePresentation(
        mode=scope,
        browser_title=browser_title,
        tree_visible=tree_visible,
        collections_visible=collections_visible,
        scope_bar_y=scope_bar_y,
        header_bottom_y=header_bottom_y,
        selected_node_id=selected_node_id,
    )


def assert_scope_bar_pinned(
    presentation: LibraryScopePresentation,
    *,
    min_gap_from_header_px: float = 80.0,
) -> None:
    """#837: secondary icon bar is pinned at the Library pane bottom, not under the header."""
    gap = presentation.scope_bar_y - presentation.header_bottom_y
    if gap < min_gap_from_header_px:
        raise ScopeCaptureError(
            "libraryScopeBar not pinned at Library pane bottom: "
            f"bar_y={presentation.scope_bar_y} header_bottom={presentation.header_bottom_y}"
        )


def assert_presentation_matches(scope: str, observed: LibraryScopePresentation) -> None:
    if observed.mode != scope:
        raise ScopeCaptureError(
            f"scope mode mismatch: expected={scope!r} observed={observed.mode!r}"
        )
    assert_scope_bar_pinned(observed)

    if scope == SCOPE_SOURCES:
        if not observed.tree_visible:
            raise ScopeCaptureError("Sources capture requires visible Source Tree")
        if observed.collections_visible:
            raise ScopeCaptureError("Sources capture must not show Collections list")
        return

    if scope == SCOPE_ALL:
        if observed.browser_title != "All Samples":
            raise ScopeCaptureError(
                f"All Samples title mismatch: {observed.browser_title!r}"
            )
        if observed.tree_visible:
            raise ScopeCaptureError("All Samples capture requires hidden Source Tree")
        if observed.collections_visible:
            raise ScopeCaptureError("All Samples must not show Collections list")
        return

    if scope == SCOPE_FAVORITES:
        if observed.browser_title != "Favorites":
            raise ScopeCaptureError(
                f"Favorites title mismatch: {observed.browser_title!r}"
            )
        if observed.tree_visible:
            raise ScopeCaptureError("Favorites capture requires hidden Source Tree")
        if observed.collections_visible:
            raise ScopeCaptureError("Favorites must not show Collections list")
        return

    if scope == SCOPE_RECORDINGS:
        if observed.browser_title != "Recordings":
            raise ScopeCaptureError(
                f"Recordings title mismatch: {observed.browser_title!r}"
            )
        if observed.tree_visible:
            raise ScopeCaptureError("Recordings capture requires hidden Source Tree")
        if observed.collections_visible:
            raise ScopeCaptureError("Recordings must not show Collections list")
        return

    if scope == SCOPE_COLLECTIONS:
        if not observed.collections_visible:
            raise ScopeCaptureError(
                "Collections capture requires visible libraryCollectionList"
            )
        if observed.tree_visible:
            raise ScopeCaptureError("Collections capture requires hidden Source Tree")
        return

    raise ScopeCaptureError(f"unknown scope for capture: {scope!r}")


def sha256_file(path: str) -> str:
    from pathlib import Path

    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def assert_distinct_secondary_scope_hashes(
    hashes: Mapping[str, str],
) -> None:
    """Integrity guard for secondary #837 acceptance states.

    All-Samples / Favorites / Recordings / Collections must not all be
    byte-identical.
    """
    secondary = [
        hashes.get(EVIDENCE_FILENAMES[SCOPE_ALL], ""),
        hashes.get(EVIDENCE_FILENAMES[SCOPE_FAVORITES], ""),
        hashes.get(EVIDENCE_FILENAMES[SCOPE_RECORDINGS], ""),
        hashes.get(EVIDENCE_FILENAMES[SCOPE_COLLECTIONS], ""),
    ]
    if not all(secondary):
        raise ScopeCaptureError("missing secondary-scope SHA for integrity guard")
    if len(set(secondary)) == 1:
        raise ScopeCaptureError(
            "evidence integrity fail: secondary scope captures are byte-identical"
        )


def capture_report_lines(
    *,
    hashes: Mapping[str, str],
    titles: Mapping[str, str],
) -> list[str]:
    return [
        f"01 SHA: {hashes[EVIDENCE_FILENAMES[SCOPE_SOURCES]]}",
        f"02 SHA: {hashes[EVIDENCE_FILENAMES[SCOPE_ALL]]}",
        f"03 SHA: {hashes[EVIDENCE_FILENAMES[SCOPE_FAVORITES]]}",
        f"04 SHA: {hashes[EVIDENCE_FILENAMES[SCOPE_RECORDINGS]]}",
        f"05 SHA: {hashes[EVIDENCE_FILENAMES[SCOPE_COLLECTIONS]]}",
        f"02 expected scope/title: all / {titles.get(SCOPE_ALL, 'All Samples')}",
        f"03 expected scope/title: favorites / {titles.get(SCOPE_FAVORITES, 'Favorites')}",
        f"04 expected scope/title: recordings / {titles.get(SCOPE_RECORDINGS, 'Recordings')}",
        f"05 expected scope/title: collections / {titles.get(SCOPE_COLLECTIONS, '(collections surface)')}",
    ]
