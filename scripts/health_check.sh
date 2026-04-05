#!/usr/bin/env bash
#####################################################################################################################################################################################################
# Project:       Juniper
# File Name:     health_check.sh
# Author:        Paul Calnon
#
# License:       MIT License
# Copyright:     Copyright (c) 2024-2026 Paul Calnon
#
# Description:
#    Queries all three Juniper service /v1/health/ready endpoints and
#    displays a formatted report with service name, status, version,
#    dependency health, and response latency.
#
# Usage:
#    bash scripts/health_check.sh
#
#####################################################################################################################################################################################################

set -euo pipefail

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

# Validate port values are numeric to prevent injection
for varname in JUNIPER_DATA_PORT CASCOR_HOST_PORT CANOPY_PORT; do
    val="${!varname:-}"
    if [[ -n "$val" ]] && ! [[ "$val" =~ ^[0-9]+$ ]]; then
        echo "ERROR: ${varname} contains non-numeric value: ${val}"
        exit 1
    fi
done

SERVICES=(
    "juniper-data:${JUNIPER_DATA_PORT:-8100}"
    "juniper-cascor:${CASCOR_HOST_PORT:-8201}"
    "juniper-canopy:${CANOPY_PORT:-8050}"
)

echo -e "${BOLD}Juniper Platform — Health Report${RESET}"
echo ""
printf "  %-18s %-10s %-12s %s\n" "SERVICE" "STATUS" "VERSION" "LATENCY"
printf "  %-18s %-10s %-12s %s\n" "────────────────" "────────" "──────────" "───────"

all_healthy=true

for entry in "${SERVICES[@]}"; do
    name="${entry%%:*}"
    port="${entry##*:}"
    url="http://localhost:${port}/v1/health/ready"

    result=$(python3 -c "
import urllib.request, json, time, sys
url = sys.argv[1]
try:
    start = time.monotonic()
    resp = urllib.request.urlopen(url, timeout=5)
    elapsed = (time.monotonic() - start) * 1000
    data = json.loads(resp.read().decode())
    status = data.get('status', 'unknown')
    version = data.get('version', 'n/a')
    deps = data.get('dependencies', {})
    dep_parts = []
    for dk, dv in deps.items():
        ds = dv.get('status', '?')
        dl = dv.get('latency_ms')
        dl_str = f' {dl:.0f}ms' if dl is not None else ''
        dep_parts.append(f'{dk}={ds}{dl_str}')
    dep_str = ', '.join(dep_parts) if dep_parts else ''
    print(f'ok|{status}|{version}|{elapsed:.0f}ms|{dep_str}')
except Exception as e:
    print(f'error|unreachable|n/a|—|')
" "$url" 2>/dev/null)

    IFS='|' read -r ok status version latency deps <<< "$result"

    if [[ "$ok" == "ok" ]]; then
        printf "  ${CYAN}%-18s${RESET} ${GREEN}%-10s${RESET} %-12s %s\n" "$name" "$status" "$version" "$latency"
    else
        printf "  ${CYAN}%-18s${RESET} ${RED}%-10s${RESET} %-12s %s\n" "$name" "$status" "$version" "$latency"
        all_healthy=false
    fi

    # Print dependency details if present
    if [[ -n "${deps:-}" ]]; then
        printf "  ${DIM}  └── deps: %s${RESET}\n" "$deps"
    fi
done

echo ""
if $all_healthy; then
    echo -e "  ${GREEN}All services healthy.${RESET}"
else
    echo -e "  ${YELLOW}One or more services are not reachable.${RESET}"
    exit 1
fi
