#!/usr/bin/env python
"""Snapshot tests for Helm chart probe wiring.

Renders the chart with ``helm template`` and asserts that every Juniper
service Deployment's livenessProbe.httpGet.path and
readinessProbe.httpGet.path point at the R1.2 endpoints
(``/v1/health/live`` and ``/v1/health/ready`` respectively) — never at
the legacy combined ``/v1/health`` no-op endpoint.

Skips when the ``helm`` binary is not available so the test can run on
runners without Helm installed; CI environments with Helm will execute
it as a regression guard.

References:
- juniper-ml notes/code-review/METRICS_MONITORING_R1.2_PROBE_DESIGN_2026-04-27.md
- METRICS-MON seed-02, seed-03
"""

import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

CHART_DIR = Path(__file__).resolve().parent.parent / "k8s" / "helm" / "juniper"
RELEASE_NAME = "juniper-test"

# R1.2 contract: every Juniper service Deployment must point its probes at
# the per-service liveness/readiness endpoints, never at the legacy
# combined /v1/health no-op endpoint.
EXPECTED_LIVENESS_PATH = "/v1/health/live"
EXPECTED_READINESS_PATH = "/v1/health/ready"

# Services rendered by the chart that follow the R1.2 contract. Matched
# by container ``name`` field on the Deployment's pod spec.
JUNIPER_SERVICE_CONTAINER_NAMES = {"juniper-data", "juniper-cascor", "juniper-canopy"}


pytestmark = pytest.mark.skipif(
    shutil.which("helm") is None,
    reason="helm binary not available; skipping chart-render snapshot test",
)


def _render_chart(*, set_values: list[str] | None = None) -> list[dict]:
    """Run ``helm template`` and return the parsed YAML documents.

    ``set_values`` is forwarded to ``helm template --set`` and is used
    by R1.3 worker probe tests to flip ``worker.healthcheck.enabled``
    between renders.
    """
    cmd = ["helm", "template", RELEASE_NAME, str(CHART_DIR)]
    for kv in set_values or ():
        cmd += ["--set", kv]
    result = subprocess.run(cmd, capture_output=True, text=True, check=False)
    assert result.returncode == 0, f"helm template failed:\nstderr={result.stderr}\nstdout={result.stdout[:500]}"
    return [doc for doc in yaml.safe_load_all(result.stdout) if doc]


def _worker_container(docs: list[dict]) -> dict | None:
    """Return the rendered worker container spec, or None if not rendered."""
    for doc in docs:
        if doc.get("kind") != "Deployment":
            continue
        try:
            containers = doc["spec"]["template"]["spec"]["containers"]
        except (KeyError, TypeError):
            continue
        for container in containers:
            if container.get("name") == "juniper-cascor-worker":
                return container
    return None


def _juniper_deployments(docs: list[dict]) -> list[tuple[str, dict]]:
    """Return [(container_name, deployment_doc), ...] for each Juniper Deployment."""
    out = []
    for doc in docs:
        if doc.get("kind") != "Deployment":
            continue
        try:
            containers = doc["spec"]["template"]["spec"]["containers"]
        except (KeyError, TypeError):
            continue
        for container in containers:
            if container.get("name") in JUNIPER_SERVICE_CONTAINER_NAMES:
                out.append((container["name"], doc))
    return out


def test_helm_renders_at_least_three_juniper_deployments():
    """Sanity check: chart must produce a Deployment for each of the three services."""
    docs = _render_chart()
    juniper_deps = _juniper_deployments(docs)
    rendered_names = {name for name, _ in juniper_deps}
    missing = JUNIPER_SERVICE_CONTAINER_NAMES - rendered_names
    assert not missing, f"chart did not render Deployments for {missing}; rendered: {rendered_names}"


@pytest.mark.parametrize("container_name", sorted(JUNIPER_SERVICE_CONTAINER_NAMES))
def test_liveness_probe_path_uses_health_live(container_name: str):
    """R1.2 / seed-03: livenessProbe must point at /v1/health/live, not /v1/health."""
    docs = _render_chart()
    for name, doc in _juniper_deployments(docs):
        if name != container_name:
            continue
        for container in doc["spec"]["template"]["spec"]["containers"]:
            if container.get("name") != container_name:
                continue
            probe_path = container["livenessProbe"]["httpGet"]["path"]
            assert probe_path == EXPECTED_LIVENESS_PATH, (
                f"{container_name} livenessProbe.httpGet.path = {probe_path!r}; "
                f"expected {EXPECTED_LIVENESS_PATH!r} per R1.2 / seed-03 contract"
            )
            return
    pytest.fail(f"no Deployment rendered for container {container_name}")


