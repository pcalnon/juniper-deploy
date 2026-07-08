#!/usr/bin/env bash
#####################################################################################################################################################################################################
# Project:       Juniper
# Application:   juniper-deploy
# File Name:     preflight_build_freshness.sh
# Author:        Paul Calnon
#
# Date Created:  2026-07-07
#
# License:       MIT License
# Copyright:     Copyright (c) 2024-2026 Paul Calnon
#
# Description:
#    Build-freshness preflight for `make build` / `make build-no-cache`. The
#    compose stack builds its first-party images from LOCAL sibling checkouts
#    (`build.context: ../juniper-cascor` etc.), so image freshness is bounded
#    by local-checkout freshness — NOT by GitHub main. A cross-repo coupled
#    change (e.g. the SEC-F22/D2 two-flag env contract) can be merged in every
#    repo yet still produce broken images if a sibling checkout is stale at
#    build time.
#
#    Incident of record (2026-07-07): deploy #148 switched compose to the
#    two-flag attestation while the local juniper-cascor / juniper-canopy
#    checkouts (3 and 5 commits behind their already-merged sibling PRs
#    cascor#393 / canopy#432) fed `make build` — the rebuilt images enforced
#    the OLD flag against the NEW env, and juniper-cascor crash-looped
#    (exit 3, NonLoopbackBindError) blocking canopy + both workers.
#
#    This preflight renders `docker compose config --format json`, resolves
#    every unique `build.context` to its ENCLOSING git repository (contexts
#    may be nested subdirectories, e.g. ../juniper-recurrence/juniper-recurrence),
#    fetches the origin default branch (local-path remotes work offline;
#    network failure degrades to a warning), and classifies each repo:
#
#      [FRESH]      on the default branch, in sync with origin      -> OK
#      [STALE]      on the default branch, BEHIND origin            -> FAIL
#      [DIVERGED]   on the default branch, ahead AND behind origin  -> FAIL
#      [AHEAD]      on the default branch, ahead of origin only     -> warn
#      [BRANCH]     on a non-default branch / detached HEAD         -> warn
#                   (building unmerged work is a deliberate dev flow)
#      [UNVERIFIED] not a git repo / no origin remote / no ref      -> warn
#      [MISSING]    context directory does not exist                -> warn
#                   (the compose build itself would fail anyway)
#
#    A dirty working tree is appended as a note on any status (uncommitted
#    changes get baked into the image). Only [STALE] / [DIVERGED] on the
#    default branch — exactly the incident class — refuse the build (exit 1).
#    Escape hatch: `--allow-stale` or JUNIPER_BUILD_STALE_OK=1 downgrades the
#    refusal to a loud warning (exit 0).
#
#    Wired into the Makefile build path (`build` / `build-no-cache`) before
#    `docker compose build`, and exposed standalone as `make build-preflight`.
#    Parse-only apart from `git fetch` of the origin default branch — it never
#    touches the working trees, the images, or the running stack.
#
# Usage:
#    make build-preflight
#    scripts/preflight_build_freshness.sh [--profile full] [--env-file FILE] ...
#    scripts/preflight_build_freshness.sh --config-json rendered.json   # offline
#
#    Any argument other than the flags below is passed through verbatim to
#    `docker compose <ARGS> config --format json`, so the preflight inspects
#    exactly the build contexts the matching `docker compose build` will use.
#
#      --config-json FILE   Check a pre-rendered `docker compose config
#                           --format json` FILE instead of invoking docker
#                           (offline; used by the CI lint
#                           tests/test_build_freshness_preflight.py).
#      --no-fetch           Skip `git fetch`; compare against the last-fetched
#                           origin refs (offline mode; may under-report).
#      --allow-stale        Downgrade STALE/DIVERGED from FAIL to a warning
#                           (same as JUNIPER_BUILD_STALE_OK=1).
#      -h, --help           Show this help and exit.
#
# Exit status:
#    0  every build-context checkout on its default branch is current with
#       origin (or staleness was explicitly allowed); warnings do not fail
#    1  a build-context checkout on its default branch is BEHIND (or has
#       DIVERGED from) its origin default branch — build refused
#    2  usage error / compose render failure
#
#####################################################################################################################################################################################################

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.yml}"

usage() {
    sed -nE 's/^# ?//p' "${BASH_SOURCE[0]}" | sed -n '/^Usage:/,/^Exit status:/p'
}

CONFIG_JSON=""
NO_FETCH=0
ALLOW_STALE=0
[[ "${JUNIPER_BUILD_STALE_OK:-}" == "1" ]] && ALLOW_STALE=1
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
        --no-fetch)
            NO_FETCH=1
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

# ── Obtain the rendered compose config JSON ────────────────────────────────
if [[ -n "$CONFIG_JSON" ]]; then
    if [[ ! -f "$CONFIG_JSON" ]]; then
        echo "preflight_build_freshness: --config-json file not found: ${CONFIG_JSON}" >&2
        exit 2
    fi
    render_json="$(cat -- "$CONFIG_JSON")"
    source_desc="--config-json ${CONFIG_JSON}"
