# Fix Plan: conftest Import Errors in juniper-deploy Tests

**Date**: 2026-03-13
**Author**: Claude Code
**Status**: Completed

---

## Problem Statement

All three test files in `tests/` fail to collect with:

```
ModuleNotFoundError: No module named 'conftest'
```

Caused by `from conftest import DEFAULT_TIMEOUT` at module level in:
- `tests/test_data_service.py` (line 26)
- `tests/test_full_stack.py` (line 32)
- `tests/test_health.py` (line 26)

## Root Cause

`conftest.py` is a **pytest-special module**: pytest auto-discovers and loads it for fixtures and hooks, but it is **not placed on `sys.path`** and therefore cannot be imported as a regular Python module via `from conftest import ...`.

This pattern may have worked under older pytest import modes (`prepend`, which added the test directory to `sys.path`), but fails under pytest 9.x with default settings, especially when the test directory contains an `__init__.py` (making it a package, which triggers different import semantics).

## Secondary Issues

1. **No `pyproject.toml`**: The project has no centralized pytest configuration file. Markers are registered programmatically in `conftest.py` via `pytest_configure()`, which works but is less conventional than declaring them in config.

2. **No `pythonpath` configuration**: Without `pythonpath` in pytest config, helper modules within `tests/` are not importable by test files under modern pytest import modes.

## Fix Plan

### Step 1: Create `tests/constants.py`

Extract the shared `DEFAULT_TIMEOUT` constant into a new, regular Python module that can be imported normally.

**New file**: `tests/constants.py`
- Move `DEFAULT_TIMEOUT = 10` here
- Follow the project's standard file header format

### Step 2: Create `pyproject.toml`

Add a minimal `pyproject.toml` with `[tool.pytest.ini_options]`:

```toml
[tool.pytest.ini_options]
testpaths = ["tests"]
pythonpath = ["tests"]
markers = [
    "health: health endpoint checks",
    "data: JuniperData service tests",
    "full_stack: cross-service integration tests",
]
```

- `pythonpath = ["tests"]` ensures modules in `tests/` (like `constants.py`) are importable
- `markers` declaration replaces the programmatic `pytest_configure()` hook in conftest.py

### Step 3: Update `tests/conftest.py`

- Import `DEFAULT_TIMEOUT` from `constants` instead of defining it inline
- Remove the `pytest_configure()` hook (markers now declared in `pyproject.toml`)

### Step 4: Update test file imports

In all three test files, change:
```python
from conftest import DEFAULT_TIMEOUT
```
to:
```python
from constants import DEFAULT_TIMEOUT
```

### Step 5: Validate

Run `pytest --collect-only` to verify all tests are collected without import errors. This does not require running services — it only verifies that Python can import and parse all test modules.

## Files Modified

| File | Change |
|------|--------|
| `tests/constants.py` | **New** — shared test constants |
| `pyproject.toml` | **New** — pytest configuration |
| `tests/conftest.py` | Import from `constants`, remove `pytest_configure()` |
| `tests/test_data_service.py` | Update import line |
| `tests/test_full_stack.py` | Update import line |
| `tests/test_health.py` | Update import line |

## Risk Assessment

- **Low risk**: Changes are limited to import paths and configuration
- **No behavioral changes**: All test logic, fixtures, and assertions remain identical
- **Backward compatible**: `pyproject.toml` is additive; existing `Makefile` targets continue to work
- **Verifiable without services**: `pytest --collect-only` confirms collection success
