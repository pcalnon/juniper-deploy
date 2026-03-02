#!/usr/bin/env bash
#####################################################################################################################################################################################################
# Project:       Juniper
# File Name:     test_demo_profile.sh
# Author:        Paul Calnon
#
# License:       MIT License
# Copyright:     Copyright (c) 2024-2026 Paul Calnon
#
# Description:
#    Integration test for the demo Docker Compose profile.
#    Validates that the demo stack starts, seeds a dataset, auto-starts
#    training, and Canopy connects successfully.
#
# Usage:
#    bash scripts/test_demo_profile.sh
#    bash scripts/test_demo_profile.sh --timeout 120
#
#####################################################################################################################################################################################################

set -euo pipefail

TIMEOUT=${1:-120}
POLL_INTERVAL=3
ELAPSED=0
EXIT_CODE=0

DATA_URL="http://localhost:8100/v1/health"
CASCOR_URL="http://localhost:8200/v1/health"
CANOPY_URL="http://localhost:8050/v1/health"
TRAINING_STATUS_URL="http://localhost:8200/v1/training/status"

# Colors (disabled if NO_COLOR is set)
if [[ -z "${NO_COLOR:-}" ]]; then
    GREEN='\033[0;32m'
    RED='\033[0;31m'
    YELLOW='\033[0;33m'
    CYAN='\033[0;36m'
    BOLD='\033[1m'
    RESET='\033[0m'
else
    GREEN='' RED='' YELLOW='' CYAN='' BOLD='' RESET=''
fi

pass() { echo -e "  ${GREEN}PASS${RESET} $1"; }
fail() { echo -e "  ${RED}FAIL${RESET} $1"; EXIT_CODE=1; }

echo -e "${BOLD}Juniper Demo Profile — Integration Test${RESET}"
echo ""

# ── Step 1: Validate compose config ──────────────────────────────────────────
echo -e "${CYAN}[1/7]${RESET} Validating compose config for demo profile..."
if docker compose --profile demo config --quiet 2>/dev/null; then
    pass "docker compose --profile demo config is valid"
else
    fail "docker compose config validation failed"
    exit 1
fi

# ── Step 2: Start demo stack ─────────────────────────────────────────────────
echo -e "${CYAN}[2/7]${RESET} Starting demo stack..."
docker compose --profile demo up -d

# ── Step 3: Wait for services ────────────────────────────────────────────────
echo -e "${CYAN}[3/7]${RESET} Waiting for services to become healthy (timeout: ${TIMEOUT}s)..."

check_service() {
    python3 -c "import urllib.request; urllib.request.urlopen('$1', timeout=3)" 2>/dev/null
}

while true; do
    data_ok=0; cascor_ok=0; canopy_ok=0

    check_service "${DATA_URL}"   && data_ok=1   || true
    check_service "${CASCOR_URL}" && cascor_ok=1 || true
    check_service "${CANOPY_URL}" && canopy_ok=1 || true

    if [[ $data_ok -eq 1 && $cascor_ok -eq 1 && $canopy_ok -eq 1 ]]; then
        pass "All services healthy"
        break
    fi

    if [[ $ELAPSED -ge $TIMEOUT ]]; then
        fail "Services did not become healthy within ${TIMEOUT}s"
        echo ""
        echo "Container status:"
        docker compose --profile demo ps
        echo ""
        echo "Recent logs:"
        docker compose --profile demo logs --tail 30
        docker compose --profile demo down
        exit 1
    fi

    sleep ${POLL_INTERVAL}
    ELAPSED=$((ELAPSED + POLL_INTERVAL))
done

# ── Step 4: Verify demo-seed completed ───────────────────────────────────────
echo -e "${CYAN}[4/7]${RESET} Verifying demo-seed container..."
SEED_STATUS=$(docker compose ps demo-seed --format '{{.State}}' 2>/dev/null || echo "unknown")
if [[ "${SEED_STATUS}" == *"exited"* ]] || docker compose ps demo-seed 2>/dev/null | grep -q "Exited (0)"; then
    pass "demo-seed exited successfully"
else
    fail "demo-seed status: ${SEED_STATUS}"
fi

# ── Step 5: Verify training started ──────────────────────────────────────────
echo -e "${CYAN}[5/7]${RESET} Checking training status..."
# Allow a few seconds for auto-start to kick in
sleep 5
TRAINING_JSON=$(python3 -c "
import urllib.request, json
try:
    resp = urllib.request.urlopen('${TRAINING_STATUS_URL}', timeout=5)
    print(resp.read().decode())
except Exception as e:
    print(json.dumps({'error': str(e)}))
" 2>/dev/null)

if echo "${TRAINING_JSON}" | python3 -c "
import sys, json
data = json.load(sys.stdin)
# Check if training is active via state_machine or training_state
active = data.get('training_active', False)
state = data.get('training_state', {}).get('status', '')
if active or state in ('Started', 'Completed'):
    sys.exit(0)
sys.exit(1)
" 2>/dev/null; then
    pass "Training is active"
else
    echo -e "  ${YELLOW}INFO${RESET} Training status: ${TRAINING_JSON}"
    fail "Training does not appear to be active"
fi

# ── Step 6: Verify Canopy dashboard is accessible ────────────────────────────
echo -e "${CYAN}[6/7]${RESET} Verifying Canopy dashboard..."
if check_service "${CANOPY_URL}"; then
    pass "Canopy dashboard is accessible"
else
    fail "Canopy dashboard health check failed"
fi

# ── Step 7: Clean shutdown ───────────────────────────────────────────────────
echo -e "${CYAN}[7/7]${RESET} Stopping demo stack..."
docker compose --profile demo down
pass "Demo stack stopped cleanly"

# ── Summary ──────────────────────────────────────────────────────────────────
echo ""
if [[ $EXIT_CODE -eq 0 ]]; then
    echo -e "${GREEN}${BOLD}All demo profile tests passed.${RESET}"
else
    echo -e "${RED}${BOLD}Some demo profile tests failed.${RESET}"
fi
exit $EXIT_CODE
