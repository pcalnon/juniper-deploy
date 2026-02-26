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
#    and response latency.
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
    RESET='\033[0m'
else
    GREEN=''
    RED=''
    YELLOW=''
    CYAN=''
    BOLD=''
    RESET=''
fi

SERVICES=(
    "juniper-data:${JUNIPER_DATA_PORT:-8100}"
    "juniper-cascor:${CASCOR_PORT:-8200}"
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
try:
    start = time.monotonic()
    resp = urllib.request.urlopen('${url}', timeout=5)
    elapsed = (time.monotonic() - start) * 1000
    data = json.loads(resp.read().decode())
    status = data.get('status', 'unknown')
    version = data.get('version', 'n/a')
    print(f'ok|{status}|{version}|{elapsed:.0f}ms')
except Exception as e:
    print(f'error|unreachable|n/a|—')
" 2>/dev/null)

    IFS='|' read -r ok status version latency <<< "$result"

    if [[ "$ok" == "ok" ]]; then
        printf "  ${CYAN}%-18s${RESET} ${GREEN}%-10s${RESET} %-12s %s\n" "$name" "$status" "$version" "$latency"
    else
        printf "  ${CYAN}%-18s${RESET} ${RED}%-10s${RESET} %-12s %s\n" "$name" "$status" "$version" "$latency"
        all_healthy=false
    fi
done

echo ""
if $all_healthy; then
    echo -e "  ${GREEN}All services healthy.${RESET}"
else
    echo -e "  ${YELLOW}One or more services are not reachable.${RESET}"
    exit 1
fi
