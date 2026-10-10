#!/usr/bin/env python
#####################################################################################################################################################################################################
# Project:       Juniper
# Application:   juniper-deploy
# File Name:     conftest.py
# Author:        Paul Calnon
#
# Date Created:  2026-02-25
# Last Modified: 2026-10-08
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
from pathlib import Path

import pytest
import requests

from constants import (  # noqa: F401 — DEFAULT_TIMEOUT is re-exported for fixtures below
    DEFAULT_CANOPY_URL,
    DEFAULT_CASCOR_URL,
    DEFAULT_DATA_URL,
    DEFAULT_INTERNAL_DATA_URL,
    DEFAULT_TIMEOUT,
    ENV_CANOPY_API_KEY,
    ENV_CANOPY_API_KEY_FILE,
    ENV_CANOPY_URL,
    ENV_CASCOR_API_KEY,
    ENV_CASCOR_API_KEY_FILE,
    ENV_CASCOR_URL,
    ENV_DATA_API_KEY,
    ENV_DATA_API_KEY_FILE,
    ENV_DATA_URL,
    ENV_INTERNAL_DATA_URL,
)

# ---------------------------------------------------------------------------
# Service base URLs (host-side ports exposed by docker-compose.yml)
# Override via environment variables for non-default port configurations.
# ---------------------------------------------------------------------------
DATA_URL = os.environ.get(ENV_DATA_URL, DEFAULT_DATA_URL)
CASCOR_URL = os.environ.get(ENV_CASCOR_URL, DEFAULT_CASCOR_URL)
CANOPY_URL = os.environ.get(ENV_CANOPY_URL, DEFAULT_CANOPY_URL)

# URL that juniper-cascor uses internally to reach juniper-data (docker network)
_CASCOR_INTERNAL_DATA_URL = os.environ.get(ENV_INTERNAL_DATA_URL, DEFAULT_INTERNAL_DATA_URL)

def _api_key(env_name: str, file_env_name: str) -> str:
    """Resolve one service's API key: ``env_name``, else the file ``file_env_name`` names, else "".

    The file form is the stack's Docker-secret convention, so the compose ``test-runner`` can
    hand a key over as ``/run/secrets/<name>`` instead of as an environment value. The first
    non-comment line is read, and within it the first comma-separated entry: the
    ``juniper_data_api_keys`` secret is an ACCEPT-LIST, and any one of its keys authenticates.

    An unreadable file resolves to "" rather than raising. Raising here would fail the import
    of this conftest and with it every module in the session, including the ones that need no
    key. Without a key, the first authenticated call answers 401, and the modules that make
    one say which variable to set.
    """
    value = os.environ.get(env_name, "")
    if value:
        return value
    key_file = os.environ.get(file_env_name, "")
    if not key_file:
        return ""
    try:
        text = Path(key_file).read_text(encoding="utf-8")
    except OSError:
        return ""
    for line in text.splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            return line.split(",", 1)[0].strip()
    return ""


# API keys for authenticated requests (empty string = no auth)
DATA_API_KEY = _api_key(ENV_DATA_API_KEY, ENV_DATA_API_KEY_FILE)
CASCOR_API_KEY = _api_key(ENV_CASCOR_API_KEY, ENV_CASCOR_API_KEY_FILE)
CANOPY_API_KEY = _api_key(ENV_CANOPY_API_KEY, ENV_CANOPY_API_KEY_FILE)


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


# ---------------------------------------------------------------------------
# Per-service availability fixtures (session-scoped)
# ---------------------------------------------------------------------------
@pytest.fixture(scope="session")
def require_data() -> None:
    """Skip the entire session if juniper-data is not reachable."""
    _check_service_available(DATA_URL, "juniper-data")


@pytest.fixture(scope="session")
def require_cascor() -> None:
    """Skip the entire session if juniper-cascor is not reachable."""
    _check_service_available(CASCOR_URL, "juniper-cascor")


@pytest.fixture(scope="session")
def require_canopy() -> None:
    """Skip the entire session if juniper-canopy is not reachable."""
    _check_service_available(CANOPY_URL, "juniper-canopy")


@pytest.fixture(scope="session", autouse=False)
def require_all_services(require_data, require_cascor, require_canopy) -> None:
    """Session fixture that skips the suite if any service is not reachable.

    Composes the three per-service availability checks.  Each check is
    session-scoped and cached, so requesting this fixture does not duplicate
    HTTP requests already made by individual ``require_*`` fixtures.
    """
    pass  # All checks happen in the dependency fixtures
