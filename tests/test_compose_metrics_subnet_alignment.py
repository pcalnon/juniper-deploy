#!/usr/bin/env python
#####################################################################################################################################################################################################
# Project:       Juniper
# Application:   juniper-deploy
# File Name:     test_compose_metrics_subnet_alignment.py
# Author:        Juniper Automation
#
# Date Created:  2026-07-04
#
# License:       MIT License
# Copyright:     Copyright (c) 2024-2026 Paul Calnon
#
# Description:
#    SEC-F19 / D5 drift check (design: juniper-ml
#    notes/JUNIPER_CANOPY_CONTROL_SURFACE_AUTH_AND_NAT_DESIGN_2026-07-03.md
#    §5 Option C1, §9 testing). Asserts that the STATIC compose network
#    ``ipam.config.subnet`` CIDRs and the ``*_METRICS_TRUSTED_IPS`` CIDRs in
#    ``.env.observability`` AGREE, so the metrics allowlist cannot drift away
#    from the pinned subnets (the 172.23-vs-172.18-21 failure class, audit
#    HO-3). Pure YAML + env parse — no Docker daemon required (mirrors the
#    repo's other compose-lint tests, e.g. test_compose_security_config.py).
#
#    The invariant, computed from the compose file (never hard-coded, so it
#    stays true as the topology evolves): for each metrics target, the set of
#    CIDRs in its allowlist == the set of pinned subnets of the networks that
#    BOTH the target AND Prometheus attach to; loopback (127.0.0.1, ::1) is
#    preserved; every declared network carries a unique static subnet.
#
#####################################################################################################################################################################################################

from __future__ import annotations

import ipaddress
import json
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
COMPOSE_PATH = REPO_ROOT / "docker-compose.yml"
ENV_OBS_PATH = REPO_ROOT / ".env.observability"
PROMETHEUS_PATHS = (
    REPO_ROOT / "prometheus" / "prometheus.yml",
    REPO_ROOT / "prometheus" / "prometheus.demo.yml",
)

# The four networks declared in the compose `networks:` block. Pinning them is
# the whole point of D5, so their absence is itself a drift.
EXPECTED_NETWORKS = ("backend", "data", "frontend", "monitoring")

# Metrics-scraping target service -> its allowlist env var. These are the
# MetricsAuthMiddleware-gated services `.env.observability` widens.
TARGETS = {
    "juniper-data": "JUNIPER_DATA_METRICS_TRUSTED_IPS",
    "juniper-cascor": "JUNIPER_CASCOR_METRICS_TRUSTED_IPS",
    "juniper-recurrence": "JUNIPER_RECURRENCE_METRICS_TRUSTED_IPS",
    "juniper-canopy": "JUNIPER_CANOPY_METRICS_TRUSTED_IPS",
}
METRICS_ENABLED_VARS = {
    "juniper-data": "JUNIPER_DATA_METRICS_ENABLED",
    "juniper-cascor": "JUNIPER_CASCOR_METRICS_ENABLED",
    "juniper-recurrence": "JUNIPER_RECURRENCE_METRICS_ENABLED",
    "juniper-canopy": "CANOPY_METRICS_ENABLED",
}
SCRAPER = "prometheus"
LOOPBACK = {ipaddress.ip_address("127.0.0.1"), ipaddress.ip_address("::1")}


def _load_compose() -> dict:
    return yaml.safe_load(COMPOSE_PATH.read_text(encoding="utf-8"))


def _network_subnets(compose: dict) -> dict[str, ipaddress._BaseNetwork]:
    """Map each declared network -> its single static ipam.config.subnet.

    A network with no ipam/subnet is dynamic IPAM (the pre-D5 state) and is
    omitted here, so the caller's completeness assertion catches it.
    """
    out: dict[str, ipaddress._BaseNetwork] = {}
    networks = compose.get("networks") or {}
    for name, spec in networks.items():
        spec = spec or {}
        configs = ((spec.get("ipam") or {}).get("config")) or []
        subnets = [c["subnet"] for c in configs if isinstance(c, dict) and "subnet" in c]
        if len(subnets) == 1:
            out[name] = ipaddress.ip_network(subnets[0], strict=False)
        elif len(subnets) > 1:
            raise AssertionError(f"network `{name}` pins {len(subnets)} subnets; D5 expects exactly one")
    return out


