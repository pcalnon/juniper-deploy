#!/usr/bin/env bash
#####################################################################################################################################################################################################
# Project:       Juniper
# Application:   juniper-deploy
# File Name:     preflight_image_provenance.sh
# Author:        Paul Calnon
#
# Date Created:  2026-07-07
#
# License:       MIT License
# Copyright:     Copyright (c) 2024-2026 Paul Calnon
#
# Description:
#    Image-provenance preflight for the bring-up path (`make up` / `demo` /
#    `dev` / `monitor` / `obs-demo`) — the INVERSE of the build-freshness
#    preflight (#150). #150 stops `make build` from baking images out of stale
#    checkouts; this preflight stops `docker compose up` from RUNNING images
#    that no longer match the code on disk ("checkout updated but image not
#    rebuilt").
#
#    Mechanism (build-provenance design, juniper-ml
#    notes/JUNIPER_2026-06-14_JUNIPER-ML_BUILD-PROVENANCE-DESIGN.md): `make
#    build` stamps each image with its source repo's short git SHA
#    (scripts/provenance_sha.sh -> build arg -> OCI label
#    org.opencontainers.image.revision, `-dirty`-suffixed when built from
#    uncommitted tracked changes). This preflight renders `docker compose
#    config --format json` for the profiles about to come up, pairs every
#    service's `image:` with its `build.context`'s ENCLOSING git repository
#    (nested contexts like ../juniper-recurrence/juniper-recurrence resolve to
#    their repo; shared images — cascor:latest x2, canopy:latest x3 — are
#    checked once), reads each BUILT image's revision label (`docker image
#    inspect`, NOT the running container: `up` recreates from the built tag),
#    and compares against the checkout's current HEAD using the same
#    conventions as scripts/doctor.sh (prefix compare so 7- vs 8-char short
#    SHAs match).
#
#    Classification (mirrors #150's philosophy: hard-fail ONLY the silent
#    incident class; deliberate dev flows warn):
#
#      [MATCH]      image revision == checkout HEAD                 -> OK
#                   (a note is added if the checkout has uncommitted
#                    tracked edits the image cannot contain)
#      [STALE]      revision != HEAD and the checkout is on its
#                   default branch                                  -> FAIL
#                   (says how many commits behind when the revision
#                    is in local history; "not in local history"
#                    otherwise — either way the image provably was
#                    not built from HEAD)
#      [DIRTY]      `-dirty` revision whose base SHA == HEAD:
#                     checkout still dirty  -> warn (in-flight work)
#                     checkout now clean    -> FAIL (the image holds
#                       uncommitted code that no longer exists)
#      [BRANCH]     revision != HEAD on a NON-default branch        -> warn
#                   (deliberate feature-branch state assumed)
#      [NO-IMAGE]   image not built yet                             -> info
#                   (`docker compose up` builds it fresh from the
#                    current checkout)
#      [UNVERIFIED] empty/absent revision label (pre-provenance or
#                   built without PROVENANCE_ENV), non-git context,
#                   or docker daemon unreachable                    -> warn
#
#    Fix for any FAIL: `make build` (itself gated by the build-freshness
#    preflight, so the rebuild is guaranteed to come from current checkouts),
#    then re-run the bring-up. Escape hatch: `--allow-stale` or
#    JUNIPER_IMAGE_STALE_OK=1 downgrades FAILs to loud warnings.
#
#    Relationship to `make doctor` (scripts/doctor.sh): doctor is the
#    interactive running-stack auditor (prefers the running container's
#    image); this preflight is the enforcing bring-up gate over the rendered
#    compose config. Same label, same comparison conventions.
#
# Usage:
#    make image-preflight
#    scripts/preflight_image_provenance.sh [--profile full] [--env-file FILE] ...
#    scripts/preflight_image_provenance.sh --config-json rendered.json \
#        --image-provenance-map shas.json                            # offline
#
#    Any argument other than the flags below is passed through verbatim to
#    `docker compose <ARGS> config --format json`, so the preflight inspects
#    exactly the services the matching bring-up will start.
#
#      --config-json FILE           Check a pre-rendered `docker compose
#                                   config --format json` FILE instead of
#                                   invoking docker (offline; CI).
#      --image-provenance-map FILE  JSON object mapping image ref ->
#                                   revision-label value ("" = image exists
#                                   but has no label; a MISSING key = image
#                                   not built). Replaces `docker image
#                                   inspect` (offline; used by the CI lint
#                                   tests/test_image_provenance_preflight.py).
#      --allow-stale                Downgrade STALE/DIRTY-orphan from FAIL to
#                                   a warning (same as
#                                   JUNIPER_IMAGE_STALE_OK=1).
#      -h, --help                   Show this help and exit.
#
# Exit status:
#    0  every built image matches its checkout (or staleness was explicitly
#       allowed); warnings do not fail
#    1  an image about to run provably does not match its default-branch
#       checkout (stale image / orphaned-dirty image) — bring-up refused
#    2  usage error / compose render failure
#
#####################################################################################################################################################################################################

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.yml}"
REVISION_LABEL="org.opencontainers.image.revision"

