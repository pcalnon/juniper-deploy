# Testing Quick Start

## Run juniper-deploy Integration Tests in 5 Minutes

**Version:** 0.1.0
**Status:** Active
**Last Updated:** May 4, 2026
**Project:** Juniper - Docker Compose Orchestration

---

## Table of Contents

- [Prerequisites](#prerequisites)
- [Install Dependencies](#1-install-dependencies)
- [Start Services](#2-start-services)
- [Run Tests](#3-run-tests)
- [Script-Based Tests](#4-script-based-tests)
- [Next Steps](#5-next-steps)

---

## Prerequisites

- **Docker** with Docker Compose v2
- **Python 3.12+** with pip
- **Running Juniper stack** (full or demo profile)

---

## 1. Install Dependencies

```bash
cd juniper-deploy
pip install -r requirements-test.txt
```

This installs the host-side test dependencies:

| Package | Used For |
|---------|----------|
| `pytest` | Test collection, markers, fixtures, and assertions |
| `requests` | HTTP checks against local Juniper services |
| `numpy` | Dataset payload and response validation |
| `PyYAML` | Parsing rendered Helm YAML in chart snapshot tests |

Keep this list aligned with `requirements-test.txt`; CI installs that file before running `pytest tests/ -v --tb=short`.

---

## 2. Start Services

```bash
# Start the full stack
make build && make up

# Wait until all services are healthy
make wait
```

---

## 3. Run Tests

```bash
# All integration tests
pytest tests/ -v

# Health endpoint tests only
pytest tests/ -m health -v

# Data service tests only
pytest tests/ -m data -v

# Full stack integration tests
pytest tests/ -m full_stack -v
```

### With Custom Service URLs

```bash
JUNIPER_TEST_DATA_URL=http://custom-host:8100 pytest tests/ -v
```

### With API Keys

```bash
JUNIPER_TEST_DATA_API_KEY=mykey JUNIPER_TEST_CASCOR_API_KEY=mykey pytest tests/ -v
```

---

## 4. Script-Based Tests

### Demo Profile Test

Full end-to-end test of the demo profile (starts, seeds, trains, verifies dashboard, shuts down):

```bash
bash scripts/test_demo_profile.sh
```

### Enhanced Health Test

Validates health check response format across all services:

```bash
bash scripts/test_health_enhanced.sh
```

---

## 5. Next Steps

- [Reference](../REFERENCE.md#test-configuration) -- test markers, environment variables, test files
- [User Manual](../USER_MANUAL.md#scripts) -- script descriptions
- [Documentation Overview](../DOCUMENTATION_OVERVIEW.md) -- navigation index

---

**Last Updated:** May 4, 2026
**Version:** 0.1.0
**Status:** Active