@pytest.mark.parametrize("container_name", sorted(JUNIPER_SERVICE_CONTAINER_NAMES))
def test_readiness_probe_path_uses_health_ready(container_name: str):
    """R1.2 / seed-02: readinessProbe must point at /v1/health/ready, not /v1/health."""
    docs = _render_chart()
    for name, doc in _juniper_deployments(docs):
        if name != container_name:
            continue
        for container in doc["spec"]["template"]["spec"]["containers"]:
            if container.get("name") != container_name:
                continue
            probe_path = container["readinessProbe"]["httpGet"]["path"]
            assert probe_path == EXPECTED_READINESS_PATH, (
                f"{container_name} readinessProbe.httpGet.path = {probe_path!r}; "
                f"expected {EXPECTED_READINESS_PATH!r} per R1.2 / seed-02 contract"
            )
            return
    pytest.fail(f"no Deployment rendered for container {container_name}")


# ---------------------------------------------------------------------------
# METRICS-MON R1.3 / seed-04: worker probe wiring is gated by a flag. Both
# states must render correctly — flag-off keeps the legacy ``exec`` probe
# (so old worker images keep working), flag-on switches to httpGet against
# the in-process health server shipped in juniper-cascor-worker >= 0.4.0.
# ---------------------------------------------------------------------------


def test_worker_probes_use_exec_when_flag_disabled():
    """Default chart values: worker keeps ``exec: kill -0 1`` legacy probe."""
    docs = _render_chart()
    container = _worker_container(docs)
    assert container is not None, "worker Deployment did not render under default values"
    liveness = container.get("livenessProbe", {})
    readiness = container.get("readinessProbe", {})
    assert "exec" in liveness, f"expected liveness ``exec`` probe when flag disabled; got: {liveness}"
    assert "exec" in readiness, f"expected readiness ``exec`` probe when flag disabled; got: {readiness}"
    assert "httpGet" not in liveness
    assert "httpGet" not in readiness
    # The container must NOT advertise the health port when the flag is off.
    port_names = {p.get("name") for p in container.get("ports") or []}
    assert "health" not in port_names, "worker must not expose ``health`` port when flag disabled"


def test_worker_probes_use_httpget_when_flag_enabled():
    """Flag enabled: worker uses httpGet against /v1/health/{live,ready}."""
    docs = _render_chart(set_values=["worker.healthcheck.enabled=true"])
    container = _worker_container(docs)
    assert container is not None, "worker Deployment did not render with flag enabled"
    liveness = container["livenessProbe"]
    readiness = container["readinessProbe"]
    assert liveness["httpGet"]["path"] == EXPECTED_LIVENESS_PATH, f"worker liveness httpGet.path = {liveness['httpGet']['path']!r}"
    assert readiness["httpGet"]["path"] == EXPECTED_READINESS_PATH, f"worker readiness httpGet.path = {readiness['httpGet']['path']!r}"
    assert liveness["httpGet"]["port"] == "health"
    assert readiness["httpGet"]["port"] == "health"
    # Port must be exposed on the container.
    port_names = {p.get("name") for p in container.get("ports") or []}
    assert "health" in port_names, "worker must expose ``health`` port when flag enabled"


def test_worker_health_env_vars_set_when_flag_enabled():
    """Flag enabled: ``JUNIPER_CASCOR_WORKER_HEALTH_BIND=0.0.0.0`` + ``_PORT=8210``
    injected. CFG-06 (juniper-cascor-worker >= 0.4.0): env-var names migrated
    CASCOR_WORKER_* -> JUNIPER_CASCOR_WORKER_*."""
    docs = _render_chart(set_values=["worker.healthcheck.enabled=true"])
    container = _worker_container(docs)
    assert container is not None
    env = {entry["name"]: entry.get("value") for entry in container.get("env") or [] if "value" in entry}
    assert env.get("JUNIPER_CASCOR_WORKER_HEALTH_BIND") == "0.0.0.0"
    assert env.get("JUNIPER_CASCOR_WORKER_HEALTH_PORT") == "8210"


def test_worker_health_env_vars_absent_when_flag_disabled():
    """Flag disabled: health env vars must not be injected (worker stays
    localhost-only). CFG-06: assert the canonical JUNIPER_CASCOR_WORKER_*
    names are absent."""
    docs = _render_chart()
    container = _worker_container(docs)
    assert container is not None
    env_names = {entry["name"] for entry in container.get("env") or []}
    assert "JUNIPER_CASCOR_WORKER_HEALTH_BIND" not in env_names
    assert "JUNIPER_CASCOR_WORKER_HEALTH_PORT" not in env_names
