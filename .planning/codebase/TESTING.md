# Testing Patterns

**Analysis Date:** 2026-03-26

## Project Status

No testing infrastructure exists. There are zero test files, no test framework configured, no test runner, no coverage tooling, and no CI/CD pipeline. Everything below under "Current State" documents what is absent. The "Recommended Setup" sections provide prescriptive guidance for establishing testing.

## Current State

**Test Framework:** Not configured
**Test Files:** None
**Test Configuration:** None (no `[tool.pytest]` in `pyproject.toml`, no `conftest.py`, no `pytest.ini`)
**Coverage:** Not configured
**CI/CD:** Not configured (no `.github/` directory, no CI config files)

## Test Framework (Recommended)

**Runner:**
- pytest (the standard for Python projects, well-supported by pydantic-ai)
- Add to `pyproject.toml`:
  ```toml
  [project.optional-dependencies]
  dev = [
      "pytest>=8.0",
      "pytest-asyncio>=0.24",
      "pytest-cov>=5.0",
  ]
  ```

**Configuration in `pyproject.toml`:**
```toml
[tool.pytest.ini_options]
testpaths = ["tests"]
asyncio_mode = "auto"
pythonpath = ["."]
```

**Assertion Library:**
- Use pytest's built-in assertions (no need for a separate library)

**Run Commands:**
```bash
uv run pytest                    # Run all tests
uv run pytest -x                 # Stop on first failure
uv run pytest --cov              # Run with coverage
uv run pytest -k "test_name"    # Run specific test
uv run pytest tests/unit/        # Run only unit tests
```

## Test File Organization (Recommended)

**Location:**
- Use a separate `tests/` directory at project root (not co-located with source)

**Naming:**
- Test files: `test_<module_name>.py`
- Test functions: `test_<behavior_description>`
- Test classes (for grouping): `TestClassName`

**Structure:**
```
pitcher-narratives/
├── main.py
├── tests/
│   ├── __init__.py
│   ├── conftest.py           # Shared fixtures
│   ├── unit/
│   │   ├── __init__.py
│   │   └── test_main.py
│   └── integration/
│       ├── __init__.py
│       └── test_agent.py
```

## Test Structure (Recommended)

**Suite Organization:**
```python
"""Tests for the main module."""
import pytest

from main import main


class TestMain:
    """Tests for the main() entry point."""

    def test_main_runs_without_error(self, capsys: pytest.CaptureFixture[str]) -> None:
        """Verify main() executes and produces expected output."""
        main()
        captured = capsys.readouterr()
        assert "Hello from pitcher-narratives!" in captured.out
```

**Patterns:**
- Use `conftest.py` for shared fixtures at each test directory level
- Use `pytest.fixture` for setup, not `setUp`/`tearDown` methods
- Prefer function-scoped fixtures (the default) unless expensive to create

## Mocking

**Framework:** `unittest.mock` (built-in) or `pytest-mock`

**Patterns for Pydantic AI:**
- Use `pydantic_ai.models.test.TestModel` for mocking AI model responses:
  ```python
  from pydantic_ai import Agent
  from pydantic_ai.models.test import TestModel

  async def test_agent_response():
      agent = Agent(model=TestModel())
      result = await agent.run("test prompt")
      assert result.data is not None
  ```

**What to Mock:**
- External API calls (AI model providers)
- File system operations for data loading
- Network requests

**What NOT to Mock:**
- Pydantic model validation (test real validation behavior)
- Polars DataFrame transformations (test with real data)
- Pure functions with no side effects

## Fixtures and Factories (Recommended)

**Test Data:**
```python
import polars as pl
import pytest


@pytest.fixture
def sample_game_data() -> pl.DataFrame:
    """Provide a minimal DataFrame for testing."""
    return pl.DataFrame({
        "pitcher_id": [1, 2],
        "pitch_type": ["FF", "SL"],
        "velocity": [95.2, 84.1],
    })
```

**Location:**
- Shared fixtures: `tests/conftest.py`
- Module-specific fixtures: `tests/<subdir>/conftest.py`
- Static test data files: `tests/fixtures/` (CSV, JSON, etc.)

## Coverage

**Requirements:** Not enforced. No coverage tooling configured.

**Recommended Setup:**
```toml
[tool.coverage.run]
source = ["."]
omit = ["tests/*", ".venv/*"]

[tool.coverage.report]
fail_under = 80
show_missing = true
```

**View Coverage:**
```bash
uv run pytest --cov --cov-report=html    # Generate HTML report
open htmlcov/index.html                   # View in browser
```

## Test Types

**Unit Tests:**
- Scope: Individual functions and classes
- Location: `tests/unit/`
- No external dependencies -- mock all I/O

**Integration Tests:**
- Scope: Pydantic AI agent workflows, Polars data pipelines end-to-end
- Location: `tests/integration/`
- May use TestModel from pydantic-ai for deterministic AI responses

**E2E Tests:**
- Not applicable yet (no web interface or API server)

## Async Testing

Given that `pydantic-ai` is async-first, async test support is critical.

**Pattern:**
```python
import pytest


@pytest.mark.asyncio
async def test_async_operation() -> None:
    """Test an async function."""
    result = await some_async_function()
    assert result is not None
```

With `asyncio_mode = "auto"` in pytest config, the `@pytest.mark.asyncio` decorator is applied automatically.

## Error Testing (Recommended Pattern)

```python
import pytest


def test_invalid_input_raises() -> None:
    """Verify that invalid input raises the expected error."""
    with pytest.raises(ValueError, match="expected error message"):
        process_invalid_data()
```

## Current Test Coverage

**Coverage: 0%** -- No tests exist.

**Untested areas (everything):**
- `main.py`: The sole source file with `main()` function

## Priority Test Targets

When tests are added, prioritize in this order:

1. **Data transformation logic** (Polars operations) -- most likely to have subtle bugs
2. **Pydantic model validation** -- ensure data contracts are enforced
3. **AI agent integration** -- use TestModel to verify prompt/response handling
4. **CLI/entry point** -- basic smoke tests for `main()`

---

*Testing analysis: 2026-03-26*
