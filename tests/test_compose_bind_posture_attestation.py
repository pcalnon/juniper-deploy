#!/usr/bin/env python
#####################################################################################################################################################################################################
# Project:       Juniper
# Application:   juniper-deploy
# File Name:     test_compose_bind_posture_attestation.py
# Author:        Juniper Automation
#
# Date Created:  2026-07-06
#
# License:       MIT License
# Copyright:     Copyright (c) 2024-2026 Paul Calnon
#
# Description:
#    Offline lint + behavioural gate for the two-flag bind attestation
#    (deployment trust contract notes/DEPLOYMENT_TRUST_CONTRACT_2026-07-04.md
#    §3/§5, design D2). Mirrors the repo's other compose-lint tests (pure
#    YAML/JSON parse, no Docker daemon required — e.g.
#    test_compose_metrics_subnet_alignment.py).
#
#    The canonical two-flag spec (identical across canopy / cascor / deploy):
#      * JUNIPER_<SVC>_LOOPBACK_PUBLISH_ATTESTED — reachable ONLY via a
#        loopback-only host publish. VERIFIABLE: scripts/preflight_bind_posture.sh
#        asserts every published host port of the service binds 127.0.0.0/8.
#      * JUNIPER_<SVC>_AUTH_PROXY_ATTESTED — a fronting authenticating reverse
#        proxy fronts it (Phase-4 / D7; attestation-only, not verified).
#
#    The compose containers bind 0.0.0.0 (``..._HOST=0.0.0.0``), so the app-layer
#    bind-guard would hard-fail unless the loopback-publish attest is set; this
#    file pins that (a) every LOOPBACK_PUBLISH_ATTESTED service defaults to a
#    loopback host publish, (b) canopy AND cascor both carry the flag, (c)
#    AUTH_PROXY_ATTESTED is set nowhere (the containers ARE loopback-published),
#    (d) no stale FRONTING_AUTH_ATTESTED survives, and (e) the preflight PASSES
#    the shipped config and BITES (exit 1) on an injected non-loopback publish.
#
#####################################################################################################################################################################################################

from __future__ import annotations

import ipaddress
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
COMPOSE_PATH = REPO_ROOT / "docker-compose.yml"
PREFLIGHT_SCRIPT = REPO_ROOT / "scripts" / "preflight_bind_posture.sh"
TRUST_CONTRACT = REPO_ROOT / "notes" / "DEPLOYMENT_TRUST_CONTRACT_2026-07-04.md"

ATTEST_SUFFIX = "_LOOPBACK_PUBLISH_ATTESTED"
PROXY_SUFFIX = "_AUTH_PROXY_ATTESTED"
STALE_FLAG = "FRONTING_AUTH_ATTESTED"

CASCOR_ATTEST = "JUNIPER_CASCOR_LOOPBACK_PUBLISH_ATTESTED"
CANOPY_ATTEST = "JUNIPER_CANOPY_LOOPBACK_PUBLISH_ATTESTED"

# The canopy + cascor services (and their demo/dev variants) that bind 0.0.0.0
# inside the container and therefore MUST carry the loopback-publish attest.
EXPECTED_ATTEST = {
    "juniper-cascor": CASCOR_ATTEST,
    "juniper-cascor-demo": CASCOR_ATTEST,
    "juniper-canopy": CANOPY_ATTEST,
    "juniper-canopy-demo": CANOPY_ATTEST,
    "juniper-canopy-dev": CANOPY_ATTEST,
}

LOOPBACK_V4 = ipaddress.ip_network("127.0.0.0/8")
# Matches a compose ``${VAR}`` / ``${VAR:-default}`` interpolation. Expanded
# across the WHOLE port string before splitting on ':' — the host-bind default
# ``${BIND_HOST:-127.0.0.1}`` itself contains a ':', so a naive split would
# shred it.
_VAR_RE = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)(?::-([^}]*))?\}")


def _load_compose() -> dict:
    return yaml.safe_load(COMPOSE_PATH.read_text(encoding="utf-8"))


def _as_env_dict(env) -> dict[str, str]:
    """Normalise a compose service `environment:` (map or list form) to a dict."""
    if isinstance(env, dict):
        return {str(k): "" if v is None else str(v) for k, v in env.items()}
    if isinstance(env, list):
        out: dict[str, str] = {}
        for item in env:
            key, _, val = str(item).partition("=")
            out[key] = val
        return out
    return {}


def _service_env(compose: dict, service: str) -> dict[str, str]:
    return _as_env_dict((compose["services"].get(service) or {}).get("environment"))


