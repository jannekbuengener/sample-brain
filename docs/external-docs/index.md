# External References — Sample Brain

This repo-local index records external technical references that are materially relevant to Sample Brain. It follows the Agent Workforce external-reference contract: <https://github.com/jannekbuengener/agent-workforce/blob/main/contracts/EXTERNAL_REFERENCE_CONTRACT.md>.

This file is **not** repository truth. GitHub/repo live state, local `AGENTS.md`, canon, source/config/CI and dependency manifests remain authoritative for what Sample Brain actually uses.

## Priority and authority

- `P0` — active/core reference backed by a current repo signal.
- `P1` — active secondary/conditional reference backed by a current repo signal.
- `P2` — parked/reference-only; never evidence of active implementation.

External source authority is separate from priority: `OFFICIAL_SPEC` > `OFFICIAL_DOCS` > `UPSTREAM_PROJECT_DOCS` > `UPSTREAM_ISSUES_RELEASES` > `ESTABLISHED_TECHNICAL_KNOWLEDGE` > `COMMUNITY` > `EXAMPLE_DISCOVERY`.

Load only entries relevant to the current task.

## Active references

| Category | Name | Priority | Source type | Authority | Purpose | Repo signal | When to use | Canonical URL / identity |
|---|---|---|---|---|---|---|---|---|
| Runtime | Python | `P0` | `official_docs` | `OFFICIAL_DOCS` | Language/runtime semantics and stdlib behavior. | `pyproject.toml` requires Python `>=3.12`; root `AGENTS.md` defines Python as the control/analysis baseline. | Python runtime, packaging, stdlib or compatibility work. | https://docs.python.org/3/ |
| Data | SQLite | `P0` | `official_docs` | `OFFICIAL_DOCS` | Embedded catalog/storage behavior. | Root `AGENTS.md` names sqlite in the project stack; catalog/database behavior is repo-owned. | Database, SQL, transactions, SQLite limits or migration behavior. | https://sqlite.org/docs.html |
| Analysis | sample-brain-analysis | `P0` | `upstream_project_docs` | `UPSTREAM_PROJECT_DOCS` | Package-owned analysis contracts and compute used by Sample Brain. | `pyproject.toml` pins the `sample-brain-analysis` wheel as a direct dependency; root `AGENTS.md` names it as a real component dependency. | Analysis API/compute boundary or package-integration work. | https://github.com/jannekbuengener/sample-brain-analysis |
| Audio analysis | librosa | `P0` | `official_docs` | `OFFICIAL_DOCS` | Audio feature/analysis API behavior. | `pyproject.toml` direct dependency `librosa==1.0.0`. | Analyzer/DSP code using librosa. | https://librosa.org/doc/latest/ |
| Numeric | NumPy | `P0` | `official_docs` | `OFFICIAL_DOCS` | Array/numerical semantics used across analysis and search. | `pyproject.toml` direct dependency `numpy>=2.5,<3`. | Array operations, vector math, dtype/shape behavior. | https://numpy.org/doc/stable/ |
| Numeric | SciPy | `P0` | `official_docs` | `OFFICIAL_DOCS` | Scientific/numerical algorithms used by analysis paths. | `pyproject.toml` direct dependency `scipy>=1.18,<2`. | SciPy-backed analysis or numerical behavior. | https://docs.scipy.org/doc/scipy/ |
| Audio I/O | SoundFile | `P0` | `upstream_project_docs` | `UPSTREAM_PROJECT_DOCS` | Audio file decode/encode and libsndfile-backed I/O. | `pyproject.toml` direct dependency `soundfile>=0.14,<0.15`; root `AGENTS.md` requires libsndfile for real analyze runs. | Audio file I/O, format or libsndfile behavior. | https://python-soundfile.readthedocs.io/ |
| Persistence | SQLAlchemy | `P0` | `official_docs` | `OFFICIAL_DOCS` | ORM/database abstraction behavior where used by current catalog/storage code. | `pyproject.toml` direct dependency `SQLAlchemy>=2.0.52,<3`. | SQLAlchemy engine/session/model behavior. | https://docs.sqlalchemy.org/ |
| Desktop UI | Qt for Python / PySide6 | `P0` | `official_docs` | `OFFICIAL_DOCS` | Qt Quick/QML and PySide6 desktop implementation reference. | Root `AGENTS.md` freezes `LOCK_PYSIDE6_QML`; `pyproject.toml` exposes the `qtquick` extra. | Screen-1/QML/PySide6 UI work. | https://doc.qt.io/qtforpython-6/ |
| Testing | pytest | `P0` | `official_docs` | `OFFICIAL_DOCS` | Unit/integration/runtime test behavior. | `tests/` plus root `AGENTS.md` quality gate `python -m pytest -q`. | Fixtures, collection, markers, parametrization or test behavior. | https://docs.pytest.org/en/stable/ |
| Static analysis | Ruff | `P1` | `official_docs` | `OFFICIAL_DOCS` | Current Python lint gate. | `[tool.ruff]` in `pyproject.toml`; root `AGENTS.md` identifies the CI Ruff gate. | Lint configuration or CI static-correctness work. | https://docs.astral.sh/ruff/ |
| Repository CI | GitHub Actions | `P1` | `official_docs` | `OFFICIAL_DOCS` | Workflow/check semantics used by repository CI. | `.github/workflows/`; root `AGENTS.md` defines CI/review gates. | Workflow, check, artifact or Actions behavior. | https://docs.github.com/en/actions |
| Semantic analysis | Transformers | `P1` | `official_docs` | `OFFICIAL_DOCS` | Optional CLAP/transformer runtime behavior. | `pyproject.toml` `clap` extra pins `transformers==5.20.1`; CLAP remains optional. | CLAP/transformer feature work only. | https://huggingface.co/docs/transformers/ |
| Semantic analysis | PyTorch | `P1` | `official_docs` | `OFFICIAL_DOCS` | Tensor/runtime reference for optional CLAP backend. | `pyproject.toml` `clap` extra pins `torch==2.14.0`; bootstrap explicitly avoids model download by default. | CLAP/PyTorch backend work only. | https://docs.pytorch.org/docs/stable/ |
| Vector search | sqlite-vec | `P1` | `upstream_project_docs` | `UPSTREAM_PROJECT_DOCS` | Optional SQLite vector-search backend. | `pyproject.toml` `vec` extra pins `sqlite-vec==0.1.9`; root `AGENTS.md` documents the optional vec gate. | sqlite-vec backend, gate or benchmark work only. | https://github.com/asg017/sqlite-vec |

## Parked references

No generic future technology is parked here merely because it is interesting. Add a `P2` entry only when a concrete Sample Brain issue/canon path gives it a real future purpose.

## Maintenance rules

- Every `P0`/`P1` row must keep a current repo signal.
- Demote or remove references when their supporting dependency/config/canon disappears.
- Optional dependencies remain `P1` unless local canon promotes them to an always-required path.
- Community/example material may aid discovery but cannot override current official/upstream or repository evidence.
- Do not commit workstation-specific absolute paths, credentials, private endpoints, private samples/tracks, generated audio or transient installation state.