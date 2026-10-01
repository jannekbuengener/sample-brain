# Workbench QML Library Tree Contract

## Purpose and boundary

The Screen-1 Library keeps one renderer-neutral navigation authority while #765
separates **Source folders** from **secondary Library scopes** in the QML
presentation. QML remains a thin renderer/intent layer; Browser loading, cache
state, playlists, Catalog, analysis, Preview, Harmony, and Live Kit remain owned
by their existing Python contracts.

This contract supersedes the historical #575 presentation taxonomy that rendered
`Sample Sources / All Samples / Catalog / Collections` as four equal tree roots
and placed `Add Source…` inside `Sample Sources`.

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
All Samples, Catalog, Collections, Favorites, or synthetic convenience folders.

The single primary Add Source affordance is the existing button in the Library
header. `action:add-source` is no longer emitted by the navigation model.

## Compact secondary icon navigation

A compact icon-only row above the Source tree exposes the secondary Library
concepts:

- **Sample Sources** — returns the pane to the real Source tree;
- **All Samples** — selects `scope:all-library`;
- **Catalog** — selects `scope:catalog-readonly`;
- **Favorites** — selects `scope:favorites` (`LibraryScopeKind.FAVORITES`);
- **Collections** — reveals the existing persisted Workbench playlists.

Favorites (#766) joins the same icon row as a dedicated user-organization
scope. It is not a Source-tree folder and is not modeled as a playlist /
Collection alias. Persistence and path→row projection follow
`docs/WORKBENCH_FAVORITES_PERSISTENCE_CONTRACT.md`.

The icon row is presentation only. Stable node IDs and `LibraryScope`
resolution remain authoritative. All Samples, Catalog, Favorites, and
collection entries flow through the exact same typed selection intent used by
Source rows.

Every icon-only control exposes a stable object/semantic identity and accessible
name. #770 owns the shared bottom-center context-hint display; the icon row
reports hover/focus intents into that seam and does not rely on classic
cursor-adjacent ToolTips for Library scope discoverability.

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
visible. All icon controls retain accessible names.

## Source Tree visibility by scope mode

Presentation rule for the Library pane (no opacity-only hide with active input):

| Mode | Source Tree | Secondary surface |
|------|-------------|-------------------|
| Sources | visible + focusable/interactive | — |
| All Samples | not visible; not focusable; no input | — |
| Catalog | not visible; not focusable; no input | — |
| Favorites | not visible; not focusable; no input | — |
| Collections | not visible; not focusable; no input | Collection list visible |

`libraryScopeBar` is permanent Library chrome under the LIBRARY / Add Source
header. Mode switches must not move it: tree/list visibility is hosted inside a
single `libraryContentHost` (`Layout.fillHeight`) so hiding the tree cannot
collapse or re-pack the scope bar to the pane bottom.

Returning to Sources keeps the existing Tree expand/selection state; do not
reload navigation solely because of a scope-bar mode switch.

## Visual and responsive contract

The Library pane keeps the existing near-black surfaces, thin dividers, compact
density, and sparse blood-red intent. Scope controls are icon-only geometric
marks (no emoji/Unicode glyph icons, no brain artwork). Active scope uses
`selectionSurface` + `selectionBorder`/`actionActive`; idle uses panel-dark
surfaces — never light-gray native chrome.

Labels are clipped/elided rather than exposing raw producer paths. The pane must
remain usable at the existing Screen-1 acceptance sizes and Windows scale
factors. #765 does not introduce a general docking/layout system.

## Qt optionality

Normal core imports remain possible without PySide6. The optional Qt model and
QML renderer are still created only on the Qt Quick path; no new mandatory
dependency is introduced.

## Test / migration note

The old #575 RED/freeze record remains historical evidence for the original QML
tree migration. #765 is an explicit Owner-authorized product supersession of only
its presentation taxonomy and Add-Source tree action.

Regression coverage now freezes:

- one visible Source-tree root;
- no `action:add-source` child;
- All Samples / Catalog / Favorites / Collections remembered as secondary nodes;
- secondary selections use the same typed intent/scope authority;
- Favorites lists only persisted favorite paths via existing Browser rows;
- persisted collection entries remain loadable and remain distinct from Favorites;
- Source lazy loading, retry, offline, keyboard, and focus behavior remain intact.

## Dependency boundary

#765 delivered the compact icon-bar presentation. #766 completes Favorites in
that bar. #770 delivers the shared bottom-center context-hint seam for those
icon-only controls. This contract still excludes sample Drag & Drop (#768)
and the future modular snap/docking system. Packaging/installer work is also
out of scope.
