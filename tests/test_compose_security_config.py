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
    _assert_list_item(data, "juniper_data_api_key")

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

    grafana = services["grafana"]
    _assert_mapping_line(grafana, "GF_SECURITY_ADMIN_PASSWORD__FILE", "/run/secrets/grafana_admin_password")
    _assert_list_item(grafana, "grafana_admin_password")


def test_declared_top_level_secrets_match_expected_files():
    compose_text = _read_text(COMPOSE_PATH)
    secrets = _extract_two_space_blocks(compose_text, "secrets")

    assert set(secrets.keys()) >= {
        "juniper_data_api_key",
        "juniper_cascor_api_key",
        "cascor_sentry_dsn",
        "canopy_api_key",
        "grafana_admin_password",
    }
    # Secret files use env-var overrides with secrets.example/ defaults
    for name in ("juniper_data_api_key", "juniper_cascor_api_key",
                 "cascor_sentry_dsn", "canopy_api_key", "grafana_admin_password"):
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
