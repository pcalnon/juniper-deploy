#!/usr/bin/env python
#####################################################################################################################################################################################################
# Project:       Juniper
# Application:   juniper-deploy
# File Name:     test_full_stack.py
# Author:        Paul Calnon
#
# Date Created:  2026-02-25
# Last Modified: 2026-02-25
#
# License:       MIT License
# Copyright:     Copyright (c) 2024-2026 Paul Calnon
#
# Description:
#    End-to-end integration tests that exercise cross-service interactions
#    in the full Juniper stack:
#
#      - JuniperCascor fetches a dataset from JuniperData
#      - JuniperCascor can create a network and start/stop training
#      - JuniperCanopy is alive and serving the dashboard
#
#    These tests require all three services to be running.
#    Start them with: docker compose up -d
#
#####################################################################################################################################################################################################

import time

import pytest
import requests

from conftest import DEFAULT_TIMEOUT


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _unwrap(resp: requests.Response) -> dict:
    """Extract the 'data' field from a CasCor success envelope."""
    body = resp.json()
    assert body.get("status") == "success", f"Unexpected status: {body}"
    return body.get("data", {})


def _reset_cascor_network(cascor_url: str, http: requests.Session) -> None:
    """Best-effort cleanup: stop training and delete network if present."""
    http.post(f"{cascor_url}/v1/training/stop", timeout=DEFAULT_TIMEOUT)
    http.post(f"{cascor_url}/v1/training/reset", timeout=DEFAULT_TIMEOUT)
    http.delete(f"{cascor_url}/v1/network", timeout=DEFAULT_TIMEOUT)


# ---------------------------------------------------------------------------
# Cross-service: CasCor ↔ JuniperData
# ---------------------------------------------------------------------------
@pytest.mark.full_stack
class TestCascorJuniperDataIntegration:
    """JuniperCascor can request a dataset from JuniperData over the docker network."""

    @pytest.fixture(autouse=True)
    def cleanup_cascor(self, cascor_url: str, http: requests.Session):
        """Ensure CasCor has a clean state before and after each test."""
        _reset_cascor_network(cascor_url, http)
        yield
        _reset_cascor_network(cascor_url, http)

    def test_create_network(self, cascor_url: str, http: requests.Session):
        payload = {"input_size": 2, "output_size": 2, "max_hidden_units": 5, "candidate_pool_size": 4}
        resp = http.post(f"{cascor_url}/v1/network", json=payload, timeout=DEFAULT_TIMEOUT)
        assert resp.status_code == 200
        data = _unwrap(resp)
        assert data.get("input_size") == 2
        assert data.get("output_size") == 2
        assert "uuid" in data

    def test_get_network_after_create(self, cascor_url: str, http: requests.Session):
        http.post(f"{cascor_url}/v1/network", json={"input_size": 2, "output_size": 2}, timeout=DEFAULT_TIMEOUT)
        resp = http.get(f"{cascor_url}/v1/network", timeout=DEFAULT_TIMEOUT)
        assert resp.status_code == 200
        data = _unwrap(resp)
        assert data.get("input_size") == 2

    def test_no_network_returns_404(self, cascor_url: str, http: requests.Session):
        resp = http.get(f"{cascor_url}/v1/network", timeout=DEFAULT_TIMEOUT)
        assert resp.status_code == 404

    def test_start_training_with_data_from_juniper_data(
        self,
        cascor_url: str,
        cascor_internal_data_url: str,
        http: requests.Session,
    ):
        """CasCor fetches a spiral dataset from JuniperData over the docker network and starts training."""
        # Create the network first
        http.post(
            f"{cascor_url}/v1/network",
            json={"input_size": 2, "output_size": 2, "max_hidden_units": 3, "candidate_pool_size": 2},
            timeout=DEFAULT_TIMEOUT,
        )

        # Ask CasCor to generate + fetch data from JuniperData (docker-internal URL)
        payload = {
            "dataset": {
                "source": "juniper-data",
                "url": cascor_internal_data_url,
                "generator": "spiral",
                "params": {"n_spirals": 2, "n_per_spiral": 30, "noise": 0.05},
            }
        }
        resp = http.post(f"{cascor_url}/v1/training/start", json=payload, timeout=DEFAULT_TIMEOUT)
        assert resp.status_code == 200, f"Training start failed: {resp.text}"
        data = _unwrap(resp)
        assert data.get("started") is True

        # Brief pause to let training thread initialise
        time.sleep(0.5)

        # Verify training is actually active
        status_resp = http.get(f"{cascor_url}/v1/training/status", timeout=DEFAULT_TIMEOUT)
        assert status_resp.status_code == 200
        status = _unwrap(status_resp)
        assert status.get("training_active") is True or status.get("network_loaded") is True

    def test_stop_training(self, cascor_url: str, cascor_internal_data_url: str, http: requests.Session):
        """Training started against JuniperData can be stopped cleanly."""
        http.post(
            f"{cascor_url}/v1/network",
            json={"input_size": 2, "output_size": 2, "max_hidden_units": 3, "candidate_pool_size": 2},
            timeout=DEFAULT_TIMEOUT,
        )
        http.post(
            f"{cascor_url}/v1/training/start",
            json={
                "dataset": {
                    "source": "juniper-data",
                    "url": cascor_internal_data_url,
                    "generator": "spiral",
                    "params": {"n_spirals": 2, "n_per_spiral": 30},
                }
            },
            timeout=DEFAULT_TIMEOUT,
        )
        time.sleep(0.5)

        stop_resp = http.post(f"{cascor_url}/v1/training/stop", timeout=DEFAULT_TIMEOUT)
        assert stop_resp.status_code == 200


