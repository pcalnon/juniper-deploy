#!/usr/bin/env python
#####################################################################################################################################################################################################
# Project:       Juniper
# Application:   juniper-deploy
# File Name:     test_snapshot_root_preflight.py
# Author:        Paul Calnon
#
# Date Created:  2026-10-05
#
# License:       MIT License
# Copyright:     Copyright (c) 2024-2026 Paul Calnon
#
# Description:
#    Offline behavioural gate for scripts/preflight_snapshot_root.sh, the bring-up check that
#    every bind-mounted snapshot root exists and is writable BEFORE `docker compose up`. The
#    failure it prevents is silent: the daemon creates a missing bind source root-owned, and
#    the stack comes up healthy over an empty archive whose every save then fails.
#
#    Hermetic: the script is driven with --config-json (a pre-rendered compose config), so no
#    Docker daemon is touched. Pins:
#
#      (a) both roots -- cascor's /app/cascor-snapshots (.h5) and recurrence's
#          /app/recurrence-snapshots (.npz, W1.12) -- are checked, and pass when usable
#      (b) a missing root FAILS, names the variable that relocates THAT root, and is not
#          created by the check
#      (c) the artifact count is per root: .h5 for cascor, .npz for recurrence
#      (d) NOTDIR and READONLY fail; JUNIPER_SNAPSHOT_ROOT_OK=1 bypasses both roots
#      (e) other bind targets are ignored, and a source shared by several services is
#          reported once
#      (f) every *-snapshots mount target in docker-compose.yml is in the script's table, so a
#          new snapshot root cannot ship unchecked
#      (g) every Makefile bring-up target runs it before `docker compose ... up` -- obs-demo
#          did not until W1.12, although it starts juniper-recurrence and cascor-demo
#
#####################################################################################################################################################################################################

from __future__ import annotations

import json
import os
import re
import subprocess
from pathlib import Path

import pytest
import yaml

from tests.redacted_env import RedactedEnv

REPO_ROOT = Path(__file__).resolve().parents[1]
PREFLIGHT = REPO_ROOT / "scripts" / "preflight_snapshot_root.sh"
COMPOSE_PATH = REPO_ROOT / "docker-compose.yml"
MAKEFILE_PATH = REPO_ROOT / "Makefile"

#: The targets that bring services up, as tests/test_image_provenance_preflight.py names them.
BRING_UP_TARGETS = ("up", "demo", "dev", "monitor", "obs-demo")

CASCOR = "/app/cascor-snapshots"
RECURRENCE = "/app/recurrence-snapshots"

#: Trailing access/consistency modes a short-syntax volume entry may carry after its target.
_MODES = {"ro", "rw", "z", "Z", "cached", "delegated", "consistent"}


def _render(tmp_path: Path, mounts: list[tuple[str, Path]]) -> Path:
    """A minimal `docker compose config --format json` render: one service per (target, source)."""
    services = {f"svc-{index}": {"volumes": [{"type": "bind", "source": str(source), "target": target}]} for index, (target, source) in enumerate(mounts)}
    path = tmp_path / "render.json"
    path.write_text(json.dumps({"services": services}), encoding="utf-8")
    return path


def _run(tmp_path: Path, render: Path, **env_overrides: str) -> subprocess.CompletedProcess[str]:
    # JUNIPER_ROOT=tmp_path puts every synthetic root inside "the Juniper tree", so the OUTSIDE
    # warning never muddies these assertions.
    env = RedactedEnv(os.environ, NO_COLOR="1", JUNIPER_ROOT=str(tmp_path), **env_overrides)
    if "JUNIPER_SNAPSHOT_ROOT_OK" not in env_overrides:
        env.pop("JUNIPER_SNAPSHOT_ROOT_OK", None)
    return subprocess.run(["bash", str(PREFLIGHT), "--config-json", str(render)], cwd=REPO_ROOT, env=env, capture_output=True, text=True, check=False, timeout=60)


def _root(tmp_path: Path, name: str, *artifacts: str) -> Path:
    root = tmp_path / name
    root.mkdir()
    for artifact in artifacts:
        (root / artifact).write_bytes(b"")
    return root.resolve()