else
    source_desc="docker compose ${PASSTHROUGH[*]:-} config"
    if ! command -v docker >/dev/null 2>&1; then
        echo "preflight_build_freshness: docker not found; pass --config-json for an offline check" >&2
        exit 2
    fi
    if ! render_json="$(cd "$REPO_ROOT" && docker compose -f "$COMPOSE_FILE" "${PASSTHROUGH[@]}" config --format json 2>/dev/null)"; then
        echo "preflight_build_freshness: \`docker compose -f ${COMPOSE_FILE} ${PASSTHROUGH[*]:-} config\` failed to render" >&2
        exit 2
    fi
fi

if [[ -z "${render_json//[[:space:]]/}" ]]; then
    echo "preflight_build_freshness: empty compose config render (nothing to check)" >&2
    exit 2
fi

# ── Extract the unique build contexts ──────────────────────────────────────
# python3 owns the JSON parse (guaranteed present — the repo's tests are
# python; mirrors preflight_bind_posture.sh, no jq dependency). bash owns the
# git orchestration and the verdict.
render_file="$(mktemp "${TMPDIR:-/tmp}/preflight_build_freshness.XXXXXX")"
trap 'rm -f "$render_file"' EXIT
printf '%s' "$render_json" > "$render_file"

contexts_raw="$(python3 - "$render_file" <<'PY'
import json
import sys

try:
    with open(sys.argv[1], encoding="utf-8") as handle:
        config = json.loads(handle.read())
except (OSError, ValueError) as exc:
    sys.stderr.write(f"preflight_build_freshness: could not read/parse compose config JSON: {exc}\n")
    sys.exit(2)

contexts = set()
for svc in (config.get("services") or {}).values():
    build = (svc or {}).get("build")
    if isinstance(build, str):
        contexts.add(build)
    elif isinstance(build, dict):
        context = build.get("context")
        if context:
            contexts.add(str(context))
print("\n".join(sorted(contexts)))
PY
)"

# ── Colors (match the Makefile / sibling preflight conventions) ────────────
if [[ -n "${NO_COLOR:-}" ]]; then
    GREEN="" RED="" YELLOW="" CYAN="" BOLD="" DIM="" RESET=""
else
    GREEN=$'\033[0;32m' RED=$'\033[0;31m' YELLOW=$'\033[0;33m'
    CYAN=$'\033[0;36m' BOLD=$'\033[1m' DIM=$'\033[2m' RESET=$'\033[0m'
fi

echo "${BOLD}Juniper Platform — Build-Freshness Preflight${RESET}"
echo "${DIM}  verify every compose build-context checkout is current with its origin${RESET}"
echo "${DIM}  source: ${source_desc}${RESET}"
echo ""

if [[ -z "${contexts_raw//[[:space:]]/}" ]]; then
    echo "${YELLOW}  PASS (no-op) — no service declares a build context; nothing to check.${RESET}"
    exit 0
fi

mapfile -t contexts <<< "$contexts_raw"

declare -A seen_repos=()
fresh_count=0
warn_count=0
declare -a failures=()   # "repo|kind|detail"

report() { # label_color label repo detail
    local label_color="$1" label="$2" repo="$3" detail="$4"
    printf '  %s[%-10s]%s %s%s%s  %s\n' "$label_color" "$label" "$RESET" "$CYAN" "$repo" "$RESET" "$detail"
}

