#!/usr/bin/env python
#####################################################################################################################################################################################################
# Project:       Juniper
# Application:   juniper-deploy
# File Name:     test_recurrence_snapshot_smoke_images.py
# Author:        Paul Calnon
#
# Date Created:  2026-10-26
#
# License:       MIT License
# Copyright:     Copyright (c) 2024-2026 Paul Calnon
#
# Description:
#    juniper-deploy#250: scripts/test_recurrence_snapshots.sh never builds an image. Both services
#    it brings up carry a `build:` block whose context is a sibling checkout, so a plain
#    `compose up` with an image missing from the local store tried to build juniper-data from
#    ../juniper-data, and beside a worktree, where no such checkout exists, the smoke failed before
#    step 2 with `unable to prepare context`.
#
#    Pins, against a stub `docker` on PATH that records every call:
#      (a) an image that is neither local nor pullable stops the run with exit 2 after the
#          configured number of pull attempts, and no `up` is ever issued;
#      (b) an image missing from the local store is pulled, once, and `up` runs with --no-build;
#      (c) a local image is used as it is: no pull;
#      (d) statically, every `compose up` the recurrence smokes issue passes --no-build, so the
#          recreate in step 7 (which the stub never reaches) is covered too.
#
#    The smoke itself, against a real daemon, is still the script.
#
#####################################################################################################################################################################################################

from __future__ import annotations

import os
import re
import stat
import subprocess
from pathlib import Path

from tests.redacted_env import RedactedEnv

REPO_ROOT = Path(__file__).resolve().parents[1]
SMOKE = REPO_ROOT / "scripts" / "test_recurrence_snapshots.sh"
NO_BUILD_SMOKES = (SMOKE, REPO_ROOT / "scripts" / "test_canopy_recurrence_smoke.sh")

# What the stub's `compose config --images` answers. Deliberately not the compose pins: the smoke
# must pull whatever compose resolves, and a pin bump must not make this file look stale.
RECURRENCE_IMAGE = "ghcr.io/pcalnon/juniper-recurrence:stub"
DATA_IMAGE = "ghcr.io/pcalnon/juniper-data:stub"

# The flags the smoke's compose() wrapper puts before every compose subcommand.
_COMPOSE_GLOBAL_FLAGS = ("-p", "--project-directory", "-f", "--profile")

# Records each call in FAKE_DOCKER_LOG (one per line), then answers what the smoke asks before and
# during its bring-up. The rendered config passes step 1: the compose() wrapper exports the scratch
# snapshot root to docker, so the stub binds exactly what the smoke expects. `up` always fails, so
# a run that reaches it stops there, with exit 1.
_FAKE_DOCKER = r"""#!/usr/bin/env bash
printf '%s\n' "$*" >> "$FAKE_DOCKER_LOG"
case "$1" in
    info) exit 0 ;;
    container) exit 1 ;;
    image) [[ "$FAKE_IMAGES_LOCAL" == 1 ]] && exit 0; exit 1 ;;
    pull) [[ "$FAKE_PULL_OK" == 1 ]] && exit 0; echo "unexpected EOF" >&2; exit 1 ;;
    compose) shift ;;
    *) exit 0 ;;
esac
while [[ $# -gt 0 ]]; do
    case "$1" in
        -p|--project-directory|-f|--profile) shift 2 ;;
        *) break ;;
    esac
done
case "${1:-}" in
    config)
        if [[ " $* " == *" --images "* ]]; then
            printf '%s\n' "$FAKE_RECURRENCE_IMAGE" "$FAKE_DATA_IMAGE"
        else
            printf '{"services": {"juniper-recurrence": {"environment": {"JUNIPER_RECURRENCE_SNAPSHOTS_DIR": "/app/recurrence-snapshots"}, "volumes": [{"type": "bind", "source": "%s", "target": "/app/recurrence-snapshots"}]}}}\n' "$JUNIPER_RECURRENCE_SNAPSHOTS_HOST_DIR"
        fi
        ;;
    up) echo "stub docker: up stops the smoke here" >&2; exit 1 ;;
esac
exit 0
"""


