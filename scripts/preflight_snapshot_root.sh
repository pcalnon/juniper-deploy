#!/usr/bin/env bash
#####################################################################################################################################################################################################
# Project:       Juniper
# Application:   juniper-deploy
# File Name:     preflight_snapshot_root.sh
# Author:        Paul Calnon
#
# Date Created:  2026-08-20
#
# License:       MIT License
# Copyright:     Copyright (c) 2024-2026 Paul Calnon
#
# Description:
#    Snapshot-root preflight for `make up` / `demo` / `dev` / `monitor` / `obs-demo`.
#
#    The stack shares ONE snapshot root across every origin — the host's direct
#    CLI, the systemd service, and the containers, which BIND-MOUNT the host
#    directory at /app/cascor-snapshots. Snapshots are project assets: they live
#    inside the Juniper tree so the whole-tree offline backup captures them, and
#    they are protected from deletion (a bind mount survives `docker compose
#    down -v` and `make clean`, which a named volume does not).
#
#    WHY THIS PREFLIGHT EXISTS — the failure it prevents is SILENT.
#
#    Compose resolves a relative bind-mount source against the COMPOSE FILE's
#    directory, exactly like `build.context: ../juniper-cascor`. But where a
#    wrong build context fails LOUDLY (no Dockerfile, build aborts), a wrong
#    bind-mount source fails QUIETLY: the daemon CREATES the missing directory,
#    root-owned, and the stack comes up healthy with an empty archive. Every
#    snapshot list returns "No snapshots available" and every save either lands
#    somewhere nobody backs up or EPERMs against root ownership — the exact
#    silently-empty class this whole change set exists to close.
#
#    Two ways to hit it without doing anything obviously wrong: run compose from
#    a copy of the repo (a worktree, an extracted archive) so `../juniper-cascor`
#    resolves elsewhere, or set JUNIPER_CASCOR_SNAPSHOTS_HOST_DIR to a path that
#    does not exist yet.
#
#    Checks, per unique bind-mount source targeting /app/cascor-snapshots:
#
#      [OK]         exists, is a directory, and is writable by this uid   -> OK
#      [MISSING]    does not exist — the daemon would create it root-owned -> FAIL
#      [NOTDIR]     exists but is not a directory                         -> FAIL
#      [READONLY]   exists but is not writable by this uid                -> FAIL
#      [OUTSIDE]    resolves outside the Juniper tree                     -> warn
#                   (backup coverage is the owner's call, not this script's)
#      [EMPTY]      exists and is writable but holds no .h5               -> warn
#                   (legitimate on a first run; suspicious otherwise)
#
#    Bypass with JUNIPER_SNAPSHOT_ROOT_OK=1 (mirrors JUNIPER_BUILD_STALE_OK /
#    JUNIPER_IMAGE_STALE_OK). Read-only: creates nothing, changes nothing.
#
# Usage:
#    scripts/preflight_snapshot_root.sh [--profile full] [--env-file FILE] ...
#    scripts/preflight_snapshot_root.sh --config-json FILE   # offline, no daemon
#
#    Unrecognized arguments are passed through verbatim to
#    `docker compose <ARGS> config --format json`, matching the sibling
#    preflights so the Makefile can hand it the same profile flags.
#
# Exit codes:
#    0  all sources OK (or bypassed, or nothing to check)
#    1  at least one FAIL
#    2  usage / render error
#####################################################################################################################################################################################################

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(dirname "$SCRIPT_DIR")"
COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.yml}"
MOUNT_TARGET="/app/cascor-snapshots"

CONFIG_JSON=""
PASSTHROUGH=()

usage() {
    sed -n '12,63p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --config-json)
            CONFIG_JSON="${2:?--config-json requires a FILE argument}"
            shift 2
            ;;
        --config-json=*)
            CONFIG_JSON="${1#*=}"
            shift
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        --)
            shift
            PASSTHROUGH+=("$@")
            break
            ;;
        *)
            PASSTHROUGH+=("$1")
            shift
            ;;
    esac
done

if [[ "${JUNIPER_SNAPSHOT_ROOT_OK:-0}" == "1" ]]; then
    echo "preflight_snapshot_root: bypassed (JUNIPER_SNAPSHOT_ROOT_OK=1)"
    exit 0
fi

# ── Obtain the rendered compose config JSON ────────────────────────────────
if [[ -n "$CONFIG_JSON" ]]; then
    if [[ ! -f "$CONFIG_JSON" ]]; then
        echo "preflight_snapshot_root: --config-json file not found: ${CONFIG_JSON}" >&2
        exit 2
    fi
    render_json="$(cat -- "$CONFIG_JSON")"
else
    if ! command -v docker >/dev/null 2>&1; then
        echo "preflight_snapshot_root: docker not found; pass --config-json for an offline check" >&2
        exit 2
    fi
    if ! render_json="$(cd "$REPO_ROOT" && docker compose -f "$COMPOSE_FILE" "${PASSTHROUGH[@]}" config --format json 2>/dev/null)"; then
        echo "preflight_snapshot_root: \`docker compose -f ${COMPOSE_FILE} ${PASSTHROUGH[*]:-} config\` failed to render" >&2
        exit 2
    fi