usage() {
    sed -nE 's/^# ?//p' "${BASH_SOURCE[0]}" | sed -n '/^Usage:/,/^Exit status:/p'
}

CONFIG_JSON=""
PROVENANCE_MAP=""
ALLOW_STALE=0
[[ "${JUNIPER_IMAGE_STALE_OK:-}" == "1" ]] && ALLOW_STALE=1
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
        --allow-stale)
            ALLOW_STALE=1
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

if [[ -n "$PROVENANCE_MAP" && ! -f "$PROVENANCE_MAP" ]]; then
    echo "preflight_image_provenance: --image-provenance-map file not found: ${PROVENANCE_MAP}" >&2
    exit 2
fi

# ── Obtain the rendered compose config JSON ────────────────────────────────
if [[ -n "$CONFIG_JSON" ]]; then
    if [[ ! -f "$CONFIG_JSON" ]]; then
        echo "preflight_image_provenance: --config-json file not found: ${CONFIG_JSON}" >&2
        exit 2
    fi
    render_json="$(cat -- "$CONFIG_JSON")"
    source_desc="--config-json ${CONFIG_JSON}"
else
    source_desc="docker compose ${PASSTHROUGH[*]:-} config"
    if ! command -v docker >/dev/null 2>&1; then
        echo "preflight_image_provenance: docker not found; pass --config-json for an offline check" >&2
        exit 2
    fi
    if ! render_json="$(cd "$REPO_ROOT" && docker compose -f "$COMPOSE_FILE" "${PASSTHROUGH[@]}" config --format json 2>/dev/null)"; then
        echo "preflight_image_provenance: \`docker compose -f ${COMPOSE_FILE} ${PASSTHROUGH[*]:-} config\` failed to render" >&2
        exit 2
    fi
fi

if [[ -z "${render_json//[[:space:]]/}" ]]; then
    echo "preflight_image_provenance: empty compose config render (nothing to check)" >&2
    exit 2
fi

# ── Extract image<TAB>context pairs for every built service ────────────────
# python3 owns the JSON parse (stdlib only, no jq — mirrors the sibling
# preflights); bash owns the git/docker orchestration and the verdict.
render_file="$(mktemp "${TMPDIR:-/tmp}/preflight_image_provenance.XXXXXX")"
trap 'rm -f "$render_file"' EXIT
printf '%s' "$render_json" > "$render_file"

pairs_raw="$(python3 - "$render_file" <<'PY'
import json
import sys

try:
    with open(sys.argv[1], encoding="utf-8") as handle:
        config = json.loads(handle.read())
except (OSError, ValueError) as exc:
    sys.stderr.write(f"preflight_image_provenance: could not read/parse compose config JSON: {exc}\n")
    sys.exit(2)

pairs = {}
for name in sorted(config.get("services") or {}):
    svc = (config["services"][name] or {})
    build = svc.get("build")
    image = svc.get("image")
    if not build or not image:
        continue  # image-only services (redis, prometheus, ...) have no local source to compare
    if isinstance(build, str):
        context = build
    else:
        context = build.get("context") or ""
    if context:
        pairs.setdefault(str(image), str(context))
for image in sorted(pairs):
    print(f"{image}\t{pairs[image]}")
PY
)"

# ── Colors (match the sibling preflights) ──────────────────────────────────
if [[ -n "${NO_COLOR:-}" ]]; then
    GREEN="" RED="" YELLOW="" CYAN="" BOLD="" DIM="" RESET=""
else
    GREEN=$'\033[0;32m' RED=$'\033[0;31m' YELLOW=$'\033[0;33m'
    CYAN=$'\033[0;36m' BOLD=$'\033[1m' DIM=$'\033[2m' RESET=$'\033[0m'
fi

echo "${BOLD}Juniper Platform — Image-Provenance Preflight${RESET}"
echo "${DIM}  verify the built images about to run match the code on disk (${REVISION_LABEL})${RESET}"
echo "${DIM}  source: ${source_desc}${RESET}"
echo ""