def _run_smoke(tmp_path: Path, *, images_local: bool, pull_ok: bool) -> tuple[subprocess.CompletedProcess[str], list[str]]:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    docker = bin_dir / "docker"
    docker.write_text(_FAKE_DOCKER, encoding="utf-8")
    docker.chmod(docker.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
    scratch = tmp_path / "scratch"
    scratch.mkdir()
    log = tmp_path / "docker.log"

    env = RedactedEnv(os.environ)
    env["PATH"] = f"{bin_dir}{os.pathsep}{env.get('PATH', '')}"
    env["TMPDIR"] = str(scratch)
    env["NO_COLOR"] = "1"
    env["FAKE_DOCKER_LOG"] = str(log)
    env["FAKE_IMAGES_LOCAL"] = "1" if images_local else "0"
    env["FAKE_PULL_OK"] = "1" if pull_ok else "0"
    env["FAKE_RECURRENCE_IMAGE"] = RECURRENCE_IMAGE
    env["FAKE_DATA_IMAGE"] = DATA_IMAGE
    env["RECURRENCE_SMOKE_PULL_RETRY_DELAY"] = "0"
    env.pop("COMPOSE_FILE", None)

    result = subprocess.run(
        ["bash", str(SMOKE)],
        cwd=REPO_ROOT,
        env=env,
        check=False,
        capture_output=True,
        text=True,
        timeout=60,
    )
    calls = log.read_text(encoding="utf-8").splitlines() if log.exists() else []
    return result, calls


def _compose_calls(calls: list[str], subcommand: str) -> list[list[str]]:
    """The argument lists after `compose <global flags> <subcommand>`, one per matching call."""
    found = []
    for call in calls:
        words = call.split()
        if not words or words[0] != "compose":
            continue
        i = 1
        while i < len(words) and words[i] in _COMPOSE_GLOBAL_FLAGS:
            i += 2
        if i < len(words) and words[i] == subcommand:
            found.append(words[i + 1 :])
    return found


def _pulls(calls: list[str]) -> list[str]:
    return [call.split()[-1] for call in calls if call.split()[:1] == ["pull"]]


def test_an_image_neither_local_nor_pullable_stops_the_run_before_anything_starts(tmp_path: Path) -> None:
    result, calls = _run_smoke(tmp_path, images_local=False, pull_ok=False)
    combined = f"{result.stdout}\n{result.stderr}"

    assert result.returncode == 2, combined
    assert "neither local nor pullable" in result.stderr, combined
    # `sort -u` puts juniper-data first, so its pull is the one that fails; three attempts.
    assert _pulls(calls) == [DATA_IMAGE] * 3, calls
    assert _compose_calls(calls, "up") == [], calls
    assert "unexpected EOF" in result.stderr, combined


def test_a_missing_image_is_pulled_once_and_up_never_builds(tmp_path: Path) -> None:
    result, calls = _run_smoke(tmp_path, images_local=False, pull_ok=True)
    combined = f"{result.stdout}\n{result.stderr}"

    assert result.returncode == 1, combined  # the stub's `up` stops the run
    assert sorted(_pulls(calls)) == sorted([RECURRENCE_IMAGE, DATA_IMAGE]), calls
    ups = _compose_calls(calls, "up")
    assert len(ups) == 1, calls
    assert "--no-build" in ups[0], ups
    assert ups[0][-1] == "juniper-recurrence", ups
    assert f"images resolved by compose: {DATA_IMAGE} {RECURRENCE_IMAGE}" in result.stdout, combined


def test_a_local_image_is_used_as_it_is(tmp_path: Path) -> None:
    result, calls = _run_smoke(tmp_path, images_local=True, pull_ok=False)
    combined = f"{result.stdout}\n{result.stderr}"

    assert result.returncode == 1, combined
    assert _pulls(calls) == [], calls
    ups = _compose_calls(calls, "up")
    assert len(ups) == 1 and "--no-build" in ups[0], calls


# A message that merely names `compose up` (fail "docker compose up failed") is not an invocation.
_MESSAGE = re.compile(r'\b(?:fail|info|pass|echo)\s+"[^"]*"')
_COMPOSE_UP = re.compile(r"\bcompose\s+up\b")


def test_every_compose_up_in_the_recurrence_smokes_passes_no_build() -> None:
    for script in NO_BUILD_SMOKES:
        invocations = []
        for number, line in enumerate(script.read_text(encoding="utf-8").splitlines(), start=1):
            if line.lstrip().startswith("#"):
                continue
            if _COMPOSE_UP.search(_MESSAGE.sub("", line)):
                invocations.append((number, line.strip()))
        assert invocations, f"{script.name}: found no `compose up`, so this check would pass vacuously"
        building = [f"{script.name}:{number}: {line}" for number, line in invocations if "--no-build" not in line]
        assert building == [], "every `compose up` in a recurrence smoke must pass --no-build (juniper-deploy#250): " + "; ".join(building)
