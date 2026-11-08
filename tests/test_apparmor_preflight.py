#!/usr/bin/env python
#####################################################################################################################################################################################################
# Project:       Juniper
# Application:   juniper-deploy
# File Name:     test_apparmor_preflight.py
# Author:        Paul Calnon
#
# Date Created:  2026-11-07
#
# License:       MIT License
# Copyright:     Copyright (c) 2024-2026 Paul Calnon
#
# Description:
#    Offline behavioural gate for scripts/preflight_apparmor.sh, the bring-up check that dockerd can
#    load its docker-default AppArmor profile BEFORE `docker compose up`. The incident it encodes
#    (yamaguchi, 2026-10-27 / 2026-11-07): securityfs was unmounted from /sys/kernel/security while
#    dockerd -- which decides "AppArmor supported" once, at start -- kept applying docker-default,
#    so every container start failed with "Could not check if docker-default AppArmor profile was
#    loaded: open /sys/kernel/security/apparmor/profiles: no such file or directory".
#
#    Hermetic: --sys-root / --mountinfo / --security-options replace the host, and a PATH stub
#    replaces `docker` where the daemon query itself is under test. Pins:
#
#      (a) a healthy host passes [OK]; a kernel without AppArmor passes [SKIP]
#      (b) the incident, as yamaguchi had it (its real mount lines and SecurityOptions), FAILS,
#          quotes Docker's error, names the missing mount and the remount command, warns against
#          restarting dockerd, and points at the runbook
#      (c) the same host after a dockerd restart (AppArmor dropped from SecurityOptions) FAILS as
#          "WITHOUT AppArmor confinement", and its fix adds the dockerd restart
#      (d) securityfs mounted without an apparmor/ directory is told apart from securityfs missing
#      (e) interface present but dockerd not using AppArmor passes with [WARN]
#      (f) the daemon is asked only when AppArmor is on, through `docker info`; an unreachable
#          daemon exits 2; JUNIPER_APPARMOR_OK=1 bypasses; bad arguments exit 2
#      (g) the check is read-only
#      (h) every Makefile bring-up target runs it before `docker compose ... up`, and
#          `make apparmor-preflight` exists
#
#####################################################################################################################################################################################################

from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path

import pytest

from tests.redacted_env import RedactedEnv

REPO_ROOT = Path(__file__).resolve().parents[1]
# Overridable only so util/ad-hoc/2026-11-07_apparmor_preflight_mutation_check.py can run this suite on mutants.
PREFLIGHT = Path(os.environ.get("APPARMOR_PREFLIGHT_SCRIPT", str(REPO_ROOT / "scripts" / "preflight_apparmor.sh")))
MAKEFILE_PATH = REPO_ROOT / "Makefile"

#: The targets that bring services up, as tests/test_snapshot_root_preflight.py names them.
BRING_UP_TARGETS = ("up", "demo", "dev", "monitor", "obs-demo")

DOCKER_ERROR = "Could not check if docker-default AppArmor profile was loaded: open /sys/kernel/security/apparmor/profiles: no such file or directory"
REMOUNT = "sudo mount -t securityfs -o nosuid,nodev,noexec securityfs /sys/kernel/security"
RUNBOOK = "JUNIPER_2026-11-07_JUNIPER-ECOSYSTEM_YAMAGUCHI-API-FILESYSTEM-REMOUNT-RUNBOOK.md"

#: yamaguchi's dockerd on 2026-11-07 (`docker info --format '{{json .SecurityOptions}}'`).
OPTS_APPARMOR = '["name=apparmor","name=seccomp,profile=builtin","name=cgroupns"]'
#: The same daemon had it been restarted after securityfs vanished: HostSupports() is false.
OPTS_NO_APPARMOR = '["name=seccomp,profile=builtin","name=cgroupns"]'