fi

if [[ -z "${render_json//[[:space:]]/}" ]]; then
    echo "preflight_snapshot_root: empty compose config render (nothing to check)" >&2
    exit 2
fi

# ── Extract the unique bind-mount sources for the snapshot target ──────────
# python3 owns the JSON parse (no jq dependency), matching the sibling preflights.
render_file="$(mktemp "${TMPDIR:-/tmp}/preflight_snapshot_root.XXXXXX")"
trap 'rm -f "$render_file"' EXIT
printf '%s' "$render_json" > "$render_file"

sources_raw="$(python3 - "$render_file" "$MOUNT_TARGET" <<'PY'
import json
import sys

try:
    with open(sys.argv[1], encoding="utf-8") as handle:
        config = json.loads(handle.read())
except (OSError, ValueError) as exc:
    sys.stderr.write(f"preflight_snapshot_root: could not read/parse compose config JSON: {exc}\n")
    sys.exit(2)

target = sys.argv[2]
sources = set()
for svc in (config.get("services") or {}).values():
    for vol in ((svc or {}).get("volumes") or []):
        # Long form (what `config --format json` always renders) and, defensively,
        # the short "src:dst[:opts]" string form in case a future render differs.
        if isinstance(vol, dict):
            if vol.get("target") == target and vol.get("type") == "bind" and vol.get("source"):
                sources.add(str(vol["source"]))
        elif isinstance(vol, str):
            parts = vol.split(":")
            if len(parts) >= 2 and parts[1] == target:
                sources.add(parts[0])
print("\n".join(sorted(sources)))
PY
)"

if [[ -z "${sources_raw//[[:space:]]/}" ]]; then
    echo "preflight_snapshot_root: no ${MOUNT_TARGET} bind mounts in this render (nothing to check)"
    exit 0
fi

# ── Colors (match the Makefile / sibling preflight conventions) ────────────
if [[ -t 1 ]]; then
    RED=$'\033[0;31m'; GREEN=$'\033[0;32m'; YELLOW=$'\033[0;33m'; RESET=$'\033[0m'
else
    RED=""; GREEN=""; YELLOW=""; RESET=""
fi

JUNIPER_TREE="${JUNIPER_ROOT:-$(dirname "$REPO_ROOT")}"
failures=0
warnings=0

while IFS= read -r source; do
    [[ -z "$source" ]] && continue
    if [[ ! -e "$source" ]]; then
        printf '%s[MISSING]%s    %s\n' "$RED" "$RESET" "$source"
        printf '             the daemon would CREATE this root-owned and the stack would come up\n'
        printf '             with an empty archive. Create it yourself, or point\n'
        printf '             JUNIPER_CASCOR_SNAPSHOTS_HOST_DIR at the real root.\n'
        failures=$((failures + 1))
        continue
    fi
    if [[ ! -d "$source" ]]; then
        printf '%s[NOTDIR]%s     %s\n' "$RED" "$RESET" "$source"
        failures=$((failures + 1))
        continue
    fi
    if [[ ! -w "$source" ]]; then
        printf '%s[READONLY]%s   %s\n' "$RED" "$RESET" "$source"
        printf '             not writable by uid %s; container saves would EPERM\n' "$(id -u)"
        failures=$((failures + 1))
        continue
    fi

    resolved="$(cd "$source" && pwd -P)"
    note=""
    if [[ "$resolved" != "$JUNIPER_TREE"/* ]]; then
        note=" ${YELLOW}(outside ${JUNIPER_TREE} — the whole-tree offline backup will NOT capture it)${RESET}"
        warnings=$((warnings + 1))
    fi

    count="$(find "$resolved" -maxdepth 1 -name '*.h5' -printf '.' 2>/dev/null | wc -c)"
    if [[ "$count" -eq 0 ]]; then
        printf '%s[EMPTY]%s      %s%s\n' "$YELLOW" "$RESET" "$resolved" "$note"
        printf '             no .h5 present — expected on a first run, suspicious otherwise\n'
        warnings=$((warnings + 1))
    else
        printf '%s[OK]%s         %s (%s .h5)%s\n' "$GREEN" "$RESET" "$resolved" "$count" "$note"
    fi
done <<< "$sources_raw"

if [[ "$failures" -gt 0 ]]; then
    printf '%spreflight_snapshot_root: %d unusable snapshot root(s). Bypass with JUNIPER_SNAPSHOT_ROOT_OK=1.%s\n' \
        "$RED" "$failures" "$RESET" >&2
    exit 1
fi

if [[ "$warnings" -gt 0 ]]; then
    printf '%spreflight_snapshot_root: %d warning(s); continuing.%s\n' "$YELLOW" "$warnings" "$RESET"
fi

exit 0