def _service_networks(compose: dict, service: str) -> set[str]:
    """Return the set of network names a service attaches to (list or dict form)."""
    svc = compose["services"][service]
    nets = svc.get("networks")
    if nets is None:
        return set()
    if isinstance(nets, dict):  # long form: `networks: {backend: {...}}`
        return set(nets.keys())
    return set(nets)  # short form: `networks: [backend, data]`


def _parse_env_file(path: Path) -> dict[str, str]:
    env: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        env[key.strip()] = value.strip()
    return env


def _split_allowlist(value: str) -> tuple[set, set]:
    """Parse a JSON allowlist into (CIDR networks, bare IP addresses)."""
    entries = json.loads(value)
    assert isinstance(entries, list), f"allowlist is not a JSON list: {value!r}"
    cidrs = {ipaddress.ip_network(e, strict=False) for e in entries if "/" in e}
    addrs = {ipaddress.ip_address(e) for e in entries if "/" not in e}
    return cidrs, addrs


def _normalize_scrape_service(target: str) -> str:
    """Return compose service name from a Prometheus static target."""
    host, _, _port = target.partition(":")
    if host.endswith("-demo"):
        return host.removesuffix("-demo")
    return host


def _prometheus_app_targets() -> set[str]:
    """Derive Juniper app scrape targets from full and demo Prometheus configs."""
    targets: set[str] = set()
    for path in PROMETHEUS_PATHS:
        config = yaml.safe_load(path.read_text(encoding="utf-8"))
        for scrape in config.get("scrape_configs", []):
            for static_config in scrape.get("static_configs", []):
                for target in static_config.get("targets", []):
                    service = _normalize_scrape_service(target)
                    if service.startswith("juniper-"):
                        targets.add(service)
    return targets


def test_target_contract_covers_every_prometheus_app_scrape() -> None:
    """Adding a Prometheus app target must update this allowlist-alignment contract."""
    assert _prometheus_app_targets() == set(TARGETS), (
        "TARGETS must match the Juniper app services scraped by prometheus.yml "
        "and prometheus.demo.yml so no metrics endpoint is left out of the "
        "subnet/allowlist drift gate."
    )


def test_every_network_pins_a_unique_static_subnet() -> None:
    """All four compose networks must carry a static ipam.config.subnet (no dynamic IPAM)."""
    compose = _load_compose()
    subnets = _network_subnets(compose)
    for name in EXPECTED_NETWORKS:
        assert name in subnets, (
            f"network `{name}` has no static ipam.config.subnet — SEC-F19/D5 requires a pinned "
            f"subnet so Prometheus's scrape source IP is deterministic (design §5 C1)."
        )
    pinned = [subnets[n] for n in EXPECTED_NETWORKS]
    assert len(set(pinned)) == len(pinned), f"pinned subnets are not unique: {pinned}"


def test_allowlist_cidrs_equal_shared_pinned_subnets() -> None:
    """Each target's allowlist CIDRs == the pinned subnets it shares with Prometheus.

    This is the drift gate: if someone repins a network subnet without updating
    `.env.observability` (or vice versa), the sets diverge and this fails.
    """
    compose = _load_compose()
    subnets = _network_subnets(compose)
    env = _parse_env_file(ENV_OBS_PATH)
    scraper_nets = _service_networks(compose, SCRAPER)
    assert scraper_nets, f"`{SCRAPER}` has no networks — cannot derive scrape reachability"

    for service, var in TARGETS.items():
        target_nets = _service_networks(compose, service)
        shared = target_nets & scraper_nets
        assert shared, f"`{service}` shares no network with `{SCRAPER}` — Prometheus cannot scrape it"
        expected_cidrs = {subnets[n] for n in shared}

        assert var in env, f"`.env.observability` must set `{var}` (SEC-F19/D5)"
        allow_cidrs, allow_addrs = _split_allowlist(env[var])

        assert allow_cidrs == expected_cidrs, (
            f"DRIFT: `{var}` CIDRs {sorted(map(str, allow_cidrs))} != the pinned subnets of the "
            f"networks `{service}` shares with `{SCRAPER}` {sorted(shared)} -> "
            f"{sorted(map(str, expected_cidrs))}. The compose ipam.config.subnet values and the "
            f".env.observability allowlist must AGREE (design §5 C1 / §9)."
        )
        assert LOOPBACK <= allow_addrs, (
            f"`{var}` must preserve loopback {sorted(map(str, LOOPBACK))} for host-local scrapes; "
            f"MetricsAuthMiddleware default is loopback-only."
        )


