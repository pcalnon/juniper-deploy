#!/usr/bin/env bash
#####################################################################################################################################################################################################
# Project:       Juniper
# Application:   juniper-deploy
# File Name:     test_canopy_recurrence_smoke.sh
# Author:        Paul Calnon
#
# Date Created:  2026-10-08
#
# License:       MIT License
# Copyright:     Copyright (c) 2024-2026 Paul Calnon
#
# Description:
#    Runs the W1.11 canopy -> juniper-recurrence -> juniper-data smoke
#    (tests/test_canopy_recurrence_equities_smoke.py) inside the test-runner image, against a
#    stack this script brings up in its OWN compose project and tears down afterwards. W1.11 is
#    in juniper-ml notes/JUNIPER_2026-10-03_JUNIPER-RECURRENCE_EQUITIES-END-TO-END-AUDIT-AND-DEVELOPMENT-PLAN.md.
#
#    WHAT IT ANSWERS. Whether the stack, as composed, takes an operator from "select Recurrence,
#    stage equities_seq, Start" to a completed fit, and whether juniper-data labels that
#    fit's dataset `regression`. With --data-image it asks the same of a juniper-data image you
#    supply: the W1.11 slip rule's "smoke green against a `main` checkout of juniper-data" is
#    this script with --data-image naming an image built from that checkout.
#
#    ISOLATION. It must never touch an operator's stack, archive or secrets, and it can run
#    beside a live one:
#      * its own compose project (juniper-canopy-recurrence-smoke), whose closing `down -v`
#        can remove only its own containers, networks and volumes;
#      * every container it starts is RENAMED under that prefix. docker-compose.yml fixes
#        container_name, which would otherwise collide with a live stack's containers;
#      * NO host port is published: the test-runner reaches every service over the project's
#        own networks, so no host listener can collide with it;
#      * the networks' pinned subnets are released to Docker's pool. A pinned subnet is
#        exclusive host-wide, so keeping them would block a live stack's bring-up;
#      * both snapshot roots go to a scratch directory, never the real archives;
#      * throwaway API keys, through the secret-source variables: it never reads secrets/,
#        and every service still runs with its auth required;
#      * the operator's .env is not read (--env-file names the scratch one), so the smoke
#        tests the shipped defaults.
#    The rendered config is checked for all of the above before anything starts. Nothing is
#    built from a sibling checkout: `up --no-build`, and an image that is neither local nor
#    pullable stops the run.
#
#    THE IMAGES DECIDE THE RESULT. It prints each service image's reference and its version and
#    revision labels. Against published juniper-data <= 0.16.0 the fit completes, and the label
#    check FAILS by design: that release serves equities_seq at 5.0.0 / classification.
#
#    A LOCAL TAG IS NOT A RELEASE. `docker compose build` stamps a dev tree with the release tag
#    (see the image-reference banner in docker-compose.yml), and with Docker's containerd image
#    store such a build even carries a digest, so neither the tag nor `RepoDigests` proves what
#    the image is. Measured on the host this script was written on (2026-10-08): all four of the
#    stack's local Juniper tags were dev builds, and none matched GHCR. --published resolves every
#    pin to the digest GHCR serves for its tag NOW and runs that digest, so the run is the
#    released artifact. It reads no local tag and changes none.
#
#    The test-runner image is built from this checkout, so it carries the module under test. It
#    gets a local tag that is removed afterwards; --runner-image uses an existing image instead.
#
#    NETWORK. juniper-data fetches the AAPL prices and SEC filings at request time, over the
#    stack's data-egress network. A repeat within one run is a cache hit; a new run is cold.
#
# Usage:
#    bash scripts/test_canopy_recurrence_smoke.sh [--published] [--image SERVICE=REF ...] [--data-image REF]
#                                                 [--runner-image REF] [--timeout SECONDS]
#                                                 [--fit-timeout SECONDS] [--keep]
#
#      --published           run every pinned ghcr.io/pcalnon image by the digest GHCR serves for
#                            its tag (needs the registry); --image overrides take precedence
#      --image SERVICE=REF   run SERVICE (juniper-data, juniper-recurrence, juniper-canopy,
#                            juniper-cascor) from REF instead of the compose pin; repeatable
#      --data-image REF      shorthand for --image juniper-data=REF
#      --runner-image REF    run the smoke from REF instead of a test-runner built from here
#      --timeout SECONDS     bring-up health wait (default CANOPY_RECURRENCE_SMOKE_TIMEOUT, 300)
#      --fit-timeout SECONDS budget for the fit, Start to terminal status (the module's default
#                            is 360; sets JUNIPER_TEST_RECURRENCE_SMOKE_TIMEOUT in the runner)
#      --keep                leave the project, the runner image and the scratch directory
#
#    The W1.11 slip-rule run, with juniper-data built from a checkout and everything else as
#    released:
#      docker build -t juniper-data-local:main ../juniper-data
#      bash scripts/test_canopy_recurrence_smoke.sh --published --data-image juniper-data-local:main
#
#    COMPOSE_FILE (default docker-compose.yml, resolved against the repo root) selects the
#    compose file, as it does for the preflights.
#
# Exit status:
#    0  the smoke passed
#    1  the smoke failed (pytest's verdict), or the stack did not come up
#    2  usage error, or an unmet precondition (no docker or python3, an image that cannot be
#       had, a pin GHCR does not serve under --published, this project already present)
#####################################################################################################################################################################################################

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(dirname "$SCRIPT_DIR")"
# shellcheck source=scripts/config.sh
source "${SCRIPT_DIR}/config.sh"