for ctx in "${contexts[@]}"; do
    [[ -n "${ctx//[[:space:]]/}" ]] || continue
    # A rendered config emits absolute contexts; offline fixtures may be relative.
    [[ "$ctx" == /* ]] || ctx="${REPO_ROOT}/${ctx}"

    if [[ ! -d "$ctx" ]]; then
        report "$YELLOW" "MISSING" "$ctx" "context directory does not exist (the compose build itself would fail)"
        warn_count=$((warn_count + 1))
        continue
    fi

    toplevel="$(git -C "$ctx" rev-parse --show-toplevel 2>/dev/null || true)"
    if [[ -z "$toplevel" ]]; then
        report "$YELLOW" "UNVERIFIED" "$ctx" "not inside a git repository — freshness cannot be checked"
        warn_count=$((warn_count + 1))
        continue
    fi

    # Contexts may be nested subdirectories of one repo — check each repo once.
    if [[ -n "${seen_repos[$toplevel]:-}" ]]; then
        continue
    fi
    seen_repos[$toplevel]=1

    if ! git -C "$toplevel" remote get-url origin >/dev/null 2>&1; then
        report "$YELLOW" "UNVERIFIED" "$toplevel" "no 'origin' remote — freshness cannot be checked"
        warn_count=$((warn_count + 1))
        continue
    fi

    default_branch="$(git -C "$toplevel" symbolic-ref --short refs/remotes/origin/HEAD 2>/dev/null || true)"
    default_branch="${default_branch#origin/}"
    [[ -n "$default_branch" ]] || default_branch="main"

    fetch_note=""
    if [[ "$NO_FETCH" -eq 1 ]]; then
        fetch_note=" ${DIM}(--no-fetch: compared against last-fetched refs)${RESET}"
    elif ! GIT_TERMINAL_PROMPT=0 git -C "$toplevel" fetch --quiet origin "$default_branch" 2>/dev/null; then
        fetch_note=" ${DIM}(fetch failed — compared against last-fetched refs)${RESET}"
    fi

    if ! git -C "$toplevel" rev-parse --verify --quiet "origin/${default_branch}" >/dev/null 2>&1; then
        report "$YELLOW" "UNVERIFIED" "$toplevel" "no origin/${default_branch} ref — freshness cannot be checked${fetch_note}"
        warn_count=$((warn_count + 1))
        continue
    fi

    branch="$(git -C "$toplevel" rev-parse --abbrev-ref HEAD 2>/dev/null || echo "HEAD")"
    head_sha="$(git -C "$toplevel" rev-parse --short=8 HEAD 2>/dev/null || echo "????????")"

    dirty_note=""
    if [[ -n "$(git -C "$toplevel" status --porcelain 2>/dev/null)" ]]; then
        dirty_note=" ${YELLOW}+ DIRTY working tree (uncommitted changes get baked into the image)${RESET}"
    fi

    if [[ "$branch" != "$default_branch" ]]; then
        report "$YELLOW" "BRANCH" "$toplevel" "on '${branch}' @ ${head_sha}, not '${default_branch}' — deliberate non-default-branch build assumed${dirty_note}${fetch_note}"
        warn_count=$((warn_count + 1))
        continue
    fi

    counts="$(git -C "$toplevel" rev-list --left-right --count "HEAD...origin/${default_branch}" 2>/dev/null || echo "0	0")"
    ahead="${counts%%[[:space:]]*}"
    behind="${counts##*[[:space:]]}"

    if [[ "$behind" -gt 0 && "$ahead" -gt 0 ]]; then
        if [[ "$ALLOW_STALE" -eq 1 ]]; then
            report "$YELLOW" "DIVERGED" "$toplevel" "${branch} @ ${head_sha} is ${ahead} ahead / ${behind} BEHIND origin/${default_branch} — allowed by JUNIPER_BUILD_STALE_OK${dirty_note}${fetch_note}"
            warn_count=$((warn_count + 1))
        else
            report "$RED" "DIVERGED" "$toplevel" "${branch} @ ${head_sha} is ${ahead} ahead / ${behind} BEHIND origin/${default_branch}${dirty_note}${fetch_note}"
            failures+=("${toplevel}|DIVERGED|${behind}")
        fi
    elif [[ "$behind" -gt 0 ]]; then
        if [[ "$ALLOW_STALE" -eq 1 ]]; then
            report "$YELLOW" "STALE-OK" "$toplevel" "${branch} @ ${head_sha} is ${behind} commit(s) BEHIND origin/${default_branch} — allowed by JUNIPER_BUILD_STALE_OK${dirty_note}${fetch_note}"
            warn_count=$((warn_count + 1))
        else
            report "$RED" "STALE" "$toplevel" "${branch} @ ${head_sha} is ${behind} commit(s) BEHIND origin/${default_branch}${dirty_note}${fetch_note}"
            failures+=("${toplevel}|STALE|${behind}")
        fi
    elif [[ "$ahead" -gt 0 ]]; then
        report "$YELLOW" "AHEAD" "$toplevel" "${branch} @ ${head_sha} is ${ahead} commit(s) ahead of origin/${default_branch} (unpushed local work)${dirty_note}${fetch_note}"
        warn_count=$((warn_count + 1))
    else
        report "$GREEN" "FRESH" "$toplevel" "${branch} @ ${head_sha} in sync with origin/${default_branch}${dirty_note}${fetch_note}"
        fresh_count=$((fresh_count + 1))
        [[ -n "$dirty_note" ]] && warn_count=$((warn_count + 1))
    fi
done

echo ""

if [[ "${#failures[@]}" -gt 0 ]]; then
    echo "${BOLD}${RED}  FAIL — ${#failures[@]} build-context checkout(s) are STALE; images built now would NOT match origin:${RESET}"
    for failure in "${failures[@]}"; do
        repo="${failure%%|*}"
        rest="${failure#*|}"
        kind="${rest%%|*}"
        behind="${rest#*|}"
        echo "${RED}    • ${repo} (${kind}: ${behind} commit(s) behind).${RESET}"
        echo "${DIM}      Fix: git -C ${repo} pull --ff-only    (then re-run make build)${RESET}"
    done
    echo "${DIM}      Deliberately building stale/local state instead: JUNIPER_BUILD_STALE_OK=1 make build (or --allow-stale).${RESET}"
    echo "${BOLD}${RED}  Build-freshness preflight FAILED — refusing to build images from stale checkouts.${RESET}"
    exit 1
fi

if [[ "$warn_count" -gt 0 ]]; then
    echo "${GREEN}  PASS — ${fresh_count} checkout(s) fresh; ${YELLOW}${warn_count} warning(s) above${GREEN} (non-default branches / unverifiable contexts do not block).${RESET}"
else
    echo "${GREEN}  PASS — ${fresh_count} build-context checkout(s) in sync with origin; freshness verified.${RESET}"
fi
exit 0
