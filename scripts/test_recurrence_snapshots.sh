#!/usr/bin/env bash
#####################################################################################################################################################################################################
# Project:       Juniper
# Application:   juniper-deploy
# File Name:     test_recurrence_snapshots.sh
# Author:        Paul Calnon
#
# Date Created:  2026-10-05
#
# License:       MIT License
# Copyright:     Copyright (c) 2024-2026 Paul Calnon
#
# Description:
#    Snapshot-persistence smoke for juniper-recurrence (W1.12 / F-DEP2). Proves that a model
#    snapshot saved by the container OUTLIVES the container, through the bind mount, and that
#    nothing restores it on boot:
#
#      train -> save -> restart -> list -> RECREATE -> list -> restore
#
#    WHY A RECREATE, AND NOT ONLY A RESTART. `docker compose restart` keeps the container, and
#    with it the container's writable layer, so a snapshot written to an UNMOUNTED path survives
#    a restart as well. A restart alone passes with or without the bind mount, so it proves
#    nothing about it. `up --force-recreate` replaces the container and discards that layer:
#    only a file that went through the mount is still listed afterwards. The smoke runs both,
#    asserts the container id CHANGED across the recreate, and checks that the saved file is on
#    the HOST side of the mount.
#
#    NO RESTORE ON BOOT is asserted, not assumed: after the restart and after the recreate,
#    GET /v1/training/status must report `idle`. `restored` is reached only by an explicit
#    POST /v1/model/snapshots/{id}/restore, with an id from GET /v1/model/snapshots.
#
#    ISOLATION. It must never touch an operator's stack, archive or secrets:
#      * its own compose project (juniper-recurrence-snapshot-smoke), so its juniper-data
#        volume is not the operator's, and its closing `down -v` can remove only its own;
#      * it refuses to start while a `juniper-data` or `juniper-recurrence` container exists.
#        container_name is fixed, so it could not run beside a live stack anyway;
#      * snapshots go to a scratch directory through JUNIPER_RECURRENCE_SNAPSHOTS_HOST_DIR,
#        never the real archive. Snapshot retention is no-deletion, so a smoke artifact
#        written there could never be cleaned up;
#      * throwaway API keys through the secret-source variables, so it never reads secrets/,
#        and it still runs with JUNIPER_RECURRENCE_REQUIRE_AUTH on.
#
#    THE IMAGE DECIDES THE RESULT. It runs whatever image compose resolves for
#    juniper-recurrence, and prints that image's id and its version and revision labels. The
#    published juniper-recurrence:0.5.0 PREDATES the snapshot routes (juniper-recurrence#172 is
#    unreleased), so against it step 3 fails with that diagnosis. An image built from a
#    recurrence checkout that carries #172 passes, and `docker compose build` gives that image
#    the same 0.5.0 tag, which is why the labels are printed.
#
#    Offline apart from the local daemon: the dataset is juniper-data's closed-form
#    irregular_sine generator.
#
# Usage:
#    bash scripts/test_recurrence_snapshots.sh [--timeout SECONDS] [--keep]
#
#      --timeout SECONDS   health wait after each bring-up (default RECURRENCE_SMOKE_TIMEOUT, 120)
#      --keep              leave the smoke stack and its scratch directory up for inspection
#
#    COMPOSE_FILE (default docker-compose.yml, resolved against the repo root) selects the
#    compose file, as it does for the preflights.
#
# Exit status:
#    0  every step passed
#    1  at least one step failed
#    2  usage error, or an unmet precondition (no docker or python3, a Juniper stack already up)
#####################################################################################################################################################################################################

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(dirname "$SCRIPT_DIR")"
# shellcheck source=scripts/config.sh
source "${SCRIPT_DIR}/config.sh"

# A constant, deliberately not configurable: the closing teardown runs `down -v` against this
# project, so it must never be pointed at an operator's project and its named volumes.
readonly PROJECT="juniper-recurrence-snapshot-smoke"
readonly SERVICE="juniper-recurrence"
readonly CONTAINER_PORT="8210"
readonly MOUNT_TARGET="/app/recurrence-snapshots"
readonly STEPS=8

COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.yml}"
if [[ "$COMPOSE_FILE" == /* ]]; then
    COMPOSE_PATH="$COMPOSE_FILE"
else
    COMPOSE_PATH="${REPO_ROOT}/${COMPOSE_FILE}"
fi

TIMEOUT="${RECURRENCE_SMOKE_TIMEOUT}"
HTTP_TIMEOUT="${RECURRENCE_SMOKE_HTTP_TIMEOUT}"
KEEP=0

# A tiny closed-form fit: no network, a second or two of compute.
TRAIN_BODY='{"dataset": {"generator": "irregular_sine", "params": {"n_steps": 256, "lookback": 16, "horizon": 1, "seed": 20261005}}, "d": 4, "ridge": 1.0}'
SAVE_BODY='{"description": "juniper-deploy W1.12 snapshot-persistence smoke"}'

usage() {
    # Description through Exit status, wherever they fall: stop at the closing banner.
    awk 'NR > 2 && /^#####/ { exit } /^# Description:/ { on = 1 } on { sub(/^# ?/, ""); print }' "${BASH_SOURCE[0]}"
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --timeout)
            TIMEOUT="${2:?--timeout requires SECONDS}"
            shift 2
            ;;
        --timeout=*)
            TIMEOUT="${1#*=}"
            shift
            ;;
        --keep)
            KEEP=1
            shift
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        *)
            echo "test_recurrence_snapshots: unknown argument: $1 (see --help)" >&2
            exit 2
            ;;
    esac
done

# Numeric guards. These values reach python3 argv and `sleep`, never a code string, but a
# non-number is still an operator error worth naming before anything starts.
for varname in TIMEOUT HTTP_TIMEOUT POLL_INTERVAL_DEFAULT CURL_TIMEOUT; do
    val="${!varname}"
    if ! [[ "$val" =~ ^[0-9]+$ ]]; then
        echo "test_recurrence_snapshots: ${varname} must be a whole number of seconds, got: ${val}" >&2
        exit 2
    fi
done

# Colors (disabled if NO_COLOR is set)
if [[ -z "${NO_COLOR:-}" ]]; then
    GREEN='\033[0;32m'
    RED='\033[0;31m'
    YELLOW='\033[0;33m'
    CYAN='\033[0;36m'
    BOLD='\033[1m'
    RESET='\033[0m'
else
    GREEN='' RED='' YELLOW='' CYAN='' BOLD='' RESET=''
fi

EXIT_CODE=0
BASE_URL=""
HTTP_STATUS=""
HTTP_BODY=""
SNAP_ID=""

pass() { printf '  %bPASS%b %s\n' "$GREEN" "$RESET" "$1"; }
fail() { printf '  %bFAIL%b %s\n' "$RED" "$RESET" "$1"; EXIT_CODE=1; }
info() { printf '  %bINFO%b %s\n' "$YELLOW" "$RESET" "$1"; }
step() { printf '%b[%s/%s]%b %s\n' "$CYAN" "$1" "$STEPS" "$RESET" "$2"; }

# Every compose call targets the smoke's own project and carries the three overrides: the
# scratch snapshot root and the two throwaway key files.
compose() {
    JUNIPER_RECURRENCE_SNAPSHOTS_HOST_DIR="$SNAP_DIR" \
    JUNIPER_DATA_API_KEYS_FILE="$DATA_KEY_FILE" \
    JUNIPER_RECURRENCE_API_KEYS_SOURCE="$RECURRENCE_KEY_FILE" \
        docker compose -p "$PROJECT" --project-directory "$REPO_ROOT" -f "$COMPOSE_PATH" --profile full "$@"
}

container_id() {
    compose ps -q "$SERVICE" 2>/dev/null | head -n 1
}

# The URL compose actually published for the container port, read back from the daemon, so it
# can never be some other service that happens to listen on a configured port.
published_url() {
    local mapping host port
    mapping="$(compose port "$SERVICE" "$CONTAINER_PORT" 2>/dev/null | head -n 1)"
    port="${mapping##*:}"
    host="${mapping%:*}"
    if ! [[ "$port" =~ ^[0-9]+$ ]]; then
        return 1
    fi
    case "$host" in
        "" | 0.0.0.0 | "[::]" | "::") host="127.0.0.1" ;;
    esac
    printf 'http://%s:%s' "$host" "$port"
}

wait_healthy() {
    local deadline=$((SECONDS + TIMEOUT)) url
    while ((SECONDS < deadline)); do
        if url="$(published_url)" && python3 -c 'import sys, urllib.request; urllib.request.build_opener(urllib.request.ProxyHandler({})).open(sys.argv[1], timeout=float(sys.argv[2]))' "${url}/v1/health" "$CURL_TIMEOUT" >/dev/null 2>&1; then
            BASE_URL="$url"
            return 0
        fi
        sleep "$POLL_INTERVAL_DEFAULT"
    done
    return 1
}

health_or_die() {
    if wait_healthy; then
        pass "${SERVICE} answers /v1/health at ${BASE_URL} after the $1"
    else
        fail "${SERVICE} did not answer /v1/health within ${TIMEOUT}s after the $1"
        compose ps -a || true
        compose logs --tail 40 "$SERVICE" || true
        exit 1
    fi
}

# api METHOD PATH [JSON_BODY]: one authenticated request against BASE_URL. Sets HTTP_STATUS
# (0 when nothing answered) and HTTP_BODY (compact JSON). The key is read from its file inside
# python, so it never appears in an argument list or a process listing.
api() {
    local out
    out="$(python3 - "$1" "${BASE_URL}$2" "${3:-}" "$RECURRENCE_KEY_FILE" "$HTTP_TIMEOUT" <<'PY'
import json
import sys
import urllib.error
import urllib.request

method, url, body, key_file, timeout = sys.argv[1:6]
with open(key_file, encoding="utf-8") as handle:
    key = handle.read().strip()
request = urllib.request.Request(
    url,
    data=body.encode("utf-8") if body else None,
    method=method,
    headers={"X-API-Key": key, "Content-Type": "application/json", "Accept": "application/json"},
)
# No proxy: this only ever talks to a port the local daemon published.
opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
try:
    with opener.open(request, timeout=float(timeout)) as response:
        status, raw = response.status, response.read()
except urllib.error.HTTPError as exc:
    status, raw = exc.code, exc.read()
except Exception as exc:  # refused, reset, timed out: no HTTP answer at all
    status, raw = 0, str(exc).encode("utf-8")
text = raw.decode("utf-8", errors="replace")
try:
    payload = json.loads(text)
except ValueError:
    payload = text
print(f"{status}\t{json.dumps(payload, separators=(',', ':'))}")
PY
)"
    HTTP_STATUS="${out%%$'\t'*}"
    HTTP_BODY="${out#*$'\t'}"
}

# field JSON KEY: a top-level value ('' when absent; non-strings as JSON).
field() {
    python3 - "$1" "$2" <<'PY'
import json
import sys

try:
    value = json.loads(sys.argv[1])
    value = value.get(sys.argv[2]) if isinstance(value, dict) else None
except ValueError:
    value = None
print("" if value is None else value if isinstance(value, str) else json.dumps(value))
PY
}

# snapshot_ids JSON: the ids in a GET /v1/model/snapshots body, one per line.
snapshot_ids() {
    python3 - "$1" <<'PY'
import json
import sys

try:
    snapshots = json.loads(sys.argv[1]).get("snapshots") or []
except (ValueError, AttributeError):
    sys.exit(1)
for snapshot in snapshots:
    print(snapshot.get("id", ""))
PY
}

expect_state() {
    local state from
    api GET /v1/training/status
    state="$(field "$HTTP_BODY" state)"
    from="$(field "$HTTP_BODY" restored_from)"
    if [[ "$HTTP_STATUS" == "200" && "$state" == "$1" && ("$1" != "restored" || "$from" == "$SNAP_ID") ]]; then
        pass "GET /v1/training/status -> state '${state}'${from:+, restored_from ${from}} $2"
    else
        fail "GET /v1/training/status -> HTTP ${HTTP_STATUS}, state '${state}', restored_from '${from}' $2 (expected '$1')"
    fi
}

# expect_listed WHEN [WHAT_A_PASS_MEANS]
expect_listed() {
    local ids=""
    api GET /v1/model/snapshots
    if [[ "$HTTP_STATUS" == "200" ]]; then
        ids="$(snapshot_ids "$HTTP_BODY" || true)"
    fi
    # Captured first, then searched: grep -q on a pipe can SIGPIPE the writer under pipefail.
    if grep -qxF -- "$SNAP_ID" <<< "$ids"; then
        pass "GET /v1/model/snapshots lists ${SNAP_ID} $1${2:+: $2}"
    else
        fail "GET /v1/model/snapshots does not list ${SNAP_ID} $1 (HTTP ${HTTP_STATUS})"
    fi
}

# shellcheck disable=SC2317  # reached only through `trap finish EXIT`, which shellcheck cannot see
finish() {
    local status=$?
    echo ""
    if [[ "$KEEP" -eq 1 ]]; then
        info "--keep: project ${PROJECT} and ${WORK_DIR} are left in place. Tear down with:"
        printf '         docker compose -p %s --project-directory %s -f %s --profile full down -v --remove-orphans; rm -rf %s\n' \
            "$PROJECT" "$REPO_ROOT" "$COMPOSE_PATH" "$WORK_DIR"
    else
        echo "Tearing down compose project ${PROJECT} ..."
        compose down -v --remove-orphans >/dev/null 2>&1 || info "teardown reported an error; inspect with: docker compose -p ${PROJECT} ps -a"
        rm -rf "$WORK_DIR"
    fi
    echo ""
    if [[ "$status" -eq 0 && "$EXIT_CODE" -eq 0 ]]; then
        printf '%b%bAll recurrence snapshot-persistence checks passed.%b\n' "$GREEN" "$BOLD" "$RESET"
    else
        printf '%b%bThe recurrence snapshot-persistence smoke FAILED.%b\n' "$RED" "$BOLD" "$RESET"
    fi
}

printf '%bJuniper Recurrence — Snapshot Persistence Smoke (W1.12)%b\n\n' "$BOLD" "$RESET"

# ── Preconditions: nothing below this block changes anything if they fail ─────
for tool in docker python3; do
    if ! command -v "$tool" >/dev/null 2>&1; then
        echo "test_recurrence_snapshots: ${tool} not found" >&2
        exit 2
    fi
done
if ! docker compose version >/dev/null 2>&1 || ! docker info >/dev/null 2>&1; then
    echo "test_recurrence_snapshots: the Docker daemon or the compose plugin is not usable" >&2
    exit 2
fi
for name in juniper-data "$SERVICE"; do
    if docker container inspect "$name" >/dev/null 2>&1; then
        echo "test_recurrence_snapshots: a '${name}' container already exists. container_name is fixed, so this smoke cannot run beside another Juniper stack; bring that stack down first (make down). Nothing was touched." >&2
        exit 2
    fi
done

# ── Scratch workspace: snapshot root + throwaway keys ──────────────────────────
WORK_DIR="$(mktemp -d "${TMPDIR:-/tmp}/recurrence-snapshot-smoke.XXXXXX")"
SNAP_DIR="${WORK_DIR}/snapshots"
DATA_KEY_FILE="${WORK_DIR}/juniper_data_api_keys.txt"
RECURRENCE_KEY_FILE="${WORK_DIR}/juniper_recurrence_api_keys.txt"
trap finish EXIT
trap 'exit 130' INT TERM

mkdir "$SNAP_DIR"
# The container runs as uid 1000 (the image's `juniper` user), which need not be the uid
# running this script. WORK_DIR stays 0700, so opening SNAP_DIR (and the key files) to every
# uid exposes them to no other host user, while the container reaches them through its mounts.
chmod 0777 "$SNAP_DIR"
for key_file in "$DATA_KEY_FILE" "$RECURRENCE_KEY_FILE"; do
    python3 -c 'import secrets, sys; open(sys.argv[1], "w", encoding="utf-8").write(secrets.token_urlsafe(32) + "\n")' "$key_file"
    chmod 0644 "$key_file"
done

# ── 1. The rendered config ──────────────────────────────────────────────────────
step 1 "Rendered config: ${SERVICE} declares its snapshot dir and bind-mounts it"
if ! compose config --format json > "${WORK_DIR}/render.json" 2>/dev/null; then
    fail "docker compose config failed to render ${COMPOSE_PATH}"
    exit 1
fi
render_verdict="$(python3 - "$MOUNT_TARGET" "$SNAP_DIR" "$SERVICE" "${WORK_DIR}/render.json" <<'PY'
import json
import os
import sys

target, scratch_root, service, render_file = sys.argv[1:5]
with open(render_file, encoding="utf-8") as handle:
    config = json.load(handle)
svc = (config.get("services") or {}).get(service) or {}
problems = []
declared = (svc.get("environment") or {}).get("JUNIPER_RECURRENCE_SNAPSHOTS_DIR")
if declared != target:
    problems.append(f"JUNIPER_RECURRENCE_SNAPSHOTS_DIR is {declared!r}, not {target!r}")
mounts = [v for v in svc.get("volumes") or [] if isinstance(v, dict) and v.get("target") == target]
if not mounts:
    problems.append(f"no volume targets {target}")
elif mounts[0].get("type") != "bind":
    problems.append(f"{target} is a {mounts[0].get('type')!r} mount, not a bind mount")
elif os.path.realpath(str(mounts[0].get("source"))) != os.path.realpath(scratch_root):
    problems.append(f"{target} binds {mounts[0].get('source')!r}, not JUNIPER_RECURRENCE_SNAPSHOTS_HOST_DIR")
print("; ".join(problems) or "ok")
PY
)"
if [[ "$render_verdict" == "ok" ]]; then
    pass "JUNIPER_RECURRENCE_SNAPSHOTS_DIR=${MOUNT_TARGET}, bind-mounted from JUNIPER_RECURRENCE_SNAPSHOTS_HOST_DIR"
else
    fail "rendered config: ${render_verdict}"
fi

# ── 2. Bring-up ─────────────────────────────────────────────────────────────────
step 2 "Bring up ${SERVICE} (and juniper-data, its dependency) as compose project ${PROJECT}"
if ! up_log="$(compose up -d "$SERVICE" 2>&1)"; then
    fail "docker compose up failed:"
    printf '%s\n' "$up_log" | tail -n 20
    exit 1
fi
health_or_die "bring-up"
CID_FIRST="$(container_id)"
image_id="$(docker inspect --format '{{.Image}}' "$CID_FIRST")"
image_ref="$(docker inspect --format '{{.Config.Image}}' "$CID_FIRST")"
image_version="$(docker image inspect --format '{{index .Config.Labels "org.opencontainers.image.version"}}' "$image_id")"
image_revision="$(docker image inspect --format '{{index .Config.Labels "org.opencontainers.image.revision"}}' "$image_id")"
info "image under test: ${image_ref} = ${image_id}, version label '${image_version}', revision label '${image_revision}'"

# ── 3. Routes, empty archive, idle ──────────────────────────────────────────────
step 3 "The snapshot routes exist, the scratch archive is empty, and the service starts idle"
api GET /v1/model/snapshots
case "$HTTP_STATUS" in
    200)
        if [[ -z "$(snapshot_ids "$HTTP_BODY" || true)" ]]; then
            pass "GET /v1/model/snapshots -> 200, no snapshots (a fresh scratch root)"
        else
            fail "GET /v1/model/snapshots -> 200 but the fresh scratch root already lists snapshots: ${HTTP_BODY}"
        fi
        ;;
    404)
        fail "GET /v1/model/snapshots -> 404: this image has no snapshot routes. The published juniper-recurrence:0.5.0 predates them (juniper-recurrence#172 is unreleased); they ship with the next recurrence release. To exercise the mount before that, build the image from a recurrence checkout that carries #172 (docker compose build juniper-recurrence)."
        exit 1
        ;;
    *)
        fail "GET /v1/model/snapshots -> HTTP ${HTTP_STATUS}: ${HTTP_BODY}"
        exit 1
        ;;
esac
expect_state idle "before any fit"

# ── 4. Train ────────────────────────────────────────────────────────────────────
step 4 "Train a tiny closed-form fit (juniper-data irregular_sine, no network)"
api POST /v1/train "$TRAIN_BODY"
if [[ "$HTTP_STATUS" == "200" ]]; then
    pass "POST /v1/train -> 200"
else
    fail "POST /v1/train -> HTTP ${HTTP_STATUS}: ${HTTP_BODY}"
    exit 1
fi
expect_state trained "after the fit"

# ── 5. Save ─────────────────────────────────────────────────────────────────────
step 5 "Save a snapshot; the file must land on the HOST side of the bind mount"
api POST /v1/model/snapshots "$SAVE_BODY"
SNAP_ID="$(field "$HTTP_BODY" id)"
if [[ "$HTTP_STATUS" == "201" && "$SNAP_ID" =~ ^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$ ]]; then
    pass "POST /v1/model/snapshots -> 201, id ${SNAP_ID}"
else
    fail "POST /v1/model/snapshots -> HTTP ${HTTP_STATUS}: ${HTTP_BODY}"
    exit 1
fi
if [[ -f "${SNAP_DIR}/${SNAP_ID}.npz" ]]; then
    pass "${SNAP_ID}.npz is in the host directory bound at ${MOUNT_TARGET}"
else
    fail "${SNAP_ID}.npz is NOT in the host directory bound at ${MOUNT_TARGET}: the service wrote it where the mount does not reach"
fi
expect_listed "after the save"

# ── 6. Restart ──────────────────────────────────────────────────────────────────
step 6 "docker compose restart ${SERVICE}: nothing restores the model, the snapshot is still listed"
if ! compose restart "$SERVICE" >/dev/null 2>&1; then
    fail "docker compose restart ${SERVICE} failed"
    exit 1
fi
health_or_die "restart"
if [[ "$(container_id)" == "$CID_FIRST" ]]; then
    info "same container ${CID_FIRST:0:12}: a restart keeps its writable layer, so this step cannot tell a mounted snapshot from an unmounted one. Step 7 can."
fi
expect_state idle "after the restart (no restore on boot)"
expect_listed "after the restart"

# ── 7. Recreate ─────────────────────────────────────────────────────────────────
step 7 "Recreate ${SERVICE} (up --force-recreate): a NEW container, idle, the snapshot still listed"
if ! compose up -d --force-recreate --no-deps "$SERVICE" >/dev/null 2>&1; then
    fail "docker compose up --force-recreate ${SERVICE} failed"
    exit 1
fi
health_or_die "recreate"
CID_RECREATED="$(container_id)"
if [[ -n "$CID_RECREATED" && "$CID_RECREATED" != "$CID_FIRST" ]]; then
    pass "container ${CID_RECREATED:0:12} replaced ${CID_FIRST:0:12}; the old writable layer is gone"
else
    fail "the container id did not change (${CID_RECREATED:0:12}), so nothing was recreated"
fi
expect_state idle "after the recreate (no restore on boot)"
expect_listed "after the recreate" "it lives on the host, not in the discarded layer"

# ── 8. Restore ──────────────────────────────────────────────────────────────────
step 8 "Restore ${SNAP_ID}: state 'restored', and restored_from names it"
api POST "/v1/model/snapshots/${SNAP_ID}/restore"
restore_state="$(field "$HTTP_BODY" state)"
restore_from="$(field "$HTTP_BODY" restored_from)"
if [[ "$HTTP_STATUS" == "200" && "$restore_state" == "restored" && "$restore_from" == "$SNAP_ID" ]]; then
    pass "POST /v1/model/snapshots/${SNAP_ID}/restore -> 200, state 'restored', restored_from ${restore_from}"
else
    fail "POST /v1/model/snapshots/${SNAP_ID}/restore -> HTTP ${HTTP_STATUS}, state '${restore_state}', restored_from '${restore_from}'"
fi
expect_state restored "after the restore"

exit "$EXIT_CODE"