# A constant, deliberately not configurable: the closing teardown runs `down -v` against this
# project, so it must never be pointed at an operator's project and its named volumes.
readonly PROJECT="juniper-canopy-recurrence-smoke"
readonly SMOKE_MODULE="tests/test_canopy_recurrence_equities_smoke.py"
readonly LOCAL_RUNNER_TAG="juniper-deploy-test-smoke:local"
# Every service the bring-up and the run can start. Each is renamed under ${PROJECT}-.
readonly -a RENAMED_SERVICES=(juniper-data juniper-cascor juniper-recurrence juniper-canopy redis test-runner)
# The services docker-compose.yml publishes a host port for. Each loses it here.
readonly -a PUBLISHING_SERVICES=(juniper-cascor juniper-recurrence juniper-canopy)
readonly -a NETWORKS=(backend data frontend monitoring data-egress)
# The services whose images decide the result: overridable with --image, resolved by
# --published, and reported before the run.
readonly -a IMAGE_SERVICES=(juniper-data juniper-recurrence juniper-canopy juniper-cascor)
readonly STEPS=5

COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.yml}"
if [[ "$COMPOSE_FILE" == /* ]]; then
    COMPOSE_PATH="$COMPOSE_FILE"
else
    COMPOSE_PATH="${REPO_ROOT}/${COMPOSE_FILE}"
fi

TIMEOUT="${CANOPY_RECURRENCE_SMOKE_TIMEOUT}"
FIT_TIMEOUT=""
RUNNER_IMAGE=""
PUBLISHED=0
KEEP=0
declare -A IMAGE_OVERRIDES=()

set_image() {
    local service="${1%%=*}" ref="${1#*=}" known
    if [[ "$service" == "$1" || -z "$service" || -z "$ref" ]]; then
        echo "test_canopy_recurrence_smoke: --image takes SERVICE=REF, got: $1" >&2
        exit 2
    fi
    for known in "${IMAGE_SERVICES[@]}"; do
        if [[ "$service" == "$known" ]]; then
            IMAGE_OVERRIDES["$service"]="$ref"
            return
        fi
    done
    echo "test_canopy_recurrence_smoke: --image SERVICE must be one of ${IMAGE_SERVICES[*]}, got: ${service}" >&2
    exit 2
}

usage() {
    # Description through Exit status, wherever they fall: stop at the closing banner.
    awk 'NR > 2 && /^#####/ { exit } /^# Description:/ { on = 1 } on { sub(/^# ?/, ""); print }' "${BASH_SOURCE[0]}"
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --published)
            PUBLISHED=1
            shift
            ;;
        --image)
            set_image "${2:?--image requires SERVICE=REF}"
            shift 2
            ;;
        --image=*)
            set_image "${1#*=}"
            shift
            ;;
        --data-image)
            set_image "juniper-data=${2:?--data-image requires REF}"
            shift 2
            ;;
        --data-image=*)
            set_image "juniper-data=${1#*=}"
            shift
            ;;
        --runner-image)
            RUNNER_IMAGE="${2:?--runner-image requires REF}"
            shift 2
            ;;
        --runner-image=*)
            RUNNER_IMAGE="${1#*=}"
            shift
            ;;
        --timeout)
            TIMEOUT="${2:?--timeout requires SECONDS}"
            shift 2
            ;;
        --timeout=*)
            TIMEOUT="${1#*=}"
            shift
            ;;
        --fit-timeout)
            FIT_TIMEOUT="${2:?--fit-timeout requires SECONDS}"
            shift 2
            ;;
        --fit-timeout=*)
            FIT_TIMEOUT="${1#*=}"
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
            echo "test_canopy_recurrence_smoke: unknown argument: $1 (see --help)" >&2
            exit 2
            ;;
    esac
done

# Numeric guards. These values reach docker argv and a container's environment, never a code
# string, but a non-number is still an operator error worth naming before anything starts.
if ! [[ "$TIMEOUT" =~ ^[0-9]+$ ]]; then
    echo "test_canopy_recurrence_smoke: --timeout must be a whole number of seconds, got: ${TIMEOUT}" >&2
    exit 2
fi
if [[ -n "$FIT_TIMEOUT" ]] && ! [[ "$FIT_TIMEOUT" =~ ^[0-9]+$ ]]; then
    echo "test_canopy_recurrence_smoke: --fit-timeout must be a whole number of seconds, got: ${FIT_TIMEOUT}" >&2
    exit 2
fi
# An image reference is written into a YAML override, so it is held to the reference grammar
# rather than quoted: no whitespace, quotes, or YAML flow characters can reach that file.
valid_ref() {
    [[ "$1" =~ ^[A-Za-z0-9][A-Za-z0-9._/:@+-]*$ ]]
}
for service in "${!IMAGE_OVERRIDES[@]}"; do
    if ! valid_ref "${IMAGE_OVERRIDES[$service]}"; then
        echo "test_canopy_recurrence_smoke: not an image reference for ${service}: ${IMAGE_OVERRIDES[$service]}" >&2
        exit 2
    fi
done
if [[ -n "$RUNNER_IMAGE" ]] && ! valid_ref "$RUNNER_IMAGE"; then
    echo "test_canopy_recurrence_smoke: not an image reference: ${RUNNER_IMAGE}" >&2
    exit 2
fi

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
BUILT_RUNNER=0
WORK_DIR=""

pass() { printf '  %bPASS%b %s\n' "$GREEN" "$RESET" "$1"; }
fail() { printf '  %bFAIL%b %s\n' "$RED" "$RESET" "$1"; EXIT_CODE=1; }
info() { printf '  %bINFO%b %s\n' "$YELLOW" "$RESET" "$1"; }
step() { printf '%b[%s/%s]%b %s\n' "$CYAN" "$1" "$STEPS" "$RESET" "$2"; }

# Every compose call targets the smoke's own project, its scratch env file (which carries the
# throwaway key and snapshot-root overrides) and its override file.
compose() {
    docker compose -p "$PROJECT" --project-directory "$REPO_ROOT" --env-file "$ENV_FILE" \
        -f "$COMPOSE_PATH" -f "$OVERRIDE_FILE" --profile test "$@"
}

# Bounded log tails for diagnosis. The keys in this stack are throwaway, made for this run.
show_logs() {
    compose ps -a || true
    compose logs --no-color --tail 60 juniper-canopy juniper-recurrence juniper-data || true
}

# shellcheck disable=SC2317,SC2329  # reached only through `trap finish EXIT`, which shellcheck cannot see
finish() {
    local status=$?
    echo ""
    if [[ -z "$WORK_DIR" ]]; then
        return
    fi
    if [[ "$KEEP" -eq 1 ]]; then
        local kept="project ${PROJECT} and ${WORK_DIR}"
        if [[ "$BUILT_RUNNER" -eq 1 ]]; then
            kept="project ${PROJECT}, ${WORK_DIR} and ${LOCAL_RUNNER_TAG}"
        fi
        info "--keep: ${kept} are left in place. Tear down with:"
        printf '         docker compose -p %s --project-directory %s --env-file %s -f %s -f %s --profile test down -v --remove-orphans; rm -rf %s\n' \
            "$PROJECT" "$REPO_ROOT" "$ENV_FILE" "$COMPOSE_PATH" "$OVERRIDE_FILE" "$WORK_DIR"
        if [[ "$BUILT_RUNNER" -eq 1 ]]; then
            printf '         docker image rm %s\n' "$LOCAL_RUNNER_TAG"
        fi
    else
        echo "Tearing down compose project ${PROJECT} ..."
        compose down -v --remove-orphans >/dev/null 2>&1 || info "teardown reported an error; inspect with: docker compose -p ${PROJECT} ps -a"
        if [[ "$BUILT_RUNNER" -eq 1 ]]; then
            docker image rm "$LOCAL_RUNNER_TAG" >/dev/null 2>&1 || info "could not remove ${LOCAL_RUNNER_TAG}"
        fi
        rm -rf "$WORK_DIR"
    fi
    echo ""
    if [[ "$status" -eq 0 && "$EXIT_CODE" -eq 0 ]]; then
        printf '%b%bThe canopy -> recurrence -> juniper-data smoke passed.%b\n' "$GREEN" "$BOLD" "$RESET"
    else
        printf '%b%bThe canopy -> recurrence -> juniper-data smoke FAILED.%b\n' "$RED" "$BOLD" "$RESET"
    fi
}

printf '%bJuniper — canopy -> recurrence -> juniper-data smoke (W1.11)%b\n\n' "$BOLD" "$RESET"

# ── Preconditions: nothing below this block changes anything if they fail ─────
for tool in docker python3; do
    if ! command -v "$tool" >/dev/null 2>&1; then
        echo "test_canopy_recurrence_smoke: ${tool} not found" >&2
        exit 2
    fi
done
if ! docker compose version >/dev/null 2>&1 || ! docker info >/dev/null 2>&1; then
    echo "test_canopy_recurrence_smoke: the Docker daemon or the compose plugin is not usable" >&2
    exit 2
fi
if [[ -n "$(docker ps -a -q --filter "label=com.docker.compose.project=${PROJECT}")" ]]; then
    echo "test_canopy_recurrence_smoke: compose project ${PROJECT} already has containers (an earlier --keep run?). Tear it down first; the teardown command is printed by that run. Nothing was touched." >&2
    exit 2
fi

# ── Scratch workspace: env file, override, snapshot roots, throwaway keys ──────
WORK_DIR="$(mktemp -d "${TMPDIR:-/tmp}/canopy-recurrence-smoke.XXXXXX")"
ENV_FILE="${WORK_DIR}/smoke.env"
OVERRIDE_FILE="${WORK_DIR}/smoke.override.yml"
trap finish EXIT
trap 'exit 130' INT TERM

# The services run as uid 1000, which need not be the uid running this script. WORK_DIR stays
# 0700, so opening what is inside it to every uid exposes nothing to another host user, while
# the containers reach it through their mounts.
for dir in cascor-snapshots recurrence-snapshots; do
    mkdir "${WORK_DIR}/${dir}"
    chmod 0777 "${WORK_DIR}/${dir}"
done
new_key() {
    python3 -c 'import secrets, sys; open(sys.argv[1], "w", encoding="utf-8").write(secrets.token_urlsafe(32) + "\n")' "$1"
    chmod 0644 "$1"
}
new_key "${WORK_DIR}/juniper_data_api_keys.txt"
new_key "${WORK_DIR}/juniper_recurrence_api_keys.txt"
new_key "${WORK_DIR}/canopy_api_key.txt"
# cascor's accept-list, the key canopy sends it and the worker token are one value in the
# shipped secrets (scripts/prepare_secrets.bash), so the three files share one token here.
new_key "${WORK_DIR}/juniper_cascor_api_keys.txt"
cp "${WORK_DIR}/juniper_cascor_api_keys.txt" "${WORK_DIR}/juniper_cascor_api_key.txt"
cp "${WORK_DIR}/juniper_cascor_api_keys.txt" "${WORK_DIR}/cascor_auth_token.txt"

{
    echo "JUNIPER_DATA_API_KEYS_FILE=${WORK_DIR}/juniper_data_api_keys.txt"
    echo "JUNIPER_RECURRENCE_API_KEYS_SOURCE=${WORK_DIR}/juniper_recurrence_api_keys.txt"
    echo "JUNIPER_CASCOR_API_KEYS_FILE=${WORK_DIR}/juniper_cascor_api_keys.txt"
    echo "JUNIPER_CASCOR_API_KEY_FILE=${WORK_DIR}/juniper_cascor_api_key.txt"
    echo "CASCOR_AUTH_TOKEN_FILE=${WORK_DIR}/cascor_auth_token.txt"
    echo "CANOPY_API_KEY_FILE=${WORK_DIR}/canopy_api_key.txt"
    echo "JUNIPER_CASCOR_SNAPSHOTS_HOST_DIR=${WORK_DIR}/cascor-snapshots"
    echo "JUNIPER_RECURRENCE_SNAPSHOTS_HOST_DIR=${WORK_DIR}/recurrence-snapshots"
} > "$ENV_FILE"

if [[ -z "$RUNNER_IMAGE" ]]; then
    RUNNER_IMAGE="$LOCAL_RUNNER_TAG"
fi

# --published: every pin not overridden by --image runs by the digest GHCR serves for its tag.
declare -A RESOLVED_FROM=()
if [[ "$PUBLISHED" -eq 1 ]]; then
    to_resolve=()
    for svc in "${IMAGE_SERVICES[@]}"; do
        if [[ -z "${IMAGE_OVERRIDES[$svc]:-}" ]]; then
            to_resolve+=("$svc")
        fi
    done
    if [[ "${#to_resolve[@]}" -gt 0 ]]; then
        if ! docker compose -p "$PROJECT" --project-directory "$REPO_ROOT" --env-file "$ENV_FILE" -f "$COMPOSE_PATH" --profile test \
                config --format json > "${WORK_DIR}/pins.json" 2>"${WORK_DIR}/pins.err"; then
            echo "test_canopy_recurrence_smoke: docker compose config failed to render ${COMPOSE_PATH}:" >&2
            tail -n 20 "${WORK_DIR}/pins.err" >&2
            exit 2
        fi
        if ! resolved="$(python3 - "${WORK_DIR}/pins.json" "${to_resolve[@]}" <<'PY'
import json
import sys
import urllib.error
import urllib.request

ACCEPT = ", ".join(
    [
        "application/vnd.oci.image.index.v1+json",
        "application/vnd.docker.distribution.manifest.list.v2+json",
        "application/vnd.oci.image.manifest.v1+json",
        "application/vnd.docker.distribution.manifest.v2+json",
    ]
)
REGISTRY = "ghcr.io/"
render_file, services = sys.argv[1], sys.argv[2:]
with open(render_file, encoding="utf-8") as handle:
    config = json.load(handle)
# Environment proxies are honoured: this talks to the public registry, not to a local port.
for service in services:
    pin = str(((config.get("services") or {}).get(service) or {}).get("image") or "")
    name, _, tag = pin.rpartition(":")
    if not pin.startswith(REGISTRY + "pcalnon/") or "@" in pin or not name or "/" in tag:
        sys.exit(f"--published: {service} pins {pin!r}, which is not a ghcr.io/pcalnon/<image>:<tag> release reference")
    repo = name[len(REGISTRY):]
    try:
        with urllib.request.urlopen(f"https://ghcr.io/token?scope=repository:{repo}:pull", timeout=30) as response:  # nosec B310 - fixed https registry URL
            token = json.load(response)["token"]
        request = urllib.request.Request(f"https://ghcr.io/v2/{repo}/manifests/{tag}", headers={"Authorization": f"Bearer {token}", "Accept": ACCEPT})
        with urllib.request.urlopen(request, timeout=30) as response:  # nosec B310 - fixed https registry URL
            digest = response.headers.get("Docker-Content-Digest", "")
    except urllib.error.HTTPError as exc:
        sys.exit(f"--published: GHCR answered HTTP {exc.code} for {pin}" + (" -- that tag was never published" if exc.code == 404 else ""))
    except (urllib.error.URLError, OSError, ValueError, KeyError) as exc:
        sys.exit(f"--published: could not resolve {pin} on GHCR: {exc}")
    if not digest.startswith("sha256:"):
        sys.exit(f"--published: GHCR returned no digest for {pin}")
    print(f"{service}\t{name}@{digest}\t{pin}")
PY
)"; then
            echo "test_canopy_recurrence_smoke: --published could not resolve every pin to a GHCR digest (above). Nothing was started." >&2
            exit 2
        fi
        while IFS=$'\t' read -r svc digest_ref pin; do
            IMAGE_OVERRIDES["$svc"]="$digest_ref"
            RESOLVED_FROM["$svc"]="$pin"
        done <<< "$resolved"
    fi
fi

{
    echo "# Generated by scripts/test_canopy_recurrence_smoke.sh for compose project ${PROJECT}."
    echo "services:"
    for svc in "${RENAMED_SERVICES[@]}"; do
        echo "  ${svc}:"
        echo "    container_name: ${PROJECT}-${svc}"
        for publishing in "${PUBLISHING_SERVICES[@]}"; do
            if [[ "$svc" == "$publishing" ]]; then
                echo "    ports: !reset []"
            fi
        done
        if [[ -n "${IMAGE_OVERRIDES[$svc]:-}" ]]; then
            echo "    image: ${IMAGE_OVERRIDES[$svc]}"
        fi
        if [[ "$svc" == "test-runner" ]]; then
            echo "    image: ${RUNNER_IMAGE}"
        fi
    done
    echo "networks:"
    for net in "${NETWORKS[@]}"; do
        echo "  ${net}:"
        echo "    ipam: !reset {}"
    done
} > "$OVERRIDE_FILE"

# ── 1. The rendered config ──────────────────────────────────────────────────────
step 1 "Rendered config: renamed, unpublished, unpinned, scratch-only"
if ! compose config --format json > "${WORK_DIR}/render.json" 2>"${WORK_DIR}/render.err"; then
    fail "docker compose config failed to render ${COMPOSE_PATH} with the smoke override:"
    tail -n 20 "${WORK_DIR}/render.err"
    exit 1
fi
render_verdict="$(python3 - "${WORK_DIR}/render.json" "$PROJECT" "$WORK_DIR" "${REPO_ROOT}/secrets.example" <<'PY'
import json
import os
import sys

render_file, project, work_dir, examples = sys.argv[1:5]
with open(render_file, encoding="utf-8") as handle:
    config = json.load(handle)


def inside(path, root):
    path, root = os.path.realpath(path), os.path.realpath(root)
    return path == root or path.startswith(root + os.sep)


problems = []
for name, svc in sorted((config.get("services") or {}).items()):
    if svc.get("ports"):
        problems.append(f"{name} still publishes {svc['ports']}")
    container = svc.get("container_name")
    if container and not container.startswith(project + "-"):
        problems.append(f"{name} keeps container_name {container!r}")
    for volume in svc.get("volumes") or []:
        if isinstance(volume, dict) and volume.get("type") == "bind" and not inside(str(volume.get("source")), work_dir):
            problems.append(f"{name} bind-mounts {volume.get('source')!r}, outside the scratch directory")
for name, secret in sorted((config.get("secrets") or {}).items()):
    source = str(secret.get("file", ""))
    if source and not (inside(source, work_dir) or inside(source, examples)):
        problems.append(f"secret {name} reads {source!r}, which is neither scratch nor secrets.example/")
for name, network in sorted((config.get("networks") or {}).items()):
    pinned = [cfg.get("subnet") for cfg in ((network.get("ipam") or {}).get("config") or []) if cfg.get("subnet")]
    if pinned:
        problems.append(f"network {name} still pins {pinned}")
    if not str(network.get("name", "")).startswith(project + "_"):
        problems.append(f"network {name} is named {network.get('name')!r}, outside the project")
print("; ".join(problems) or "ok")
PY
)"
if [[ "$render_verdict" == "ok" ]]; then
    pass "every container is ${PROJECT}-*, nothing is published, no subnet is pinned, every mount and secret is scratch (or secrets.example/)"
else
    fail "the rendered config is not isolated, so nothing was started: ${render_verdict}"
    exit 1
fi

# ── 2. Images ───────────────────────────────────────────────────────────────────
step 2 "Images: every service image local or pullable; the runner carries the module"
mapfile -t images < <(compose config --images juniper-data juniper-cascor juniper-recurrence juniper-canopy redis 2>/dev/null | sort -u)
if [[ "${#images[@]}" -eq 0 ]]; then
    fail "docker compose config --images named no image for the five services"
    exit 1
fi
for image in "${images[@]}"; do
    if docker image inspect "$image" >/dev/null 2>&1; then
        continue
    fi
    info "pulling ${image}"
    if ! docker pull --quiet "$image" >/dev/null 2>&1; then
        echo "test_canopy_recurrence_smoke: ${image} is neither local nor pullable, and the smoke never builds a service image from a sibling checkout" >&2
        exit 2
    fi
done
pass "service images present: ${images[*]}"
if [[ "$RUNNER_IMAGE" == "$LOCAL_RUNNER_TAG" ]]; then
    git_sha="$(git -C "$REPO_ROOT" rev-parse HEAD 2>/dev/null || true)"
    if ! build_log="$(docker build -f "${REPO_ROOT}/Dockerfile.test" -t "$LOCAL_RUNNER_TAG" --build-arg "GIT_SHA=${git_sha}" "$REPO_ROOT" 2>&1)"; then
        fail "building the test-runner image from ${REPO_ROOT} failed:"
        printf '%s\n' "$build_log" | tail -n 20
        exit 1
    fi
    BUILT_RUNNER=1
    pass "test-runner built from this checkout as ${LOCAL_RUNNER_TAG} (HEAD ${git_sha:0:12}; uncommitted edits included)"
elif ! docker image inspect "$RUNNER_IMAGE" >/dev/null 2>&1 && ! docker pull --quiet "$RUNNER_IMAGE" >/dev/null 2>&1; then
    echo "test_canopy_recurrence_smoke: --runner-image ${RUNNER_IMAGE} is neither local nor pullable" >&2
    exit 2
fi
if ! docker run --rm --entrypoint test "$RUNNER_IMAGE" -f "/app/${SMOKE_MODULE}"; then
    fail "${RUNNER_IMAGE} does not carry ${SMOKE_MODULE}, so it cannot run this smoke"
    exit 1
fi

# ── 3. Bring-up ─────────────────────────────────────────────────────────────────
step 3 "Bring up juniper-canopy and juniper-recurrence (with juniper-data, juniper-cascor, redis) as ${PROJECT}"
if ! up_log="$(compose up -d --no-build --wait --wait-timeout "$TIMEOUT" juniper-canopy juniper-recurrence 2>&1)"; then
    fail "the stack did not come up healthy within ${TIMEOUT}s:"
    printf '%s\n' "$up_log" | tail -n 20
    show_logs
    exit 1
fi
pass "juniper-data, juniper-cascor, redis, juniper-recurrence and juniper-canopy are healthy"

# ── 4. The images under test ────────────────────────────────────────────────────
step 4 "The images under test"
for svc in "${IMAGE_SERVICES[@]}"; do
    cid="$(compose ps -q "$svc" 2>/dev/null | head -n 1)"
    if [[ -z "$cid" ]]; then
        info "${svc}: no container"
        continue
    fi
    image_ref="$(docker inspect --format '{{.Config.Image}}' "$cid")"
    image_id="$(docker inspect --format '{{.Image}}' "$cid")"
    image_version="$(docker image inspect --format '{{index .Config.Labels "org.opencontainers.image.version"}}' "$image_id")"
    image_revision="$(docker image inspect --format '{{index .Config.Labels "org.opencontainers.image.revision"}}' "$image_id")"
    if [[ -n "${RESOLVED_FROM[$svc]:-}" ]]; then
        origin="the digest GHCR serves for ${RESOLVED_FROM[$svc]}"
    elif [[ -n "${IMAGE_OVERRIDES[$svc]:-}" ]]; then
        origin="an --image override"
    else
        origin="the compose pin AS TAGGED LOCALLY, which may be a dev build (see --published)"
    fi
    info "${svc}: ${image_ref} (${origin}), version label '${image_version}', revision label '${image_revision}'"
done

# ── 5. The smoke ────────────────────────────────────────────────────────────────
step 5 "Run ${SMOKE_MODULE} in the test-runner"
run_env=()
if [[ -n "$FIT_TIMEOUT" ]]; then
    run_env=(-e "JUNIPER_TEST_RECURRENCE_SMOKE_TIMEOUT=${FIT_TIMEOUT}")
fi
set +e
compose run --rm --no-deps ${run_env[@]+"${run_env[@]}"} test-runner pytest "$SMOKE_MODULE" -v --tb=short -rA
pytest_status=$?
set -e
if [[ "$pytest_status" -eq 0 ]]; then
    pass "pytest passed"
else
    fail "pytest exited ${pytest_status}"
    show_logs
fi

exit "$EXIT_CODE"
