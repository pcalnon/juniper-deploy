#!/usr/bin/env python
#####################################################################################################################################################################################################
# Project:       Juniper
# Application:   juniper-deploy
# File Name:     test_compose_recurrence_snapshot_mount.py
# Author:        Paul Calnon
#
# Date Created:  2026-10-05
#
# License:       MIT License
# Copyright:     Copyright (c) 2024-2026 Paul Calnon
#
# Description:
#    W1.12 / F-DEP2: juniper-recurrence's model snapshots are a BIND MOUNT of the host's
#    snapshot store, and the in-container path is DECLARED, not derived. Decision of record:
#    juniper-recurrence `juniper_recurrence/settings.py` (`snapshots_dir`), ruled in §11.1 of
#    juniper-ml notes/JUNIPER_2026-09-16_JUNIPER-RECURRENCE_MODEL-PERSISTENCE-DESIGN.md.
#
#    Pins:
#      (a) JUNIPER_RECURRENCE_SNAPSHOTS_DIR equals the mount target. cascor's snapshots were
#          lost for exactly this reason -- the writer and the mount one directory apart, so
#          every save went to the container's writable layer and died on recreate.
#      (b) exactly one volume targets that path, and it is the ruled host default behind the
#          JUNIPER_RECURRENCE_SNAPSHOTS_HOST_DIR override -- a bind source, not a named volume,
#          which `docker compose down -v` / `make clean` would delete.
#      (c) every service running the recurrence image carries both (design §11.4: the mount
#          belongs at every profile the service appears in), so a future variant cannot ship
#          without it.
#      (d) .env.example documents the override with the same default.
#
#    The behaviour behind it -- save, restart, recreate, list, restore -- is
#    scripts/test_recurrence_snapshots.sh, which needs a Docker daemon.
#
#####################################################################################################################################################################################################

from __future__ import annotations

import re
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
COMPOSE_PATH = REPO_ROOT / "docker-compose.yml"
ENV_EXAMPLE_PATH = REPO_ROOT / ".env.example"

RECURRENCE_IMAGE = "ghcr.io/pcalnon/juniper-recurrence"
MOUNT_TARGET = "/app/recurrence-snapshots"
HOST_DIR_VAR = "JUNIPER_RECURRENCE_SNAPSHOTS_HOST_DIR"
DEFAULT_HOST_DIR = "../juniper-recurrence/recurrence-snapshots"
EXPECTED_MOUNT = "${" + HOST_DIR_VAR + ":-" + DEFAULT_HOST_DIR + "}:" + MOUNT_TARGET


def _compose() -> dict:
    return yaml.safe_load(COMPOSE_PATH.read_text(encoding="utf-8"))


def _recurrence_services(compose: dict) -> dict[str, dict]:
    """Every service that runs the recurrence image, whatever it is named."""
    return {
        name: svc
        for name, svc in (compose.get("services") or {}).items()
        if str((svc or {}).get("image", "")).startswith(RECURRENCE_IMAGE + ":")
    }


#: Trailing access/consistency modes a short-syntax volume entry may carry after its target.
_MODES = {"ro", "rw", "z", "Z", "cached", "delegated", "consistent"}


def _split_short(volume: str) -> tuple[str, str]:
    """``(source, target)`` of a short-syntax entry. The source may itself hold colons
    (``${VAR:-default}``), so the target is found from the right."""
    parts = volume.split(":")
    if len(parts) > 2 and parts[-1] in _MODES:
        parts = parts[:-1]
    return ":".join(parts[:-1]), parts[-1]


def _snapshot_mounts(svc: dict) -> list:
    """Volume entries whose container target is the snapshot root, in either syntax."""
    mounts = []
    for volume in svc.get("volumes") or []:
        if isinstance(volume, dict):
            if volume.get("target") == MOUNT_TARGET:
                mounts.append(volume)
        elif _split_short(str(volume))[1] == MOUNT_TARGET:
            mounts.append(volume)
    return mounts


def test_recurrence_service_is_present() -> None:
    """Guard against the census below passing vacuously on an empty set."""
    services = _recurrence_services(_compose())
    assert "juniper-recurrence" in services, f"no service runs {RECURRENCE_IMAGE}:<tag>; found {sorted(services)}"


def test_snapshots_dir_is_declared_and_matches_the_mount_target() -> None:
    for name, svc in _recurrence_services(_compose()).items():
        declared = (svc.get("environment") or {}).get("JUNIPER_RECURRENCE_SNAPSHOTS_DIR")
        assert declared == MOUNT_TARGET, (
            f"{name}: JUNIPER_RECURRENCE_SNAPSHOTS_DIR is {declared!r}, not {MOUNT_TARGET!r}. The "
            "service writes where this variable points and the mount persists only its target, so "
            "the two must name the same path -- one directory apart, every snapshot lands in the "
            "container's writable layer and dies on recreate (cascor's F-CANOPY-007 class)."
        )


def test_snapshot_root_is_a_bind_of_the_ruled_host_default() -> None:
    for name, svc in _recurrence_services(_compose()).items():
        mounts = _snapshot_mounts(svc)
        assert mounts == [EXPECTED_MOUNT], (
            f"{name}: the volumes targeting {MOUNT_TARGET} are {mounts!r}; expected exactly "
            f"[{EXPECTED_MOUNT!r}]. The ruling is a BIND MOUNT of the host store, overridable via "
            f"{HOST_DIR_VAR}: a named volume does not survive `docker compose down -v` or "
            "`make clean`, is not the directory the host CLI tier uses, and is not inside the "
            "Juniper tree the offline backup walks."
        )


def test_snapshot_root_source_is_not_a_named_volume() -> None:
    compose = _compose()
    named = set((compose.get("volumes") or {}).keys())
    for name, svc in _recurrence_services(compose).items():
        for mount in _snapshot_mounts(svc):
            source = mount.get("source") if isinstance(mount, dict) else _split_short(str(mount))[0]
            assert source not in named, f"{name}: {MOUNT_TARGET} is the named volume {source!r}; the ruling is a bind mount"


def test_env_example_documents_the_override_with_the_same_default() -> None:
    text = ENV_EXAMPLE_PATH.read_text(encoding="utf-8")
    lines = re.findall(rf"^#\s*{HOST_DIR_VAR}=(.*)$", text, flags=re.MULTILINE)
    assert lines == [DEFAULT_HOST_DIR], (
        f".env.example must carry exactly one commented `{HOST_DIR_VAR}={DEFAULT_HOST_DIR}` line, "
        f"matching the compose default; found {lines!r}."
    )
