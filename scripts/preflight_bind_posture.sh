#!/usr/bin/env bash
#####################################################################################################################################################################################################
# Project:       Juniper
# Application:   juniper-deploy
# File Name:     preflight_bind_posture.sh
# Author:        Paul Calnon
#
# License:       MIT License
# Copyright:     Copyright (c) 2024-2026 Paul Calnon
#
# Description:
#    Verifiable bring-up preflight for the two-flag bind attestation
#    (deployment trust contract notes/DEPLOYMENT_TRUST_CONTRACT_2026-07-04.md
#    §3/§5, design D2). Renders `docker compose config --format json` and, for
#    every service that sets ``JUNIPER_<SVC>_LOOPBACK_PUBLISH_ATTESTED=true``,
#    asserts that EVERY published host port for that service binds a loopback
#    IP (127.0.0.0/8 or ::1). The compose containers bind 0.0.0.0 inside their
#    netns (``..._HOST=0.0.0.0``), so canopy/cascor's app-layer startup
#    bind-guard would hard-fail unless one attestation flag is set; this guard
#    makes the LOOPBACK_PUBLISH attestation VERIFIABLE (that is B's job) rather
#    than a bare claim, catching the silent ``BIND_HOST=0.0.0.0`` footgun
#    BEFORE the stack comes up.
#
#    A service that attests loopback-publish but publishes a NON-loopback host
#    IP and does NOT also set ``JUNIPER_<SVC>_AUTH_PROXY_ATTESTED=true`` is a
#    hard failure (exit 1, loud). The AUTH_PROXY flag is the Phase-4 (D7)
#    escape hatch — attestation-only (a fronting authenticating reverse proxy
#    is asserted present); this preflight does not, and cannot, verify the
#    proxy, so it only stops verifying the loopback bind when that flag is set.
#
#    Wired into the Makefile bring-up path (up/demo/dev/monitor/obs-demo)
#    before `docker compose up`, and exposed as `make preflight`. Parse-only —
#    `docker compose config` never touches the running stack or the daemon
#    state.
#
# Usage:
#    make preflight
#    scripts/preflight_bind_posture.sh [--profile full] [--env-file FILE] ...
#    scripts/preflight_bind_posture.sh --config-json rendered.json   # offline
#
#    Any argument other than the two below is passed through verbatim to
#    `docker compose <ARGS> config --format json`, so the preflight renders
#    exactly the config the matching bring-up will start (same --profile /
#    --env-file flags).
#
#      --config-json FILE   Check a pre-rendered `docker compose config
#                           --format json` FILE instead of invoking docker
#                           (offline; used by the CI lint
#                           tests/test_compose_bind_posture_attestation.py).
#      -h, --help           Show this help and exit.
#
# Exit status:
#    0  every loopback-publish-attested service publishes loopback-only
#       (or a non-loopback publish is explicitly AUTH_PROXY-attested)
#    1  a loopback-publish-attested service publishes a non-loopback host bind
#       with no AUTH_PROXY attestation (posture violation — bring-up refused)
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
    [[ -f "$CONFIG_JSON" ]] || {
        echo "preflight_bind_posture: --config-json file not found: ${CONFIG_JSON}" >&2
        exit 2
    }
    render_json="$(cat -- "$CONFIG_JSON")"
    source_desc="--config-json ${CONFIG_JSON}"
else
    source_desc="docker compose ${PASSTHROUGH[*]:-} config"
    if ! command -v docker >/dev/null 2>&1; then
        echo "preflight_bind_posture: docker not found; pass --config-json for an offline check" >&2
        exit 2
    fi
    if ! render_json="$(cd "$REPO_ROOT" && docker compose -f "$COMPOSE_FILE" "${PASSTHROUGH[@]}" config --format json 2>/dev/null)"; then
        echo "preflight_bind_posture: \`docker compose -f ${COMPOSE_FILE} ${PASSTHROUGH[*]:-} config\` failed to render" >&2
        exit 2
    fi
fi

if [[ -z "${render_json//[[:space:]]/}" ]]; then
    echo "preflight_bind_posture: empty compose config render (nothing to check)" >&2
    exit 2
fi

# ── Classify the rendered config ───────────────────────────────────────────
# The IP-in-CIDR loopback classification (127.0.0.0/8 + ::1, with
# IPv4-mapped-IPv6 unwrap to mirror MetricsAuthMiddleware) is done in python3
# (guaranteed present — the repo's tests are python), keeping this one
# self-contained bash file with no jq dependency. python owns the JSON parse
# and the verdict; bash owns orchestration. The program is fed on stdin
# (`python3 -`); the source label + rendered-config path are argv (the heredoc
# owns stdin, so the JSON cannot ride the same channel). This is the final
# command, so under `set -e` + `pipefail` python's exact exit status (0 pass /
# 1 posture violation / 2 parse error) becomes the script's exit status.
render_file="$(mktemp "${TMPDIR:-/tmp}/preflight_bind_posture.XXXXXX")"
trap 'rm -f "$render_file"' EXIT
printf '%s' "$render_json" > "$render_file"

python3 - "$source_desc" "$render_file" <<'PY'
import ipaddress
import json
import os
import sys

ATTEST_SUFFIX = "_LOOPBACK_PUBLISH_ATTESTED"
PROXY_SUFFIX = "_AUTH_PROXY_ATTESTED"
LOOPBACK_V4 = ipaddress.ip_network("127.0.0.0/8")

source_desc = sys.argv[1] if len(sys.argv) > 1 else "compose config"
render_path = sys.argv[2] if len(sys.argv) > 2 else ""

if os.environ.get("NO_COLOR"):
    GREEN = RED = YELLOW = CYAN = BOLD = DIM = RESET = ""
