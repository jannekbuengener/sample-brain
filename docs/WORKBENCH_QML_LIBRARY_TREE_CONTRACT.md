# Workbench QML Library Tree Contract

## Purpose and boundary

The Screen-1 Library keeps one renderer-neutral navigation authority while the
QML presentation separates **Source folders** from **secondary Library scopes**.
QML remains a thin renderer/intent layer; Browser loading, cache state,
playlists, Catalog loaders, analysis, Preview, Harmony, and Live Kit remain
owned by their existing Python contracts.

This contract supersedes the historical #575 presentation taxonomy that rendered
`Sample Sources / All Samples / Catalog / Collections` as four equal tree roots
and placed `Add Source…` inside `Sample Sources`. It also supersedes the
#765/#766 compact icon row that sat **above** the Source tree and exposed a
visible Catalog control.

#837 is the current presentation authority for secondary icon placement and
visible secondary scopes.

## Source tree taxonomy

The visible QML tree now has exactly one top-level container:

```text
Sample Sources
  <registered source root>
    <real direct subfolder>
      ...
```

`Sample Sources` contains only persisted registered roots plus their real lazy
subfolders and bounded status/error nodes. It does **not** contain `Add Source…`,
All Samples, Catalog, Collections, Favorites, Recordings, or synthetic
convenience folders.

The single primary Add Source affordance remains the existing button in the
Library header. `action:add-source` is not emitted by the navigation model.

## Bottom secondary icon navigation (#837)

Historical #837 placement was a compact icon-only row at the bottom of the left Library/Browser pane, directly above the ApplicationWindow footer. #830
(`docs/PROGRAM_CHROME_CONTRACT.md`) moves that existing utility onto the left of
the global footer band. This section still owns the scope set and the intent
dispatch. Do not render the same scope twice.

Visible secondary controls:

- **Sample Sources** — returns the pane to the real Source tree;
- **All Samples** — selects `scope:all-library`;
- **Collections** — reveals the existing persisted Workbench playlists;
- **Favorites** — selects `scope:favorites` (`LibraryScopeKind.FAVORITES`) with
  a geometric star mark;
- **Recordings** — selects `scope:recordings` (`LibraryScopeKind.RECORDINGS`).

The visible Catalog / Katalog read-only control is removed from Library
navigation. Catalog data ownership, loaders, and `scope:catalog-readonly`
resolution remain available to Python/core contracts; only the visible
navigation entry is gone.

The icon row is presentation only. Stable node IDs and `LibraryScope`
resolution remain authoritative. All Samples, Favorites, Recordings, and
collection entries flow through the same typed selection intent used by Source
rows.

Every icon-only control exposes a stable object/semantic identity and accessible
name. #770 owns the shared bottom-center context-hint display; the icon row
reports hover/focus intents into that seam and does not rely on classic
cursor-adjacent ToolTips for Library scope discoverability.

## Recordings projection

Recordings reuses the existing Workbench recording registration path:

- finalized takes persist under the local workbench state `recordings/` directory;
- registration adds paths to the existing `Recordings` playlist
  (`RECORDINGS_PLAYLIST_NAME` in `recording_take`).

`scope:recordings` is a dedicated typed scope that projects those already
registered takes through the existing playlist→Browser row loader. It is not a
Collections alias in the UI, not a Favorites alias, and does not introduce a new
Recording Engine, capture path, or audio ownership.

## Collections

`Collections` remains a container over existing persisted Workbench playlists.
The renderer asks the same `WorkbenchLibraryNavigation.children(
"container:collections")` authority for entries. Selecting a collection resolves
the existing `LibraryScopeKind.COLLECTION` with the persisted playlist identity.

No second playlist model or QML-owned collection truth is introduced.

## Lazy loading

Source expansion requests exactly one direct branch from
`navigation.children(parent_id)`. It never recursively expands descendants or
siblings and never starts scan/analyze/audio/Catalog work.