def _short_target(volume: str) -> str:
    """The container path of a short-syntax entry; the source may itself hold colons."""
    parts = volume.split(":")
    if len(parts) > 2 and parts[-1] in _MODES:
        parts = parts[:-1]
    return parts[-1]


# ── (a) both roots ───────────────────────────────────────────────────────────


def test_both_roots_are_checked_and_pass_when_usable(tmp_path: Path) -> None:
    cascor = _root(tmp_path, "cascor-snapshots", "run.h5")
    recurrence = _root(tmp_path, "recurrence-snapshots", "lmu-1.npz", "lmu-2.npz")
    result = _run(tmp_path, _render(tmp_path, [(CASCOR, cascor), (RECURRENCE, recurrence)]))
    assert result.returncode == 0, result.stdout + result.stderr
    assert f"[OK]         {cascor} (1 .h5)" in result.stdout
    assert f"[OK]         {recurrence} (2 .npz)" in result.stdout


# ── (b) a missing root ───────────────────────────────────────────────────────


def test_missing_recurrence_root_fails_and_names_its_variable(tmp_path: Path) -> None:
    cascor = _root(tmp_path, "cascor-snapshots", "run.h5")
    missing = tmp_path / "recurrence-snapshots"
    result = _run(tmp_path, _render(tmp_path, [(CASCOR, cascor), (RECURRENCE, missing)]))
    assert result.returncode == 1, result.stdout + result.stderr
    assert f"[MISSING]    {missing}" in result.stdout
    assert "JUNIPER_RECURRENCE_SNAPSHOTS_HOST_DIR at the real root" in result.stdout
    assert "JUNIPER_CASCOR_SNAPSHOTS_HOST_DIR" not in result.stdout, "the cascor root is usable; only the recurrence variable belongs in the remedy"
    assert "1 unusable snapshot root(s)" in result.stderr
    assert not missing.exists(), "the preflight is read-only; it must not create the root it reports"


def test_missing_cascor_root_still_names_the_cascor_variable(tmp_path: Path) -> None:
    missing = tmp_path / "cascor-snapshots"
    result = _run(tmp_path, _render(tmp_path, [(CASCOR, missing)]))
    assert result.returncode == 1, result.stdout + result.stderr
    assert f"[MISSING]    {missing}" in result.stdout
    assert "JUNIPER_CASCOR_SNAPSHOTS_HOST_DIR at the real root" in result.stdout


# ── (c) per-root artifact counts ─────────────────────────────────────────────


def test_artifact_count_is_per_root(tmp_path: Path) -> None:
    # Each root holds only the OTHER service's artifact type, so both must read as empty.
    cascor = _root(tmp_path, "cascor-snapshots", "stray.npz")
    recurrence = _root(tmp_path, "recurrence-snapshots", "stray.h5")
    result = _run(tmp_path, _render(tmp_path, [(CASCOR, cascor), (RECURRENCE, recurrence)]))
    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stdout.count("[EMPTY]") == 2, result.stdout
    assert "no .h5 present" in result.stdout
    assert "no .npz present" in result.stdout


# ── (d) unusable roots, and the bypass ───────────────────────────────────────


def test_a_file_where_the_root_should_be_fails(tmp_path: Path) -> None:
    not_a_dir = tmp_path / "recurrence-snapshots"
    not_a_dir.write_text("", encoding="utf-8")
    result = _run(tmp_path, _render(tmp_path, [(RECURRENCE, not_a_dir)]))
    assert result.returncode == 1, result.stdout + result.stderr
    assert f"[NOTDIR]     {not_a_dir}" in result.stdout


@pytest.mark.skipif(os.geteuid() == 0, reason="root can write a 0555 directory, so READONLY cannot be provoked")
def test_an_unwritable_root_fails(tmp_path: Path) -> None:
    root = _root(tmp_path, "recurrence-snapshots")
    root.chmod(0o555)
    try:
        result = _run(tmp_path, _render(tmp_path, [(RECURRENCE, root)]))
    finally:
        root.chmod(0o755)
    assert result.returncode == 1, result.stdout + result.stderr
    assert f"[READONLY]   {root}" in result.stdout


