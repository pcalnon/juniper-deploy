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
#    Build-provenance drift checker. For each Juniper service image, compares
#    the source git SHA baked into the image (the OCI
#    org.opencontainers.image.revision label, read via `docker inspect`) with
#    the current HEAD of that service's sibling source repo, and reports
#    FRESH / STALE / UNKNOWN per service so a container silently running behind
#    source is caught.
#
#    Uses `docker inspect` of the image label rather than the service's
#    /v1/health endpoint because not every service publishes its port on the
#    host (e.g. juniper-data), so a label read works uniformly. The running
#    container's image is inspected when up; otherwise the built `:latest`
#    image is used (catches "forgot to rebuild after a source change").
#
#    See juniper-ml notes/BUILD_PROVENANCE_DESIGN_2026-06-14.md (Part 7).
#
# Usage:
#    make doctor
#    bash scripts/doctor.sh
#
# Exit status:
#    0  no STALE image found (FRESH / UNKNOWN are non-fatal)
#    1  at least one running/built image is STALE relative to its source repo
#
#####################################################################################################################################################################################################

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
# Sibling Juniper source repos live next to juniper-deploy.
SIBLING_ROOT="$(cd "${REPO_ROOT}/.." && pwd)"
COMPOSE=(docker compose)
COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.yml}"
REVISION_LABEL="org.opencontainers.image.revision"

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

# compose service name | image ref | sibling source repo dir name
SERVICES=(
    "juniper-data|juniper-data:latest|juniper-data"
    "juniper-cascor|juniper-cascor:latest|juniper-cascor"
    "juniper-canopy|juniper-canopy:latest|juniper-canopy"
    "juniper-cascor-worker|juniper-cascor-worker:latest|juniper-cascor-worker"
)

# Read the build-provenance revision label from a container id or image ref.
# Empty string when the ref is missing or carries no such label.
revision_of() {
    local ref="$1" sha
    sha="$(docker inspect --format "{{ index .Config.Labels \"${REVISION_LABEL}\" }}" "$ref" 2>/dev/null || true)"
    [[ "$sha" == "<no value>" ]] && sha=""
    printf '%s' "$sha"
}

echo -e "${BOLD}Juniper Platform — Build-Provenance Doctor${RESET}"
echo -e "${DIM}  running image revision (OCI label) vs source repo HEAD${RESET}"
echo ""
printf "  %-22s %-12s %-12s %s\n" "SERVICE" "IMAGE SHA" "SOURCE HEAD" "STATUS"
printf "  %-22s %-12s %-12s %s\n" "──────────────────────" "──────────" "──────────" "──────"

stale_found=false
dirty_found=false

for entry in "${SERVICES[@]}"; do
    IFS='|' read -r name image repo <<< "$entry"
    repo_dir="${SIBLING_ROOT}/${repo}"

    # Source HEAD (short). Empty when the sibling repo is absent / not a repo.
    src="$(git -C "$repo_dir" rev-parse --short HEAD 2>/dev/null || true)"

    # Prefer the running container's image; fall back to the built :latest image.
    cid="$("${COMPOSE[@]}" -f "${REPO_ROOT}/${COMPOSE_FILE}" ps -q "$name" 2>/dev/null | head -n1 || true)"
    if [[ -n "$cid" ]]; then
        img_sha="$(revision_of "$cid")"
    else
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
        note="source repo not found at ../${repo}"
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
done

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
