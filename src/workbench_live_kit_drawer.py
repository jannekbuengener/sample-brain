"""Pure presentation geometry for the transient Screen-1 Live-Kit drawer."""

from __future__ import annotations

from dataclasses import dataclass


DRAWER_HEADER_HEIGHT_PX = 64
DRAWER_ROW_HEIGHT_PX = 48
DRAWER_MAX_HEIGHT_RATIO = 0.40


@dataclass(frozen=True)
class LiveKitDrawerGeometry:
    """Renderer-facing dimensions; never owns musical Live-Kit state."""

    height: int
    browser_bottom_inset: int
    internal_scroll: bool


def drawer_geometry_for_rows(
    row_count: int, available_height: int
) -> LiveKitDrawerGeometry:
    """Return a compact, browser-scoped drawer height for real projected rows.

    No rows means no drawer band.  Once a real row exists, the header plus one
    row is visible; further rows grow the drawer until the 40 percent cap.  The
    renderer then owns scrolling inside that bounded overlay.
    """

    if row_count < 0:
        raise ValueError("row_count darf nicht negativ sein.")
    if available_height < 0:
        raise ValueError("available_height darf nicht negativ sein.")
    if row_count == 0 or available_height == 0:
        return LiveKitDrawerGeometry(
            height=0,
            browser_bottom_inset=0,
            internal_scroll=False,
        )

    requested_height = DRAWER_HEADER_HEIGHT_PX + row_count * DRAWER_ROW_HEIGHT_PX
    capped_height = int(available_height * DRAWER_MAX_HEIGHT_RATIO)
    height = min(requested_height, capped_height)
    return LiveKitDrawerGeometry(
        height=height,
        browser_bottom_inset=height,
        internal_scroll=requested_height > height,
    )
