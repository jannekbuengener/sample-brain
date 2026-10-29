# TRANSFER — lifecycle / virtualization variant (#1305)

**Status:** changed scenario after GREEN  
**Prompt:** Design coverage for: after Browser ListView scrolls with
`reuseItems: true`, pooled delegates must not leave stale presentation hover
owners; presentation hover must not mutate selection or kit product state.

## Compact test design (with skill)

```text
Behavior/authority:
  ListView.onPooled clears context-hint hover owners for browser.sample_row /
  audition / favorite. Product selection and kit assignment stay Python-owned;
  hover is presentation-only.

Why QML component coverage required:
  Static assert `reuseItems: true` and Python hint-state unit tests miss the
  pooled-delegate path where a reused item still reports containsMouse / stale
  hover id after scroll.

Layer decision: mixed

Fixture/boundary:
  Existing Screen-1 `_qml_engine` harness with enough browser rows to scroll;
  find contextHintState by objectName.

Inputs/events:
  Hover a visible row (QTest.mouseMove); scroll contentY enough to pool that
  delegate; optionally hover a context-menu item after bridge-open.

Observable assertions:
  After pool: hoveredId for that row family cleared (or not stuck on pooled
  owner); selected_browser_index and live-kit assignments unchanged by hover;
  do not assert persistent QQuickItem identity of a specific delegate across
  scroll.

Async/wait strategy:
  processEvents / settle until contentY and hint properties stabilize.

Lifecycle/virtualization:
  Explicit reuseItems + onPooled; re-query items after scroll; never treat
  cached visual index as sample identity for deferred commands.

Companion tests:
  docs/WORKBENCH_CONTEXT_HINT_CONTRACT.md Python/projection companions;
  adapter selection contracts remain Python-owned.

Non-goals:
  Pixel screenshot of hover chrome; inventing a second virtualization framework.
```

## Why this transfers

RED/GREEN taught pointer/signal layer choice. This variant reuses the same
output contract for a **different failure family** (pooled delegate /
presentation-only) without requiring a new skill body.

## Verdict

Transfer PASS — skill accounts for virtualization/lifecycle without collapsing
to static `reuseItems` substring checks.
