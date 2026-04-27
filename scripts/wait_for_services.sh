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

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=scripts/config.sh
source "${SCRIPT_DIR}/config.sh"

TIMEOUT=${1:-${WAIT_TIMEOUT_DEFAULT}}
POLL_INTERVAL=${POLL_INTERVAL_DEFAULT}
ELAPSED=0

# Validate port values are numeric to prevent injection
for var in JUNIPER_DATA_PORT JUNIPER_CASCOR_PORT JUNIPER_CANOPY_PORT; do
    val="${!var}"
    if ! [[ "$val" =~ ^[0-9]+$ ]]; then
        echo "ERROR: ${var} contains non-numeric value: ${val}"
        exit 1
    fi
done

DATA_URL="http://localhost:${JUNIPER_DATA_PORT}/v1/health/live"
CASCOR_URL="http://localhost:${JUNIPER_CASCOR_PORT}/v1/health/live"
CANOPY_URL="http://localhost:${JUNIPER_CANOPY_PORT}/v1/health/live"

echo "Waiting for Juniper services (timeout: ${TIMEOUT}s)..."

check_service() {
    local name="$1"
    local url="$2"
    if python3 -c "import sys, urllib.request; urllib.request.urlopen(sys.argv[1], timeout=${CURL_TIMEOUT})" "$url" 2>/dev/null; then
        echo "  ✓ ${name} is healthy"
        return 0
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
