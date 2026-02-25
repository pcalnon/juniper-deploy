#!/usr/bin/env python
#####################################################################################################################################################################################################
# Project:       Juniper
# Application:   juniper-deploy
# File Name:     test_data_service.py
# Author:        Paul Calnon
#
# Date Created:  2026-02-25
# Last Modified: 2026-02-25
#
# License:       MIT License
# Copyright:     Copyright (c) 2024-2026 Paul Calnon
#
# Description:
#    Integration tests for the JuniperData dataset generation service.
#    Tests dataset creation, retrieval, artifact download, and cleanup.
#
#####################################################################################################################################################################################################

import io

import numpy as np
import pytest
import requests

from conftest import DEFAULT_TIMEOUT


@pytest.mark.data
class TestGenerators:
    def test_list_generators(self, data_url: str, http: requests.Session):
        resp = http.get(f"{data_url}/v1/generators", timeout=DEFAULT_TIMEOUT)
        assert resp.status_code == 200
        generators = resp.json()
        assert isinstance(generators, list)
        assert len(generators) > 0

    def test_spiral_generator_present(self, data_url: str, http: requests.Session):
        resp = http.get(f"{data_url}/v1/generators", timeout=DEFAULT_TIMEOUT)
        names = [g["name"] for g in resp.json()]
        assert "spiral" in names

    def test_generator_has_schema(self, data_url: str, http: requests.Session):
        resp = http.get(f"{data_url}/v1/generators/spiral/schema", timeout=DEFAULT_TIMEOUT)
        assert resp.status_code == 200
        schema = resp.json()
        assert schema.get("type") == "object"
        assert "properties" in schema

    def test_unknown_generator_schema_returns_404(self, data_url: str, http: requests.Session):
        resp = http.get(f"{data_url}/v1/generators/nonexistent_generator_xyz/schema", timeout=DEFAULT_TIMEOUT)
        assert resp.status_code == 404


@pytest.mark.data
class TestDatasetLifecycle:
    """Create → read → download → delete a spiral dataset."""

    @pytest.fixture(scope="class")
    def created_dataset(self, data_url: str, http: requests.Session):
        """Create a spiral dataset, yield its metadata, then clean up."""
        payload = {
            "generator": "spiral",
            "params": {"n_spirals": 2, "n_per_spiral": 50, "noise": 0.05},
            "persist": True,
            "tags": ["integration-test"],
        }
        resp = http.post(f"{data_url}/v1/datasets", json=payload, timeout=DEFAULT_TIMEOUT)
        assert resp.status_code == 201, f"Dataset creation failed: {resp.text}"
        data = resp.json()
        yield data
        # Cleanup: delete the dataset after the test class finishes
        dataset_id = data.get("dataset_id")
        if dataset_id:
            http.delete(f"{data_url}/v1/datasets/{dataset_id}", timeout=DEFAULT_TIMEOUT)

    def test_create_returns_dataset_id(self, created_dataset: dict):
        assert "dataset_id" in created_dataset
        assert isinstance(created_dataset["dataset_id"], str)
        assert len(created_dataset["dataset_id"]) > 0

    def test_create_returns_artifact_url(self, created_dataset: dict):
        assert "artifact_url" in created_dataset
        assert "/artifact" in created_dataset["artifact_url"]

    def test_create_returns_metadata(self, created_dataset: dict):
        meta = created_dataset.get("meta", {})
        assert meta.get("generator") == "spiral"
        assert meta.get("n_samples", 0) > 0
        assert meta.get("n_features", 0) == 2
        assert meta.get("n_classes", 0) == 2

    def test_get_metadata(self, data_url: str, http: requests.Session, created_dataset: dict):
        dataset_id = created_dataset["dataset_id"]
        resp = http.get(f"{data_url}/v1/datasets/{dataset_id}", timeout=DEFAULT_TIMEOUT)
        assert resp.status_code == 200
        meta = resp.json()
        assert meta["dataset_id"] == dataset_id
        assert meta["generator"] == "spiral"
        assert "integration-test" in meta.get("tags", [])

    def test_list_datasets_includes_created(self, data_url: str, http: requests.Session, created_dataset: dict):
        dataset_id = created_dataset["dataset_id"]
        resp = http.get(f"{data_url}/v1/datasets", timeout=DEFAULT_TIMEOUT)
        assert resp.status_code == 200
        ids = resp.json()
        assert dataset_id in ids

    def test_download_artifact_is_npz(self, data_url: str, http: requests.Session, created_dataset: dict):
        dataset_id = created_dataset["dataset_id"]
        resp = http.get(f"{data_url}/v1/datasets/{dataset_id}/artifact", timeout=DEFAULT_TIMEOUT)
        assert resp.status_code == 200
        # Verify it's a valid NPZ archive
        npz = np.load(io.BytesIO(resp.content))
        for key in ("X_train", "y_train", "X_test", "y_test"):
            assert key in npz, f"Expected key '{key}' missing from NPZ archive"

    def test_artifact_shapes_match_metadata(self, data_url: str, http: requests.Session, created_dataset: dict):
        dataset_id = created_dataset["dataset_id"]
        meta = created_dataset.get("meta", {})
        resp = http.get(f"{data_url}/v1/datasets/{dataset_id}/artifact", timeout=DEFAULT_TIMEOUT)
        npz = np.load(io.BytesIO(resp.content))
        n_train = meta.get("n_train", 0)
        n_test = meta.get("n_test", 0)
        assert npz["X_train"].shape[0] == n_train
        assert npz["X_test"].shape[0] == n_test
        assert npz["X_train"].shape[1] == 2  # spiral has 2 features
        assert npz["y_train"].dtype == np.float32

    def test_artifact_dtype_is_float32(self, data_url: str, http: requests.Session, created_dataset: dict):
        dataset_id = created_dataset["dataset_id"]
        resp = http.get(f"{data_url}/v1/datasets/{dataset_id}/artifact", timeout=DEFAULT_TIMEOUT)
        npz = np.load(io.BytesIO(resp.content))
        for key in ("X_train", "y_train", "X_test", "y_test"):
            assert npz[key].dtype == np.float32, f"{key} dtype is {npz[key].dtype}, expected float32"

    def test_get_nonexistent_dataset_returns_404(self, data_url: str, http: requests.Session):
        resp = http.get(f"{data_url}/v1/datasets/nonexistent_id_zzz", timeout=DEFAULT_TIMEOUT)
        assert resp.status_code == 404


@pytest.mark.data
class TestDatasetStats:
    def test_stats_endpoint(self, data_url: str, http: requests.Session):
        resp = http.get(f"{data_url}/v1/datasets/stats", timeout=DEFAULT_TIMEOUT)
        assert resp.status_code == 200
        stats = resp.json()
        assert "total_datasets" in stats
        assert isinstance(stats["total_datasets"], int)