def _expand(text: str) -> str:
    """Expand every compose `${VAR:-default}` / `${VAR}` in a string (no override in play).

    `${VAR:-default}` -> `default`; a bare `${VAR}` -> empty string (docker would
    then bind all interfaces — deliberately NOT loopback).
    """
    return _VAR_RE.sub(lambda m: m.group(2) if m.group(2) is not None else "", text)


def _host_ip_is_loopback(host_ip: str) -> bool:
    if not host_ip:
        return False
    try:
        ip = ipaddress.ip_address(host_ip)
    except ValueError:
        return False
    if ip.version == 6 and ip.ipv4_mapped is not None:
        ip = ip.ipv4_mapped
    if ip.version == 4:
        return ip in LOOPBACK_V4
    return ip.is_loopback


def _port_to_rendered(port) -> dict:
    """Turn a compose `ports:` entry into the shape `docker compose config` renders.

    Short-syntax strings (`${BIND_HOST:-127.0.0.1}:8201:8200`) have their
    host-bind default resolved so the offline test needs no Docker daemon.
    """
    if isinstance(port, dict):
        return {
            "host_ip": str(port.get("host_ip") or ""),
            "published": str(port.get("published") or ""),
            "target": port.get("target"),
        }
    parts = _expand(str(port)).split(":")
    if len(parts) >= 3:
        return {"host_ip": parts[0], "published": parts[1], "target": parts[2]}
    if len(parts) == 2:
        return {"host_ip": "", "published": parts[0], "target": parts[1]}
    return {"host_ip": "", "published": "", "target": parts[0]}


def _attested_services(compose: dict) -> dict[str, str]:
    """Map each service that sets a truthy `*_LOOPBACK_PUBLISH_ATTESTED` -> that flag name."""
    out: dict[str, str] = {}
    for name, svc in (compose.get("services") or {}).items():
        env = _as_env_dict((svc or {}).get("environment"))
        for key, value in env.items():
            if key.endswith(ATTEST_SUFFIX) and value.strip().lower() == "true":
                out[name] = key
    return out


def _render_config_from_compose() -> dict:
    """Build a `docker compose config --format json`-shaped dict from compose defaults.

    Host-bind defaults are resolved offline, so this is a faithful stand-in for the
    shipped rendered config that the preflight can consume via --config-json.
    """
    compose = _load_compose()
    services: dict[str, dict] = {}
    for name, svc in (compose.get("services") or {}).items():
        svc = svc or {}
        services[name] = {
            "environment": _as_env_dict(svc.get("environment")),
            "ports": [_port_to_rendered(p) for p in (svc.get("ports") or [])],
        }
    return {"services": services}


def _run_preflight(config: dict) -> subprocess.CompletedProcess:
    """Invoke scripts/preflight_bind_posture.sh --config-json on a rendered config (offline)."""
    handle = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8")
    try:
        json.dump(config, handle)
        handle.close()
        env = dict(os.environ, NO_COLOR="1")
        return subprocess.run(
            ["bash", str(PREFLIGHT_SCRIPT), "--config-json", handle.name],
            capture_output=True,
            text=True,
            env=env,
            timeout=90,
            check=False,
        )
    finally:
        os.unlink(handle.name)


# ── (a) every LOOPBACK_PUBLISH_ATTESTED service defaults to a loopback publish ──


def test_every_attested_service_defaults_to_loopback_publish() -> None:
    compose = _load_compose()
    attested = _attested_services(compose)
    assert attested, "no service sets *_LOOPBACK_PUBLISH_ATTESTED — the attestation was dropped"
    for service, flag in sorted(attested.items()):
        ports = (compose["services"][service] or {}).get("ports") or []
        assert ports, f"`{service}` attests loopback-publish ({flag}) but publishes no host port"
        for port in ports:
            rendered = _port_to_rendered(port)
            host_ip = rendered["host_ip"]
            assert _host_ip_is_loopback(host_ip), (
                f"`{service}` sets {flag}=true but its default host publish binds "
                f"{host_ip or '0.0.0.0 (all interfaces)'!r} — the attestation would be "
                f"UNVERIFIABLE. The host bind must default to loopback (127.0.0.0/8)."
            )


# ── (b) the attested service set is exactly the five canopy/cascor variants ──


def test_attested_services_are_exactly_the_expected_five() -> None:
    compose = _load_compose()
    assert _attested_services(compose) == EXPECTED_ATTEST, (
        "the set of *_LOOPBACK_PUBLISH_ATTESTED services drifted from the canonical "
        "canopy/cascor five; update this contract in the same PR if that is intended."
    )