An empty branch is a successful loaded branch with zero children. Error branches
remain path-free and retry only their direct branch. Offline registered roots
stay visible/selectable with cached scope and are not expandable.

Collections use the same bounded lazy state internally, but their container is
remembered as a secondary navigation node rather than rendered as a Source-tree
root.

## Selection and focus

Selecting any actionable Source or secondary node resolves exactly one existing
`LibraryScope` and emits one typed selection intent. No renderer-only loader or
second selection authority is introduced.

Tree chevrons expand/collapse only. Source-tree Up/Down and Left/Right behavior
remains native TreeView behavior. Enter transfers focus to the Browser without
auditioning. The tree does not consume Escape; the higher-level Preview/Escape
contract remains authoritative.

Collections entries are keyboard-focusable when the Collections surface is
visible. All icon controls retain accessible names. View switches must not start
preview/audition and must not duplicate selection intents beyond the single typed
dispatch.

## Source Tree visibility by scope mode

Presentation rule for the Library pane (no opacity-only hide with active input):

| Mode | Source Tree | Secondary surface |
|------|-------------|-------------------|
| Sources | visible + focusable/interactive | — |
| All Samples | not visible; not focusable; no input | — |
| Favorites | not visible; not focusable; no input | — |
| Recordings | not visible; not focusable; no input | — |
| Collections | not visible; not focusable; no input | Collection list visible |

`libraryScopeBar` is the left side of the global footer band
(`docs/PROGRAM_CHROME_CONTRACT.md`, #830). It is not a second row inside the
Library pane, and mode switches must not move it above the Library header.
Tree/list visibility stays in one `libraryContentHost` (`Layout.fillHeight`),
which fills the Library pane under the Library header.

Returning to Sources keeps the existing Tree expand/selection state; do not
reload navigation solely because of a scope-bar mode switch.

## Visual and responsive contract

The Library pane keeps the existing near-black surfaces, thin dividers, compact
density, and sparse blood-red intent. Scope controls are icon-only geometric
marks (no emoji/Unicode glyph icons, no brain artwork). Favorites uses a
geometric star. Active scope uses `selectionSurface` +
`selectionBorder`/`actionActive`; idle uses panel-dark surfaces — never
light-gray native chrome.

Labels are clipped/elided rather than exposing raw producer paths. The pane must
remain usable at the existing Screen-1 acceptance sizes and Windows scale
factors. This contract does not introduce a general docking/layout system.

## Qt optionality

Normal core imports remain possible without PySide6. The optional Qt model and
QML renderer are still created only on the Qt Quick path; no new mandatory
dependency is introduced.

## Test / migration note

The old #575 RED/freeze record remains historical evidence for the original QML
tree migration. #765/#766 delivered the earlier top compact bar. #837 is an
explicit Owner-authorized product supersession of secondary icon placement and
visible Catalog navigation.

Regression coverage now freezes:

- one visible Source-tree root;
- no `action:add-source` child;
- secondary icons reuse the #837 scope set; #830 places that utility on the left of the global footer band instead of a separate row above it;
- All Samples / Favorites / Collections / Recordings remembered as secondary
  nodes;
- no visible Catalog navigation control;
- Catalog Python resolve/load contracts remain intact;
- secondary selections use the same typed intent/scope authority;
- Favorites lists only persisted favorite paths via existing Browser rows;
- Recordings projects the existing Recordings playlist registration path;
- persisted collection entries remain loadable and remain distinct from
  Favorites/Recordings;
- Source lazy loading, retry, offline, keyboard, and focus behavior remain
  intact;
- view switch does not auto-preview.

## Dependency boundary

#836 owns Sample Sources expand/hydrate reliability. #837 owns bottom secondary
icon placement and Recordings navigation projection. #770 delivers the shared
bottom-center context-hint seam for those icon-only controls. This contract
still excludes sample Drag & Drop ownership changes, Add Source relocation, and
the future modular snap/docking system. Packaging/installer work is also out of
scope.
