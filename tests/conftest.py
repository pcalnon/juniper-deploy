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
CASCOR_URL = os.environ.get("JUNIPER_TEST_CASCOR_URL", "http://localhost:8201")
CANOPY_URL = os.environ.get("JUNIPER_TEST_CANOPY_URL", "http://localhost:8050")

# URL that juniper-cascor uses internally to reach juniper-data (docker network)
_CASCOR_INTERNAL_DATA_URL = os.environ.get("JUNIPER_TEST_INTERNAL_DATA_URL", "http://juniper-data:8100")

# API keys for authenticated requests (empty string = no auth)
DATA_API_KEY = os.environ.get("JUNIPER_TEST_DATA_API_KEY", "")
CASCOR_API_KEY = os.environ.get("JUNIPER_TEST_CASCOR_API_KEY", "")
CANOPY_API_KEY = os.environ.get("JUNIPER_TEST_CANOPY_API_KEY", "")

from constants import DEFAULT_TIMEOUT  # noqa: F401 — re-exported for fixtures below


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
def data_api_key() -> str:
    return DATA_API_KEY


@pytest.fixture(scope="session")
def cascor_api_key() -> str:
    return CASCOR_API_KEY


@pytest.fixture(scope="session")
def canopy_api_key() -> str:
    return CANOPY_API_KEY


@pytest.fixture(scope="session")
def http() -> requests.Session:
    """Shared requests.Session with JSON content-type and default timeout.

    When API keys are configured via ``JUNIPER_TEST_*_API_KEY`` environment
    variables, the ``X-API-Key`` header is **not** set globally on the session
    because each service may use a different key.  Instead, use the per-service
    helper fixtures (``data_http``, ``cascor_http``, ``canopy_http``) which
    attach the correct key for the target service.
    """
    session = requests.Session()
    session.headers.update({"Content-Type": "application/json", "Accept": "application/json"})
    yield session
    session.close()


@pytest.fixture(scope="session")
def data_http() -> requests.Session:
    """Session pre-configured with juniper-data API key (if set)."""
    session = requests.Session()
    headers = {"Content-Type": "application/json", "Accept": "application/json"}
    if DATA_API_KEY:
        headers["X-API-Key"] = DATA_API_KEY
    session.headers.update(headers)
    yield session
    session.close()


@pytest.fixture(scope="session")
def cascor_http() -> requests.Session:
    """Session pre-configured with juniper-cascor API key (if set)."""
    session = requests.Session()
    headers = {"Content-Type": "application/json", "Accept": "application/json"}
    if CASCOR_API_KEY:
        headers["X-API-Key"] = CASCOR_API_KEY
    session.headers.update(headers)
    yield session
    session.close()


@pytest.fixture(scope="session")
def canopy_http() -> requests.Session:
    """Session pre-configured with juniper-canopy API key (if set)."""
    session = requests.Session()
    headers = {"Content-Type": "application/json", "Accept": "application/json"}
    if CANOPY_API_KEY:
        headers["X-API-Key"] = CANOPY_API_KEY
    session.headers.update(headers)
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
