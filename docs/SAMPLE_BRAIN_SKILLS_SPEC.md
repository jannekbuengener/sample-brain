# Sample Brain Skills Spec

## 1. Purpose

This document describes planned Sample-Brain-specific skills. Skills are repeatable work patterns for agents operating on this repository. This file is a specification, not an installation. Skills must respect the Bootloader Strategy and the Artifact Policy.

## 2. Skill Design Principles

- Repo-specific over generic
- Context-first, action-second
- Read-only by default
- Explicit write approval
- No private file access
- No generated artifact commits
- No `git add .`
- No silent dependency changes
- No sample/audio processing unless explicitly requested
- Documentation and architecture context take precedence over tool automation

## 3. Required Bootloader Integration

Every skill must define:

- Mandatory docs
- Task-specific docs
- Forbidden sources
- Allowed repo operations
- Expected output
- Stop conditions

Referenced documents:

- `docs/BOOTLOADER_AND_CONTEXT_STRATEGY.md`
- `docs/DATA_AND_ARTIFACT_POLICY.md`

## 4. Proposed Skill Inventory

| Skill | Purpose | Category | Risk | Priority |
|-------|---------|----------|------|----------|
| `sample-brain-session-start` | Boot session cleanly | Governance | Low | P0 |
| `sample-brain-docs-architect` | Design doc structure, maintain specs | Documentation | Low | P0 |
| `sample-brain-backlog-triage` | Consolidate backlog + GitHub issues | Planning | Low | P0 |
| `sample-brain-epic2-planner` | Plan semantic search steps | Architecture | Medium | P1 |
| `sample-brain-artifact-guard` | Pre-commit artifact hygiene check | Governance | Low | P0 |
| `sample-brain-pr-review` | Review PRs without merge action | Review | Medium | P1 |
| `sample-brain-ci-guard` | Evaluate CI/workflow changes | Review | Medium | P1 |
| `sample-brain-export-workflow` | Plan/review DAW export | Documentation | Low | P2 |
| `sample-brain-skill-audit` | Evaluate external skill packs | Planning | Low | P2 |
| `sample-brain-session-close` | Close session cleanly | Governance | Low | P0 |

## 5. Skill: sample-brain-session-start

**Purpose:** Boot a new session cleanly — check branch/status, load mandatory documents, classify task, name risks.

**Inputs:**
- User task description
- Repo status (`git status --short --branch`)

**Mandatory docs:**
- `docs/BOOTLOADER_AND_CONTEXT_STRATEGY.md`
- `docs/PRODUCT_REQUIREMENTS.md`
- `docs/SYSTEM_REQUIREMENTS.md`
- `docs/TARGET_ARCHITECTURE.md`
- `docs/DATA_AND_ARTIFACT_POLICY.md`
- `knowledge/CURRENT_STATUS.md`
- `knowledge/ACTIVE_ROADMAP.md`
- `agents/AGENTS.md`

**Outputs:**
- Branch and working tree status
- List of loaded documents
- Task classification
- Identified constraints
- Recommended next action

**Stop conditions:**
- Dirty working tree
- Wrong branch (work on main vs feature branch mismatch)
- Private files requested without explicit approval
- Unclear write action without user clarification

## 6. Skill: sample-brain-docs-architect

**Purpose:** Design documentation structure, maintain requirements/architecture/specs, detect contradictions.

**Inputs:**
- Requested doc change or new doc topic
- Existing documentation files

**Allowed operations:**
- Read public docs
- Propose doc patches
- Create docs-only files

**Forbidden:**
- Code changes
- Private knowledge files
- External skill pack reading
- Generated artifact creation

**Outputs:**
- Gap analysis (what is missing, what contradicts)
- Proposed doc structure
- Commit-ready doc patch
- Review checklist

**Mandatory docs for any architecture work:**
- `docs/TARGET_ARCHITECTURE.md`
- `docs/PRODUCT_REQUIREMENTS.md`
- `docs/SYSTEM_REQUIREMENTS.md`
- `docs/DATA_AND_ARTIFACT_POLICY.md`

## 7. Skill: sample-brain-backlog-triage

**Purpose:** Consolidate `docs/ISSUE_BACKLOG.md` and GitHub issues/PRs as work sources. Prioritise tasks, derive next action.

**Inputs:**
- Issue Backlog
- Active Roadmap
- Current Status
- Optional: GitHub issue list (read-only)

**Outputs:**
- Task table with priority, risk, effort estimate
- Recommendation for next action

**Rules:**
- GitHub is a reference, not the authority — backlog doc is source of truth
- No issues created without explicit approval
- No merge or PR action without explicit approval

## 8. Skill: sample-brain-epic2-planner

**Purpose:** Plan semantic search work according to the EPIC 2 spec. Distinguish between spike and production status.

**Mandatory docs:**
- `docs/EPIC_2_SEMANTIC_SEARCH_SPEC.md`
- `knowledge/roadmap/adr/ADR-0001-embedding-model-strategy.md`
- `knowledge/roadmap/adr/ADR-0002-local-vector-index-strategy.md`
- `knowledge/roadmap/adr/ADR-0003-embedding-db-schema-design.md`
- `docs/TARGET_ARCHITECTURE.md`
- `docs/DATA_AND_ARTIFACT_POLICY.md`

