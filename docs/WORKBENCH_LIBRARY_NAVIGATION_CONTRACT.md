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
  Catalog resolution and loaders remain part of the Python/core contract even
  when no visible Catalog navigation control is presented (#837).
- Collections present existing Workbench playlists and retain their
  `playlist_id` identity.
- Favorites project persisted `favorite_samples` paths.
- Recordings project takes already registered into the existing `Recordings`
  playlist by the Workbench recording finalization path. No new recording
  engine or persistence schema is introduced for navigation.

## Navigation model

The renderer-neutral authority still owns Sample Sources, All Samples,
Catalog (resolve/load), Collections, Favorites, and Recordings.

Presentation split (owned by the QML Library Tree contract / #837; geometry
superseded for footer placement by `docs/PROGRAM_CHROME_CONTRACT.md` #830):

- **Source tree:** Sample Sources with registered roots and lazy subfolders.
  Add Source lives in the Library header, not inside the tree.
- **Secondary scope controls:** All Samples, Collections, Favorites
  (geometric star), and Recordings — same scope intents as #837; #830 moves their
  presentation into the global footer utility band (left), not a Library-pane row
  above the footer. The visible Catalog control is not presented.

Favorites is a dedicated user-organization scope
(`scope:favorites` / `LibraryScopeKind.FAVORITES`). Recordings is a dedicated
scope (`scope:recordings` / `LibraryScopeKind.RECORDINGS`). Neither is a
Source-tree folder, analysis category, or playlist/Collection UI alias.
Implicit filesystem locations, counts, and fake collections remain absent.

Stable IDs are `root:<folder_id>`,
`folder:<folder_id>:<base64url(normcase-relative-path)>`,
`collection:<playlist_id>`, `scope:favorites`, `scope:recordings`, and stable
IDs for other static secondary nodes. Display labels are never identity. Root
labels use the directory name, with the shortest unique parent suffix only for
duplicate names.

## I/O and availability

Expansion performs one direct directory listing. It does not recurse, follow
symlinks or junctions, scan samples, analyze audio, or load the
catalog. Missing roots remain visible and cache-selectable but are not
expandable. Controlled loading and error availability states are
renderer-neutral; error details must not expose an absolute producer path.

## Scope resolution

Selectable roots, subfolders, All Samples, Catalog, Favorites, Recordings, and
Collections resolve to typed scopes. A subfolder scope selects cached
descendants by `folder_id` and a relative-path prefix; it never triggers a
filesystem scan. The query compares legacy Windows and POSIX separators only
at read time, without migrating stored `relative_path` values. Prefix matching
escapes SQL wildcard characters and preserves directory boundaries.

Catalog scopes remain read-only and use the existing load limit. Favorites
scopes project persisted `favorite_samples` paths through the existing Browser
row contracts (`docs/WORKBENCH_FAVORITES_PERSISTENCE_CONTRACT.md`). Recordings
scopes project the existing `Recordings` playlist registration path through the
existing playlist→Browser row loader. Collection scopes retain the stable
playlist ID. Add Source is an action, not a sample scope.

## Non-scope

This navigation authority itself does not own QML presentation, folder dialog
UX, Browser-row chrome, schema migration beyond the Favorites table owned by
#766, audio/preview behavior, Harmony, or Live Kit work. Favorites
persistence + Favorites scope loading are specified in
`docs/WORKBENCH_FAVORITES_PERSISTENCE_CONTRACT.md`. Recording capture/engine
ownership remains outside this navigation contract.

## Test freeze

The original #574 contract tests were frozen before implementation. During
GREEN validation the navigation test oracle was corrected once:
**TEST_CONTRACT_FIX: Frozen test contradicted canonical normcase contract;
product behavior unchanged.** The previous literal encoded `Drums`; the
canonical value is derived from `base64url(normcase(relative-path))` and is
therefore platform-correct.

Historical closed freeze hashes (#574 era; not current #837 authority):

- `tests/test_workbench_library_navigation.py`:
  `08FF5AE872C0E9563EC6F1BB5A8E2BECA39356F31921502C20E65E173107C51A`
- `tests/test_workbench_library.py`:
  `C6EA5EF785E4D438121BAB2FAA233272B98A11BBA1086975892FB0F29F9C810A`
- `tests/test_workbench_controller.py`:
  `01B20E31F6B61A377D2DF52622C1AA3ED84FA936BC2C10F1FC33ACC6D735488F`

#837 supersedes the secondary presentation list (bottom icons, Recordings,
no visible Catalog). Live tests under `tests/test_workbench_library_bottom_icons_837.py`
and the updated navigation/tree suites are the current authority for that slice.
