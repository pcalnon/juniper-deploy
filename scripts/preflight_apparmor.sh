#!/usr/bin/env bash
#####################################################################################################################################################################################################
# Project:       Juniper
# Application:   juniper-deploy
# File Name:     preflight_apparmor.sh
# Author:        Paul Calnon
#
# Date Created:  2026-11-07
# Last Modified: 2026-11-07
#
# License:       MIT License
# Copyright:     Copyright (c) 2024-2026 Paul Calnon
#
# Description:
#    AppArmor-interface preflight for `make up` / `demo` / `dev` / `monitor` / `obs-demo`.
#
#    Docker applies its `docker-default` AppArmor profile to every container that is not
#    privileged and names no profile of its own -- every service in this stack. Before each
#    start it checks that the profile is loaded by reading
#    /sys/kernel/security/apparmor/profiles, an interface that exists only while securityfs is
#    mounted on /sys/kernel/security.
#
#    WHY THIS PREFLIGHT EXISTS (incident of record, yamaguchi, 2026-10-27 / 2026-11-07).
#
#    A root `umount -a`-like event unmounted every filesystem not in use, securityfs among them.
#    systemd's PID 1 mounts securityfs itself at boot; it has no unit file, so nothing remounts
#    it and `systemctl` cannot even list it once it is gone. dockerd computes "does this host
#    support AppArmor?" ONCE, at daemon start (containerd's apparmor.HostSupports, a sync.Once),
#    so a daemon started before the unmount keeps answering yes. Eleven days later `make up`
#    created every container and started none:
#
#      Error response from daemon: Could not check if docker-default AppArmor profile was
#      loaded: open /sys/kernel/security/apparmor/profiles: no such file or directory
#
#    The message names a profile; the cause is a missing mount. This check names the mount.
#    Analysis: juniper-ml notes/JUNIPER_2026-11-07_JUNIPER-ECOSYSTEM_YAMAGUCHI-SECURITYFS-UNMOUNT-ROOT-CAUSE-ANALYSIS.md
#    Remedy:   juniper-ml notes/JUNIPER_2026-11-07_JUNIPER-ECOSYSTEM_YAMAGUCHI-API-FILESYSTEM-REMOUNT-RUNBOOK.md
#
#    Facts read (none needs root):
#
#      kernel    /sys/module/apparmor/parameters/enabled   (Y = AppArmor is the active LSM)
#      mount     /proc/self/mountinfo                      (is securityfs on /sys/kernel/security?)
#      interface /sys/kernel/security/apparmor/profiles     (what dockerd opens)
#      daemon    docker info  SecurityOptions               (name=apparmor = dockerd applies docker-default)
#
#    Verdicts:
#
#      [OK]    AppArmor enabled, interface present, dockerd confines with it      -> pass
#      [SKIP]  AppArmor not enabled in the kernel: nothing to check               -> pass
#      [WARN]  interface present but dockerd does not use AppArmor (a daemon
#              started while the interface was missing): containers run
#              unconfined until dockerd restarts                                 -> pass, warned
#      [FAIL]  AppArmor enabled, interface MISSING, dockerd uses AppArmor:
#              every container start fails with the error above                  -> fail
#      [FAIL]  AppArmor enabled, interface MISSING, dockerd does not use it:
#              containers would start WITHOUT AppArmor confinement               -> fail
#
#    Bypass with JUNIPER_APPARMOR_OK=1 (mirrors JUNIPER_SNAPSHOT_ROOT_OK / JUNIPER_IMAGE_STALE_OK).
#    Read-only: mounts nothing, restarts nothing, creates nothing.
#
# Usage:
#    scripts/preflight_apparmor.sh
#    scripts/preflight_apparmor.sh --sys-root DIR --mountinfo FILE --security-options JSON   # hermetic
#
#    --sys-root DIR            prefix for the two /sys paths above (default: /)
#    --mountinfo FILE          mount table to read (default: /proc/self/mountinfo)
#    --security-options JSON   dockerd's SecurityOptions, as `docker info --format '{{json .SecurityOptions}}'`
#                              prints it; when absent the daemon is asked (DOCKER overrides the binary)
#
# Exit codes:
#    0  OK, SKIP or WARN (or bypassed)
#    1  FAIL
#    2  usage error, or the daemon could not be queried
#####################################################################################################################################################################################################

