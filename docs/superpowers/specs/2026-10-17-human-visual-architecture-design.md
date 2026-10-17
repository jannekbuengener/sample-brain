# Human Visual Architecture Layer — Design

**Issue:** #1163  
**Status:** Design for review  
**Scope:** Human-readable visual explanations only; no new runtime or domain authority.

## 1. Intent

Sample Brain already has detailed machine-/agent-oriented canon and contracts. This slice adds a deliberately small **human layer** for the parts a person may need to understand quickly without reconstructing the system from many technical documents.

Success means a reader can answer these questions in roughly 30–60 seconds each:

1. What are the major Sample Brain repositories/components and how do they relate?
2. Which repository/domain owns which responsibilities, and where are the hard non-ownership boundaries?
3. How does a normal technical slice move from intent to repository routing, implementation, review, merge, and live verification?
4. At a high level, how does a sample move through the core analysis path?

The visual layer explains existing truth. It does not become a new source of domain truth.

## 2. Human layer vs machine layer

### Machine / authority layer

Remains unchanged:

- GitHub and repository live state
- `docs/CANON_INDEX.md`
- `docs/TARGET_ARCHITECTURE.md`
- `docs/PRODUCT_WORKFLOW_CANON.md`
- subsystem contracts
- repository-local `AGENTS.md`
- tests, manifests, dependency declarations, validation evidence

### Human explanation layer

Create only:

- `docs/visuals/README.md`
- `docs/visuals/system-map.md`
- `docs/visuals/ownership-map.md`
- `docs/visuals/agent-workflow.md`

These documents link to their authorities rather than restating large contracts.

## 3. Chosen representation

### Decision: Mermaid inside Markdown

Use Mermaid as the primary visual representation because it is:

- rendered directly by GitHub;
- text-diffable and reviewable;
- easy to update with repository changes;
- free of unnecessary binary diagram assets;
- readable as source when rendering is unavailable.

### Alternatives considered

1. **Static SVG/PNG diagrams** — visually flexible, but create binary/generated-artifact maintenance and source-of-truth drift.
2. **External diagram tool/canvas** — useful for design work, but makes critical architecture comprehension depend on another service/tool.
3. **Mermaid in repo** — selected because the diagrams remain local, inspectable, diffable, and available even without AI assistance.

No automatic diagram generator is introduced in this slice.

## 4. Shared document contract

Every visual document begins with a short orientation block containing:

- **Purpose** — the question this visual answers;
- **Audience** — human maintainer/owner/technical reviewer;
- **Source of truth** — links to authoritative repo docs;
- **Not covered** — prevents the visual from expanding into a second canon.

Every visual document also contains:

- one primary Mermaid diagram;
- a compact `If you only have 30 seconds` explanation;
- links back to the detailed authoritative documents.

Avoid volatile values such as branch SHAs, current open-issue lists, temporary CI states, and release hashes unless the visual explicitly marks them as non-authoritative examples. Stable repository names and ownership boundaries may be shown.

## 5. Visual 1 — System Map

**File:** `docs/visuals/system-map.md`

### Purpose

Show the current high-level topology and the core analysis path without forcing a reader through the full target architecture.

### Diagram A — Current system topology

Show only repositories/components that currently exist or are current runtime responsibilities.

At minimum:

- `sample-brain-analysis` — Analysis API/contracts and database-free compute authority;
- `sample-brain` — product/application/integration repository;
- inside Sample Brain, a small set of major runtime areas rather than every module:
  - Catalog / DB / persistence;
  - Product adapters / orchestration;
  - Workbench / Session / QML;
  - AQ / evaluation orchestration.

Dependency direction must make clear that Sample Brain **consumes** the versioned Analysis package; Analysis does not depend on Sample Brain product/runtime code.

Do not draw hypothetical future component repositories as if they exist.

### Diagram B — Core sample analysis flow

Keep this intentionally high-level:

`Local audio sample → Scan/catalog identity → Sample Brain analyze adapter → sample-brain-analysis compute → Analysis result → Sample Brain persistence/product projections`

The diagram must distinguish:

- discovery/persistence owned by Sample Brain;
- neutral computation owned by `sample-brain-analysis`;
- persistence back into Sample Brain after computation.

This is the human-facing answer to “how does analysis actually run?” It is not a function-by-function call graph.

### Authorities

- `docs/TARGET_ARCHITECTURE.md`
- `docs/ANALYSIS_PACKAGE_BOUNDARY_V1.md`
- `docs/ANALYSIS_PUBLIC_CONTRACT_V1.md`
- live dependency manifests / repository state

## 6. Visual 2 — Ownership Map

**File:** `docs/visuals/ownership-map.md`

### Purpose

Answer “who owns what?” and, just as importantly, “who must not own what?”

