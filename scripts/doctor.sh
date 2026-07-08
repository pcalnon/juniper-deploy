#!/usr/bin/env bash
#####################################################################################################################################################################################################
# Project:       Juniper
# Application:   juniper-deploy
# File Name:     doctor.sh
# Author:        Paul Calnon
#
# License:       MIT License
# Copyright:     Copyright (c) 2024-2026 Paul Calnon
#
# Description:
#    Build-provenance drift checker. For each Juniper service the compose
#    stack BUILDS (derived live from `docker compose config --format json` —
#    every service declaring both `build:` and `image:`), compares the source
#    git SHA baked into the image (the OCI org.opencontainers.image.revision
#    label, read via `docker inspect`) with the current HEAD of the
#    build-context's ENCLOSING git repository, and reports FRESH / STALE /
#    UNKNOWN / DIRTY per service so a container silently running behind source
#    is caught.
#
#    The service list is DERIVED, not hardcoded: an earlier hardcoded list
#    drifted (it lacked juniper-recurrence and the demo/dev variants), and —
#    because every built service is profile-gated while the old `docker
#    compose ps` lookup passed no --profile flags — the "prefer the running
#    container" branch could never resolve a service name, so the running
#    container was never actually inspected. Deriving from the same rendered
#    config that bring-up uses (the preflight_build_freshness.sh /
#    preflight_image_provenance.sh mechanism) fixes both: new built services
#    are covered automatically, and `ps` is invoked with the same profile
#    flags as the render so the running container's image IS preferred when
#    the service is up (falling back to the built `:latest` tag otherwise —
#    catches "forgot to rebuild after a source change").
#
#    Uses `docker inspect` of the image label rather than the service's
#    /v1/health endpoint because not every service publishes its port on the
#    host (e.g. juniper-data), so a label read works uniformly. Build contexts
#    may be nested subdirectories of their repo (e.g.
#    ../juniper-recurrence/juniper-recurrence); each resolves to its enclosing
#    repository. Classification is unchanged: `-dirty` revisions (image built
#    from uncommitted tracked changes, OQ-2) report DIRTY before the FRESH
#    prefix compare; 7- vs 8-char short SHAs prefix-match.
#
#    See juniper-ml notes/JUNIPER_2026-06-14_JUNIPER-ECOSYSTEM_BUILD-PROVENANCE-DESIGN.md (Part 7).
#
# Usage:
#    make doctor
#    bash scripts/doctor.sh [--profile NAME ...] [--env-file FILE ...]
#    bash scripts/doctor.sh --config-json rendered.json \
#        --image-provenance-map shas.json                            # offline
#
#    With no arguments, the config is rendered with every profile (full demo
#    dev test observability) so all built services are covered. Any argument
#    other than the flags below is passed through verbatim to `docker compose
#    <ARGS> config --format json` AND to the running-container lookup
#    (`docker compose <ARGS> ps -q <service>`).
#
#      --config-json FILE           Check a pre-rendered `docker compose
#                                   config --format json` FILE instead of
#                                   invoking docker (offline).
#      --image-provenance-map FILE  JSON object mapping image ref ->
#                                   revision-label value ("" or a missing key
#                                   = no label / not built). Replaces `docker
#                                   inspect` and disables the running-container
#                                   preference (offline; used by the CI lint
#                                   tests/test_doctor_provenance_derivation.py).
#      -h, --help                   Show this help and exit.
#
# Exit status:
#    0  no STALE or DIRTY image found (FRESH / UNKNOWN are non-fatal)
#    1  at least one running/built image is STALE relative to its source repo,
#       or was built from uncommitted changes (DIRTY)
#    2  usage error / compose render failure
#
#####################################################################################################################################################################################################

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.yml}"
REVISION_LABEL="org.opencontainers.image.revision"
DEFAULT_PROFILES=(--profile full --profile demo --profile dev --profile test --profile observability)

usage() {
    sed -nE 's/^# ?//p' "${BASH_SOURCE[0]}" | sed -n '/^Usage:/,/^Exit status:/p'
}