set -euo pipefail

SYS_ROOT="/"
MOUNTINFO="/proc/self/mountinfo"
SECURITY_OPTIONS=""
SECURITY_OPTIONS_SET=0
DOCKER_BIN="${DOCKER:-docker}"
RUNBOOK="juniper-ml/notes/JUNIPER_2026-11-07_JUNIPER-ECOSYSTEM_YAMAGUCHI-API-FILESYSTEM-REMOUNT-RUNBOOK.md"
REMOUNT="sudo mount -t securityfs -o nosuid,nodev,noexec securityfs /sys/kernel/security"
DOCKER_ERROR="Could not check if docker-default AppArmor profile was loaded: open /sys/kernel/security/apparmor/profiles: no such file or directory"

usage() {
    # Description through Exit codes, wherever they fall: stop at the closing banner.
    awk 'NR > 2 && /^#####/ { exit } /^# Description:/ { on = 1 } on { sub(/^# ?/, ""); print }' "${BASH_SOURCE[0]}"
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --sys-root)
            SYS_ROOT="${2:?--sys-root requires a DIR argument}"
            shift 2
            ;;
        --mountinfo)
            MOUNTINFO="${2:?--mountinfo requires a FILE argument}"
            shift 2
            ;;
        --security-options)
            SECURITY_OPTIONS="${2?--security-options requires a JSON argument}"
            SECURITY_OPTIONS_SET=1
            shift 2
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        *)
            echo "preflight_apparmor: unknown argument: $1 (see --help)" >&2
            exit 2
            ;;
    esac
done

if [[ "${JUNIPER_APPARMOR_OK:-0}" == "1" ]]; then
    echo "preflight_apparmor: bypassed (JUNIPER_APPARMOR_OK=1)"
    exit 0
fi

if [[ ! -r "$MOUNTINFO" ]]; then
    echo "preflight_apparmor: cannot read mount table: ${MOUNTINFO}" >&2
    exit 2
fi

sys_path() { printf '%s/%s' "${SYS_ROOT%/}" "${1#/}"; }

# ── kernel ────────────────────────────────────────────────────────────────
enabled_raw=""
if [[ -r "$(sys_path /sys/module/apparmor/parameters/enabled)" ]]; then
    enabled_raw="$(head -c 8 "$(sys_path /sys/module/apparmor/parameters/enabled)" | tr -d '[:space:]')"
fi
kernel_enabled=0
[[ "$enabled_raw" == Y* ]] && kernel_enabled=1

# ── mount (the fstype is the first field after the " - " separator; proc(5)) ──
securityfs_mounted=0
if awk '{ sep = 0; for (i = 1; i <= NF; i++) if ($i == "-") { sep = i; break } }
        sep && $5 == "/sys/kernel/security" { top = $(sep + 1) }
        END { exit !(top == "securityfs") }' "$MOUNTINFO"; then
    securityfs_mounted=1
fi

# ── interface ─────────────────────────────────────────────────────────────
interface=0
[[ -e "$(sys_path /sys/kernel/security/apparmor/profiles)" ]] && interface=1

# ── colors (match the sibling preflights) ─────────────────────────────────
if [[ -t 1 && -z "${NO_COLOR:-}" ]]; then
    RED=$'\033[0;31m'; GREEN=$'\033[0;32m'; YELLOW=$'\033[0;33m'; RESET=$'\033[0m'
else
    RED=""; GREEN=""; YELLOW=""; RESET=""
fi

echo "Juniper Platform — AppArmor-Interface Preflight"
echo "  verify dockerd can load docker-default for the containers about to start"

