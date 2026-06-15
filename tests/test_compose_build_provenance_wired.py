#!/usr/bin/env python
#####################################################################################################################################################################################################
# Project:       Juniper
# Application:   juniper-deploy
# File Name:     test_compose_build_provenance_wired.py
# Author:        Paul Calnon
#
# Date Created:  2026-06-14
#
# License:       MIT License
# Copyright:     Copyright (c) 2024-2026 Paul Calnon
#
# Description:
#    Build-provenance regression: every juniper service build block in
#    ``docker-compose.yml`` must declare the GIT_SHA / BUILD_DATE / APP_VERSION
#    build-args, each referencing its OWN source repo's per-repo env var, so
#    ``make build`` can stamp every image with its own provenance. Guards the
#    failure class where the wiring is silently dropped (cf. the WS-Origin
#    regression in juniper-deploy #102 -> #103).
#
#    See juniper-ml ``notes/BUILD_PROVENANCE_DESIGN_2026-06-14.md`` §5.4/§6.
#
#####################################################################################################################################################################################################

from pathlib import Path
import re

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
COMPOSE_PATH = REPO_ROOT / "docker-compose.yml"
MAKEFILE_PATH = REPO_ROOT / "Makefile"


# Each juniper service build block -> the per-repo suffix its build-args must
# use. Demo/dev variants share their parent repo's build context, so they must
# reuse the same per-repo var (a single global GIT_SHA would mislabel them).
EXPECTED_SUFFIX = {
    "juniper-data": "DATA",
    "juniper-cascor": "CASCOR",
    "juniper-cascor-demo": "CASCOR",
    "juniper-cascor-worker": "WORKER",
    "juniper-canopy": "CANOPY",
    "juniper-canopy-demo": "CANOPY",
    "juniper-canopy-dev": "CANOPY",
}


def _services() -> dict:
    return yaml.safe_load(COMPOSE_PATH.read_text(encoding="utf-8"))["services"]


def test_every_juniper_service_declares_provenance_build_args() -> None:
    """All 7 juniper build blocks wire GIT_SHA / BUILD_DATE / APP_VERSION, each
    GIT_SHA / APP_VERSION referencing its own per-repo var."""
    services = _services()
    for svc, suffix in EXPECTED_SUFFIX.items():
        assert svc in services, f"service `{svc}` missing from docker-compose.yml"
        build = services[svc].get("build")
        assert isinstance(build, dict), f"{svc}: `build:` must be a mapping carrying `args:`"
        args = build.get("args")
        assert isinstance(args, dict), f"{svc}: `build.args` missing — image cannot be stamped with provenance"
        assert args.get("GIT_SHA") == f"${{GIT_SHA_{suffix}:-}}", f"{svc}: GIT_SHA must reference the per-repo var GIT_SHA_{suffix}; got {args.get('GIT_SHA')!r}"
        assert args.get("BUILD_DATE") == "${BUILD_DATE:-}", f"{svc}: BUILD_DATE build-arg missing/wrong; got {args.get('BUILD_DATE')!r}"
        assert args.get("APP_VERSION") == f"${{APP_VERSION_{suffix}:-}}", f"{svc}: APP_VERSION must reference APP_VERSION_{suffix}; got {args.get('APP_VERSION')!r}"


def test_no_build_block_uses_a_global_git_sha() -> None:
    """Per-service-SHA guard: a build block must never reference a bare
    ``${GIT_SHA}`` — that would stamp every image with one repo's SHA, the
    exact mistake the per-repo vars exist to prevent."""
    for svc, cfg in _services().items():
        build = cfg.get("build")
        if not isinstance(build, dict):
            continue
        git_sha = (build.get("args") or {}).get("GIT_SHA")
        if git_sha is None:
            continue
        assert git_sha not in ("${GIT_SHA:-}", "${GIT_SHA}"), f"{svc}: build uses a global GIT_SHA — would mislabel a multi-service build; use a per-repo GIT_SHA_<REPO> var"


def test_makefile_defines_every_referenced_provenance_var() -> None:
    """Every ``${VAR:-}`` a build-arg references must be defined in the
    Makefile's PROVENANCE_ENV, so the compose<->Makefile contract can't drift
    (an undefined var would silently stamp the image with an empty value)."""
    makefile = MAKEFILE_PATH.read_text(encoding="utf-8")
    referenced: set[str] = set()
    for cfg in _services().values():
        build = cfg.get("build")
        if not isinstance(build, dict) or not isinstance(build.get("args"), dict):
            continue
        for value in build["args"].values():
            match = re.fullmatch(r"\$\{([A-Z_]+):-\}", str(value))
            if match:
                referenced.add(match.group(1))
    assert referenced, "no provenance build-args found — did the wiring get dropped?"
    for var in sorted(referenced):
        assert re.search(rf"\b{re.escape(var)}=", makefile), f"Makefile PROVENANCE_ENV does not define `{var}` referenced by a compose build-arg"