**Outputs:**
- Implementation sequence per EPIC 2 Section 7
- Acceptance criteria per milestone
- Risk register
- Explicit "do not implement yet" boundaries

**Forbidden:**
- Treating PR #10 (`spike/clap-embedding`) as `main` status
- Claiming FAISS or search as complete
- Introducing heavy dependencies without policy check

## 9. Skill: sample-brain-artifact-guard

**Purpose:** Ensure no artifacts or private data are staged before any commit.

**Checks:**
- `git status --short --branch`
- Tracked/untracked artifact patterns:
  - `.db`, `.sqlite`, `.faiss`, `.index`, `.npy`, `.npz`, `.pkl`
  - `reports/`
  - `.venv/`
  - `knowledge/SHARED.WORKING.MEMORY.md`
  - `knowledge/logs/`
  - Sample audio files (`.wav`, `.aiff`, `.flac`, `.mp3`)

**Outputs:**
- Safe / unsafe verdict
- Remediation steps if unsafe
- Exact list of files allowed to stage

**Rules:**
- Never `git add .`
- Use targeted staging only

## 10. Skill: sample-brain-pr-review

**Purpose:** Review PRs without performing any merge action. Classify diffs, prepare comments.

**Allowed:**
- Read PR status and diff
- Produce review matrix
- Draft comments

**Requires explicit approval:**
- Posting comments on GitHub
- Changing PR state
- Merging
- Rerunning checks

**Outputs:**
- Risk category
- Test plan
- Recommendation
- Comment draft

## 11. Skill: sample-brain-ci-guard

**Purpose:** Evaluate CI/workflow changes. Do not modify GitHub Actions blindly. Separate billing/runner issues from code errors.

**Inputs:**
- Workflow diff
- Run status
- Logs if available

**Rules:**
- No workflow activation without review
- No fake green status
- No trigger commits
- No merge with unknown red checks

**Outputs:**
- Root cause analysis
- Safe fix plan
- Rerun / hold recommendation

## 12. Skill: sample-brain-export-workflow

**Purpose:** Plan and review FL Studio export and future DAW integration.

**Mandatory docs:**
- `docs/DAW_INTEGRATION_SPEC.md`
- `docs/TARGET_ARCHITECTURE.md`
- `docs/DATA_AND_ARTIFACT_POLICY.md`

**Rules:**
- No private sample paths in documentation
- No real FL User Data paths in examples
- No generated tag files committed
- Placeholder paths only

**Outputs:**
- Export flow review
- Edge case inventory
- Validation plan

## 13. Skill: sample-brain-skill-audit

**Purpose:** Evaluate external skill packs for future usability. This skill is future-only and must not read external directories unless explicitly approved.

**Candidate packs (names only, not paths):**
- `jMerta`
- `skillforge`
- `Anthropic-Cybersecurity-Skills`
- `cdb-docs-ops`
- `cdb-ci-cd-guard`
- `gh-address-comments`
- `cdb-session-start`
- `cdb-session-close`
- `cdb-issue-to-session-plan`
- `cdb-drift-reconcile`

**Evaluation criteria:**
- Relevance to Sample Brain
- Safety (no broad write actions, no secret handling risk)
- No private path assumptions
- Compatibility with Bootloader Strategy

**Outputs:**
- Recommended
- Adapt before use
- Reject
- Reason

## 14. Skill: sample-brain-session-close

**Purpose:** Close a session cleanly — produce a result report, derive status and next prompt, document open risks.

**Outputs:**
- Changed files
- Commits made
- Pushed / not pushed status
- Open risks
- Recommended next prompt
- Confirmation that no forbidden sources were read

**Rules:**
- No private working memory dump
- No logs committed
- No background promises or follow-up tasks without explicit user intent

## 15. Skill Definition Template

```md
## Skill: <name>

Purpose:
Inputs:
Mandatory docs:
Task-specific docs:
Forbidden sources:
Allowed operations:
Requires approval:
Stop conditions:
Expected output:
Validation:
```

## 16. Approval Model

- **Read-only default** — all operations start as read-only
- **Write requires explicit approval** — any file modification, creation, or deletion
- **GitHub write requires explicit gate** — posting comments, changing PR state, merging
- **Git admin/merge requires explicit gate** — merge, rebase, force-push
- **Local commits require explicit user intent** — user must say "commit" or equivalent
- **Push requires explicit user intent** — user must say "push" or equivalent

## 17. Non-Goals

- No actual skill installation
- No external skill-pack reading
- No private prompt ingestion
- No MCP server implementation
- No global Codex/opencode configuration change
- No automatic GitHub writes
- No background automation

## 18. Related Documents

- `docs/BOOTLOADER_AND_CONTEXT_STRATEGY.md`
- `docs/DATA_AND_ARTIFACT_POLICY.md`
- `docs/TARGET_ARCHITECTURE.md`
- `docs/EPIC_2_SEMANTIC_SEARCH_SPEC.md`
- `docs/DAW_INTEGRATION_SPEC.md`
- `agents/AGENTS.md`
- `docs/MCP_SETUP.md`