### Diagram

Use two primary ownership zones:

#### `sample-brain-analysis`

Owns:

- public Analysis API / DTOs;
- feature/classification/key/BPM/attack/gesture/harmony compute;
- neutral Analysis contracts;
- package-local validation.

Does not own:

- catalog/database persistence;
- Workbench/Session/QML;
- product state;
- AQ orchestration;
- Sample Brain consumer acceptance.

#### `sample-brain`

Owns:

- scan/catalog/SQLite/SQLAlchemy;
- application adapters and persistence;
- Workbench/Session/QML/product state;
- AQ/evaluation orchestration;
- released-package consumer integration and acceptance.

Does not own:

- duplicate implementations of package-owned Analysis algorithms/contracts.

The diagram should use arrows only where there is an actual handoff/consumption relationship. A small table below the diagram may summarize the most important boundary pairs if that is clearer than adding more arrows.

### Authorities

- `docs/ANALYSIS_PACKAGE_BOUNDARY_V1.md`
- `docs/CANON_INDEX.md`
- `docs/TARGET_ARCHITECTURE.md`

## 7. Visual 3 — Agent Workflow

**File:** `docs/visuals/agent-workflow.md`

### Purpose

Show the normal technical delivery path without exposing private reasoning or provider-specific tooling.

### Diagram

Primary flow:

`Intent / Issue → Live-state check → Determine owning repo → Read repo-local authority → Branch/worktree → Change + focused validation → broader relevant gates → PR → CI + review feedback → Merge → live verification → DONE`

Include one decision point:

- **Does the task belong to another component repo?**
  - yes → enter that repo and adopt its local rules/canon;
  - no → continue in Sample Brain.

Include one explicit feedback loop:

- test/CI/review finding inside the same scope → repair → revalidate → return to gate.

The visual must not mention or require private MCP, connector names, hidden chain-of-thought, or vendor-specific agent internals.

### Authority / governance sources

- root `AGENTS.md`
- repository-local `AGENTS.md` after routing
- `docs/CANON_INDEX.md`
- `docs/MERGE_REVIEW_FEEDBACK_GATE.md`
- live GitHub state

## 8. Visuals index

**File:** `docs/visuals/README.md`

Keep this page short. It is a router, not an architecture essay.

It should answer:

- “I want the big picture” → System Map
- “I need to know who owns this” → Ownership Map
- “I need to know how a slice gets delivered” → Agent Workflow

It must state prominently:

> Visuals explain current authority; they do not replace it. When a visual conflicts with live state or canonical contracts, live/canonical authority wins.

## 9. Visual style rules

The visual layer should feel deliberate and readable rather than mechanically exhaustive.

Rules:

- Prefer left-to-right flows where chronology/dependency is the point.
- Prefer grouped subgraphs/zones for ownership.
- Keep a normal GitHub viewport readable; do not produce giant node forests.
- Use short human labels in nodes; put exact module/file details in supporting prose/links.
- Use status/future labels only when necessary to prevent misunderstanding.
- No decorative complexity that makes the source harder to maintain.
- No duplicated long tables from canonical docs.

## 10. Current vs future

The system map represents **current confirmed topology**.

Planned component repositories are not shown as active nodes. If future architecture needs to be illustrated later, it must be visually and textually separated from current state and sourced from an approved architecture decision.

Product-mode future state (for example later Live) is not part of this initial system-repository map unless needed to prevent a direct architecture misunderstanding.

## 11. Validation

Before merge:

1. Re-read current `main`, issue #1163, and the listed authority docs.
2. Check all repository/document links.
3. Review Mermaid source for GitHub-compatible syntax and readable graph size.
4. Compare every ownership claim against `ANALYSIS_PACKAGE_BOUNDARY_V1.md` and `TARGET_ARCHITECTURE.md`.
5. Verify the agent workflow against root/docs agent guidance and merge-review policy.
6. Run `python tools/check_canon_drift.py`.
7. Run `git diff --check`.
8. Review final PR head and all CI/review feedback before merge.

No runtime test suite is required solely because these are explanatory docs unless repository CI or a changed executable contract requires it.

## 12. Non-goals

This slice does not:

- create a generic repository template;
- redesign system architecture;
- move ownership between repositories;
- add a separate Consumer Flow visual;
- visualize every contract or module;
- create product UI mockups;
- add a diagram-generation framework;
- add provider-specific agent instructions;
- expose private reasoning/tooling internals;
- make future repositories look implemented.

## 13. Completion condition

The slice is complete when the four visual documents are merged, all diagrams are consistent with current authority, relevant doc/CI/review gates pass, issue #1163 is closed, and the delivery exit is:

`HUMAN_VISUAL_ARCH_LAYER_READY`
