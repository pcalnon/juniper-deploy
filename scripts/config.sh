#!/usr/bin/env bash
#####################################################################################################################################################################################################
# Project:       Juniper
# Application:   juniper-deploy
# File Name:     config.sh
# Author:        Paul Calnon
#
# License:       MIT License
# Copyright:     Copyright (c) 2024-2026 Paul Calnon
#
# Description:
#    Shared configuration defaults for the juniper-deploy shell scripts.
#    Source this file at the top of any script in scripts/ to pull in the
#    standard timeout, poll-interval, and request-timeout values used across
#    health checks, integration tests, and stack readiness probes.
#
#    Each value is defined with the parameter expansion form:
#        VAR=${VAR:-DEFAULT}
#    so callers can override any default by exporting the variable in their
#    environment before sourcing this file. Defaults match the previously
#    hardcoded values in each individual script — sourcing this file does
#    not change current behavior.
#
# Usage:
#    # At the top of a script in scripts/:
#    SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
#    # shellcheck source=scripts/config.sh
#    source "${SCRIPT_DIR}/config.sh"
#
#####################################################################################################################################################################################################

# ─────────────────────────────────────────────────────────────────────────
# Host-side service ports (DEPLOY-12)
# Match the docker-compose host port bindings. Override only if the compose
# stack publishes services on non-default host ports.
# ─────────────────────────────────────────────────────────────────────────

JUNIPER_DATA_PORT="${JUNIPER_DATA_PORT:-8100}"
JUNIPER_CASCOR_PORT="${JUNIPER_CASCOR_PORT:-${CASCOR_HOST_PORT:-8201}}"
JUNIPER_RECURRENCE_PORT="${JUNIPER_RECURRENCE_PORT:-${RECURRENCE_HOST_PORT:-8211}}"
JUNIPER_CANOPY_PORT="${JUNIPER_CANOPY_PORT:-${CANOPY_PORT:-8050}}"

# ─────────────────────────────────────────────────────────────────────────
# Service-readiness wait defaults (wait_for_services.sh)
# ─────────────────────────────────────────────────────────────────────────

# How long (seconds) to wait for the full Juniper stack to become healthy
# before giving up. wait_for_services.sh accepts an override as $1.
WAIT_TIMEOUT_DEFAULT="${WAIT_TIMEOUT_DEFAULT:-90}"

# Seconds between health-check polls inside wait loops.
POLL_INTERVAL_DEFAULT="${POLL_INTERVAL_DEFAULT:-3}"

# Per-request timeout (seconds) for the curl/urllib probes used during waits.
CURL_TIMEOUT="${CURL_TIMEOUT:-3}"

# ─────────────────────────────────────────────────────────────────────────
# health_check.sh — single-shot stack readiness probe
# ─────────────────────────────────────────────────────────────────────────

# Per-request timeout (seconds) for the urllib.request.urlopen calls used
# by health_check.sh to query each service's /v1/health/ready endpoint.
HEALTH_TIMEOUT="${HEALTH_TIMEOUT:-5}"

# ─────────────────────────────────────────────────────────────────────────
# test_demo_profile.sh — demo profile integration test
# ─────────────────────────────────────────────────────────────────────────

# Total wait budget (seconds) for the demo profile integration test.
DEMO_TIMEOUT="${DEMO_TIMEOUT:-120}"

# Seconds between health checks during the demo wait loop.
DEMO_POLL_INTERVAL="${DEMO_POLL_INTERVAL:-3}"

# Seconds to wait after services become healthy before checking that
# auto-training has actually started inside the demo container.
TRAINING_START_WAIT="${TRAINING_START_WAIT:-5}"

# ─────────────────────────────────────────────────────────────────────────
# test_health_enhanced.sh — Phase 8 enhanced health-check integration test
# ─────────────────────────────────────────────────────────────────────────

# Total wait budget (seconds) for the enhanced health-check integration test
# to bring up the full stack and verify ReadinessResponse format on each
# /v1/health/ready endpoint.
ENHANCED_TIMEOUT="${ENHANCED_TIMEOUT:-90}"
