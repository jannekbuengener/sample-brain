# EPIC 1 — Config and Profiles Spec

## 1. Purpose

EPIC 1 creates a clean configuration layer for Sample Brain. The goal is to remove hardcoded local paths from code and documentation. Profiles make Sample Brain portable, reproducible, and local-first.

## 2. Problem Statement

Several configuration values are currently hardcoded or fragile:

- `src/config.py` contains a machine-specific `SAMPLE_ROOTS` default that must be replaced by profile-based configuration
- `src/export_fl.py` imports `SAMPLE_ROOTS` and uses `roots[0]` for path resolution — brittle across machines
- `MAX_TAGS = 5` is hardcoded in `src/export_fl.py` — not configurable without code changes
- `src/embed.py` hardcodes `get_backend("noop")` — no way to select a backend via CLI or config
- No profile system exists — single-user, single-machine assumptions
- Bootstrap and testing require manual path editing

Without a config layer, onboarding, multi-library workflows, and CI remain unnecessarily fragile.

## 3. Scope

### In scope

- Profile-based configuration (YAML)
- Local-only overrides (untracked profile)
- Environment variable support
- Library roots configuration
- FL Studio User Data path
- Export settings (max tags, output format)
- Embedding backend selection (`--backend`, model cache dir)
- Path validation and clear error messages
- Migration of current hardcoded values

### Out of scope

- Cloud sync or remote config
- User accounts or authentication
- Secrets management beyond local config hygiene
- GUI settings screen
- Automatic sample discovery outside configured roots
- Hot-reloading config during a pipeline run

## 4. Configuration Principles

- **Committed config must be safe defaults only** — example paths are placeholders, not real values
- **Local config must stay untracked** — `config/profiles.local.yaml` must be added to `.gitignore` before local profiles are introduced
- **No private absolute paths in committed files** — use `<PLACEHOLDER>` syntax in examples
- **Environment variables may override profile values** — but never replace a missing profile
- **CLI flags may override config and env values** — precedence is explicit and documented
- **Generated state is not config** — DB path, index dir, report dir are runtime artifacts
- **Profiles are explicit, not magical** — a profile is selected by name, never auto-detected

## 5. Proposed Config Layers

Precedence from lowest to highest:

| Layer | Example | Committed? | Use case | Risk |
|-------|---------|------------|----------|------|
| Built-in safe defaults | `backend = "noop"`, `max_tags = 5` | ✅ Yes (in code) | Fallback when no config file exists | Low |
| Committed example profile | `config/profiles.example.yaml` | ✅ Yes | Documentation, CI, fresh clone reference | Low |
| Local untracked profile | `config/profiles.local.yaml` | ❌ Must be added to `.gitignore` | User's real paths and preferences | Low |
| Environment variables | `SAMPLE_BRAIN_LIBRARY_ROOTS` | ❌ Never | CI, headless, temporary overrides | Low |
| CLI flags | `--backend clap`, `--max-tags 10` | ❌ Never | Per-invocation overrides | Low |

## 6. Profile File Design

### 6.1 Location

- `config/profiles.example.yaml` — committed, safe defaults with placeholders
- `config/profiles.local.yaml` — must be ignored by `.gitignore`, user's real values
- Selected by name via `--profile <name>` or `SAMPLE_BRAIN_PROFILE`

### 6.2 Example (placeholder values only)

```yaml
profiles:
  default:
    library_roots:
      - "<SAMPLE_LIBRARY_ROOT>"
    fl_user_data_path: "<FL_USER_DATA_PATH>"
    export:
      max_tags: 5
    embedding:
      backend: "noop"
      model_cache_dir: "<MODEL_CACHE_DIR>"

  minimal-demo:
    library_roots:
      - "<DEMO_SAMPLE_ROOT>"
    fl_user_data_path: "<FL_USER_DATA_PATH>"
    export:
      max_tags: 3
    embedding:
      backend: "noop"
```

### 6.3 Rules

- All paths in the example file use `<PLACEHOLDER>` syntax
- No real absolute paths are ever committed
- The local profile (`profiles.local.yaml`) uses the same schema but with user's real values
- Profile names are alphanumeric with hyphens
- Unspecified values fall through to the committed example profile defaults

## 7. Environment Variables

### 7.1 Defined variables