if [[ "$kernel_enabled" -eq 0 ]]; then
    printf '  %s[SKIP]%s AppArmor is not enabled in this kernel (enabled=%s); containers run without it\n' \
        "$GREEN" "$RESET" "${enabled_raw:-absent}"
    exit 0
fi

# ── daemon (only consulted when AppArmor is on) ───────────────────────────
if [[ "$SECURITY_OPTIONS_SET" -eq 0 ]]; then
    if ! SECURITY_OPTIONS="$("$DOCKER_BIN" info --format '{{json .SecurityOptions}}' 2>/dev/null)"; then
        echo "preflight_apparmor: could not query the Docker daemon (\`${DOCKER_BIN} info\`); pass --security-options for an offline check" >&2
        exit 2
    fi
fi
daemon_apparmor=0
[[ "$SECURITY_OPTIONS" == *'"name=apparmor"'* ]] && daemon_apparmor=1

state_line() {
    printf '  kernel=%s  securityfs on /sys/kernel/security=%s  interface=%s  dockerd AppArmor=%s\n' \
        "${enabled_raw}" "$([[ $securityfs_mounted -eq 1 ]] && echo mounted || echo MISSING)" \
        "$([[ $interface -eq 1 ]] && echo present || echo MISSING)" "$([[ $daemon_apparmor -eq 1 ]] && echo yes || echo no)"
}

if [[ "$interface" -eq 1 ]]; then
    if [[ "$daemon_apparmor" -eq 1 ]]; then
        printf '  %s[OK]%s   AppArmor interface present; dockerd confines containers with docker-default\n' "$GREEN" "$RESET"
        state_line
        exit 0
    fi
    printf '  %s[WARN]%s AppArmor interface present, but dockerd does not use AppArmor\n' "$YELLOW" "$RESET"
    state_line
    printf '         dockerd decides once, at start: it was started while the interface was missing, so every\n'
    printf '         container runs WITHOUT AppArmor until dockerd restarts (sudo systemctl restart docker).\n'
    printf '         See %s.\n' "$RUNBOOK"
    exit 0
fi

# AppArmor enabled, interface missing.
if [[ "$securityfs_mounted" -eq 1 ]]; then
    cause="securityfs is mounted on /sys/kernel/security, but it has no apparmor/ directory"
else
    cause="securityfs is NOT mounted on /sys/kernel/security (PID 1 mounts it at boot; it has no unit file, so nothing remounts it)"
fi

if [[ "$daemon_apparmor" -eq 1 ]]; then
    printf '  %s[FAIL]%s AppArmor is enabled but its interface is gone: every container start will fail with\n' "$RED" "$RESET"
    printf '         "%s"\n' "$DOCKER_ERROR"
    state_line
    printf '  cause: %s\n' "$cause"
    printf '  dockerd cached "AppArmor supported" when it started, so it still applies docker-default.\n'
    printf '  fix (owner, root; read the runbook first on a host with a Kubernetes install):\n'
    printf '         %s\n' "$REMOUNT"
    printf '  Do NOT restart dockerd to make this go away: a dockerd started without the interface runs\n'
    printf '  every container WITHOUT AppArmor confinement, silently.\n'
else
    printf '  %s[FAIL]%s AppArmor is enabled but its interface is gone, and dockerd no longer uses AppArmor:\n' "$RED" "$RESET"
    printf '         containers would start WITHOUT AppArmor confinement\n'
    state_line
    printf '  cause: %s\n' "$cause"
    printf '  fix (owner, root; read the runbook first on a host with a Kubernetes install):\n'
    printf '         %s\n' "$REMOUNT"
    printf '         then restart dockerd so it re-detects AppArmor: sudo systemctl restart docker\n'
fi
printf '  runbook: %s\n' "$RUNBOOK"
printf '%spreflight_apparmor: AppArmor interface missing. Bypass with JUNIPER_APPARMOR_OK=1.%s\n' "$RED" "$RESET" >&2
exit 1