def test_both_canopy_and_cascor_loopback_flags_are_present() -> None:
    """Both flag NAMES from the two-flag spec must appear (canopy AND cascor sides)."""
    compose = _load_compose()
    flags = set(_attested_services(compose).values())
    assert CASCOR_ATTEST in flags, f"{CASCOR_ATTEST} is not set on any cascor service"
    assert CANOPY_ATTEST in flags, f"{CANOPY_ATTEST} is not set on any canopy service"


def test_each_expected_service_sets_its_own_flag_true() -> None:
    compose = _load_compose()
    for service, flag in EXPECTED_ATTEST.items():
        env = _service_env(compose, service)
        assert env.get(flag, "").strip().lower() == "true", (
            f"`{service}` must set `{flag}: \"true\"` (it binds 0.0.0.0 in-container; "
            f"the app bind-guard hard-fails without the loopback-publish attest)."
        )


# ── (c) AUTH_PROXY_ATTESTED is set nowhere (the containers ARE loopback-published) ──


def test_auth_proxy_attested_is_not_set_anywhere() -> None:
    compose = _load_compose()
    offenders = {}
    for name, svc in (compose.get("services") or {}).items():
        env = _as_env_dict((svc or {}).get("environment"))
        proxy = [k for k, v in env.items() if k.endswith(PROXY_SUFFIX) and v.strip().lower() == "true"]
        if proxy:
            offenders[name] = proxy
    assert not offenders, (
        f"*_AUTH_PROXY_ATTESTED must not be set in the shipped compose (no fronting proxy "
        f"exists — D7 is deferred); found {offenders}. That flag is an operator opt-in only."
    )


# ── (d) no stale FRONTING_AUTH_ATTESTED survives ──


def test_no_stale_fronting_auth_attested_reference() -> None:
    scanned = [COMPOSE_PATH, TRUST_CONTRACT]
    scanned += sorted((REPO_ROOT / "notes").glob("*.md"))
    scanned += sorted(REPO_ROOT.glob(".env*"))
    for path in scanned:
        if not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        assert STALE_FLAG not in text, (
            f"stale `{STALE_FLAG}` reference in {path.relative_to(REPO_ROOT)} — it was renamed to the "
            f"two-flag {CANOPY_ATTEST.replace('CANOPY', '<SVC>')} / "
            f"JUNIPER_<SVC>{PROXY_SUFFIX} contract."
        )


# ── (e) the preflight PASSES the shipped config and BITES on a non-loopback publish ──


def test_preflight_passes_the_shipped_loopback_config() -> None:
    result = _run_preflight(_render_config_from_compose())
    assert result.returncode == 0, (
        f"preflight FAILED on the shipped (loopback) config:\n{result.stdout}\n{result.stderr}"
    )


def test_preflight_bites_on_injected_nonloopback_publish() -> None:
    config = _render_config_from_compose()
    # Flip the first attested service's first host bind to 0.0.0.0.
    victim = next(iter(EXPECTED_ATTEST))
    assert config["services"][victim]["ports"], f"{victim} has no ports to mutate"
    config["services"][victim]["ports"][0]["host_ip"] = "0.0.0.0"
    result = _run_preflight(config)
    assert result.returncode == 1, (
        f"preflight did NOT bite on a non-loopback publish for {victim} "
        f"(exit {result.returncode}):\n{result.stdout}\n{result.stderr}"
    )
    assert victim in result.stdout and "0.0.0.0" in result.stdout, (
        f"preflight failure output should name the offending service + bind:\n{result.stdout}"
    )


def test_preflight_auth_proxy_attest_permits_nonloopback() -> None:
    """The Phase-4 escape hatch: an off-loopback publish is allowed iff AUTH_PROXY-attested."""
    config = _render_config_from_compose()
    victim = next(iter(EXPECTED_ATTEST))
    prefix = EXPECTED_ATTEST[victim][: -len(ATTEST_SUFFIX)]
    config["services"][victim]["ports"][0]["host_ip"] = "0.0.0.0"
    config["services"][victim]["environment"][prefix + PROXY_SUFFIX] = "true"
    result = _run_preflight(config)
    assert result.returncode == 0, (
        f"preflight should PASS an off-loopback publish that is AUTH_PROXY-attested "
        f"(exit {result.returncode}):\n{result.stdout}\n{result.stderr}"
    )


if __name__ == "__main__":  # pragma: no cover - convenience for manual runs
    import pytest

    sys.exit(pytest.main([__file__, "-v"]))
