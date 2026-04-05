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
#    Polls all three Juniper service health endpoints until they are ready
#    or a timeout is reached. Used before running integration tests.
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

# Validate port values are numeric to prevent injection
cascor_port="${CASCOR_HOST_PORT:-8201}"
if ! [[ "$cascor_port" =~ ^[0-9]+$ ]]; then
    echo "ERROR: CASCOR_HOST_PORT contains non-numeric value: ${cascor_port}"
    exit 1
fi

DATA_URL="http://localhost:8100/v1/health/live"
CASCOR_URL="http://localhost:${cascor_port}/v1/health/live"
CANOPY_URL="http://localhost:8050/v1/health/live"

echo "Waiting for Juniper services (timeout: ${TIMEOUT}s)..."

check_service() {
    local name="$1"
    local url="$2"
    if python3 -c "import sys, urllib.request; urllib.request.urlopen(sys.argv[1], timeout=3)" "$url" 2>/dev/null; then
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
        echo "All services are healthy. Ready to run integration tests."
        exit 0
    fi

    if [[ $ELAPSED -ge $TIMEOUT ]]; then
        echo ""
        echo "ERROR: Services did not become healthy within ${TIMEOUT}s"
        exit 1
    fi

    echo "  ... waiting (${ELAPSED}s elapsed)"
    sleep ${POLL_INTERVAL}
    ELAPSED=$((ELAPSED + POLL_INTERVAL))
done
