#!/usr/bin/env python
#####################################################################################################################################################################################################
# Project:       Juniper
# Application:   juniper-deploy
# File Name:     test_compose_security_config.py
# Author:        Juniper Automation
#
# Date Created:  2026-04-01
#
# License:       MIT License
# Copyright:     Copyright (c) 2024-2026 Paul Calnon
#
# Description:
#    Regression tests for docker-compose security hardening:
#      - Docker secrets file wiring for sensitive service config
#      - Observability service network isolation on `monitoring`
#      - Secret file gitignore safety rules
#
#####################################################################################################################################################################################################

from pathlib import Path
import re


REPO_ROOT = Path(__file__).resolve().parents[1]
COMPOSE_PATH = REPO_ROOT / "docker-compose.yml"
GITIGNORE_PATH = REPO_ROOT / ".gitignore"


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _extract_two_space_blocks(compose_text: str, section_name: str) -> dict[str, str]:
    """Extract `  name:` blocks within a top-level compose section."""
    lines = compose_text.splitlines()

    section_idx = None
    for idx, line in enumerate(lines):
        if line == f"{section_name}:":
            section_idx = idx
            break

    assert section_idx is not None, f"Section `{section_name}` not found in docker-compose.yml"

    blocks: dict[str, str] = {}
    current_name = None
    current_lines: list[str] = []

    for line in lines[section_idx + 1 :]:
        # Reached the next top-level section.
        if line and not line.startswith(" "):
            break

        match = re.match(r"^  ([A-Za-z0-9_-]+):\s*$", line)
        if match:
            if current_name is not None:
                blocks[current_name] = "\n".join(current_lines)
            current_name = match.group(1)
            current_lines = []
            continue

        if current_name is not None:
            current_lines.append(line)

    if current_name is not None:
        blocks[current_name] = "\n".join(current_lines)

    return blocks


def _assert_mapping_line(block_text: str, key: str, value: str) -> None:
    pattern = rf"^\s+{re.escape(key)}:\s+{re.escape(value)}\s*$"
    assert re.search(pattern, block_text, flags=re.MULTILINE), (
        f"Missing mapping line `{key}: {value}`"
    )


def _assert_list_item(block_text: str, item: str) -> None:
    pattern = rf"^\s+-\s+{re.escape(item)}\s*$"
    assert re.search(pattern, block_text, flags=re.MULTILINE), f"Missing list item `{item}`"


def test_sensitive_services_use_docker_secret_file_env_vars_and_mounts():
    compose_text = _read_text(COMPOSE_PATH)
    services = _extract_two_space_blocks(compose_text, "services")

    data = services["juniper-data"]
    _assert_mapping_line(data, "JUNIPER_DATA_API_KEYS_FILE", "/run/secrets/juniper_data_api_keys")
    _assert_list_item(data, "juniper_data_api_keys")

    cascor = services["juniper-cascor"]
    _assert_mapping_line(cascor, "JUNIPER_CASCOR_API_KEYS_FILE", "/run/secrets/juniper_cascor_api_keys")
    _assert_mapping_line(cascor, "JUNIPER_DATA_API_KEY_FILE", "/run/secrets/juniper_data_api_keys")
    _assert_list_item(cascor, "juniper_cascor_api_key")
    _assert_list_item(cascor, "cascor_sentry_dsn")

    canopy = services["juniper-canopy"]
    _assert_mapping_line(canopy, "CANOPY_API_KEY_FILE", "/run/secrets/canopy_api_key")
    _assert_mapping_line(canopy, "JUNIPER_CASCOR_API_KEY_FILE", "/run/secrets/juniper_cascor_api_keys")
    _assert_list_item(canopy, "canopy_api_key")
    _assert_list_item(canopy, "juniper_cascor_api_keys")

    worker = services["juniper-cascor-worker"]
    _assert_mapping_line(worker, "CASCOR_AUTH_TOKEN_FILE", "/run/secrets/cascor_auth_token")
    _assert_list_item(worker, "cascor_auth_token")

    grafana = services["grafana"]
    _assert_mapping_line(grafana, "GF_SECURITY_ADMIN_PASSWORD__FILE", "/run/secrets/grafana_admin_password")
    _assert_list_item(grafana, "grafana_admin_password")


def test_declared_top_level_secrets_match_expected_files():
    compose_text = _read_text(COMPOSE_PATH)
    secrets = _extract_two_space_blocks(compose_text, "secrets")

    assert set(secrets.keys()) >= {
        "juniper_data_api_keys",
        "juniper_cascor_api_key",
        "cascor_sentry_dsn",
        "cascor_auth_token",
        "canopy_api_key",
        "grafana_admin_password",
    }
    # Secret files use env-var overrides with secrets.example/ defaults
    for name in ("juniper_data_api_keys", "juniper_cascor_api_key",
                 "cascor_sentry_dsn", "cascor_auth_token",
                 "canopy_api_key", "grafana_admin_password"):
        assert "file:" in secrets[name], f"Secret {name} missing file: declaration"


def test_observability_services_attach_to_monitoring_network():
    compose_text = _read_text(COMPOSE_PATH)
    services = _extract_two_space_blocks(compose_text, "services")

    prometheus = services["prometheus"]
    _assert_list_item(prometheus, "monitoring")
    # Prometheus also attaches to backend/data/frontend to scrape service metrics

    grafana = services["grafana"]
    _assert_list_item(grafana, "monitoring")