def test_env_observability_enables_metrics_for_all_scraped_targets() -> None:
    """Every Prometheus-scraped app target must have metrics enabled in the env file.

    `make monitor` and `make obs-demo` load `.env.observability`; omitting any
    target's flag leaves that service scraped but serving no `/metrics` endpoint.
    """
    env = _parse_env_file(ENV_OBS_PATH)
    for service, var in METRICS_ENABLED_VARS.items():
        assert env.get(var) == "true", (
            f"`.env.observability` must set `{var}=true` because Prometheus scrapes "
            f"`{service}` under the observability profile."
        )


def test_monitoring_subnet_is_absent_from_every_allowlist() -> None:
    """monitoring (172.31) hosts prometheus/grafana/alertmanager only — no scrape
    target sits there, so its subnet must NOT leak into any allowlist (keeps the
    allowlist "exactly what is needed", not "every subnet")."""
    compose = _load_compose()
    subnets = _network_subnets(compose)
    monitoring = subnets["monitoring"]
    # Sanity: no metrics target attaches to monitoring.
    for service in TARGETS:
        assert "monitoring" not in _service_networks(compose, service), (
            f"`{service}` unexpectedly attaches to `monitoring`; re-derive the allowlist scope"
        )
    env = _parse_env_file(ENV_OBS_PATH)
    for var in TARGETS.values():
        allow_cidrs, _ = _split_allowlist(env[var])
        assert monitoring not in allow_cidrs, (
            f"`{var}` includes the monitoring subnet {monitoring}, but no scrape target lives on "
            f"monitoring — the allowlist must stay scoped to shared-with-Prometheus networks."
        )


def _service_environment(compose: dict, service: str) -> dict[str, str]:
    """A service's `environment:` block as a dict, accepting either compose form."""
    env = compose["services"][service].get("environment") or {}
    if isinstance(env, list):  # ["KEY=value", ...]
        out: dict[str, str] = {}
        for item in env:
            key, _, value = str(item).partition("=")
            out[key.strip()] = value.strip()
        return out
    return {str(k): str(v) for k, v in env.items()}


def test_compose_forwards_every_metrics_var_to_its_service() -> None:
    """Setting a metrics var in `.env.observability` must actually reach the container.

    **This pins an invariant that currently holds; it is not fixing a live defect.**
    Every scraped target already declares both vars. It is here because the invariant is
    load-bearing and nothing else in this file checks it: `docker-compose.yml` declares no
    `env_file`, so a service receives only the variables its own `environment:` block
    names. A target that stopped naming them would keep passing every other check here —
    they all read the env file and the CIDRs, and none asks whether the service can see
    them — while its `/metrics` silently 404ed under a Prometheus job that goes on
    scraping it.

    That gap is not hypothetical in this repo: `juniper-canopy-dev` was missing both vars
    (added in the same change), and it survived precisely because it is not in `TARGETS`
    and so nothing looked.
    """
    compose = _load_compose()
    for service, allow_var in TARGETS.items():
        env = _service_environment(compose, service)

        assert allow_var in env, f"`{service}` never receives `{allow_var}`: compose uses no `env_file`, so a variable absent from its `environment:` block cannot reach the container."

        enabled_keys = [k for k in env if k.endswith("_METRICS_ENABLED")]
        assert enabled_keys, f"`{service}` declares no *_METRICS_ENABLED variable, so `/metrics` can never be switched on for it."

        # The value must interpolate from the name `.env.observability` actually ships,
        # or the operator-facing switch is wired to nothing.
        env_file_var = METRICS_ENABLED_VARS[service]
        wiring = " ".join(env[k] for k in enabled_keys)
        assert env_file_var in wiring, f"`{service}` declares {enabled_keys} but none reads `${{{env_file_var}}}`, the name `.env.observability` sets — the switch is wired to a variable nobody sets."
