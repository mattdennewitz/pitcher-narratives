# Coding Conventions

**Analysis Date:** 2026-03-26

## Project Status

This is a minimal scaffold project with a single source file (`main.py`). No formal conventions have been established yet. The guidelines below are **prescriptive recommendations** based on the project's technology choices (Python 3.14, Polars, Pydantic AI) and standard Python community practices. Follow these when adding new code.

## Naming Patterns

**Files:**
- Use `snake_case.py` for all Python modules
- Current example: `main.py`

**Functions:**
- Use `snake_case` for all functions and methods
- Current example: `def main():` in `main.py`

**Variables:**
- Use `snake_case` for local variables and module-level variables
- Use `UPPER_SNAKE_CASE` for constants

**Types/Classes:**
- Use `PascalCase` for classes, Pydantic models, and type aliases
- Use Pydantic models (from `pydantic` or `pydantic-ai`) for structured data rather than plain dicts

**Modules/Packages:**
- Use `snake_case` for module and package directory names

## Code Style

**Formatting:**
- Not yet configured. **Recommendation:** Add `ruff` as a dev dependency and configure in `pyproject.toml`:
  ```toml
  [tool.ruff]
  line-length = 88
  target-version = "py314"

  [tool.ruff.format]
  quote-style = "double"
  ```

**Linting:**
- Not yet configured. **Recommendation:** Use `ruff` for linting as well:
  ```toml
  [tool.ruff.lint]
  select = ["E", "F", "I", "UP", "B", "SIM"]
  ```

**Type Checking:**
- Not yet configured. **Recommendation:** Add `mypy` or `pyright` as a dev dependency. Given the use of Pydantic AI, `pyright` pairs well:
  ```toml
  [tool.pyright]
  pythonVersion = "3.14"
  typeCheckingMode = "basic"
  ```

## Import Organization

**Order (follow PEP 8 / isort conventions):**
1. Standard library imports
2. Third-party imports (polars, pydantic_ai, etc.)
3. Local application imports

**Style:**
- Use absolute imports for project modules
- Group imports with a blank line between each section
- Sort alphabetically within each group

**Example:**
```python
import json
from pathlib import Path

import polars as pl
from pydantic_ai import Agent

from pitcher_narratives.models import GameSummary
```

**Path Aliases:**
- None configured. The project does not yet use a `src/` layout or path aliasing.

## Error Handling

**Patterns (recommended):**
- Use specific exception types, not bare `except:`
- For Pydantic AI agent errors, catch `pydantic_ai` exception types specifically
- For Polars operations, handle `pl.exceptions.ComputeError` and similar
- Use structured logging (not print statements) for error reporting in production code

## Logging

**Framework:** Not yet configured.

**Recommendation:**
- Use Python's built-in `logging` module or `loguru` for structured logging
- The `pydantic-ai` dependency pulls in `logfire` as a transitive dependency, which could be used for observability
- Replace `print()` calls (currently in `main.py`) with proper logging as the project grows

## Comments

**When to Comment:**
- Add docstrings to all public functions, classes, and modules
- Use inline comments sparingly, only to explain "why" not "what"
- Use type hints on all function signatures instead of documenting parameter types in docstrings

**Docstring Style (recommended):**
- Use Google-style docstrings:
  ```python
  def process_game(game_id: str) -> GameSummary:
      """Process a single game and generate a narrative summary.

      Args:
          game_id: The unique identifier for the game.

      Returns:
          A structured summary of the game narrative.
      """
  ```

## Function Design

**Size:** Keep functions focused on a single responsibility. Aim for under 30 lines.

**Parameters:** Use type hints on all parameters. Use Pydantic models for complex parameter groups.

**Return Values:** Always annotate return types. Use `-> None` explicitly when a function returns nothing.

## Module Design

**Exports:**
- Use `__all__` in modules that serve as public APIs
- Keep internal helpers prefixed with `_`

**Barrel Files:**
- Use `__init__.py` files for package-level re-exports when creating packages

## Configuration

**Environment Variables:**
- No `.env` file exists yet
- No environment configuration pattern established
- **Recommendation:** Use `pydantic-settings` (compatible with the existing Pydantic dependency) for typed environment configuration

**Project Configuration:**
- All project metadata is in `pyproject.toml`
- No `[tool.*]` sections configured yet -- all tooling configuration should go here (not in separate config files)

## Entry Point

**Current:** `main.py` uses the `if __name__ == "__main__":` guard pattern. Maintain this pattern for script entry points.

**Recommendation:** As the project grows, add a proper CLI entry point in `pyproject.toml`:
```toml
[project.scripts]
pitcher-narratives = "pitcher_narratives.main:main"
```

---

*Convention analysis: 2026-03-26*