CONFIG_JSON=""
PROVENANCE_MAP=""
PASSTHROUGH=()
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
        --image-provenance-map)
            PROVENANCE_MAP="${2:?--image-provenance-map requires a FILE argument}"
            shift 2
            ;;
        --image-provenance-map=*)
            PROVENANCE_MAP="${1#*=}"
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
[[ ${#PASSTHROUGH[@]} -eq 0 ]] && PASSTHROUGH=("${DEFAULT_PROFILES[@]}")

if [[ -n "$PROVENANCE_MAP" && ! -f "$PROVENANCE_MAP" ]]; then
    echo "doctor: --image-provenance-map file not found: ${PROVENANCE_MAP}" >&2
    exit 2
fi

# ── Obtain the rendered compose config JSON ────────────────────────────────
if [[ -n "$CONFIG_JSON" ]]; then
    if [[ ! -f "$CONFIG_JSON" ]]; then
        echo "doctor: --config-json file not found: ${CONFIG_JSON}" >&2
        exit 2
    fi
    render_json="$(cat -- "$CONFIG_JSON")"
    source_desc="--config-json ${CONFIG_JSON}"
else
    source_desc="docker compose ${PASSTHROUGH[*]} config"
    if ! command -v docker >/dev/null 2>&1; then
        echo "doctor: docker not found; pass --config-json for an offline check" >&2
        exit 2
    fi
    if ! render_json="$(cd "$REPO_ROOT" && docker compose -f "$COMPOSE_FILE" "${PASSTHROUGH[@]}" config --format json 2>/dev/null)"; then
        echo "doctor: \`docker compose -f ${COMPOSE_FILE} ${PASSTHROUGH[*]} config\` failed to render" >&2
        exit 2
    fi
fi

if [[ -z "${render_json//[[:space:]]/}" ]]; then
    echo "doctor: empty compose config render (nothing to check)" >&2
    exit 2
fi

# ── Derive service<TAB>image<TAB>context for every BUILT service ───────────
# One row per SERVICE (not per image): doctor prefers each service's RUNNING
# container, and e.g. juniper-cascor / juniper-cascor-demo can be up with
# different container states while sharing juniper-cascor:latest. python3
# owns the JSON parse (stdlib only, no jq — mirrors the preflights).
render_file="$(mktemp "${TMPDIR:-/tmp}/doctor_render.XXXXXX")"
trap 'rm -f "$render_file"' EXIT
printf '%s' "$render_json" > "$render_file"

rows_raw="$(python3 - "$render_file" <<'PY'
import json
import sys

try:
    with open(sys.argv[1], encoding="utf-8") as handle:
        config = json.loads(handle.read())
except (OSError, ValueError) as exc:
    sys.stderr.write(f"doctor: could not read/parse compose config JSON: {exc}\n")
    sys.exit(2)

for name in sorted(config.get("services") or {}):
    svc = (config["services"][name] or {})
    build = svc.get("build")
    image = svc.get("image")
    if not build or not image:
        continue  # image-only services (redis, prometheus, ...) have no local source to compare
    context = build if isinstance(build, str) else (build.get("context") or "")
    if context:
        print(f"{name}\t{image}\t{context}")
PY
)"

# Colors (disabled if NO_COLOR is set)
if [[ -z "${NO_COLOR:-}" ]]; then
    GREEN='\033[0;32m'
    RED='\033[0;31m'
    YELLOW='\033[0;33m'
    CYAN='\033[0;36m'
    BOLD='\033[1m'
    DIM='\033[2m'
    RESET='\033[0m'
else
    GREEN=''
    RED=''
    YELLOW=''
    CYAN=''
    BOLD=''
    DIM=''
    RESET=''
fi

# Read the build-provenance revision label from a container id or image ref.
# Empty string when the ref is missing or carries no such label. In offline
# map mode the JSON map replaces docker inspect (a missing key reads as "").
revision_of() {
    local ref="$1" sha
    if [[ -n "$PROVENANCE_MAP" ]]; then
        sha="$(python3 - "$PROVENANCE_MAP" "$ref" <<'PY'
import json
import sys

with open(sys.argv[1], encoding="utf-8") as handle:
    mapping = json.load(handle)
print(mapping.get(sys.argv[2]) or "")
PY
        )"
        printf '%s' "$sha"
        return 0
    fi
    sha="$(docker inspect --format "{{ index .Config.Labels \"${REVISION_LABEL}\" }}" "$ref" 2>/dev/null || true)"
    [[ "$sha" == "<no value>" ]] && sha=""
    printf '%s' "$sha"
}

echo -e "${BOLD}Juniper Platform — Build-Provenance Doctor${RESET}"
echo -e "${DIM}  running image revision (OCI label) vs source repo HEAD${RESET}"
echo -e "${DIM}  services derived from: ${source_desc}${RESET}"
echo ""

if [[ -z "${rows_raw//[[:space:]]/}" ]]; then
    echo -e "${YELLOW}  Nothing to check — no service declares both build: and image:.${RESET}"
    exit 0
fi

printf "  %-22s %-12s %-12s %s\n" "SERVICE" "IMAGE SHA" "SOURCE HEAD" "STATUS"
printf "  %-22s %-12s %-12s %s\n" "──────────────────────" "──────────" "──────────" "──────"

stale_found=false
dirty_found=false

while IFS=$'\t' read -r name image ctx; do
    [[ -n "${name//[[:space:]]/}" ]] || continue
    # A rendered config emits absolute contexts; offline fixtures may be relative.
    [[ "$ctx" == /* ]] || ctx="${REPO_ROOT}/${ctx}"

    # Source HEAD (short) of the context's ENCLOSING repo. Empty when the
    # context is absent / not inside a git repository.
    repo_dir="$(git -C "$ctx" rev-parse --show-toplevel 2>/dev/null || true)"
    src=""
    if [[ -n "$repo_dir" ]]; then
        src="$(git -C "$repo_dir" rev-parse --short HEAD 2>/dev/null || true)"
    fi

    # Prefer the running container's image; fall back to the built image tag.
    # The ps lookup passes the SAME profile/env-file args as the render — a
    # profiled service is otherwise unresolvable and the fallback always won.
    img_sha=""
    if [[ -z "$PROVENANCE_MAP" ]]; then
        cid="$(cd "$REPO_ROOT" && docker compose -f "$COMPOSE_FILE" "${PASSTHROUGH[@]}" ps -q "$name" 2>/dev/null | head -n1 || true)"
        if [[ -n "$cid" ]]; then
            img_sha="$(revision_of "$cid")"
        fi
    fi
    if [[ -z "$img_sha" ]]; then
        img_sha="$(revision_of "$image")"
    fi

    # Classify. Prefix-compare so differing short-SHA lengths (7 vs 8) still match.
    note=""
    if [[ -z "$img_sha" ]]; then
        status="${YELLOW}UNKNOWN${RESET}"
        note="no revision label (pre-provenance image, or not built)"
    elif [[ "$img_sha" == *-dirty ]]; then
        # provenance_sha.sh appended -dirty: the image was built from a tree
        # with uncommitted tracked changes, so it contains code in no commit.
        # Flag regardless of how the base SHA compares to HEAD.
        status="${RED}DIRTY${RESET}"
        note="image built from uncommitted changes — rebuild from a clean checkout"
        dirty_found=true
    elif [[ -z "$src" ]]; then
        status="${YELLOW}UNKNOWN${RESET}"
        note="source repo not found for build context ${ctx}"
    elif [[ "$img_sha" == "$src"* || "$src" == "$img_sha"* ]]; then
        status="${GREEN}FRESH${RESET}"
    else
        status="${RED}STALE${RESET}"
        note="rebuild with: make build  (image is behind source)"
        stale_found=true
    fi

    printf "  ${CYAN}%-22s${RESET} %-12s %-12s %b\n" "$name" "${img_sha:-—}" "${src:-—}" "$status"
    if [[ -n "$note" ]]; then
        printf "  ${DIM}  └── %s${RESET}\n" "$note"
    fi
done <<< "$rows_raw"

echo ""
if $dirty_found; then
    echo -e "  ${RED}Dirty image(s) detected — built from uncommitted changes; rebuild from a clean tree.${RESET}"
fi
if $stale_found; then
    echo -e "  ${RED}Stale image(s) detected — rebuild with: make build${RESET}"
fi
if $stale_found || $dirty_found; then
    exit 1
fi
echo -e "  ${GREEN}No stale or dirty images detected.${RESET}"
