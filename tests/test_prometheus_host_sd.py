#!/usr/bin/env python
"""Structural gate for the host-experiment scrape lane (Wave 1.1/1.2).

CLI-launched on-host cascor/recurrence/data experiment runs are scraped by the
dockerized Prometheus through a launcher-owned relay on the monitoring-network
gateway, discovered via ``file_sd_configs`` target files the launcher writes
under ``prometheus/targets/`` (juniper-ml CLI experimentation plan §7; P0.10
evidence 2026-07-30 proved both arms: without the relay the scrape dies with
``connection refused``, with it the targets turn ``up == 1``).

Three structural invariants keep the lane wired:

1. The prometheus service maps ``host.docker.internal`` to the MONITORING
   network's gateway with an EXPLICIT IP — the ``host-gateway`` keyword would
   resolve to the default-bridge gateway (172.17.0.1) and never reach the
   relay. The expected IP is DERIVED here from ``networks.monitoring.ipam``,
   so re-pinning the subnet forces this mapping (and this test) to move with
   it — the same drift discipline as tests/test_compose_metrics_subnet_alignment.py.
2. ``prometheus/prometheus.yml`` carries the ``juniper-host-experiments`` job
   reading ``/etc/prometheus/targets/*.json`` with ``honor_labels: false`` so
   scrape-side run labels (run_id / experiment) always win (R1.1).
3. ``prometheus/targets/`` exists in-repo (.gitkeep), ignores runtime ``*.json``
   files, and is reachable in-container through the existing ``./prometheus``
   mount — no dedicated volume is needed (P0 evidence finding F-3).
"""

import ipaddress
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
COMPOSE_PATH = REPO_ROOT / "docker-compose.yml"
PROMETHEUS_YML = REPO_ROOT / "prometheus" / "prometheus.yml"
TARGETS_DIR = REPO_ROOT / "prometheus" / "targets"

HOST_ALIAS = "host.docker.internal"
JOB_NAME = "juniper-host-experiments"
SD_GLOB = "/etc/prometheus/targets/*.json"


def _load_yaml(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _monitoring_gateway(compose: dict) -> str:
    """First host of the pinned monitoring ipam subnet (Docker's bridge gateway)."""
    ipam_cfg = compose["networks"]["monitoring"]["ipam"]["config"]
    subnet = ipaddress.ip_network(ipam_cfg[0]["subnet"])
    return str(subnet.network_address + 1)


def test_extra_hosts_maps_monitoring_gateway() -> None:
    """prometheus's extra_hosts must pin host.docker.internal to the monitoring gateway IP."""
    compose = _load_yaml(COMPOSE_PATH)
    extra_hosts = compose["services"]["prometheus"].get("extra_hosts") or []
    entries = [e for e in extra_hosts if isinstance(e, str) and e.startswith(f"{HOST_ALIAS}:")]
    assert len(entries) == 1, (
        f"services.prometheus.extra_hosts must carry exactly one `{HOST_ALIAS}:<ip>` entry "
        f"(found {entries!r}). Without it the juniper-host-experiments file_sd targets "
        "cannot resolve and every host-experiment scrape fails."
    )
    expected = _monitoring_gateway(compose)
    actual_ip = entries[0].split(":", 1)[1]
    assert actual_ip == expected, (
        f"extra_hosts maps {HOST_ALIAS} to {actual_ip}, but networks.monitoring.ipam pins "
        f"{expected} as the gateway. The two MUST agree: the experiment launcher's relay "
        "binds the monitoring gateway, and the `host-gateway` keyword is NOT a substitute "
        "(it resolves to the default-bridge gateway — P0.10 control arm: connection refused). "
        "If the monitoring subnet was re-pinned, update the extra_hosts entry to match."
    )
    assert actual_ip != "host-gateway", (
        "extra_hosts must use the explicit monitoring-gateway IP, never the `host-gateway` "
        "keyword (it resolves to the default-bridge gateway, not the monitoring network's)."
    )


def test_host_experiments_job_wired() -> None:
    """prometheus.yml must carry the file_sd juniper-host-experiments job, labels-authoritative."""
    prom = _load_yaml(PROMETHEUS_YML)
    jobs = {j.get("job_name"): j for j in prom.get("scrape_configs", [])}
    assert JOB_NAME in jobs, (
        f"prometheus.yml has no `{JOB_NAME}` scrape job — the host-experiment lane is "
        "unwired and CLI-launched runs are invisible to Grafana (plan §7)."
    )
    job = jobs[JOB_NAME]
    sd = job.get("file_sd_configs") or []
    files = [f for cfg in sd for f in cfg.get("files", [])]
    assert SD_GLOB in files, (
        f"`{JOB_NAME}` must read target files via file_sd_configs from `{SD_GLOB}` "
        f"(found {files!r}); the launcher writes per-run JSON files there."
    )
    assert job.get("honor_labels") is False, (
        f"`{JOB_NAME}` must set `honor_labels: false` (matching every existing job) so the "
        "scrape-side run_id/experiment/service target labels always win — the R1.1-compliant "
        "run-identity mechanism."
    )
    assert job.get("metrics_path") == "/metrics", (
        f"`{JOB_NAME}` must scrape `/metrics` like every other juniper job."
    )


def test_targets_dir_tracked_and_runtime_files_ignored() -> None:
    """prometheus/targets/ ships empty (.gitkeep) and ignores runtime *.json target files."""
    assert (TARGETS_DIR / ".gitkeep").is_file(), (
        "prometheus/targets/.gitkeep is missing — the directory must exist in a fresh clone "
        "or the file_sd glob has nowhere to look and the launcher's writes land in an "
        "untracked ad-hoc directory."
    )
    gitignore = TARGETS_DIR / ".gitignore"
    assert gitignore.is_file() and "*.json" in gitignore.read_text(encoding="utf-8"), (
        "prometheus/targets/.gitignore must ignore `*.json`: per-run target files are "
        "runtime state written and deleted by the experiment launcher and must never be "
        "committed (a stray committed target would resurrect a stale scrape on every boot)."
    )


def test_targets_dir_reachable_via_existing_prometheus_mount() -> None:
    """The existing ./prometheus:/etc/prometheus mount must cover targets/ (no extra volume)."""
    compose = _load_yaml(COMPOSE_PATH)
    volumes = compose["services"]["prometheus"].get("volumes") or []
    assert any(isinstance(v, str) and v.startswith("./prometheus:/etc/prometheus") for v in volumes), (
        "services.prometheus must mount ./prometheus at /etc/prometheus — the "
        f"juniper-host-experiments file_sd glob `{SD_GLOB}` resolves through that mount "
        "(P0 evidence F-3: no dedicated targets volume is needed)."
    )
