# Codebase Structure

**Analysis Date:** 2026-03-26

## Directory Layout

```
pitcher-narratives/
├── .claude/                # Claude Code local settings
│   └── settings.local.json # Allowed skills configuration
├── .planning/              # GSD planning documents
│   └── codebase/           # Codebase analysis documents (this file lives here)
├── .venv/                  # Python virtual environment (uv-managed, not committed)
├── .python-version         # Python version pin: 3.14
├── main.py                 # Application entry point (hello-world scaffold)
├── pyproject.toml          # Project metadata and dependencies
├── README.md               # Project readme (empty)
└── uv.lock                 # Locked dependency versions
```

## Directory Purposes

**`.claude/`:**
- Purpose: Claude Code configuration
- Contains: `settings.local.json` with local permission settings
- Key files: `.claude/settings.local.json`

**`.planning/`:**
- Purpose: GSD planning and analysis documents
- Contains: Codebase mapping documents
- Key files: `.planning/codebase/ARCHITECTURE.md`, `.planning/codebase/STRUCTURE.md`

**`.venv/`:**
- Purpose: Python virtual environment managed by `uv`
- Contains: Installed Python packages and interpreter symlinks
- Generated: Yes
- Committed: No (should be in `.gitignore`)

## Key File Locations

**Entry Points:**
- `main.py`: Application entry point. Run with `python main.py` or `uv run main.py`.

**Configuration:**
- `pyproject.toml`: Project metadata, Python version constraint (>=3.14), and dependency declarations (polars >=1.39.3, pydantic-ai >=1.72.0).
- `.python-version`: Pins Python 3.14 for `uv` and other version managers.
- `uv.lock`: Locked dependency graph. Do not edit manually; managed by `uv lock`.

**Core Logic:**
- `main.py`: Currently the only source file. Contains a `main()` function with a print statement.

**Testing:**
- No test files or test configuration exist yet.

## Naming Conventions

**Files:**
- Python source: `snake_case.py` (only `main.py` exists as reference)
- Config: Standard names (`pyproject.toml`, `.python-version`)

**Directories:**
- Lowercase, no separators observed (`.claude`, `.planning`)

## Where to Add New Code

**New Python Module/Package:**
- Create a package directory at the project root: e.g., `pitcher_narratives/` with `__init__.py`
- Or adopt a `src/pitcher_narratives/` layout if a src-layout is preferred
- Update `pyproject.toml` with `[tool.setuptools.packages]` or equivalent if packaging is needed
- Note: No `src/` layout exists yet -- the convention is not established. Choose one approach and be consistent.

**New pydantic-ai Agent:**
- Place agent definitions in a dedicated module, e.g., `pitcher_narratives/agents/` or `agents/`
- Each agent can be its own file: `agents/narrative_agent.py`
- Define Pydantic result models alongside or in a shared `models/` directory

**New Data Processing:**
- Place Polars-based data loading and transformation in a `data/` or `pitcher_narratives/data/` module
- Separate data loading (I/O) from transformation (pure functions on DataFrames)

**New Pydantic Models:**
- Place in `models/` or `pitcher_narratives/models/`
- Group by domain: `models/pitcher.py`, `models/narrative.py`

**New Feature (general guidance):**
- Primary code: Create appropriate module under the project package
- Tests: Place in `tests/` directory at project root, mirroring source structure
- Configuration: Add to `pyproject.toml` for dependencies; use environment variables for runtime config

**Utilities:**
- Shared helpers: `pitcher_narratives/utils/` or `utils/`

## Special Directories

**`.venv/`:**
- Purpose: Python virtual environment with all installed packages
- Generated: Yes (by `uv sync` or `uv venv`)
- Committed: No

**`.git/`:**
- Purpose: Git repository metadata
- Generated: Yes
- Committed: N/A (is the VCS itself)

## Package Management

**Tool:** `uv` (inferred from `uv.lock` and `.python-version`)

**Common commands:**
```bash
uv sync              # Install dependencies from lockfile
uv add <package>     # Add a new dependency
uv run main.py       # Run the entry point through the managed environment
uv lock              # Regenerate the lockfile
```

## Notes on Current State

This is a fresh scaffold with no established package structure. Key decisions still to be made:

1. **Package layout:** Flat (`main.py` + modules at root) vs. package (`pitcher_narratives/`) vs. src-layout (`src/pitcher_narratives/`). The package or src-layout is recommended for anything beyond a simple script.

2. **No `.gitignore`:** The project currently has no `.gitignore` file. One should be created to exclude `.venv/`, `__pycache__/`, `.env`, `*.pyc`, and other standard Python ignores.

3. **Empty README:** `README.md` exists but is empty.

4. **No test infrastructure:** No `tests/` directory, no test framework in dependencies, no test configuration in `pyproject.toml`.

---

*Structure analysis: 2026-03-26*
