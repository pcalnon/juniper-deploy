# Plan: Fix All Failing Tests in juniper-deploy

**Date**: 2026-03-14
**Author**: Paul Calnon (via Claude Code)

## Context

The juniper-deploy test suite has 42 integration tests across 3 test files, all of which currently fail (29 FAILED, 13 ERROR, 0 warnings). These are integration tests designed to run against live Docker services (juniper-data:8100, juniper-cascor:8201, juniper-canopy:8050). The tests fail because services are not running and there is no skip-gating mechanism wired into the test classes.

A `require_all_services` fixture exists in `conftest.py` that correctly implements `pytest.skip()` when services are unreachable, but it has `autouse=False` and **no test class ever requests it** — it is dead code.

**Goal**: Make the test suite produce 0 failures, 0 errors, 0 warnings when services are unavailable (all tests SKIP), while preserving full functionality when services ARE running (all tests PASS). No existing tests may be deleted, disabled, or commented out.

---

## Root Causes

| # | Root Cause | Impact |
|---|-----------|--------|
| 1 | `require_all_services` fixture exists but is never used by any test class | All 42 tests attempt connections to unavailable services |
| 2 | No per-service availability fixtures exist | Cannot selectively gate tests that only need 1-2 services |
| 3 | Fixture-level ConnectionErrors propagate as ERROR instead of SKIP | 13 tests get ERROR status (8 from `created_dataset`, 5 from `cleanup_cascor`) because their setup fixtures fail before any skip check runs |

---

## Implementation Steps

### Step 1: Add `_check_service_available()` helper to `conftest.py`

Add after existing `_assert_service_up()` (line 151). The existing helper uses `pytest.fail()` semantics — the new one uses `pytest.skip()`:

```python
def _check_service_available(url: str, name: str, timeout: int = DEFAULT_TIMEOUT) -> None:
    """Skip the current test session if the named service is not reachable."""
    try:
        resp = requests.get(f"{url}/v1/health", timeout=timeout)
        resp.raise_for_status()
    except Exception:
        pytest.skip(
            f"{name} is not reachable at {url} — start services with "
            "`docker compose up -d`"
        )
```

### Step 2: Add three per-service session-scoped fixtures to `conftest.py`

```python
@pytest.fixture(scope="session")
def require_data() -> None:
    _check_service_available(DATA_URL, "juniper-data")

@pytest.fixture(scope="session")
def require_cascor() -> None:
    _check_service_available(CASCOR_URL, "juniper-cascor")

@pytest.fixture(scope="session")
def require_canopy() -> None:
    _check_service_available(CANOPY_URL, "juniper-canopy")
```

**Why session-scoped**: Verified via pytest 9.0.1 source code that fixtures are sorted by scope (`session > module > class > function`). This guarantees the skip fires before `created_dataset` (class-scoped) or `cleanup_cascor` (function-scoped autouse), preventing the 13 ERROR cases.

### Step 3: Refactor `require_all_services` to compose from per-service fixtures

Replace the body (lines 154-162) to delegate to the three per-service fixtures:

```python
@pytest.fixture(scope="session", autouse=False)
def require_all_services(require_data, require_cascor, require_canopy) -> None:
    """Session fixture that skips the suite if any service is not reachable."""
    pass  # All checks happen in dependency fixtures
```

### Step 4: Apply `@pytest.mark.usefixtures()` to each test class

No test body or assertion logic changes — only a decorator added per class.

| File | Class | Decorator |
|------|-------|-----------|
| `test_health.py` | `TestJuniperDataHealth` | `@pytest.mark.usefixtures("require_data")` |
| `test_health.py` | `TestJuniperCascorHealth` | `@pytest.mark.usefixtures("require_cascor")` |
| `test_health.py` | `TestJuniperCanopyHealth` | `@pytest.mark.usefixtures("require_canopy")` |
| `test_data_service.py` | `TestGenerators` | `@pytest.mark.usefixtures("require_data")` |
| `test_data_service.py` | `TestDatasetLifecycle` | `@pytest.mark.usefixtures("require_data")` |
| `test_data_service.py` | `TestDatasetStats` | `@pytest.mark.usefixtures("require_data")` |
| `test_full_stack.py` | `TestCascorJuniperDataIntegration` | `@pytest.mark.usefixtures("require_cascor", "require_data")` |
| `test_full_stack.py` | `TestCanopyEndToEnd` | `@pytest.mark.usefixtures("require_canopy")` |
| `test_full_stack.py` | `TestThreeServiceStack` | `@pytest.mark.usefixtures("require_all_services")` |

### Step 5: Create `tests/test_availability.py`

New test module (~90 lines) that verifies the skip-gating mechanism itself. Tests always PASS regardless of service state.

### Step 6: Add `filterwarnings` to `pyproject.toml`

```toml
filterwarnings = [
    "error",
]
```

Promotes all warnings to errors, ensuring zero-warning policy.

---

## File Change Summary

| File | Action | Approx Changes |
|------|--------|---------------|
| `tests/conftest.py` | Modify | +25 lines (helper + 3 fixtures + refactored `require_all_services`) |
| `tests/test_health.py` | Modify | +3 lines (1 decorator per class) |
| `tests/test_data_service.py` | Modify | +3 lines (1 decorator per class) |
| `tests/test_full_stack.py` | Modify | +3 lines (1 decorator per class) |
| `tests/test_availability.py` | Create | ~90 lines (new test module) |
| `pyproject.toml` | Modify | +3 lines (filterwarnings) |

---

## Expected Outcomes

**Services NOT running**: 42 original tests SKIPPED + 9 availability tests PASSED = 0 fail, 0 error, 0 warnings

**Services running**: All tests PASSED = 0 fail, 0 error, 0 warnings

---

## Validation Summary

Three parallel validation agents confirmed all plan assumptions:

1. **Fixture scope ordering** — Confirmed via pytest 9.0.1 source. Session-scoped fixtures execute before class/function-scoped. Skip exceptions abort the fixture chain.
2. **Pytest patterns** — `pytest.skip.Exception` is public API. `match` parameter works. Fixture introspection via `getfixturedefs()` is the recommended approach. `from conftest import` works with `pythonpath = ["tests"]`.
3. **filterwarnings safety** — No dependency warnings found. No interaction with skip fixtures.