#: yamaguchi's /proc/self/mountinfo, the /sys lines, 2026-11-08: no securityfs.
MOUNTINFO_INCIDENT = """\
28 33 0:25 / /sys rw,nosuid,nodev,noexec,relatime shared:6 - sysfs sysfs rw
33 2 259:5 / / rw,relatime shared:1 - ext4 /dev/nvme0n1p5 rw
36 28 0:30 / /sys/fs/cgroup rw,nosuid,nodev,noexec,relatime shared:8 - cgroup2 cgroup2 rw,nsdelegate,memory_recursiveprot,memory_hugetlb_accounting
14679 28 0:14 / /sys/kernel/tracing rw,nosuid,nodev,noexec,relatime shared:8172 - tracefs tracefs rw
14709 28 0:9 / /sys/kernel/debug rw,nosuid,nodev,noexec,relatime shared:8191 - debugfs debugfs rw
14739 28 0:21 / /sys/kernel/config rw,nosuid,nodev,noexec,relatime shared:8210 - configfs configfs rw
"""
SECURITYFS_LINE = "40 28 0:8 / /sys/kernel/security rw,nosuid,nodev,noexec,relatime shared:7 - securityfs securityfs rw\n"
MOUNTINFO_HEALTHY = MOUNTINFO_INCIDENT + SECURITYFS_LINE


def _host(tmp_path: Path, *, enabled: str | None = "Y\n", interface: bool = True, mountinfo: str = MOUNTINFO_HEALTHY) -> tuple[Path, Path]:
    root = tmp_path / "root"
    (root / "sys").mkdir(parents=True)
    if enabled is not None:
        param = root / "sys/module/apparmor/parameters/enabled"
        param.parent.mkdir(parents=True)
        param.write_text(enabled, encoding="ascii")
    if interface:
        profiles = root / "sys/kernel/security/apparmor/profiles"
        profiles.parent.mkdir(parents=True)
        profiles.write_text("docker-default (enforce)\n", encoding="ascii")
    table = tmp_path / "mountinfo"
    table.write_text(mountinfo, encoding="utf-8")
    return root, table


def _run(*args: str, **env_overrides: str) -> subprocess.CompletedProcess[str]:
    env = RedactedEnv(os.environ, NO_COLOR="1", **env_overrides)
    if "JUNIPER_APPARMOR_OK" not in env_overrides:
        env.pop("JUNIPER_APPARMOR_OK", None)
    return subprocess.run(["bash", str(PREFLIGHT), *args], cwd=REPO_ROOT, env=env, capture_output=True, text=True, check=False, timeout=60)


def _offline(root: Path, table: Path, options: str, **env_overrides: str) -> subprocess.CompletedProcess[str]:
    return _run("--sys-root", str(root), "--mountinfo", str(table), "--security-options", options, **env_overrides)


# ── (a) pass cases ───────────────────────────────────────────────────────────


def test_healthy_host_passes(tmp_path: Path) -> None:
    root, table = _host(tmp_path)
    result = _offline(root, table, OPTS_APPARMOR)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "[OK]" in result.stdout
    assert "kernel=Y  securityfs on /sys/kernel/security=mounted  interface=present  dockerd AppArmor=yes" in result.stdout


@pytest.mark.parametrize("enabled", ["N\n", None], ids=["module-says-N", "no-apparmor-module"])
def test_kernel_without_apparmor_is_skipped(tmp_path: Path, enabled: str | None) -> None:
    root, table = _host(tmp_path, enabled=enabled, interface=False, mountinfo=MOUNTINFO_INCIDENT)
    result = _offline(root, table, OPTS_NO_APPARMOR)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "[SKIP]" in result.stdout


# ── (b) the incident ─────────────────────────────────────────────────────────


def test_yamaguchi_incident_fails_and_names_the_mount(tmp_path: Path) -> None:
    root, table = _host(tmp_path, interface=False, mountinfo=MOUNTINFO_INCIDENT)
    result = _offline(root, table, OPTS_APPARMOR)
    assert result.returncode == 1, result.stdout + result.stderr
    out = result.stdout
    assert "[FAIL]" in out
    assert DOCKER_ERROR in out, "the operator must be able to match this to the daemon's own error"
    assert "kernel=Y  securityfs on /sys/kernel/security=MISSING  interface=MISSING  dockerd AppArmor=yes" in out
    assert "securityfs is NOT mounted on /sys/kernel/security" in out
    assert "no unit file" in out
    assert REMOUNT in out
    assert "Do NOT restart dockerd" in out
    assert RUNBOOK in out
    assert "Bypass with JUNIPER_APPARMOR_OK=1" in result.stderr