if [[ -z "${pairs_raw//[[:space:]]/}" ]]; then
    echo "${YELLOW}  PASS (no-op) — no service declares both build: and image:; nothing to check.${RESET}"
    exit 0
fi

# Provenance lookup: offline map, or `docker image inspect` on the built tag.
DAEMON_OK=1
if [[ -z "$PROVENANCE_MAP" ]]; then
    if ! docker info >/dev/null 2>&1; then
        DAEMON_OK=0
    fi
fi

provenance_of() { # image ref -> revision label; "__ABSENT__" when the image is not built
    local image="$1" sha
    if [[ -n "$PROVENANCE_MAP" ]]; then
        sha="$(python3 - "$PROVENANCE_MAP" "$image" <<'PY'
import json
import sys

with open(sys.argv[1], encoding="utf-8") as handle:
    mapping = json.load(handle)
if sys.argv[2] not in mapping:
    print("__ABSENT__")
else:
    print(mapping[sys.argv[2]] or "")
PY
        )"
        printf '%s' "$sha"
        return 0
    fi
    if ! sha="$(docker image inspect --format "{{ index .Config.Labels \"${REVISION_LABEL}\" }}" "$image" 2>/dev/null)"; then
        printf '%s' "__ABSENT__"
        return 0
    fi
    [[ "$sha" == "<no value>" ]] && sha=""
    printf '%s' "$sha"
}

match_count=0
warn_count=0
declare -a failures=()   # "image|repo|detail"

report() { # label_color label image detail
    local label_color="$1" label="$2" image="$3" detail="$4"
    printf '  %s[%-10s]%s %s%-28s%s %s\n' "$label_color" "$label" "$RESET" "$CYAN" "$image" "$RESET" "$detail"
}

