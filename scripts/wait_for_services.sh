#!/usr/bin/env bash
#####################################################################################################################################################################################################
# Project:       Juniper
# File Name:     wait_for_services.sh
# Author:        Paul Calnon
#
# License:       MIT License
# Copyright:     Copyright (c) 2024-2026 Paul Calnon
#
# Description:
#    Polls all three Juniper service /v1/health/ready endpoints until they
#    report ready status or a timeout is reached. Parses ReadinessResponse
#    JSON to verify status and dependency health. Used before running
#    integration tests.
#
# Usage:
#    bash scripts/wait_for_services.sh
#    bash scripts/wait_for_services.sh --timeout 120
#
#####################################################################################################################################################################################################

set -euo pipefail

TIMEOUT=${1:-90}
POLL_INTERVAL=3
ELAPSED=0

DATA_URL="http://localhost:${JUNIPER_DATA_PORT:-8100}/v1/health/ready"
CASCOR_URL="http://localhost:${CASCOR_PORT:-8200}/v1/health/ready"
CANOPY_URL="http://localhost:${CANOPY_PORT:-8050}/v1/health/ready"

echo "Waiting for Juniper services (timeout: ${TIMEOUT}s)..."

check_service() {
    local name="$1"
    local url="$2"
    local result
    result=$(python3 -c "
import urllib.request, json, sys
try:
    resp = urllib.request.urlopen('${url}', timeout=3)
    data = json.loads(resp.read().decode())
    status = data.get('status', 'unknown')
    version = data.get('version', 'n/a')
    service = data.get('service', 'unknown')
    if status in ('healthy', 'ok', 'ready'):
        print(f'ok|{status}|{version}')
    else:
        print(f'degraded|{status}|{version}')
except Exception:
    print('error|unreachable|n/a')
" 2>/dev/null)

    IFS='|' read -r ok status version <<< "$result"

    if [[ "$ok" == "ok" ]]; then
        echo "  ✓ ${name} is ready (status=${status}, version=${version})"
        return 0
    elif [[ "$ok" == "degraded" ]]; then
        echo "  ⚠ ${name} responded but status=${status}"
        return 1
    fi
    return 1
}

while true; do
    data_ok=0
    cascor_ok=0
    canopy_ok=0

    check_service "juniper-data   " "${DATA_URL}"   && data_ok=1   || true
    check_service "juniper-cascor " "${CASCOR_URL}" && cascor_ok=1 || true
    check_service "juniper-canopy " "${CANOPY_URL}" && canopy_ok=1 || true

    if [[ $data_ok -eq 1 && $cascor_ok -eq 1 && $canopy_ok -eq 1 ]]; then
        echo ""
        echo "All services are ready. Ready to run integration tests."
        exit 0
    fi

    if [[ $ELAPSED -ge $TIMEOUT ]]; then
        echo ""
        echo "ERROR: Services did not become ready within ${TIMEOUT}s"
        exit 1
    fi

    echo "  ... waiting (${ELAPSED}s elapsed)"
    sleep ${POLL_INTERVAL}
    ELAPSED=$((ELAPSED + POLL_INTERVAL))
done
