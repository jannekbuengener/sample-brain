# Workbench Library Navigation Contract

## Purpose

This contract defines the renderer-neutral Library navigation surface for
Screen 1. It is a read-only view over the existing Workbench library cache,
playlist persistence, and catalog reader. It introduces no second Library
backend and no renderer, dialog, audio, scan, or analysis behavior.

## Reused sources

- Registered roots and cached sample rows remain owned by
  `workbench_library` and the controller cache loaders.
- All Samples continues to use the existing aggregate cached-row loader.
- Catalog continues to use the existing limited, read-only catalog loader.
- Collections present existing Workbench playlists and retain their
  `playlist_id` identity.

## Navigation model

The root surface consists of Sample Sources, All Samples, Catalog, and
Collections. Sample Sources contains registered roots and Add Source. Roots
expand lazily to direct subfolders only. Collections contains existing
playlists. Favorites, implicit filesystem locations, counts, and fake
collections are absent.

Stable IDs are `root:<folder_id>`,
`folder:<folder_id>:<base64url(normcase-relative-path)>`,
`collection:<playlist_id>`, and stable IDs for static nodes. Display labels
are never identity. Root labels use the directory name, with the shortest
unique parent suffix only for duplicate names.

## I/O and availability

Expansion performs one direct directory listing. It does not recurse, follow
symlinks or junctions, scan samples, analyze audio, read audio, or load the
catalog. Missing roots remain visible and cache-selectable but are not
expandable. Controlled loading and error availability states are
renderer-neutral; error details must not expose an absolute producer path.

## Scope resolution

Selectable roots, subfolders, All Samples, Catalog, and Collections resolve
to typed scopes. A subfolder scope selects cached descendants by `folder_id`
and a relative-path prefix; it never triggers a filesystem scan. The query
compares legacy Windows and POSIX separators only at read time, without
migrating stored `relative_path` values. Prefix matching escapes SQL wildcard
characters and preserves directory boundaries.

Catalog scopes remain read-only and use the existing load limit. Collection
scopes retain the stable playlist ID. Add Source is an action, not a sample
scope.

## Non-scope

This slice contains no QML, Tk, QAbstractItemModel, runtime composition,
browser-row redesign, folder dialog, removal wiring, Favorites persistence,
schema migration, audio/preview behavior, Harmony, or Live Kit work.

## Test freeze

The contract tests were frozen before implementation.  During GREEN validation
the navigation test oracle was corrected once: **TEST_CONTRACT_FIX: Frozen
test contradicted canonical normcase contract; product behavior unchanged.**
The previous literal encoded `Drums`; the canonical value is derived from
`base64url(normcase(relative-path))` and is therefore platform-correct.

The closed freeze hashes are:

- `tests/test_workbench_library_navigation.py`:
  `08FF5AE872C0E9563EC6F1BB5A8E2BECA39356F31921502C20E65E173107C51A`
- `tests/test_workbench_library.py`:
  `C6EA5EF785E4D438121BAB2FAA233272B98A11BBA1086975892FB0F29F9C810A`
- `tests/test_workbench_controller.py`:
  `01B20E31F6B61A377D2DF52622C1AA3ED84FA936BC2C10F1FC33ACC6D735488F`
