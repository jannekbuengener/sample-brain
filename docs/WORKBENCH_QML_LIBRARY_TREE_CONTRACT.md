# Workbench QML Library Tree Contract

## Purpose and boundary

The Screen-1 Library keeps one renderer-neutral navigation authority while the
QML presentation shows four **primary Library views** and a persistent
**Sources tree**.
QML remains a thin renderer/intent layer; Browser loading, cache state,
playlists, Catalog loaders, analysis, Preview, Harmony, and Live Kit remain
owned by their existing Python contracts.

This contract supersedes the historical #575 presentation taxonomy that rendered
`Sample Sources / All Samples / Catalog / Collections` as four equal tree roots
and placed `Add Source…` inside `Sample Sources`. It also supersedes the
#765/#766 compact icon row that sat **above** the Source tree and exposed a
visible Catalog control.

#1247 owns the structural sidebar hierarchy and visible copy. Existing Python
navigation and typed selection intents remain authoritative. #1248 owns the
follow-up visual scale, spacing, and icon contract; the global footer contains
context/status only.

## Source tree taxonomy

The visible Library sidebar has this hierarchy:

```text
LIBRARY                                      [+]

All Samples
Collections
Favorites
Records

YOUR SOURCES
  <registered source root>
    <real direct subfolder>
      ...
```

`YOUR SOURCES` projects persisted registered roots, real lazy subfolders, and
bounded status/error nodes through the existing hidden-root TreeView projection.
The logical `container:sample-sources` parent remains intact but is not a
visible primary view. The Sources tree remains visible while any primary view
is active. It does **not** contain `Add Source…`, All Samples, Catalog,
Collections, Favorites, Records, or synthetic convenience folders.

The single primary Add Source affordance remains the existing button in the
Library header. `action:add-source` is not emitted by the navigation model.

## Primary views and persistent Sources (#1247)

The title row keeps `LIBRARY` and the existing Add Source button. Four
primary rows follow it; the persistent Sources section follows the primary
views. #1247 changes this structure only. Do not add a second navigation
authority or pull #1248's visual contract forward.
The in-pane scope-bar placement introduced by #1201 remains the structural
baseline for these four primary rows.

Visible primary views:

- **All Samples** — selects `scope:all-library`;
- **Collections** — reveals the existing persisted Workbench playlists;
- **Favorites** — selects `scope:favorites` (`LibraryScopeKind.FAVORITES`) with
  a geometric star mark;
- **Records** — selects `scope:recordings` (`LibraryScopeKind.RECORDINGS`).

The visible Catalog / Katalog read-only control is removed from Library
navigation. Catalog data ownership, loaders, and `scope:catalog-readonly`
resolution remain available to Python/core contracts; only the visible
navigation entry is gone.

The rows are presentation only. Stable node IDs and `LibraryScope` resolution
remain authoritative. All Samples, Favorites, Records, collection entries,
and Source rows use the existing Python selection authority. Selecting a
primary view leaves the Sources tree visible; selecting a Source clears the
primary active presentation through Python state. Source expand/collapse is
presentation-only and does not change Browser, audio, Kit, or Source state.

Every icon-only control exposes a stable object/semantic identity and accessible
name. #770 owns the shared context-hint display; the focused footer-context
centering slice places that hint in a true center layer on the footer band
(full footer midpoint; the footer retains context/status only). Scope controls
report hover/focus (selection) intents into that seam and do not rely on
classic cursor-adjacent ToolTips for Library scope discoverability.

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

## Source Tree visibility by primary view

Presentation rule for the materialized Library pane:

| Active presentation | Sources tree | Collections list |
|---------------------|--------------|-----------------|
| All Samples | visible + interactive | hidden |
| Favorites | visible + interactive | hidden |
| Records | visible + interactive | hidden |
| Collections | visible + interactive | visible |
| Selected Source | visible + interactive | hidden |

The four primary rows follow the `LIBRARY`/Add Source title row. The
`YOUR SOURCES` section and TreeView stay visible below them as Browser scope
changes. The existing Collections list remains available when its primary view
is selected. The tree and list stay in the Library content layout below the
primary rows.

Primary view switches do not remove or collapse Sources. Selecting a Source
uses the existing authoritative route; expanding/collapsing a Source remains
presentation-only.

## Visual and responsive contract

#1248 consumes MagicPath component `464784312458436608`, revision
`464978117610602496`, and the 2026-10-25 Owner active-state amendment.
This supersedes neutral filled active rows and enclosing selection frames.

All measurements are logical UI pixels; sidebar width stays layout-solver-owned.

| Role | Contract |
|---|---|
| Header / Add Source | 52 high / 36 x 36, aligned right |
| Primary row | 35 high, 36 pitch; pane inset 6, content padding 10 |
| Icon / icon-label gap | 20 x 20 / 6 |
| Navigation / Sources text | system font, 14 / 20 / 400 |
| YOUR SOURCES | gap before 20, header 36, gap after 4; 14 / 18 / 500 |
| Source rows | 36 high/pitch, existing 16-pixel depth indentation |
| Long source labels | bounded 24-pixel trailing fade outside action controls |

Selected text/icons use category semantic accents: cool blue for All Samples,
muted gold for Collections, muted warm red for Favorites, lavender for Records.
Source selection uses the existing global Accent role. No selection fill,
enclosing selection outline, dashed marker, neon or bloom. Focus-visible has
its own ring; hover/focus never select, navigate or mutate Audio/Kit/Source state.
Existing icon primitives and functional expand/collapse indicators are reused.

Theme Core owns the minimal Library-only color seam: default Library surface
reference `#15171a`, custom surfaces derived from their bases. Browser/Workspace
`#0d0f12` is comparison evidence only; Browser rendering is outside this slice.
Category accents are fixed orientation roles independent of status colors and
the configurable global Accent. No second theme persistence or global migration
is introduced. The unassigned design value `84` is unused per Owner decision;
no opacity is inferred from it. #1257 retains broader Appearance ownership.

Runtime checks distinguish logical geometry, DPR and screenshot dimensions at
100/125/150 percent Windows scaling. Captures and objective checks do not imply
subjective Owner acceptance.

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

- exactly four visible primary rows: All Samples, Collections, Favorites, Records;
- no visible `Sample Sources` primary row;
- persistent `YOUR SOURCES` label and Source tree across primary views;
- `container:sample-sources` remains the logical tree parent;
- no `action:add-source` child;
- existing typed selection routes, including the internal `scope:recordings` ID;
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

#836 owns Source expand/hydrate reliability. #837 owns the existing scope
intents and internal Recordings navigation projection. #770 delivers the
shared context-hint seam; #830 owns footer-band geometry (context info
true-center, status right). This contract still excludes sample Drag & Drop
ownership changes, Add Source command changes, and the future modular
snap/docking system. Packaging/installer work is also out of scope.