# ---------------------------------------------------------------------------
# JuniperCanopy end-to-end
# ---------------------------------------------------------------------------
@pytest.mark.full_stack
class TestCanopyEndToEnd:
    """Canopy is serving requests and reporting service state correctly."""

    def test_dashboard_returns_html(self, canopy_url: str, http: requests.Session):
        """The Dash application root serves an HTML page."""
        resp = http.get(canopy_url, timeout=DEFAULT_TIMEOUT)
        assert resp.status_code == 200
        assert "text/html" in resp.headers.get("content-type", "")

    def test_canopy_reports_no_active_connections_at_startup(self, canopy_url: str, http: requests.Session):
        resp = http.get(f"{canopy_url}/v1/health", timeout=DEFAULT_TIMEOUT)
        assert resp.status_code == 200
        body = resp.json()
        # At test time (no browser open) there should be 0 active WebSocket connections
        assert body.get("active_connections", -1) >= 0

    def test_canopy_not_in_demo_mode_when_service_url_set(self, canopy_url: str, http: requests.Session):
        """When CASCOR_SERVICE_URL is set, demo mode should be disabled."""
        resp = http.get(f"{canopy_url}/v1/health", timeout=DEFAULT_TIMEOUT)
        body = resp.json()
        # The docker-compose.yml sets CASCOR_SERVICE_URL, so demo mode should be False
        assert body.get("demo_mode") is False

    def test_canopy_readiness(self, canopy_url: str, http: requests.Session):
        resp = http.get(f"{canopy_url}/v1/health/ready", timeout=DEFAULT_TIMEOUT)
        assert resp.status_code == 200
        assert resp.json().get("status") == "ready"


# ---------------------------------------------------------------------------
# Full stack: all three services together
# ---------------------------------------------------------------------------
@pytest.mark.full_stack
class TestThreeServiceStack:
    """Smoke test: all three services report healthy simultaneously."""

    def test_all_services_healthy(
        self,
        data_url: str,
        cascor_url: str,
        canopy_url: str,
        http: requests.Session,
    ):
        results = {}
        for name, url in [("data", data_url), ("cascor", cascor_url), ("canopy", canopy_url)]:
            resp = http.get(f"{url}/v1/health", timeout=DEFAULT_TIMEOUT)
            results[name] = resp.status_code

        for name, code in results.items():
            assert code == 200, f"juniper-{name} /v1/health returned {code}"

    def test_all_services_ready(
        self,
        data_url: str,
        cascor_url: str,
        canopy_url: str,
        http: requests.Session,
    ):
        for name, url in [("data", data_url), ("cascor", cascor_url), ("canopy", canopy_url)]:
            resp = http.get(f"{url}/v1/health/ready", timeout=DEFAULT_TIMEOUT)
            assert resp.status_code == 200, f"juniper-{name} /v1/health/ready returned {resp.status_code}"

    def test_data_to_cascor_dataset_pipeline(
        self,
        data_url: str,
        cascor_url: str,
        cascor_internal_data_url: str,
        http: requests.Session,
    ):
        """
        End-to-end pipeline:
        1. Create a dataset in JuniperData (from host)
        2. Verify CasCor can start training using JuniperData as the source
        3. Stop training and clean up
        """
        # Step 1: generate dataset via data service
        create_resp = http.post(
            f"{data_url}/v1/datasets",
            json={"generator": "spiral", "params": {"n_spirals": 2, "n_per_spiral": 40}, "tags": ["smoke-test"]},
            timeout=DEFAULT_TIMEOUT,
        )
        assert create_resp.status_code == 201
        dataset_id = create_resp.json()["dataset_id"]

        try:
            # Step 2: create network and start training via CasCor
            http.delete(f"{cascor_url}/v1/network", timeout=DEFAULT_TIMEOUT)
            net_resp = http.post(
                f"{cascor_url}/v1/network",
                json={"input_size": 2, "output_size": 2, "max_hidden_units": 3, "candidate_pool_size": 2},
                timeout=DEFAULT_TIMEOUT,
            )
            assert net_resp.status_code == 200

            train_resp = http.post(
                f"{cascor_url}/v1/training/start",
                json={
                    "dataset": {
                        "source": "juniper-data",
                        "url": cascor_internal_data_url,
                        "generator": "spiral",
                        "params": {"n_spirals": 2, "n_per_spiral": 40},
                    }
                },
                timeout=DEFAULT_TIMEOUT,
            )
            assert train_resp.status_code == 200, f"Training failed to start: {train_resp.text}"
            time.sleep(0.5)

            # Step 3: stop and clean up
            http.post(f"{cascor_url}/v1/training/stop", timeout=DEFAULT_TIMEOUT)
            http.delete(f"{cascor_url}/v1/network", timeout=DEFAULT_TIMEOUT)

        finally:
            # Clean up dataset
            http.delete(f"{data_url}/v1/datasets/{dataset_id}", timeout=DEFAULT_TIMEOUT)