while IFS=$'\t' read -r image ctx; do
    [[ -n "${image//[[:space:]]/}" ]] || continue
    # A rendered config emits absolute contexts; offline fixtures may be relative.
    [[ "$ctx" == /* ]] || ctx="${REPO_ROOT}/${ctx}"

    toplevel="$(git -C "$ctx" rev-parse --show-toplevel 2>/dev/null || true)"
    if [[ -z "$toplevel" ]]; then
        report "$YELLOW" "UNVERIFIED" "$image" "build context ${ctx} is not inside a git repository — provenance cannot be compared"
        warn_count=$((warn_count + 1))
        continue
    fi

    if [[ -z "$PROVENANCE_MAP" && "$DAEMON_OK" -eq 0 ]]; then
        report "$YELLOW" "UNVERIFIED" "$image" "docker daemon unreachable — cannot inspect the built image (compose up will fail on its own if it stays down)"
        warn_count=$((warn_count + 1))
        continue
    fi

    head_sha="$(git -C "$toplevel" rev-parse --short HEAD 2>/dev/null || true)"
    if [[ -z "$head_sha" ]]; then
        report "$YELLOW" "UNVERIFIED" "$image" "cannot resolve HEAD of ${toplevel}"
        warn_count=$((warn_count + 1))
        continue
    fi

    branch="$(git -C "$toplevel" rev-parse --abbrev-ref HEAD 2>/dev/null || echo "HEAD")"
    default_branch="$(git -C "$toplevel" symbolic-ref --short refs/remotes/origin/HEAD 2>/dev/null || true)"
    default_branch="${default_branch#origin/}"
    [[ -n "$default_branch" ]] || default_branch="main"

    tree_dirty=0
    [[ -n "$(git -C "$toplevel" status --porcelain --untracked-files=no 2>/dev/null)" ]] && tree_dirty=1

    img_sha="$(provenance_of "$image")"

    if [[ "$img_sha" == "__ABSENT__" ]]; then
        report "$DIM" "NO-IMAGE" "$image" "not built yet — docker compose up builds it fresh from ${toplevel} @ ${head_sha}"
        continue
    fi

    if [[ -z "$img_sha" ]]; then
        report "$YELLOW" "UNVERIFIED" "$image" "image has no ${REVISION_LABEL} label (pre-provenance image, or built without make build) — rebuild with: make build"
        warn_count=$((warn_count + 1))
        continue
    fi

    dirty_image=0
    base_sha="$img_sha"
    if [[ "$img_sha" == *-dirty ]]; then
        dirty_image=1
        base_sha="${img_sha%-dirty}"
    fi

    # Prefix-compare so differing short-SHA lengths (7 vs 8) still match
    # (same convention as scripts/doctor.sh).
    sha_match=0
    if [[ "$base_sha" == "$head_sha"* || "$head_sha" == "$base_sha"* ]]; then
        sha_match=1
    fi

    if [[ "$dirty_image" -eq 1 ]]; then
        if [[ "$sha_match" -eq 1 && "$tree_dirty" -eq 1 ]]; then
            report "$YELLOW" "DIRTY" "$image" "built from ${img_sha} (uncommitted tracked changes) and the checkout is still dirty — in-flight local work assumed"
            warn_count=$((warn_count + 1))
        elif [[ "$sha_match" -eq 1 ]]; then
            if [[ "$ALLOW_STALE" -eq 1 ]]; then
                report "$YELLOW" "DIRTY-OK" "$image" "built from ${img_sha} but the checkout is now CLEAN at ${head_sha} — image holds code that exists in no commit; allowed by JUNIPER_IMAGE_STALE_OK"
                warn_count=$((warn_count + 1))
            else
                report "$RED" "DIRTY" "$image" "built from ${img_sha} but the checkout is now CLEAN at ${head_sha} — the image holds uncommitted code that no longer exists on disk"
                failures+=("${image}|${toplevel}|orphaned-dirty image (rebuild from the clean checkout)")
            fi
            continue
        fi
        if [[ "$sha_match" -eq 1 ]]; then
            continue
        fi
        # dirty AND base mismatch: fall through to the stale/branch logic below
        # using the base SHA (the dirtiness is secondary to being outdated).
    fi

    if [[ "$sha_match" -eq 1 ]]; then
        note=""
        [[ "$tree_dirty" -eq 1 ]] && note="  ${YELLOW}(checkout has uncommitted tracked edits the image cannot contain)${RESET}"
        report "$GREEN" "MATCH" "$image" "revision ${img_sha} == ${toplevel##*/} HEAD ${head_sha}${note}"
        match_count=$((match_count + 1))
        [[ -n "$note" ]] && warn_count=$((warn_count + 1))
        continue
    fi

    # Revision != HEAD. Compute a behind-count when the revision exists locally.
    detail="revision ${img_sha} != HEAD ${head_sha}"
    if git -C "$toplevel" cat-file -e "${base_sha}^{commit}" 2>/dev/null; then
        behind="$(git -C "$toplevel" rev-list --count "${base_sha}..HEAD" 2>/dev/null || echo "?")"
        if [[ "$behind" != "?" && "$behind" -gt 0 ]]; then
            detail="image revision ${img_sha} is ${behind} commit(s) behind ${toplevel##*/} HEAD ${head_sha}"
        fi
    else
        detail="image revision ${img_sha} is not in ${toplevel##*/} local history (HEAD ${head_sha})"
    fi

    if [[ "$branch" != "$default_branch" ]]; then
        report "$YELLOW" "BRANCH" "$image" "${detail}; checkout on '${branch}' — deliberate non-default-branch state assumed"
        warn_count=$((warn_count + 1))
    elif [[ "$ALLOW_STALE" -eq 1 ]]; then
        report "$YELLOW" "STALE-OK" "$image" "${detail} — allowed by JUNIPER_IMAGE_STALE_OK"
        warn_count=$((warn_count + 1))
    else
        report "$RED" "STALE" "$image" "$detail"
        failures+=("${image}|${toplevel}|${detail}")
    fi
done <<< "$pairs_raw"

echo ""

if [[ "${#failures[@]}" -gt 0 ]]; then
    echo "${BOLD}${RED}  FAIL — ${#failures[@]} image(s) about to run do NOT match the code on disk:${RESET}"
    for failure in "${failures[@]}"; do
        image="${failure%%|*}"
        rest="${failure#*|}"
        repo="${rest%%|*}"
        detail="${rest#*|}"
        echo "${RED}    • ${image} (${repo}): ${detail}.${RESET}"
    done
    echo "${DIM}      Fix: make build    (freshness-gated, then re-run the bring-up target)${RESET}"
    echo "${DIM}      Deliberately running the stale image instead: JUNIPER_IMAGE_STALE_OK=1 make <target> (or --allow-stale).${RESET}"
    echo "${BOLD}${RED}  Image-provenance preflight FAILED — refusing to start images that do not match their checkouts.${RESET}"
    exit 1
fi

if [[ "$warn_count" -gt 0 ]]; then
    echo "${GREEN}  PASS — ${match_count} image(s) match their checkouts; ${YELLOW}${warn_count} warning(s) above${GREEN} (unverifiable/deliberate states do not block).${RESET}"
else
    echo "${GREEN}  PASS — ${match_count} image(s) match their checkouts; provenance verified.${RESET}"
fi
exit 0