else:
    GREEN, RED, YELLOW = "\033[0;32m", "\033[0;31m", "\033[0;33m"
    CYAN, BOLD, DIM, RESET = "\033[0;36m", "\033[1m", "\033[2m", "\033[0m"


def truthy(value) -> bool:
    return str(value).strip().lower() == "true"


def as_env_dict(env) -> dict:
    if isinstance(env, dict):
        return {str(k): "" if v is None else str(v) for k, v in env.items()}
    if isinstance(env, list):
        out = {}
        for item in env:
            key, _, val = str(item).partition("=")
            out[key] = val
        return out
    return {}


def host_ip_is_loopback(host_ip: str) -> bool:
    # Empty / missing host_ip means docker binds all interfaces (0.0.0.0) — NOT
    # loopback. Fail-closed on anything unparseable.
    if not host_ip:
        return False
    try:
        ip = ipaddress.ip_address(host_ip)
    except ValueError:
        return False
    if ip.version == 6 and ip.ipv4_mapped is not None:
        ip = ip.ipv4_mapped
    if ip.version == 4:
        return ip in LOOPBACK_V4
    return ip.is_loopback  # ::1


def port_binds(svc) -> list:
    """Return [(host_ip, published)] for each host-published port of a service."""
    out = []
    for port in svc.get("ports") or []:
        if isinstance(port, dict):
            out.append((str(port.get("host_ip") or ""), str(port.get("published") or "")))
        else:
            # Defensive: unrendered "IP:HOST:CONTAINER" / "HOST:CONTAINER" string.
            parts = str(port).split(":")
            if len(parts) >= 3:
                out.append((parts[0], parts[1]))
            elif len(parts) == 2:
                out.append(("", parts[0]))
            # a bare "CONTAINER" is not host-published — no host bind to check
    return out


try:
    with open(render_path, encoding="utf-8") as handle:
        config = json.loads(handle.read())
except (OSError, ValueError) as exc:
    sys.stderr.write(f"preflight_bind_posture: could not read/parse compose config JSON: {exc}\n")
    sys.exit(2)

services = config.get("services") or {}

print(f"{BOLD}Juniper Platform — Bind-Posture Preflight{RESET}")
print(f"{DIM}  verify every *_LOOPBACK_PUBLISH_ATTESTED service publishes loopback-only{RESET}")
print(f"{DIM}  source: {source_desc}{RESET}")
print("")

attested_count = 0
loopback_ok = 0
proxy_ok = 0
violations = []  # (service, attest_key, proxy_key, [ "host_ip:published", ... ])

for name in sorted(services):
    env = as_env_dict((services[name] or {}).get("environment"))
    attest_keys = sorted(k for k in env if k.endswith(ATTEST_SUFFIX) and truthy(env[k]))
    if not attest_keys:
        continue
    binds = port_binds(services[name] or {})
    for attest_key in attest_keys:
        attested_count += 1
        prefix = attest_key[: -len(ATTEST_SUFFIX)]
        proxy_key = prefix + PROXY_SUFFIX
        proxy_attested = truthy(env.get(proxy_key, ""))
        offending = [f"{hip or '0.0.0.0'}:{pub}" for hip, pub in binds if not host_ip_is_loopback(hip)]
        bind_str = ", ".join(f"{hip or '0.0.0.0'}:{pub}" for hip, pub in binds) or "(no host-published ports)"

        if offending and not proxy_attested:
            print(f"  {RED}[FAIL]{RESET} {CYAN}{name}{RESET}  {attest_key}=true  host binds: {RED}{bind_str}{RESET}")
            violations.append((name, attest_key, proxy_key, offending))
        elif offending and proxy_attested:
            proxy_ok += 1
            print(f"  {YELLOW}[PROXY]{RESET} {CYAN}{name}{RESET}  {attest_key}=true + {proxy_key}=true  host binds: {bind_str}")
            print(f"{DIM}         off-loopback publish explicitly attested behind a fronting auth proxy (D7).{RESET}")
        else:
            loopback_ok += 1
            print(f"  {GREEN}[OK]{RESET}   {CYAN}{name}{RESET}  {attest_key}=true  host binds: {GREEN}{bind_str}{RESET}")

print("")

if attested_count == 0:
    print(f"{YELLOW}  PASS (no-op) — no service sets *_LOOPBACK_PUBLISH_ATTESTED=true; nothing to verify.{RESET}")
    sys.exit(0)

if violations:
    print(f"{BOLD}{RED}  FAIL — bind-posture attestation is UNVERIFIED for "
          f"{len(violations)} service(s):{RESET}")
    for name, attest_key, proxy_key, offending in violations:
        print(f"{RED}    • {name} attests loopback-publish ({attest_key}=true) but publishes a "
              f"NON-loopback host bind: {', '.join(offending)}.{RESET}")
        print(f"{DIM}      Fix: bind the host publish to loopback (unset BIND_HOST, or "
              f"BIND_HOST=127.0.0.1); OR — only if a fronting authenticating reverse proxy "
              f"fronts it — set {proxy_key}=true (Phase-4 / D7, attestation-only).{RESET}")
    print(f"{BOLD}{RED}  Bind-posture preflight FAILED — refusing to continue bring-up.{RESET}")
    sys.exit(1)

if proxy_ok:
    print(f"{GREEN}  PASS — bind posture verified for {attested_count} attested service(s): "
          f"{loopback_ok} loopback-only publish(es) + {proxy_ok} explicitly proxy-attested "
          f"off-loopback (D7).{RESET}")
else:
    print(f"{GREEN}  PASS — {loopback_ok} attested service(s) publish loopback-only; "
          f"bind posture verified.{RESET}")
sys.exit(0)
PY
