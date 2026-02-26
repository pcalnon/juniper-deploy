#!/usr/bin/env python
#####################################################################################################################################################################################################
# Project:       Juniper
# Application:   juniper-deploy
# File Name:     conftest.py
# Author:        Paul Calnon
#
# Date Created:  2026-02-25
# Last Modified: 2026-02-25
#
# License:       MIT License
# Copyright:     Copyright (c) 2024-2026 Paul Calnon
#
# Description:
#    Shared pytest configuration and fixtures for the Juniper integration test
#    suite. Tests in this suite require all three Juniper services to be running
#    (start them with `docker compose up -d`).
#
# Usage:
#    pytest tests/ -v
#    pytest tests/ -v -m health
#
#####################################################################################################################################################################################################

import os

import pytest
import requests

# ---------------------------------------------------------------------------
# Service base URLs (host-side ports exposed by docker-compose.yml)
# Override via environment variables for non-default port configurations.
# ---------------------------------------------------------------------------
DATA_URL = os.environ.get("JUNIPER_TEST_DATA_URL", "http://localhost:8100")
CASCOR_URL = os.environ.get("JUNIPER_TEST_CASCOR_URL", "http://localhost:8200")
CANOPY_URL = os.environ.get("JUNIPER_TEST_CANOPY_URL", "http://localhost:8050")

# URL that juniper-cascor uses internally to reach juniper-data (docker network)
_CASCOR_INTERNAL_DATA_URL = os.environ.get("JUNIPER_TEST_INTERNAL_DATA_URL", "http://juniper-data:8100")

# Default HTTP request timeout in seconds
DEFAULT_TIMEOUT = 10


# ---------------------------------------------------------------------------
# Custom pytest markers
# ---------------------------------------------------------------------------
def pytest_configure(config):
    config.addinivalue_line("markers", "health: health endpoint checks")
    config.addinivalue_line("markers", "data: JuniperData service tests")
    config.addinivalue_line("markers", "full_stack: cross-service integration tests")


# ---------------------------------------------------------------------------
# Session-scoped service URL fixtures
# ---------------------------------------------------------------------------
@pytest.fixture(scope="session")
def data_url() -> str:
    return DATA_URL


@pytest.fixture(scope="session")
def cascor_url() -> str:
    return CASCOR_URL


@pytest.fixture(scope="session")
def canopy_url() -> str:
    return CANOPY_URL


@pytest.fixture(scope="session")
def cascor_internal_data_url() -> str:
    """URL juniper-cascor uses to reach juniper-data over the docker network."""
    return _CASCOR_INTERNAL_DATA_URL


# ---------------------------------------------------------------------------
# Shared HTTP session
# ---------------------------------------------------------------------------
@pytest.fixture(scope="session")
def http() -> requests.Session:
    """Shared requests.Session with JSON content-type and default timeout."""
    session = requests.Session()
    session.headers.update({"Content-Type": "application/json", "Accept": "application/json"})
    yield session
    session.close()


# ---------------------------------------------------------------------------
# Convenience fixture: pre-verify a service is reachable
# ---------------------------------------------------------------------------
def _assert_service_up(url: str, name: str, timeout: int = DEFAULT_TIMEOUT) -> None:
    try:
        resp = requests.get(f"{url}/v1/health", timeout=timeout)
        resp.raise_for_status()
    except Exception as exc:
        pytest.fail(f"{name} is not reachable at {url}: {exc}")


@pytest.fixture(scope="session", autouse=False)
def require_all_services() -> None:
    """Session fixture that skips the suite if any service is not reachable."""
    for url, name in [(DATA_URL, "juniper-data"), (CASCOR_URL, "juniper-cascor"), (CANOPY_URL, "juniper-canopy")]:
        try:
            resp = requests.get(f"{url}/v1/health", timeout=DEFAULT_TIMEOUT)
            resp.raise_for_status()
        except Exception:
            pytest.skip(f"{name} is not reachable at {url} — start services with `docker compose up -d`")