def test_bypass_covers_both_roots(tmp_path: Path) -> None:
    render = _render(tmp_path, [(CASCOR, tmp_path / "absent-cascor"), (RECURRENCE, tmp_path / "absent-recurrence")])
    result = _run(tmp_path, render, JUNIPER_SNAPSHOT_ROOT_OK="1")
    assert result.returncode == 0, result.stdout + result.stderr
    assert "bypassed (JUNIPER_SNAPSHOT_ROOT_OK=1)" in result.stdout


# ── (e) scope and de-duplication ─────────────────────────────────────────────


def test_other_targets_are_ignored_and_a_shared_source_is_reported_once(tmp_path: Path) -> None:
    cascor = _root(tmp_path, "cascor-snapshots", "run.h5")
    render = _render(tmp_path, [(CASCOR, cascor), (CASCOR, cascor), ("/etc/grafana/provisioning", tmp_path / "nowhere")])
    result = _run(tmp_path, render)
    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stdout.count("[OK]") == 1, result.stdout
    assert "nowhere" not in result.stdout


def test_a_render_without_snapshot_roots_has_nothing_to_check(tmp_path: Path) -> None:
    result = _run(tmp_path, _render(tmp_path, [("/app/logs", tmp_path / "logs")]))
    assert result.returncode == 0, result.stdout + result.stderr
    assert "nothing to check" in result.stdout


# ── (f) the table covers every snapshot root compose declares ────────────────


def test_every_snapshot_mount_in_compose_is_in_the_preflight_table() -> None:
    compose = yaml.safe_load(COMPOSE_PATH.read_text(encoding="utf-8"))
    targets = set()
    for svc in (compose.get("services") or {}).values():
        for volume in (svc or {}).get("volumes") or []:
            target = volume.get("target", "") if isinstance(volume, dict) else _short_target(str(volume))
            if target.endswith("-snapshots"):
                targets.add(target)
    # The census itself is pinned, so a new snapshot root is noticed here rather than at a
    # silent bring-up: add it to SNAPSHOT_ROOTS in the preflight, then to this set.
    assert targets == {CASCOR, RECURRENCE}, f"snapshot-root mount targets in docker-compose.yml: {sorted(targets)}"
    script = PREFLIGHT.read_text(encoding="utf-8")
    for target in sorted(targets):
        assert f'"{target}|' in script, f"{target} is bind-mounted in docker-compose.yml but missing from SNAPSHOT_ROOTS in {PREFLIGHT.name}"


# ── (g) every bring-up target runs it ────────────────────────────────────────


def _recipe_of(makefile: str, target: str) -> list[str]:
    match = re.search(rf"^{re.escape(target)}:.*$", makefile, flags=re.MULTILINE)
    assert match, f"Makefile target {target!r} not found"
    lines = []
    for line in makefile[match.end() :].splitlines()[1:]:
        if line.startswith("\t"):
            lines.append(line)
        elif line.strip() == "" or line.lstrip().startswith("#"):
            continue
        else:
            break
    return lines


def test_every_bring_up_target_checks_the_snapshot_roots_before_up() -> None:
    makefile = MAKEFILE_PATH.read_text(encoding="utf-8")
    assert "SNAPSHOT_PREFLIGHT := bash scripts/preflight_snapshot_root.sh" in makefile
    for target in BRING_UP_TARGETS:
        joined = "\n".join(_recipe_of(makefile, target))
        assert "$(SNAPSHOT_PREFLIGHT)" in joined, f"`make {target}` brings services up without $(SNAPSHOT_PREFLIGHT)"
        assert "up -d" in joined, f"`make {target}` no longer runs `docker compose ... up -d`; update BRING_UP_TARGETS"
        assert joined.index("$(SNAPSHOT_PREFLIGHT)") < joined.index("up -d"), f"`make {target}` must check the snapshot roots BEFORE `docker compose ... up`"