# ── (c) the same host after a dockerd restart ────────────────────────────────


def test_incident_after_a_dockerd_restart_fails_as_unconfined(tmp_path: Path) -> None:
    root, table = _host(tmp_path, interface=False, mountinfo=MOUNTINFO_INCIDENT)
    result = _offline(root, table, OPTS_NO_APPARMOR)
    assert result.returncode == 1, result.stdout + result.stderr
    assert "WITHOUT AppArmor confinement" in result.stdout
    assert "dockerd AppArmor=no" in result.stdout
    assert REMOUNT in result.stdout
    assert "sudo systemctl restart docker" in result.stdout
    assert result.stdout.index(REMOUNT) < result.stdout.index("sudo systemctl restart docker"), "remount first, then restart"


# ── (d) securityfs mounted, AppArmor directory absent ───────────────────────


def test_securityfs_mounted_without_apparmor_dir_is_reported_as_such(tmp_path: Path) -> None:
    root, table = _host(tmp_path, interface=False, mountinfo=MOUNTINFO_HEALTHY)
    result = _offline(root, table, OPTS_APPARMOR)
    assert result.returncode == 1, result.stdout + result.stderr
    assert "securityfs is mounted on /sys/kernel/security, but it has no apparmor/ directory" in result.stdout


def test_the_filesystem_type_decides_not_the_source_name(tmp_path: Path) -> None:
    """`mount -t securityfs none /sys/kernel/security` names its source `none`; a tmpfs may be named `securityfs`."""
    by_type = MOUNTINFO_INCIDENT + "40 28 0:8 / /sys/kernel/security rw,nosuid,nodev,noexec,relatime shared:7 - securityfs none rw\n"
    root, table = _host(tmp_path / "a", interface=False, mountinfo=by_type)
    assert "securityfs on /sys/kernel/security=mounted" in _offline(root, table, OPTS_APPARMOR).stdout
    decoy = MOUNTINFO_INCIDENT + "40 28 0:99 / /sys/kernel/security rw shared:7 - tmpfs securityfs rw\n"
    root, table = _host(tmp_path / "b", interface=False, mountinfo=decoy)
    assert "securityfs on /sys/kernel/security=MISSING" in _offline(root, table, OPTS_APPARMOR).stdout


def test_a_mount_stacked_over_securityfs_counts_as_missing(tmp_path: Path) -> None:
    covered = MOUNTINFO_HEALTHY + "41 40 0:99 / /sys/kernel/security rw shared:99 - tmpfs tmpfs rw\n"
    root, table = _host(tmp_path, interface=False, mountinfo=covered)
    result = _offline(root, table, OPTS_APPARMOR)
    assert result.returncode == 1
    assert "securityfs on /sys/kernel/security=MISSING" in result.stdout


# ── (e) interface present, dockerd not using it ──────────────────────────────


def test_interface_present_but_dockerd_without_apparmor_warns(tmp_path: Path) -> None:
    root, table = _host(tmp_path)
    result = _offline(root, table, OPTS_NO_APPARMOR)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "[WARN]" in result.stdout
    assert "WITHOUT AppArmor until dockerd restarts" in result.stdout


# ── (f) the daemon query, bypass, arguments ──────────────────────────────────


def _docker_stub(tmp_path: Path, payload: str, exit_code: int = 0) -> Path:
    stub = tmp_path / "bin" / "docker"
    stub.parent.mkdir(parents=True, exist_ok=True)
    log = tmp_path / "docker-argv.log"
    stub.write_text(f'#!/usr/bin/env bash\nprintf "%s\\n" "$*" >> "{log}"\nprintf \'%s\\n\' \'{payload}\'\nexit {exit_code}\n', encoding="utf-8")
    stub.chmod(0o755)
    return stub