def test_grafana_has_no_env_var_password_fallback():
    """Regression: GF_SECURITY_ADMIN_PASSWORD env var must not exist.

    The password must only be supplied via Docker secret (__FILE variant)
    to avoid predictable default credentials (issue #11).
    """
    compose_text = _read_text(COMPOSE_PATH)
    services = _extract_two_space_blocks(compose_text, "services")
    grafana = services["grafana"]
    assert not re.search(
        r"^\s+GF_SECURITY_ADMIN_PASSWORD:", grafana, flags=re.MULTILINE
    ), "GF_SECURITY_ADMIN_PASSWORD env var must not be set — use __FILE variant only"


def test_secret_files_are_ignored():
    gitignore_text = _read_text(GITIGNORE_PATH)
    assert "secrets/" in gitignore_text


def test_published_ports_default_to_loopback_bind(): # DEPLOY-08
    """All host port mappings must default to 127.0.0.1 (overridable via BIND_HOST).

    Prevents regressions that would expose cascor/canopy on 0.0.0.0 by default.
    """
    compose_text = _read_text(COMPOSE_PATH)
    services = _extract_two_space_blocks(compose_text, "services")

    # juniper-data is intentionally internal-only (no host port published; see the
    # docker-compose.yml note on the juniper-data service), so it is excluded here.
    # juniper-recurrence is host-published (8211 -> 8210) and must bind to loopback.
    for name in ("juniper-cascor", "juniper-cascor-demo", "juniper-recurrence",
                 "juniper-canopy", "juniper-canopy-demo", "juniper-canopy-dev"):
        block = services[name]
        # Match a `- "...":port:port` ports list item.
        port_lines = re.findall(r"^\s+-\s+\"([^\"]+)\"\s*$", block, flags=re.MULTILINE)
        # Only inspect lines that look like host:container port mappings (have two colons).
        host_mappings = [p for p in port_lines if p.count(":") >= 2]
        assert host_mappings, f"Service {name} has no host port mapping"
        for mapping in host_mappings:
            assert mapping.startswith("${BIND_HOST:-127.0.0.1}:") or mapping.startswith("127.0.0.1:"), (
                f"Service {name} port mapping `{mapping}` does not bind to loopback by default"
            )


def test_canopy_dev_can_reach_juniper_data(): # DEPLOY-13
    """canopy-dev must share a network with juniper-data so the dev profile is functional."""
    compose_text = _read_text(COMPOSE_PATH)
    services = _extract_two_space_blocks(compose_text, "services")

    canopy_dev = services["juniper-canopy-dev"]
    juniper_data = services["juniper-data"]

    def _networks(block: str) -> set[str]:
        in_networks = False
        nets: set[str] = set()
        for line in block.splitlines():
            stripped = line.strip()
            if stripped == "networks:":
                in_networks = True
                continue
            if in_networks:
                m = re.match(r"^\s+-\s+([A-Za-z0-9_-]+)\s*$", line)
                if m:
                    nets.add(m.group(1))
                elif stripped and not stripped.startswith("-"):
                    in_networks = False
        return nets

    canopy_dev_nets = _networks(canopy_dev)
    data_nets = _networks(juniper_data)
    shared = canopy_dev_nets & data_nets
    assert shared, (
        f"canopy-dev networks {canopy_dev_nets} share none with juniper-data {data_nets} — "
        "dev profile cannot reach the data service"
    )


def test_secrets_only_no_plain_api_key_env_vars(): # DEPLOY-09 + DEPLOY-11
    """Plain API key / auth token env vars must not coexist with their _FILE variants.

    The plain forms leak secrets into `docker inspect` output and into any
    accidentally-committed `.env` files. The _FILE variants read from
    /run/secrets at startup and are the only sanctioned source.
    """
    compose_text = _read_text(COMPOSE_PATH)
    services = _extract_two_space_blocks(compose_text, "services")

    forbidden_env_vars = (
        # DEPLOY-09: worker auth token (legacy CFG-06 name)
        "CASCOR_AUTH_TOKEN",
        # DEPLOY-09 + CFG-06: worker auth token canonical name —
        # juniper-cascor-worker >= 0.4.0 reads JUNIPER_CASCOR_WORKER_AUTH_TOKEN
        # natively; the same secret-leak invariant applies, only the _FILE
        # variant may be set in compose.
        "JUNIPER_CASCOR_WORKER_AUTH_TOKEN",
        # DEPLOY-11: every flavor of API key plain env var
        "JUNIPER_DATA_API_KEYS",
        "JUNIPER_DATA_API_KEY",
        "JUNIPER_CASCOR_API_KEYS",
        "JUNIPER_CASCOR_API_KEY",
    )
    for service_name, block in services.items():
        for var in forbidden_env_vars:
            # Match `<spaces>VAR:<value>` but NOT `VAR_FILE:` lines.
            pattern = rf"^\s+{re.escape(var)}:\s"
            assert not re.search(pattern, block, flags=re.MULTILINE), (
                f"Service {service_name} sets plain `{var}` env var — must use "
                f"{var}_FILE / Docker secret instead (DEPLOY-09/11)."
            )
