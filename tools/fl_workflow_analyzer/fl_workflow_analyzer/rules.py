"""Versioned deterministic correlation / segmentation / metric rules (#1322).

RULE_VERSION must bump when any threshold or confidence rule changes so
reprocessing can distinguish interpretations.
"""

from __future__ import annotations

from . import RULE_VERSION

# ---------------------------------------------------------------------------
# Time windows (nanoseconds)
#
# #1320 venue evidence (not universal constants):
#   - CLOCK_MARKER cross-process skew sample ~1.4 s (independent markers)
#   - nearest FL↔Windows event p50 ~73 ms, p95 ~1.3 s
#
# Correlation uses a *bounded action window* sized from the nearest-event
# distribution, not a blanket 1.4 s clock shift. Wall-clock authority remains
# raw t_wall_ns; we never rewrite recorder timestamps.
# ---------------------------------------------------------------------------

# Same-action fusion of FL semantic + Windows input evidence.
CORRELATION_WINDOW_NS = 500_000_000  # 500 ms (~>> p50, << marker skew)

# Soft staleness: after this gap since last FOCUS, confidence for win→surface
# correlation drops from high→medium. Surface itself persists until replaced or
# FL background (hard clear). Not a hard cutoff — avoids inventing Browser.
SURFACE_CONTEXT_STALE_NS = 30_000_000_000  # 30 s

# Merge adjacent same-activity segments when gap is below this.
SEGMENT_MERGE_GAP_NS = 2_000_000_000  # 2 s

# Align with recorder ActivityTracker DEFAULT_IDLE_AFTER_NS.
IDLE_QUIET_NS = 120_000_000_000  # 2 min

# Short return A→…→A treated as backtracking when return latency ≤ this.
BACKTRACK_MAX_RETURN_NS = 30_000_000_000  # 30 s

# Sliding window for context-churn density (switches per active minute).
CHURN_WINDOW_NS = 60_000_000_000  # 60 s

# Hot-path / loop: require at least this many occurrences (avoid one-offs).
HOT_PATH_MIN_COUNT = 2
LOOP_MIN_REPEATS = 2

# N-gram lengths for hot paths.
HOT_PATH_NS = (2, 3, 4, 5)

# Robust bottleneck: duration > median + k * MAD (per activity, per session).
BOTTLENECK_MAD_K = 3.0
BOTTLENECK_MIN_SAMPLES = 3

# Known #1320 blind spots — must remain visible; never invent certainty.
BLIND_SPOTS = (
    {
        "id": "playlist_active_tool",
        "description": "Playlist active tool not directly measurable; Hint/Undo only",
        "product_impact": "Edit tool identity inside Playlist remains low/medium confidence",
    },
    {
        "id": "browser_surface_label",
        "description": "Browser surface label not observed via ui.getFocused(Browser) on venue",
        "product_impact": "Browse/search often inferred from weak signals → low confidence",
    },
    {
        "id": "plugin_identity",
        "description": "Focused plugin name often empty; plugin identity deferred",
        "product_impact": "Plugin interaction detectable as focus class, not named plugin",
    },
)

# Surface → Sample Brain Edit vs Arrangement mapping (FL-side evidence only).
# Edit-like: pattern/sound editing surfaces.
# Arrangement-like: Playlist timeline.
EDIT_LIKE_SURFACES = frozenset({"PianoRoll", "ChannelRack", "Plugin"})
ARRANGEMENT_LIKE_SURFACES = frozenset({"Playlist"})

# Activity vocabulary (V1 — enough to make flows visible; not a full DAW ontology).
ACTIVITY_TYPES = frozenset(
    {
        "browse",
        "audition",
        "playlist_edit",
        "piano_roll_edit",
        "channel_rack",
        "mixer",
        "plugin_interaction",
        "transport_listening",
        "navigation",
        "idle",
        "background",
        "unknown",
        "edit",  # SB Edit-like aggregate when surface is edit-like
        "arrangement",  # SB Arrangement-like (Playlist)
    }
)

# Hint tokens that support edit correlation (explicit, testable).
# Ordered tuple — first match wins (deterministic across PYTHONHASHSEED).
HINT_EDIT_TOKENS = (
    "make unique",
    "slice",
    "brush",
    "paint",
    "pencil",
    "stretch",
    "resize",
    "delete",
    "mute",
    "slip",
    "cut",
    "select",
    "zoom",
)


def rule_manifest() -> dict:
    return {
        "rule_version": RULE_VERSION,
        "correlation_window_ns": CORRELATION_WINDOW_NS,
        "surface_context_stale_ns": SURFACE_CONTEXT_STALE_NS,
        "segment_merge_gap_ns": SEGMENT_MERGE_GAP_NS,
        "idle_quiet_ns": IDLE_QUIET_NS,
        "backtrack_max_return_ns": BACKTRACK_MAX_RETURN_NS,
        "churn_window_ns": CHURN_WINDOW_NS,
        "hot_path_min_count": HOT_PATH_MIN_COUNT,
        "loop_min_repeats": LOOP_MIN_REPEATS,
        "hot_path_ns": list(HOT_PATH_NS),
        "bottleneck_mad_k": BOTTLENECK_MAD_K,
        "bottleneck_min_samples": BOTTLENECK_MIN_SAMPLES,
        "blind_spots": list(BLIND_SPOTS),
        "edit_like_surfaces": sorted(EDIT_LIKE_SURFACES),
        "arrangement_like_surfaces": sorted(ARRANGEMENT_LIKE_SURFACES),
        "rationale": {
            "correlation_window_ns": (
                "Sized from #1320 nearest-event p50≈73ms; 500ms bounds same-action "
                "fusion without applying the ~1.4s CLOCK_MARKER skew as a global shift."
            ),
            "surface_context_stale_ns": (
                "Measured surface persists until next FOCUS or FL background; "
                "after 30s without focus refresh, win correlations downgrade to medium."
            ),
            "idle_quiet_ns": "Mirrors recorder DEFAULT_IDLE_AFTER_NS (2 min).",
        },
    }
