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

The renderer-neutral authority still owns Sample Sources, All Samples,
Catalog, Collections, and (as of #766) Favorites.

Presentation split (owned by the QML Library Tree contract / #765+#766):

- **Source tree:** Sample Sources with registered roots and lazy subfolders.
  Add Source lives in the Library header, not inside the tree.
- **Compact secondary icon bar:** All Samples, Catalog, Favorites, Collections.

Favorites is a dedicated user-organization scope
(`scope:favorites` / `LibraryScopeKind.FAVORITES`). It is not a Source-tree
folder, not an analysis category, and not a playlist/Collection alias.
Implicit filesystem locations, counts, and fake collections remain absent.

Stable IDs are `root:<folder_id>`,
`folder:<folder_id>:<base64url(normcase-relative-path)>`,
`collection:<playlist_id>`, `scope:favorites`, and stable IDs for other
static secondary nodes. Display labels are never identity. Root labels use
the directory name, with the shortest unique parent suffix only for duplicate
names.

## I/O and availability

Expansion performs one direct directory listing. It does not recurse, follow
symlinks or junctions, scan samples, analyze audio, read audio, or load the
catalog. Missing roots remain visible and cache-selectable but are not
expandable. Controlled loading and error availability states are
renderer-neutral; error details must not expose an absolute producer path.

## Scope resolution

Selectable roots, subfolders, All Samples, Catalog, Favorites, and Collections
resolve to typed scopes. A subfolder scope selects cached descendants by
`folder_id` and a relative-path prefix; it never triggers a filesystem scan.
The query compares legacy Windows and POSIX separators only at read time,
without migrating stored `relative_path` values. Prefix matching escapes SQL
wildcard characters and preserves directory boundaries.

Catalog scopes remain read-only and use the existing load limit. Favorites
scopes project persisted `favorite_samples` paths through the existing Browser
row contracts (`docs/WORKBENCH_FAVORITES_PERSISTENCE_CONTRACT.md`). Collection
scopes retain the stable playlist ID. Add Source is an action, not a sample
scope.

## Non-scope

This navigation authority itself does not own QML presentation, folder dialog
UX, Browser-row chrome, schema migration beyond the Favorites table owned by
#766, audio/preview behavior, Harmony, or Live Kit work. Favorites
persistence + Favorites scope loading are specified in
`docs/WORKBENCH_FAVORITES_PERSISTENCE_CONTRACT.md`.

## Test freeze

The original #574 contract tests were frozen before implementation. During
GREEN validation the navigation test oracle was corrected once:
**TEST_CONTRACT_FIX: Frozen test contradicted canonical normcase contract;
product behavior unchanged.** The previous literal encoded `Drums`; the
canonical value is derived from `base64url(normcase(relative-path))` and is
therefore platform-correct.

Historical closed freeze hashes (#574 era; not current #766 authority):

- `tests/test_workbench_library_navigation.py`:
  `08FF5AE872C0E9563EC6F1BB5A8E2BECA39356F31921502C20E65E173107C51A`
- `tests/test_workbench_library.py`:
  `C6EA5EF785E4D438121BAB2FAA233272B98A11BBA1086975892FB0F29F9C810A`
- `tests/test_workbench_controller.py`:
  `01B20E31F6B61A377D2DF52622C1AA3ED84FA936BC2C10F1FC33ACC6D735488F`

#766 extends secondary navigation with Favorites; live tests under
`tests/test_workbench_favorites_766.py` and the updated navigation/tree
suites are the current Favorites authority for that slice.
