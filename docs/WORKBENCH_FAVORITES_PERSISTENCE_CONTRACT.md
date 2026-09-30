# Workbench Favorites Persistence Contract (#766 minimum for #767)

## Purpose

Defines the minimum local Favorites / starred-samples domain needed so the
Screen-1 Browser Favorite column (#767) is not renderer-local state.

Full Favorites navigation in the compact top icon bar (#765/#766) is out of
scope for this minimum slice.

## Product rules

- Favorites is a user-organization concept, not a source folder and not an
  analysis category.
- Favorites is **not** a 1–5 rating system.
- Favorites is **not** silently modeled as a magic playlist. Collections /
  playlists remain a separate concept.
- Star/unstar never deletes or copies source audio.
- Missing/offline source files fail soft; favorite metadata remains truthful.

## Persistence

- Store favorites in the existing Workbench local SQLite library database.
- Prefer a dedicated `favorite_samples` table keyed by resolved sample path.
- Identity: stable absolute sample path (same normalization style as playlist
  sample paths: `Path(...).expanduser().resolve()` string).
- Duplicate star is idempotent; unstar of an unknown path is idempotent.
- State survives process restart via the same database file.

## Domain API (minimum)

- `is_sample_favorite(path) -> bool`
- `set_sample_favorite(path, favorite: bool) -> bool` (resulting state)
- `toggle_sample_favorite(path) -> bool` (resulting state)
- `list_favorite_sample_paths() -> list[str]` (deterministic order)

## Renderer wiring

- QML projects `favorite: bool` from Python for each Browser row.
- Toggle intent goes through the interaction adapter / bridge.
- QML must not keep authoritative favorite state.

## Non-scope (deferred to full #766)

- Favorites entry in compact top icon navigation
- Favorites-only Browser scope listing
- Collections redesign, tags, smart collections, cloud sync
