#!/usr/bin/env python
#####################################################################################################################################################################################################
# Project:       Juniper
# Application:   juniper-deploy
# File Name:     test_compose_secret_mount_symmetry.py
# Author:        Paul Calnon
#
# Date Created:  2026-05-28
#
# License:       MIT License
# Copyright:     Copyright (c) 2024-2026 Paul Calnon
#
# Description:
#    Static regression guard for the symmetric-mount design of docker-compose
#    secret defaults (see notes/SECRET_MOUNT_SYMMETRY_2026-05-28.md).
#
#    The five auth-path secrets must default to ``./secrets/<name>.txt`` so
#    that ``prepare_secrets.bash`` (which always populates ``./secrets/...``)
#    is the canonical source of truth.  The non-auth secrets
#    (cascor_sentry_dsn, grafana_admin_password, alertmanager_smtp_password)
#    keep their ``./secrets.example/...`` defaults.
#
#    Catches drift back toward asymmetric defaults and silent gaps where a
#    new ``./secrets/<name>.txt`` default has no corresponding entry in
#    ``prepare_secrets.bash`` MAPPINGS.
#
#####################################################################################################################################################################################################

from pathlib import Path
import re


REPO_ROOT = Path(__file__).resolve().parents[1]
COMPOSE_PATH = REPO_ROOT / "docker-compose.yml"
PREPARE_SECRETS_PATH = REPO_ROOT / "scripts" / "prepare_secrets.bash"


# Five secrets whose default MUST point at ./secrets/<name>.txt for the
# canopy ↔ cascor auth path to mount symmetrically.  Changing this list
# is a deliberate policy choice that should accompany a rationale update
# in notes/SECRET_MOUNT_SYMMETRY_2026-05-28.md.
AUTH_PATH_SECRETS = {
    "juniper_data_api_keys": "JUNIPER_DATA_API_KEYS_FILE",
    "juniper_cascor_api_key": "JUNIPER_CASCOR_API_KEY_FILE",
    "juniper_cascor_api_keys": "JUNIPER_CASCOR_API_KEYS_FILE",
    "canopy_api_key": "CANOPY_API_KEY_FILE",
    "cascor_auth_token": "CASCOR_AUTH_TOKEN_FILE",
}


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _extract_secrets_block(compose_text: str) -> str:
    """Return the lines from the top-level ``secrets:`` block to EOF / next top-level."""
    lines = compose_text.splitlines()
    start = None
    for idx, line in enumerate(lines):
        if line == "secrets:":
            start = idx
            break
    assert start is not None, "Top-level `secrets:` block not found in docker-compose.yml"

    block_lines = [lines[start]]
    for line in lines[start + 1 :]:
        if line and not line.startswith((" ", "\t", "#")):
            break
        block_lines.append(line)
    return "\n".join(block_lines)


def _secret_default_path(secrets_block: str, secret_name: str, env_var: str) -> str:
    """Extract the default path from ``file: "${ENV_VAR:-DEFAULT}"``."""
    pattern = rf'{re.escape(secret_name)}:\s*\n\s*file:\s*"\$\{{{re.escape(env_var)}:-([^"}}]+)\}}"'
    match = re.search(pattern, secrets_block)
    assert match is not None, f"Secret `{secret_name}` (env var `{env_var}`) not found with expected `file: \"${{{env_var}:-…}}\"` shape in compose"
    return match.group(1)


def test_auth_path_secrets_default_to_secrets_dir() -> None:
    """Each auth-path secret must default to ``./secrets/<name>.txt``.

    Closes the 2026-05-27 asymmetric-mount regression where canopy bound
    ``./secrets.example/juniper_cascor_api_keys.txt`` (29-byte placeholder)
    and cascor bound ``./secrets/juniper_cascor_api_keys.txt`` (43-byte
    populated token), producing 100% canopy → cascor 401s.
    """
    compose_text = _read_text(COMPOSE_PATH)
    block = _extract_secrets_block(compose_text)
    for secret_name, env_var in AUTH_PATH_SECRETS.items():
        default = _secret_default_path(block, secret_name, env_var)
        assert default == f"./secrets/{secret_name}.txt", f"Secret `{secret_name}` default is `{default}`, expected `./secrets/{secret_name}.txt`. " "See notes/SECRET_MOUNT_SYMMETRY_2026-05-28.md for rationale."


def test_prepare_secrets_covers_every_auth_path_secret() -> None:
    """Every auth-path secret default must have a matching entry in
    ``prepare_secrets.bash`` MAPPINGS — otherwise a fresh-clone
    ``make up`` would leave the file absent and the bind-mount would
    fail at compose-up time.
    """
    prepare_text = _read_text(PREPARE_SECRETS_PATH)
    for secret_name in AUTH_PATH_SECRETS:
        target_filename = f"{secret_name}.txt"
        assert target_filename in prepare_text, f"`{target_filename}` is referenced by docker-compose.yml's secrets block but not by " f"scripts/prepare_secrets.bash MAPPINGS. Add an entry so `make prepare-secrets` produces the file."


def test_symmetry_rationale_documented_in_compose_comment() -> None:
    """The compose top-level secrets block must carry the symmetry-design
    comment that points at the rationale doc — preserves the design's
    intent against future drift.
    """
    compose_text = _read_text(COMPOSE_PATH)
    assert "SECRET_MOUNT_SYMMETRY_2026-05-28.md" in compose_text, "docker-compose.yml's secrets block must reference notes/SECRET_MOUNT_SYMMETRY_2026-05-28.md " "so future operators (and Claude sessions) understand why defaults point at ./secrets/."