def test_daemon_is_asked_through_docker_info(tmp_path: Path) -> None:
    root, table = _host(tmp_path, interface=False, mountinfo=MOUNTINFO_INCIDENT)
    stub = _docker_stub(tmp_path, OPTS_APPARMOR)
    result = _run("--sys-root", str(root), "--mountinfo", str(table), DOCKER=str(stub))
    assert result.returncode == 1, result.stdout + result.stderr
    assert DOCKER_ERROR in result.stdout
    assert (tmp_path / "docker-argv.log").read_text(encoding="utf-8").strip() == "info --format {{json .SecurityOptions}}"


def test_daemon_is_not_asked_when_apparmor_is_off(tmp_path: Path) -> None:
    root, table = _host(tmp_path, enabled="N\n", interface=False)
    stub = _docker_stub(tmp_path, OPTS_APPARMOR)
    result = _run("--sys-root", str(root), "--mountinfo", str(table), DOCKER=str(stub))
    assert result.returncode == 0, result.stdout + result.stderr
    assert not (tmp_path / "docker-argv.log").exists()


def test_unreachable_daemon_exits_2(tmp_path: Path) -> None:
    root, table = _host(tmp_path, interface=False, mountinfo=MOUNTINFO_INCIDENT)
    stub = _docker_stub(tmp_path, "", exit_code=1)
    result = _run("--sys-root", str(root), "--mountinfo", str(table), DOCKER=str(stub))
    assert result.returncode == 2, result.stdout + result.stderr
    assert "could not query the Docker daemon" in result.stderr


def test_bypass(tmp_path: Path) -> None:
    root, table = _host(tmp_path, interface=False, mountinfo=MOUNTINFO_INCIDENT)
    result = _offline(root, table, OPTS_APPARMOR, JUNIPER_APPARMOR_OK="1")
    assert result.returncode == 0
    assert "bypassed (JUNIPER_APPARMOR_OK=1)" in result.stdout


def test_unknown_argument_and_unreadable_table_exit_2(tmp_path: Path) -> None:
    assert _run("--profile", "full").returncode == 2
    root, _ = _host(tmp_path)
    assert _run("--sys-root", str(root), "--mountinfo", str(tmp_path / "absent"), "--security-options", OPTS_APPARMOR).returncode == 2


def test_help_prints_the_description() -> None:
    result = _run("--help")
    assert result.returncode == 0
    assert "AppArmor-interface preflight" in result.stdout
    assert "Exit codes:" in result.stdout


# ── (g) read-only ────────────────────────────────────────────────────────────


def test_the_check_changes_nothing(tmp_path: Path) -> None:
    root, table = _host(tmp_path, interface=False, mountinfo=MOUNTINFO_INCIDENT)
    before = sorted(str(path.relative_to(tmp_path)) for path in tmp_path.rglob("*"))
    _offline(root, table, OPTS_APPARMOR)
    after = sorted(str(path.relative_to(tmp_path)) for path in tmp_path.rglob("*"))
    assert before == after


# ── (h) every bring-up target runs it ────────────────────────────────────────


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


def test_every_bring_up_target_checks_apparmor_before_up() -> None:
    makefile = MAKEFILE_PATH.read_text(encoding="utf-8")
    assert "APPARMOR_PREFLIGHT := bash scripts/preflight_apparmor.sh" in makefile
    for target in BRING_UP_TARGETS:
        joined = "\n".join(_recipe_of(makefile, target))
        assert "$(APPARMOR_PREFLIGHT)" in joined, f"`make {target}` brings services up without $(APPARMOR_PREFLIGHT)"
        assert "up -d" in joined, f"`make {target}` no longer runs `docker compose ... up -d`; update BRING_UP_TARGETS"
        assert joined.index("$(APPARMOR_PREFLIGHT)") < joined.index("up -d"), f"`make {target}` must check AppArmor BEFORE `docker compose ... up`"


def test_standalone_target_exists_and_is_phony() -> None:
    makefile = MAKEFILE_PATH.read_text(encoding="utf-8")
    assert "$(APPARMOR_PREFLIGHT)" in "\n".join(_recipe_of(makefile, "apparmor-preflight"))
    phony = re.search(r"^\.PHONY:(.*?)(?:\n(?!\s))", makefile, flags=re.MULTILINE | re.DOTALL)
    assert phony and "apparmor-preflight" in phony.group(1).split()
