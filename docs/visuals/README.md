# Architektur auf einen Blick

**Human Visual Layer = Orientierung. Canon, Contracts und Live-State = Authority.** Bei Abweichungen gelten die [Canon-Einstiege](../CANON_INDEX.md), die verlinkten Contracts und der aktuelle Repository-/GitHub-Stand.

For repository ownership and the wider meta/metatool landscape, see [Repository Ecosystem](../REPOSITORY_ECOSYSTEM.md). These visuals intentionally stay focused on Sample Brain product/component architecture; `agent-workforce`, `agent-brain`, and `arvp` are not implicit product runtime dependencies.

| Visual | Was zeigt es? | Wann schaue ich hier rein? | Eigentliche Source of Truth |
|---|---|---|---|
| [System Map](system-map.md) | Product/component repositories, Abhängigkeitsrichtung und Sample-Analysefluss | Für das Gesamtbild oder den Weg eines Samples | [Target Architecture](../TARGET_ARCHITECTURE.md), [Analysis Package Boundary](../ANALYSIS_PACKAGE_BOUNDARY_V1.md) |
| [Ownership Map](ownership-map.md) | Zuständigkeiten und harte Nicht-Ownership-Grenzen | Vor einer Änderung an Analysis, Product oder Persistence | [Analysis Package Boundary](../ANALYSIS_PACKAGE_BOUNDARY_V1.md), [Analysis Consumer Contract](../ANALYSIS_PUBLIC_CONTRACT_V1.md) |
| [Agent Workflow](agent-workflow.md) | Weg von Issue und Live-State bis Merge und Verifikation | Beim Start und Abschluss eines technischen Slices | [AGENTS.md](../../AGENTS.md), [Merge Review Feedback Gate](../MERGE_REVIEW_FEEDBACK_GATE.md) |
