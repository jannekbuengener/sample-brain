# Workbench Favorites Persistence + Navigation Contract (#766)

## Purpose

Defines the local Favorites / starred-samples domain for Screen 1:

1. Browser Favorite column wiring (delivered with #767): Python-owned
   persistence projected onto Browser rows.
2. Dedicated Favorites navigation scope in the compact `libraryScopeBar`
   (this #766 remainder): list only currently favorited samples through the
   existing Browser / audition contracts.

## Product rules

- Favorites is a user-organization concept, not a source folder and not an
  analysis category.
- Favorites is **not** a 1–5 rating system.
- Favorites is **not** silently modeled as a magic playlist. Collections /
  playlists remain a separate concept and a separate `LibraryScopeKind`.
- Star/unstar never deletes or copies source audio.
- Missing/offline source files fail soft; favorite metadata remains truthful
  and the Favorites scope may still project a fail-soft Browser row.

## Persistence

- Store favorites in the existing Workbench local SQLite library database.
- Dedicated `favorite_samples` table keyed by resolved sample path.
- Identity: stable absolute sample path (same normalization style as playlist
  sample paths: `Path(...).expanduser().resolve()` string).
- Duplicate star is idempotent; unstar of an unknown path is idempotent.
- State survives process restart via the same database file.
- There is exactly one persistent favorite owner: SQLite/Python. QML must not
  keep a second authoritative favorite store.

## Domain API

- `is_sample_favorite(path) -> bool`
- `set_sample_favorite(path, favorite: bool) -> bool` (resulting state)
- `toggle_sample_favorite(path) -> bool` (resulting state)
- `list_favorite_sample_paths() -> list[str]` (deterministic order: oldest
  assignment first)
- `load_favorite_workbench_rows(...)` projects those paths onto existing
  `WorkbenchRow` Browser rows (cache when valid; fail-soft error row when the
  source file is missing; never creates playlist rows).

## Navigation / scope

- Stable node id: `scope:favorites`
- Typed scope: `LibraryScopeKind.FAVORITES`
- Compact `libraryScopeBar` exposes a Favorites control
  (`libraryFavoritesScopeButton`, Accessible name `Favorites`) distinct from
  Collections.
- Selecting Favorites dispatches the same typed `LibrarySelectionIntent` path
  used by All Samples / Catalog / Sources.
- Favorites must **not** appear as a Source-tree folder or synthetic source
  root.
- Browser context title: `Favorites`.
- While Favorites is active, unstarring a row reloads the Favorites scope so
  the row disappears deterministically. Starring/unstarring in other scopes
  updates the projected `favorite` flag only; Favorites listing refreshes on
  next Favorites entry (or immediately when already in Favorites).

## Renderer wiring

- QML projects `favorite: bool` from Python for each Browser row.
- Toggle intent goes through the interaction adapter / bridge.
- Favorites-scope Browser rows reuse existing waveform audition, ↑/↓, Esc
  stop, search-focus protection, virtualization, Add-to-Kit, and Harmonic
  Match seams.

## Non-scope

- Collections redesign, tags, smart collections, cloud sync
- Ratings
- #768 Drag & Drop, #770 context hint, #780/#781/#782 chrome slices
- Screen 2/3, packaging, audio-engine changes