| Variable | Overrides | Example |
|----------|-----------|---------|
| `SAMPLE_BRAIN_PROFILE` | Active profile name | `default` |
| `SAMPLE_BRAIN_LIBRARY_ROOTS` | Library roots | `<ROOT1>;<ROOT2>` |
| `SAMPLE_BRAIN_FL_USER_DATA` | FL Studio path | `<FL_USER_DATA_PATH>` |
| `SAMPLE_BRAIN_MODEL_CACHE_DIR` | Model cache directory | `<MODEL_CACHE_DIR>` |
| `SAMPLE_BRAIN_DB_PATH` | SQLite database location | `<DB_PATH>/catalog.db` |
| `SAMPLE_BRAIN_MAX_TAGS` | Export max tags | `10` |

### 7.2 Rules

- Environment variables override profile values at the same level
- Multiple library roots use OS-specific delimiter (`;` on Windows, `:` on Unix)
- An env var set to an empty string is treated as unset
- No env var values are ever committed to the repository

## 8. CLI Override Strategy

### 8.1 Planned flags

| Flag | Affects | Layer overridden |
|------|---------|------------------|
| `--profile <name>` | All config values | Profile selection |
| `--config <path>` | Config file location | Default config path |
| `scan --root <path>` | Library root (single) | `library_roots` |
| `export_fl --fl-user-data <path>` | FL Studio path | `fl_user_data_path` |
| `export_fl --max-tags <n>` | Tag count | `export.max_tags` |
| `embed --backend <name>` | Embedding backend | `embedding.backend` |
| `embed --model-cache-dir <path>` | Model cache | `embedding.model_cache_dir` |

### 8.2 Rule

CLI flags override environment variables, which override profile values, which override built-in defaults. This chain is explicit and documented.

## 9. Runtime Validation

The config loader must validate:

| Check | Error message |
|-------|---------------|
| Configured paths exist where required | `Library root not found: {path}` |
| Library roots are readable directories | `Cannot read library root: {path}` |
| FL Studio path is writable before export | `FL User Data path is not writable: {path}` |
| DB path parent exists or can be created | `Cannot create database directory: {path}` |
| Model cache dir is local and untracked | Warning if model cache dir appears inside repo |
| Profile parse errors | `Error parsing config file: {filename} — {details}` |
| Unknown profile name | `Unknown profile: {name}. Available: {names}` |

## 10. Artifact and Privacy Policy

Referenced document: `docs/DATA_AND_ARTIFACT_POLICY.md`

Rules inherited and extended:

- **Local config is never committed** — `config/profiles.local.yaml` must be ignored by `.gitignore` before local profiles are introduced
- **Profiles must not contain secrets** — passwords, tokens, and API keys have no place in profile files
- **Sample roots are privacy-sensitive** — they reveal the user's directory structure and drive layout
- **No telemetry** — config must not phone home, check for updates, or report usage
- **No automatic upload** — config is local-only; there is no "sync to cloud" feature
- **FL Studio path is privacy-sensitive** — it reveals the user's OS username and drive layout
- **Model cache dir** — default to system cache outside the repo (`~/.cache/huggingface/`); user may override

## 11. Migration Plan

### Step 1: Document current config debt

Identify all hardcoded values:

- `src/config.py`: `SAMPLE_ROOTS` hardcoded sample root placeholder/debt
- `src/export_fl.py`: `MAX_TAGS = 5` (hardcoded constant)
- `src/export_fl.py`: `roots[0]` assumption (brittle)
- `src/embed.py`: `get_backend("noop")` (no selection mechanism)
- `src/config.py`: `REGEX_MAP_PATH` (relies on `DATA_DIR`)

### Step 2: Add example profile

Create `config/profiles.example.yaml` with placeholder paths.

### Step 3: Add gitignore rule

Add `config/profiles.local.yaml` to `.gitignore`.

### Step 4: Add config loader module

Create `src/config_loader.py` that:

- Reads the example profile as base defaults
- Merges the local profile (if present)
- Applies environment variable overrides
- Returns a resolved config dict

### Step 5: Wire pipeline steps to config

- `scan` reads `library_roots` from profile
- `export_fl` reads `fl_user_data_path` and `max_tags` from profile
- `embed` reads `backend` and `model_cache_dir` from profile
- CLI flags override each value

### Step 6: Add validation

Implement the checks from Section 9. Fail early with clear messages.

### Step 7: Update README

- Remove hardcoded path examples (already uses `DEINNAME` placeholder, but reference profile setup)
- Add profile setup instructions to Quickstart
- Document env var overrides

## 12. Acceptance Criteria

EPIC 1 is done when:

| # | Criterion | Validation |
|---|-----------|------------|
| 1 | No real local paths remain in committed code or config | Grep for `D:\`, `C:\Users`, or similar patterns |
| 2 | Example profile exists with placeholder paths only | `config/profiles.example.yaml` contains `<PLACEHOLDER>` values |
| 3 | Local profile is gitignored | `git check-ignore config/profiles.local.yaml` returns the file |
| 4 | CLI can select a profile via `--profile` | `sample-brain --profile minimal-demo scan` works |
| 5 | Default profile is used when none is specified | `sample-brain scan` works without flags |
| 6 | Env vars override profile values | `SAMPLE_BRAIN_LIBRARY_ROOTS=D:\Test` changes scan root |
| 7 | CLI flags override env vars | `--root` flag takes precedence over env var |
| 8 | Missing paths produce clear error messages | `sample-brain scan --root /nonexistent` says "not found" |
| 9 | Unknown profile name produces clear error | `--profile nonexistent` says "Unknown profile" |
| 10 | README explains profile setup | README has a "Configuration" or "Profiles" section |

## 12.1 Implementation Status

EPIC 1 core wiring is complete on `main`. All acceptance criteria are met (or documented as future hardening):

| # | Criterion | Status | Note |
|---|-----------|--------|------|
| 1 | No real local paths in committed code or config | ✅ | `SAMPLE_ROOTS` is empty list; `src/config.py` cleaned |
| 2 | Example profile exists with placeholder paths | ✅ | `config/profiles.example.yaml` |
| 3 | Local profile is gitignored | ✅ | `config/profiles.local.yaml` in `.gitignore` |
| 4 | CLI can select a profile via `--profile` | ✅ | Global `--profile` flag implemented |
| 5 | Default profile is used when none is specified | ✅ | `DEFAULT_PROFILE_NAME = "default"` |
| 6 | Env vars override profile values | ✅ | 6 env vars supported, tested |
| 7 | CLI flags override env vars | ✅ | Precedence: CLI > env > profile > default |
| 8 | Missing paths produce clear error messages | ⚠️ | Backend validated; path existence not yet checked |
| 9 | Unknown profile name produces clear error | ✅ | Tested and implemented |
| 10 | README explains profile setup | ✅ | Configuration section, CLI overrides, security note |

**Future hardening** (tracked but not blocking close):
- Runtime path validation (Section 9)
- CLI wiring integration tests
- `embed --model-cache-dir` CLI flag
- Explicit local-config-only flag

## 13. Risks and Mitigations

| Risk | Impact | Likelihood | Mitigation |
|------|--------|------------|------------|
| Config becomes too complex for a CLI tool | Medium — user frustration | Medium | Start simple (single YAML file), no nested profile inheritance |
| Local paths leak into git via example file | High — privacy violation | Low | Placeholder policy, `config/profiles.example.yaml` is the only committed config file |
| CLI override precedence is confusing | Medium — wrong behaviour | Low | Document explicitly: CLI > env > profile > default |
| Windows path handling is brittle (drives, backslashes, delimiters) | Medium — broken paths | Medium | Use `pathlib` throughout, test on Windows first, document delimiter rules |
| Profiles conflict with env vars silently | Medium — unexpected values | Low | Log which value was used and from which layer at startup (debug level) |
| Users expect config hot-reload | Low — minor annoyance | Medium | Document that config is read once at startup; restart to pick up changes |

## 14. Related Documents

- `docs/PRODUCT_REQUIREMENTS.md` — target audience, product principles (local-first, privacy by default)
- `docs/SYSTEM_REQUIREMENTS.md` — non-functional requirements (NFR-MNT-03: configuration externalised)
- `docs/TARGET_ARCHITECTURE.md` — Section 2.4 (known technical debt: hardcoded SAMPLE_ROOTS), Section 4.2 (config/profile layer)
- `docs/DATA_AND_ARTIFACT_POLICY.md` — what is committed vs untracked, path placeholder policy
- `docs/DAW_INTEGRATION_SPEC.md` — FL Studio path reliance on config
- `docs/EPIC_2_SEMANTIC_SEARCH_SPEC.md` — embedding backend selection via config
- `docs/BOOTLOADER_AND_CONTEXT_STRATEGY.md` — session startup relies on clean config
- `docs/SAMPLE_BRAIN_SKILLS_SPEC.md` — skills read config values
- `docs/ISSUE_BACKLOG.md` — EPIC 1 issues #7 (refactor roots) and #8 (project config file)
- `knowledge/ACTIVE_ROADMAP.md` — EPIC 1 completed; roadmap moved to EPIC 2
