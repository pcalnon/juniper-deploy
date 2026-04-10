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
#    training, and Canopy connects successfully. Validates ReadinessResponse
#    schema on all health endpoints.
#
# Usage:
#    bash scripts/test_demo_profile.sh
#    bash scripts/test_demo_profile.sh --timeout 120
#
#####################################################################################################################################################################################################

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=scripts/config.sh
source "${SCRIPT_DIR}/config.sh"

TIMEOUT=${1:-${DEMO_TIMEOUT}}
POLL_INTERVAL=${DEMO_POLL_INTERVAL}
ELAPSED=0
EXIT_CODE=0

# Validate port values are numeric to prevent injection
cascor_port="${CASCOR_HOST_PORT:-8201}"
if ! [[ "$cascor_port" =~ ^[0-9]+$ ]]; then
    echo "ERROR: CASCOR_HOST_PORT contains non-numeric value: ${cascor_port}"
    exit 1
fi

DATA_READY_URL="http://localhost:8100/v1/health"
CASCOR_READY_URL="http://localhost:${cascor_port}/v1/health"
CANOPY_READY_URL="http://localhost:8050/v1/health"
TRAINING_STATUS_URL="http://localhost:${cascor_port}/v1/training/status"

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

# ── Step 3: Wait for services and validate ReadinessResponse ─────────────────
echo -e "${CYAN}[3/7]${RESET} Waiting for services to become ready (timeout: ${TIMEOUT}s)..."

check_service_ready() {
    python3 -c "import sys, urllib.request; urllib.request.urlopen(sys.argv[1], timeout=${CURL_TIMEOUT})" "$1" 2>/dev/null
}

while true; do
    data_ok=0; cascor_ok=0; canopy_ok=0

    check_service_ready "${DATA_READY_URL}"   && data_ok=1   || true
    check_service_ready "${CASCOR_READY_URL}" && cascor_ok=1 || true
    check_service_ready "${CANOPY_READY_URL}" && canopy_ok=1 || true

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

# ── Step 3b: Validate ReadinessResponse schema ───────────────────────────────
echo -e "${CYAN}[3b/7]${RESET} Validating ReadinessResponse schema..."

validate_readiness_schema() {
    local name="$1"
    local url="$2"
    local result
    result=$(python3 -c "
import urllib.request, json, sys
url = sys.argv[1]
try:
    resp = urllib.request.urlopen(url, timeout=${HEALTH_TIMEOUT})
    data = json.loads(resp.read().decode())
    errors = []
    # Required fields: status, version, service
    for field in ('status', 'version', 'service'):
        if field not in data:
            errors.append(f'missing field: {field}')
        elif not isinstance(data[field], str):
            errors.append(f'{field} is not a string')
    # Optional field: dependencies (must be dict if present)
    if 'dependencies' in data and not isinstance(data['dependencies'], dict):
        errors.append('dependencies is not an object')
    if errors:
        print('FAIL|' + '; '.join(errors))
    else:
        print(f'PASS|status={data[\"status\"]}, version={data[\"version\"]}, service={data[\"service\"]}')
except Exception as e:
    print(f'FAIL|{e}')
" "$url" 2>/dev/null)

    IFS='|' read -r verdict detail <<< "$result"
    if [[ "$verdict" == "PASS" ]]; then
        pass "${name} ReadinessResponse schema valid (${detail})"
    else
        fail "${name} ReadinessResponse schema invalid: ${detail}"
    fi
}

validate_readiness_schema "juniper-data"   "${DATA_READY_URL}"
validate_readiness_schema "juniper-cascor" "${CASCOR_READY_URL}"
validate_readiness_schema "juniper-canopy" "${CANOPY_READY_URL}"

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
sleep "${TRAINING_START_WAIT}"
TRAINING_JSON=$(python3 -c "
import urllib.request, json, sys
try:
    resp = urllib.request.urlopen(sys.argv[1], timeout=${HEALTH_TIMEOUT})
    print(resp.read().decode())
except Exception as e:
    print(json.dumps({'error': str(e)}))
" "$TRAINING_STATUS_URL" 2>/dev/null)

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

# ── Step 6: Verify Canopy dashboard with ReadinessResponse ───────────────────
echo -e "${CYAN}[6/7]${RESET} Verifying Canopy dashboard..."
CANOPY_RESULT=$(python3 -c "
import urllib.request, json, sys
url = sys.argv[1]
try:
    resp = urllib.request.urlopen(url, timeout=${HEALTH_TIMEOUT})
    data = json.loads(resp.read().decode())
    status = data.get('status', 'unknown')
    service = data.get('service', 'unknown')
    if status in ('healthy', 'ok', 'ready') and service:
        print(f'PASS|{service} status={status}')
    else:
        print(f'FAIL|status={status}, service={service}')
except Exception as e:
    print(f'FAIL|{e}')
" "$CANOPY_READY_URL" 2>/dev/null)

IFS='|' read -r canopy_verdict canopy_detail <<< "$CANOPY_RESULT"
if [[ "$canopy_verdict" == "PASS" ]]; then
    pass "Canopy dashboard is accessible (${canopy_detail})"
else
    fail "Canopy dashboard health check failed: ${canopy_detail}"
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
