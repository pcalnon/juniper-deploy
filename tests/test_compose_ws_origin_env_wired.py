#!/usr/bin/env python
#####################################################################################################################################################################################################
# Project:       Juniper
# Application:   juniper-deploy
# File Name:     test_compose_ws_origin_env_wired.py
# Author:        Paul Calnon
#
# Date Created:  2026-05-29
#
# License:       MIT License
# Copyright:     Copyright (c) 2024-2026 Paul Calnon
#
# Description:
#    E.2 PR-2-D regression: ensure the two WS-Origin env vars are
#    correctly wired in ``docker-compose.yml``.  Without them, juniper-
#    canopy's ``ControlStreamSupervisor`` cannot connect to cascor's
#    ``/ws/control`` (juniper-cascor#129 fail-closed allowlist).
#
#    See juniper-ml ``notes/STACK_REGRESSION_CORRECTIONS_2026-05-27.md``
#    §E.2 for the cross-repo context.
#
#####################################################################################################################################################################################################

from pathlib import Path
import re


REPO_ROOT = Path(__file__).resolve().parents[1]
COMPOSE_PATH = REPO_ROOT / "docker-compose.yml"


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _extract_service_env(compose_text: str, service_name: str) -> str:
    """Return the ``environment:`` block lines for the named service."""
    lines = compose_text.splitlines()
    # Find the service block start.
    service_idx = None
    for idx, line in enumerate(lines):
        if line == f"  {service_name}:":
            service_idx = idx
            break
    assert service_idx is not None, f"Service `{service_name}` not found in docker-compose.yml"

    # Find environment block.
    env_start = None
    for idx in range(service_idx + 1, len(lines)):
        line = lines[idx]
        if line.startswith("  ") and not line.startswith("    ") and line.rstrip().endswith(":") and idx > service_idx:
            # Reached the next top-level service or the end of this service block.
            break
        if line.strip() == "environment:":
            env_start = idx
            break

    assert env_start is not None, f"Service `{service_name}` has no `environment:` block"

    env_lines = []
    for line in lines[env_start + 1 :]:
        if line.startswith("      ") or line.strip().startswith("#") or not line.strip():
            env_lines.append(line)
        else:
            break
    return "\n".join(env_lines)


def test_cascor_service_sets_ws_control_allowed_origins() -> None:
    """juniper-cascor must receive the env var so its
    ``Settings.ws_control_allowed_origins`` includes the canopy
    docker-compose service hostname.  Without this, canopy's
    ``/ws/control`` upgrade is 403-rejected.

    Default must include ``http://juniper-canopy:8050`` so the OOB
    docker-compose flow works without operator env action.
    """
    compose_text = _read_text(COMPOSE_PATH)
    cascor_env = _extract_service_env(compose_text, "juniper-cascor")
    assert "JUNIPER_CASCOR_WS_CONTROL_ALLOWED_ORIGINS" in cascor_env, "juniper-cascor service env missing JUNIPER_CASCOR_WS_CONTROL_ALLOWED_ORIGINS — " "canopy's /ws/control upgrade will be 403-rejected. See juniper-ml " "notes/STACK_REGRESSION_CORRECTIONS_2026-05-27.md §E.2."
    # The default must include the canopy hostname.
    match = re.search(r"JUNIPER_CASCOR_WS_CONTROL_ALLOWED_ORIGINS:\s*\"\$\{JUNIPER_CASCOR_WS_CONTROL_ALLOWED_ORIGINS:-([^\"}]+)\}\"", cascor_env)
    assert match is not None, "JUNIPER_CASCOR_WS_CONTROL_ALLOWED_ORIGINS must use the `${X:-default}` shape so operators can override"
    default = match.group(1)
    assert "http://juniper-canopy:8050" in default, f"Default allowlist must include http://juniper-canopy:8050 so OOB docker-compose works; " f"got {default!r}"


def test_canopy_service_sets_cascor_ws_origin() -> None:
    """juniper-canopy must receive the env var so its
    ``Settings.cascor_ws_origin`` is wired through to
    ``CascorControlStream(origin=…)``.

    The canopy Settings default is already ``http://juniper-canopy:8050``,
    so this assertion guards against future env-rewrites silently
    dropping the explicit declaration (which would still work, but
    make the contract less visible in compose).
    """
    compose_text = _read_text(COMPOSE_PATH)
    canopy_env = _extract_service_env(compose_text, "juniper-canopy")
    assert "JUNIPER_CANOPY_CASCOR_WS_ORIGIN" in canopy_env, "juniper-canopy service env missing JUNIPER_CANOPY_CASCOR_WS_ORIGIN — " "the contract with juniper-cascor's allowlist would not be visible in compose."
    match = re.search(r"JUNIPER_CANOPY_CASCOR_WS_ORIGIN:\s*\"\$\{JUNIPER_CANOPY_CASCOR_WS_ORIGIN:-([^\"}]+)\}\"", canopy_env)
    assert match is not None, "JUNIPER_CANOPY_CASCOR_WS_ORIGIN must use the `${X:-default}` shape"
    default = match.group(1)
    assert default == "http://juniper-canopy:8050", f"Default Origin must match the canopy service hostname; got {default!r}"
