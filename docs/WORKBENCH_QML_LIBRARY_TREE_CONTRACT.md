# Workbench QML Library Tree Contract

## Purpose and boundary

Issue #575 renders the existing `WorkbenchLibraryNavigation` contract as a
lazy Qt Quick tree. The tree owns presentation and selection intent only. It
does not add a Library backend, load Browser rows, start Preview/Audition,
change Harmony or Live Kit state, scan, analyze, read audio, load Catalog
rows, open a Folder dialog, or register/remove sources. Browser loader wiring
and Owner visual acceptance remain #576.

## Tree taxonomy

The exact top-level model is:

```text
Sample Sources
All Samples
Catalog
Collections
```

`Sample Sources` contains the persisted registered roots, followed by the
canonical `Add Source…` action. Each available root may expose lazy direct
subfolders. `Collections` contains only persisted Workbench playlists. The
existing `LibraryNode` IDs and `LibraryScope` resolution from
`WorkbenchLibraryNavigation` remain authoritative; display labels are never
identities.

The normal QML model must not emit or contain `Favorites`, `My Kits`,
`Recently Added`, `Splice`, `User Library`, implicit Desktop, implicit
Downloads, implicit drives, or fake counts.

## Lazy loading

The Qt adapter has a Qt-free state layer and a thin optional
`QAbstractItemModel` wrapper. Initial construction materializes only the four
top-level nodes. A branch expansion or `fetchMore()` requests exactly
`navigation.children(parent_id)` once for that direct branch, then inserts
only those returned direct children with `beginInsertRows()` / `endInsertRows()`.
It never recursively expands descendants or sibling branches and never calls
scan, analyze, audio reads, Catalog loading, or a second Library backend.

An empty branch is a successful loaded branch with zero children and cannot
fetch repeatedly. An error branch exposes the renderer-neutral error status
without an absolute producer path. Retry clears only that branch and requests
its direct children again. Offline roots remain visible and selectable,
retain their cached scope, and are not expandable.

Loading, error, and availability are explicit model roles. Synchronous
`children()` calls may complete within one `fetchMore()` call; no worker or
animation is required merely to manufacture asynchronous behavior.

## Selection and focus

Selecting a label of a selectable node resolves exactly one existing
`LibraryScope` and emits one typed selection intent. It does not invoke a
Browser loader, Preview/Audition callback, Harmony controller, or Live Kit
mutation. `Add Source…` is an action node without a scope; #575 presents it
only and does not implement its dialog or registration wiring.

The chevron/indicator expands or collapses only and must not select a scope.
While the tree owns focus, normal TreeView behavior handles Up/Down, Left and
Right. Enter transfers focus to the existing `browserList` without
auditioning. The tree has no Escape handler and does not consume Escape; the
existing higher-level Preview/Esc contract remains authoritative.

## Visual and responsive contract

The left pane uses the existing near-black surface and thin dividers. Only a
real selected Library intent uses the blood-red accent. Secondary and Offline
states are muted; chevrons and hover do not become red selection substitutes.
Labels are clipped/elided instead of exposing raw producer path walls. The
tree is vertically scrollable and remains usable inside the left pane at
`1600x900` and `1120x640`; the center Browser and right Live-Kit structure do
not collapse into a new layout.

## Qt optionality

Importing normal Sample-Brain core modules and
`src.workbench_library_navigation` remains possible without PySide6. The Qt
adapter imports PySide6 only when the optional QML renderer is started. No new
mandatory dependency is introduced; PySide6 remains under the existing
`qtquick` extra.

## Test freeze

The #575 RED contract is frozen before implementation. The controlled RED run
completed with 9 failures and 1 conditional skip because the tree adapter and
TreeView integration do not exist on the base commit. Its SHA-256 is:

```text
tests/test_workbench_qml_library_tree.py: 7F6E15DC895DF035EF89C7893281603658EB8AB9D70F27A996BA6D34149FF959
```

Any later oracle correction must be explicitly marked
`TEST_CONTRACT_FIX`, preserve the canonical behavior, and be explained in the
diff. The existing #574 freeze tests remain unchanged.

## Dependency boundary

This slice depends on delivered #574 and prepares the typed tree/selection
intent consumed by #576. It does not claim production Library-to-Browser
runtime composition or Owner visual acceptance of that path.
