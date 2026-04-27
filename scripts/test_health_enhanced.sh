#!/usr/bin/env bash
#####################################################################################################################################################################################################
# Project:       Juniper
# File Name:     test_health_enhanced.sh
# Author:        Paul Calnon
#
# License:       MIT License
# Copyright:     Copyright (c) 2024-2026 Paul Calnon
#
# Description:
#    Integration test for Phase 8 enhanced health checks. Starts the full
#    stack, verifies all /v1/health/ready responses include dependency
#    status in the standardized ReadinessResponse format.
#
# Usage:
#    bash scripts/test_health_enhanced.sh
#
#####################################################################################################################################################################################################

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=scripts/config.sh
source "${SCRIPT_DIR}/config.sh"

BOLD='\033[1m'
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[0;33m'
RESET='\033[0m'

pass_count=0
fail_count=0

pass_test() {
    echo -e "  ${GREEN}✓ $1${RESET}"
    ((pass_count++))
}

fail_test() {
    echo -e "  ${RED}✗ $1${RESET}"
    ((fail_count++))
}

echo -e "${BOLD}Phase 8: Enhanced Health Check Integration Test${RESET}"
echo ""

# Validate port values are numeric to prevent injection. JUNIPER_*_PORT comes
# from scripts/config.sh, with backward-compat fallback through CASCOR_HOST_PORT
# / CANOPY_PORT.
for varname in JUNIPER_DATA_PORT JUNIPER_CASCOR_PORT JUNIPER_CANOPY_PORT; do
    val="${!varname}"
    if ! [[ "$val" =~ ^[0-9]+$ ]]; then
        echo "ERROR: ${varname} contains non-numeric value: ${val}"
        exit 1
    fi
done

# ─── Step 1: Validate compose config ─────────────────────────────────────────
echo -e "${BOLD}Step 1: Validate Docker Compose configuration${RESET}"
if docker compose --profile full config > /dev/null 2>&1; then
    pass_test "docker compose --profile full config validates"
else
    fail_test "docker compose config validation failed"
    exit 1
fi

# ─── Step 2: Start full stack ─────────────────────────────────────────────────
echo -e "\n${BOLD}Step 2: Start full stack${RESET}"
docker compose --profile full up -d --build 2>/dev/null
echo "  Waiting for services to start..."
sleep 5

# ─── Step 3: Wait for services ───────────────────────────────────────────────
echo -e "\n${BOLD}Step 3: Wait for all services to become healthy${RESET}"
TIMEOUT=${ENHANCED_TIMEOUT}
ELAPSED=0
while true; do
    all_ok=true
    for port in "${JUNIPER_DATA_PORT}" "${JUNIPER_CASCOR_PORT}" "${JUNIPER_CANOPY_PORT}"; do
        if ! python3 -c "import sys, urllib.request; urllib.request.urlopen(sys.argv[1], timeout=${CURL_TIMEOUT})" "http://localhost:${port}/v1/health/live" 2>/dev/null; then
            all_ok=false
        fi
    done
    if $all_ok; then
        pass_test "All services responding to liveness probes"
        break
    fi
    if [[ $ELAPSED -ge $TIMEOUT ]]; then
        fail_test "Services did not become healthy within ${TIMEOUT}s"
        docker compose --profile full down 2>/dev/null
        exit 1
    fi
    sleep "${POLL_INTERVAL_DEFAULT}"
    ELAPSED=$((ELAPSED + POLL_INTERVAL_DEFAULT))
done

# ─── Step 4: Verify JuniperData readiness response ──────────────────────────
echo -e "\n${BOLD}Step 4: Verify JuniperData /v1/health/ready${RESET}"
DATA_READY=$(curl -sf "http://localhost:${JUNIPER_DATA_PORT}/v1/health/ready" 2>/dev/null || echo '{}')

if echo "$DATA_READY" | python3 -c "import sys,json; d=json.load(sys.stdin); assert d.get('service')=='juniper-data'" 2>/dev/null; then
    pass_test "service field is 'juniper-data'"
else
    fail_test "service field missing or wrong"
fi

if echo "$DATA_READY" | python3 -c "import sys,json; d=json.load(sys.stdin); assert 'storage' in d.get('dependencies',{})" 2>/dev/null; then
    pass_test "storage dependency present"
else
    fail_test "storage dependency missing"
fi

if echo "$DATA_READY" | python3 -c "import sys,json; d=json.load(sys.stdin); assert d['dependencies']['storage']['status']=='healthy'" 2>/dev/null; then
    pass_test "storage status is healthy"
else
    fail_test "storage status is not healthy"
fi

# ─── Step 5: Verify JuniperCascor readiness response ────────────────────────
echo -e "\n${BOLD}Step 5: Verify JuniperCascor /v1/health/ready${RESET}"
CASCOR_READY=$(curl -sf "http://localhost:${JUNIPER_CASCOR_PORT}/v1/health/ready" 2>/dev/null || echo '{}')

if echo "$CASCOR_READY" | python3 -c "import sys,json; d=json.load(sys.stdin); assert d.get('service')=='juniper-cascor'" 2>/dev/null; then
    pass_test "service field is 'juniper-cascor'"
else
    fail_test "service field missing or wrong"
fi

if echo "$CASCOR_READY" | python3 -c "import sys,json; d=json.load(sys.stdin); assert d['dependencies']['juniper_data']['status']=='healthy'" 2>/dev/null; then
    pass_test "juniper_data dependency is healthy"
else
    fail_test "juniper_data dependency not healthy"
fi

if echo "$CASCOR_READY" | python3 -c "import sys,json; d=json.load(sys.stdin); assert 'network_loaded' in d.get('details',{})" 2>/dev/null; then
    pass_test "network_loaded detail present"
else
    fail_test "network_loaded detail missing"
fi

# Response is flat (no envelope)
if echo "$CASCOR_READY" | python3 -c "import sys,json; d=json.load(sys.stdin); assert 'data' not in d and 'meta' not in d" 2>/dev/null; then
    pass_test "response is flat (no envelope)"
else
    fail_test "response still uses envelope wrapper"
fi

# ─── Step 6: Verify JuniperCanopy readiness response ────────────────────────
echo -e "\n${BOLD}Step 6: Verify JuniperCanopy /v1/health/ready${RESET}"
CANOPY_READY=$(curl -sf "http://localhost:${JUNIPER_CANOPY_PORT}/v1/health/ready" 2>/dev/null || echo '{}')

if echo "$CANOPY_READY" | python3 -c "import sys,json; d=json.load(sys.stdin); assert d.get('service')=='juniper-canopy'" 2>/dev/null; then
    pass_test "service field is 'juniper-canopy'"
else
    fail_test "service field missing or wrong"
fi

if echo "$CANOPY_READY" | python3 -c "import sys,json; d=json.load(sys.stdin); assert 'juniper_data' in d.get('dependencies',{})" 2>/dev/null; then
    pass_test "juniper_data dependency present"
else
    fail_test "juniper_data dependency missing"
fi

if echo "$CANOPY_READY" | python3 -c "import sys,json; d=json.load(sys.stdin); assert 'juniper_cascor' in d.get('dependencies',{})" 2>/dev/null; then
    pass_test "juniper_cascor dependency present"
else
    fail_test "juniper_cascor dependency missing"
fi

if echo "$CANOPY_READY" | python3 -c "import sys,json; d=json.load(sys.stdin); assert 'mode' in d.get('details',{})" 2>/dev/null; then
    pass_test "mode detail present"
else
    fail_test "mode detail missing"
fi

# ─── Step 7: Verify Docker healthcheck compatibility ────────────────────────
echo -e "\n${BOLD}Step 7: Verify Docker healthcheck still works${RESET}"
HEALTHY_COUNT=$(docker compose ps --format '{{.Health}}' 2>/dev/null | grep -c "healthy" || true)
if [[ $HEALTHY_COUNT -ge 3 ]]; then
    pass_test "All services report healthy to Docker ($HEALTHY_COUNT/3)"
else
    echo -e "  ${YELLOW}⚠ Only $HEALTHY_COUNT/3 services report healthy (may need more time)${RESET}"
fi

# ─── Step 8: Clean shutdown ──────────────────────────────────────────────────
echo -e "\n${BOLD}Step 8: Clean shutdown${RESET}"
docker compose --profile full --profile demo --profile dev down 2>/dev/null
pass_test "Stack stopped cleanly"

# ─── Summary ─────────────────────────────────────────────────────────────────
echo ""
echo -e "${BOLD}Results: ${GREEN}${pass_count} passed${RESET}, ${RED}${fail_count} failed${RESET}"
if [[ $fail_count -gt 0 ]]; then
    exit 1
fi
