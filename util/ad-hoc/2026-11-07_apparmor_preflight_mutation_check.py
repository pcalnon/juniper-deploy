#!/usr/bin/env python3
"""
Mutation check: tests/test_apparmor_preflight.py must FAIL on every seeded defect in scripts/preflight_apparmor.sh.

Project: Juniper
Application: juniper-deploy
Author: Paul Calnon
Created: 2026-11-07
Status: ad-hoc — test-efficacy evidence for the AppArmor-interface preflight
Retire when: RETAINED — kept as provenance of how the suite's efficacy was measured
Related: scripts/preflight_apparmor.sh, tests/test_apparmor_preflight.py,
         juniper-ml notes/JUNIPER_2026-11-07_JUNIPER-ECOSYSTEM_YAMAGUCHI-SECURITYFS-UNMOUNT-ROOT-CAUSE-ANALYSIS.md

A green suite proves nothing if it also passes a broken preflight. Each mutant re-creates a
plausible defect -- reading the wrong mount, trusting a stale cache, asking the daemon when it
need not, exiting 0 on the failure path -- and the suite is run against it through
APPARMOR_PREFLIGHT_SCRIPT. A surviving mutant is reported and the script exits 1.

Mutants are written under the repo's tmp/ (never /tmp); the suite's exit status is read directly.

Usage: python3 util/ad-hoc/2026-11-07_apparmor_preflight_mutation_check.py
Exit:  0 every mutant killed; 1 a mutant survived or an edit did not apply.
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "scripts" / "preflight_apparmor.sh"
SUITE = "tests/test_apparmor_preflight.py"

# (name, old, new): `old` must occur exactly once in the preflight.
MUTANTS = [
    ("securityfs always reported mounted", "    securityfs_mounted=1\nfi", "    :\nfi\nsecurityfs_mounted=1"),
    ("interface always present", '[[ -e "$(sys_path /sys/kernel/security/apparmor/profiles)" ]] && interface=1', "interface=1"),
    ("dockerd always reported using AppArmor", "[[ \"$SECURITY_OPTIONS\" == *'\"name=apparmor\"'* ]] && daemon_apparmor=1", "daemon_apparmor=1"),
    ("kernel Y not recognised", '[[ "$enabled_raw" == Y* ]] && kernel_enabled=1', '[[ "$enabled_raw" == Yes ]] && kernel_enabled=1'),
    ("FAIL path exits 0", 'printf \'%spreflight_apparmor: AppArmor interface missing. Bypass with JUNIPER_APPARMOR_OK=1.%s\\n\' "$RED" "$RESET" >&2\nexit 1', 'printf \'%spreflight_apparmor: AppArmor interface missing. Bypass with JUNIPER_APPARMOR_OK=1.%s\\n\' "$RED" "$RESET" >&2\nexit 0'),
    ("WARN path blocks bring-up", "    printf '         See %s.\\n' \"$RUNBOOK\"\n    exit 0", "    printf '         See %s.\\n' \"$RUNBOOK\"\n    exit 1"),
    ("bypass ignored", '[[ "${JUNIPER_APPARMOR_OK:-0}" == "1" ]]', '[[ "${JUNIPER_APPARMOR_OK:-0}" == "on" ]]'),
    ("first mount at the point wins", "sep && $5 == \"/sys/kernel/security\" { top = $(sep + 1) }", "sep && $5 == \"/sys/kernel/security\" && !top { top = $(sep + 1) }"),
    ("fstype read from the wrong field", "top = $(sep + 1)", "top = $(sep + 2)"),
    ("remount drops noexec", 'REMOUNT="sudo mount -t securityfs -o nosuid,nodev,noexec securityfs /sys/kernel/security"', 'REMOUNT="sudo mount -t securityfs -o nosuid,nodev securityfs /sys/kernel/security"'),
    ("daemon error text drifts", 'DOCKER_ERROR="Could not check if docker-default AppArmor profile was loaded:', 'DOCKER_ERROR="Could not verify the docker-default AppArmor profile:'),
    ("daemon asked even when AppArmor is off", 'if [[ "$kernel_enabled" -eq 0 ]]; then\n    printf', 'SECURITY_OPTIONS="$("$DOCKER_BIN" info --format \'{{json .SecurityOptions}}\' 2>/dev/null || true)"\nif [[ "$kernel_enabled" -eq 0 ]]; then\n    printf'),
    ("unreachable daemon treated as no AppArmor", '        echo "preflight_apparmor: could not query the Docker daemon', '        SECURITY_OPTIONS="[]"; : echo "preflight_apparmor: could not query the Docker daemon'),
    ("restart advised before the remount", "    printf '         %s\\n' \"$REMOUNT\"\n    printf '         then restart dockerd", "    printf '         first restart dockerd: sudo systemctl restart docker\\n'\n    printf '         %s\\n' \"$REMOUNT\"\n    printf '         then restart dockerd"),
]


def main() -> int:
    source = SCRIPT.read_text(encoding="utf-8")
    tmp_root = Path(os.environ.get("TMPDIR") or (REPO / "tmp"))
    tmp_root.mkdir(parents=True, exist_ok=True)
    failures = 0
    baseline = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", SUITE], cwd=REPO, capture_output=True, text=True, check=False)
    print(f"baseline (unmutated): exit={baseline.returncode}  {baseline.stdout.strip().splitlines()[-1] if baseline.stdout.strip() else ''}")
    if baseline.returncode != 0:
        print(baseline.stdout[-3000:] + baseline.stderr[-2000:])
        return 1
    with tempfile.TemporaryDirectory(dir=tmp_root, prefix="apparmor_preflight_mutants_") as work:
        for index, (name, old, new) in enumerate(MUTANTS, 1):
            if source.count(old) != 1:
                print(f"[EDIT-FAILED] {name}: anchor occurs {source.count(old)} times")
                failures += 1
                continue
            mutant = Path(work) / f"mutant_{index:02d}.sh"
            mutant.write_text(source.replace(old, new), encoding="utf-8")
            env = dict(os.environ, APPARMOR_PREFLIGHT_SCRIPT=str(mutant))
            result = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", SUITE], cwd=REPO, env=env, capture_output=True, text=True, check=False)
            verdict = "KILLED" if result.returncode != 0 else "SURVIVED"
            if verdict == "SURVIVED":
                failures += 1
            summary = result.stdout.strip().splitlines()[-1] if result.stdout.strip() else "no summary"
            print(f"[{verdict}] {name}  ({summary})")
    print(f"{len(MUTANTS) - failures} of {len(MUTANTS)} mutants killed")
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
