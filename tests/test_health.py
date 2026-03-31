#!/usr/bin/env python
#####################################################################################################################################################################################################
# Project:       Juniper
# Application:   juniper-deploy
# File Name:     test_health.py
# Author:        Paul Calnon
#
# Date Created:  2026-02-25
# Last Modified: 2026-02-25
#
# License:       MIT License
# Copyright:     Copyright (c) 2024-2026 Paul Calnon
#
# Description:
#    Integration tests for standardized health endpoints across all three
#    Juniper services. Verifies:
#      - /v1/health      (liveness probe)
#      - /v1/health/live (liveness alias)
#      - /v1/health/ready (readiness probe)
#
#####################################################################################################################################################################################################

import pytest
import requests

from constants import DEFAULT_TIMEOUT


# ---------------------------------------------------------------------------
# Schema validators — lightweight, no external dependency needed
# ---------------------------------------------------------------------------
def _assert_keys(body: dict, required_keys: set, label: str) -> None:
    """Assert that all required_keys are present in body."""
    missing = required_keys - set(body.keys())
    assert not missing, f"{label}: missing keys {missing} in {list(body.keys())}"


def _assert_cascor_envelope(body: dict) -> dict:
    """Validate CasCor response envelope and return the data field."""
    _assert_keys(body, {"status", "data", "meta"}, "CasCor envelope")
    assert isinstance(body["meta"], dict), "CasCor meta must be dict"
    _assert_keys(body["meta"], {"timestamp", "version"}, "CasCor meta")
    return body["data"]


# ---------------------------------------------------------------------------
# juniper-data health tests
# ---------------------------------------------------------------------------
@pytest.mark.health
@pytest.mark.usefixtures("require_data")
class TestJuniperDataHealth:
    def test_liveness(self, data_url: str, http: requests.Session):
        resp = http.get(f"{data_url}/v1/health", timeout=DEFAULT_TIMEOUT)
        assert resp.status_code == 200
        body = resp.json()
        assert body.get("status") == "ok"
        assert "version" in body

    def test_liveness_alias(self, data_url: str, http: requests.Session):
        resp = http.get(f"{data_url}/v1/health/live", timeout=DEFAULT_TIMEOUT)
        assert resp.status_code == 200
        body = resp.json()
        assert body.get("status") == "alive"

    def test_readiness(self, data_url: str, http: requests.Session):
        resp = http.get(f"{data_url}/v1/health/ready", timeout=DEFAULT_TIMEOUT)
        assert resp.status_code == 200
        body = resp.json()
        assert body.get("status") == "ready"
        assert "version" in body

    def test_liveness_content_type(self, data_url: str, http: requests.Session):
        resp = http.get(f"{data_url}/v1/health", timeout=DEFAULT_TIMEOUT)
        assert "application/json" in resp.headers.get("content-type", "")

    def test_liveness_schema(self, data_url: str, http: requests.Session):
        """Validate that /v1/health returns all expected fields."""
        resp = http.get(f"{data_url}/v1/health", timeout=DEFAULT_TIMEOUT)
        body = resp.json()
        _assert_keys(body, {"status", "version"}, "juniper-data /v1/health")


# ---------------------------------------------------------------------------
# juniper-cascor health tests
# ---------------------------------------------------------------------------
@pytest.mark.health
@pytest.mark.usefixtures("require_cascor")
class TestJuniperCascorHealth:
    def test_liveness(self, cascor_url: str, http: requests.Session):
        resp = http.get(f"{cascor_url}/v1/health", timeout=DEFAULT_TIMEOUT)
        assert resp.status_code == 200
        body = resp.json()
        assert body.get("status") == "ok"
        assert "version" in body

    def test_liveness_alias(self, cascor_url: str, http: requests.Session):
        resp = http.get(f"{cascor_url}/v1/health/live", timeout=DEFAULT_TIMEOUT)
        assert resp.status_code == 200
        body = resp.json()
        assert body.get("status") == "alive"

    def test_readiness(self, cascor_url: str, http: requests.Session):
        resp = http.get(f"{cascor_url}/v1/health/ready", timeout=DEFAULT_TIMEOUT)
        assert resp.status_code == 200
        body = resp.json()
        assert body.get("status") == "ready"

    def test_response_envelope(self, cascor_url: str, http: requests.Session):
        """CasCor health endpoints return flat JSON (no envelope)."""
        resp = http.get(f"{cascor_url}/v1/health", timeout=DEFAULT_TIMEOUT)
        body = resp.json()
        _assert_keys(body, {"status", "version"}, "CasCor /v1/health")

    def test_liveness_schema(self, cascor_url: str, http: requests.Session):
        """Validate CasCor /v1/health returns expected fields."""
        resp = http.get(f"{cascor_url}/v1/health", timeout=DEFAULT_TIMEOUT)
        body = resp.json()
        _assert_keys(body, {"status", "version"}, "CasCor /v1/health")

    def test_readiness_schema(self, cascor_url: str, http: requests.Session):
        """Validate CasCor /v1/health/ready returns expected fields."""
        resp = http.get(f"{cascor_url}/v1/health/ready", timeout=DEFAULT_TIMEOUT)
        body = resp.json()
        _assert_keys(body, {"status", "version", "service", "timestamp"}, "CasCor /v1/health/ready")


# ---------------------------------------------------------------------------
# juniper-canopy health tests
# ---------------------------------------------------------------------------
@pytest.mark.health
@pytest.mark.usefixtures("require_canopy")
class TestJuniperCanopyHealth:
    def test_liveness(self, canopy_url: str, http: requests.Session):
        resp = http.get(f"{canopy_url}/v1/health", timeout=DEFAULT_TIMEOUT)
        assert resp.status_code == 200
        body = resp.json()
        assert body.get("status") == "healthy"
        assert "version" in body

    def test_liveness_backward_compat(self, canopy_url: str, http: requests.Session):
        """Canopy retains /health and /api/health as backward-compatible aliases."""
        for path in ("/health", "/api/health"):
            resp = http.get(f"{canopy_url}{path}", timeout=DEFAULT_TIMEOUT)
            assert resp.status_code == 200, f"Backward-compat alias {path} returned {resp.status_code}"

    def test_liveness_live_alias(self, canopy_url: str, http: requests.Session):
        resp = http.get(f"{canopy_url}/v1/health/live", timeout=DEFAULT_TIMEOUT)
        assert resp.status_code == 200
        body = resp.json()
        assert body.get("status") == "alive"

    def test_readiness(self, canopy_url: str, http: requests.Session):
        resp = http.get(f"{canopy_url}/v1/health/ready", timeout=DEFAULT_TIMEOUT)
        assert resp.status_code == 200
        body = resp.json()
        assert body.get("status") == "ready"
        assert "version" in body

    def test_liveness_schema(self, canopy_url: str, http: requests.Session):
        """Validate that /v1/health returns all expected fields with correct types."""
        resp = http.get(f"{canopy_url}/v1/health", timeout=DEFAULT_TIMEOUT)
        body = resp.json()
        _assert_keys(
            body,
            {"status", "version", "active_connections", "training_active", "demo_mode"},
            "juniper-canopy /v1/health",
        )
        assert isinstance(body["active_connections"], int)
        assert isinstance(body["training_active"], bool)
        assert isinstance(body["demo_mode"], bool)
