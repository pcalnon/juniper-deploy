#####################################################################################################################################################################################################
# Project:       Juniper
# Application:   juniper-deploy
# File Name:     Makefile
# Author:        Paul Calnon
#
# Date Created:  2026-02-26
# Last Modified: 2026-03-02
#
# License:       MIT License
# Copyright:     Copyright (c) 2024-2026 Paul Calnon
#
# Description:
#    Developer-facing interface for the Juniper platform.
#    Wraps Docker Compose commands with ergonomic, discoverable targets.
#
# Usage:
#    make          # Show available targets
#    make up       # Start all services
#    make down     # Stop all services
#    make health   # Check service health
#
#####################################################################################################################################################################################################

SHELL := /bin/bash
.DEFAULT_GOAL := help

COMPOSE := docker compose
COMPOSE_FILE ?= docker-compose.yml
# Exported so scripts/preflight_bind_posture.sh (below) renders the same file.
export COMPOSE_FILE

# Bind-posture preflight (deployment trust contract §3/§5, design D2): verifies
# every JUNIPER_<SVC>_LOOPBACK_PUBLISH_ATTESTED service publishes loopback-only
# in the rendered `docker compose config` BEFORE bring-up, catching a silent
# BIND_HOST=0.0.0.0. Invoked per bring-up target with the SAME --profile /
# --env-file flags the bring-up uses, so it checks exactly what is about to
# start; a failure (exit 1) aborts the target before `docker compose up`.
PREFLIGHT := bash scripts/preflight_bind_posture.sh

# Build-freshness preflight (incident of record 2026-07-07): the compose stack
# builds its first-party images from LOCAL sibling checkouts (`build.context:
# ../juniper-cascor` etc.), so image freshness is bounded by local-checkout
# freshness — not by GitHub main. Refuses `make build` (exit 1) when a
# build-context checkout sitting on its default branch is BEHIND its origin
# (the class that shipped an old-flag SEC-F22 guard against the new two-flag
# env). Non-default branches / dirty trees only warn (deliberate dev flows).
# Escape hatch: JUNIPER_BUILD_STALE_OK=1 make build (or --allow-stale).
BUILD_PREFLIGHT := bash scripts/preflight_build_freshness.sh

# Image-provenance preflight — the INVERSE of BUILD_PREFLIGHT: stops the
# bring-up targets from RUNNING images that no longer match the code on disk
# ("checkout updated but image not rebuilt"). Compares each built image's
# org.opencontainers.image.revision label (stamped by PROVENANCE_ENV via
# scripts/provenance_sha.sh) against its build-context checkout's HEAD;
# refuses bring-up (exit 1) only on a provable default-branch mismatch.
# Non-default branches / in-flight dirty builds warn (deliberate dev flows).
# Fix: make build. Escape hatch: JUNIPER_IMAGE_STALE_OK=1 (or --allow-stale).
IMAGE_PREFLIGHT := bash scripts/preflight_image_provenance.sh

SECRETS_DIR := secrets
SECRETS_FILES := $(SECRETS_DIR)/juniper_data_api_keys.txt \
    $(SECRETS_DIR)/juniper_cascor_api_keys.txt \
    $(SECRETS_DIR)/canopy_api_key.txt \
    $(SECRETS_DIR)/cascor_auth_token.txt \
    $(SECRETS_DIR)/grafana_admin_password.txt

# Colors (disabled if NO_COLOR is set)
ifdef NO_COLOR
  GREEN  :=
  YELLOW :=
  CYAN   :=
  RED    :=
  BOLD   :=
  RESET  :=
else
  GREEN  := \033[0;32m
  YELLOW := \033[0;33m
  CYAN   := \033[0;36m
  RED    := \033[0;31m
  BOLD   := \033[1m
  RESET  := \033[0m
endif

.PHONY: help up down restart logs logs-data logs-cascor logs-canopy \
        status build build-no-cache build-preflight clean \
        shell-data shell-cascor shell-canopy \
        health doctor wait ps demo dev test monitor obs obs-demo preflight image-preflight

# ═══════════════════════════════════════════════════════════════════════════
# Help
# ═══════════════════════════════════════════════════════════════════════════

help:  ## Show this help message
	@echo -e "$(BOLD)Juniper Platform — Developer Interface$(RESET)"
	@echo ""
	@echo -e "$(YELLOW)Usage:$(RESET) make [target]"
	@echo ""
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  $(CYAN)%-18s$(RESET) %s\n", $$1, $$2}'
	@echo ""

# ═══════════════════════════════════════════════════════════════════════════
# Lifecycle
# ═══════════════════════════════════════════════════════════════════════════

prepare-secrets:  ## Populate ./secrets/*.txt from .env.secrets.enc (falls back to empty placeholders if no SOPS key)
	@bash scripts/prepare_secrets.bash

preflight:  ## Verify loopback-publish bind attestation for every profile (no daemon needed)
	@$(PREFLIGHT) --profile full --profile demo --profile dev --profile observability

image-preflight:  ## Verify built images match their source checkouts (provenance labels; JUNIPER_IMAGE_STALE_OK=1 to bypass)
	@$(IMAGE_PREFLIGHT) --profile full --profile demo --profile dev --profile test --profile observability

up: prepare-secrets ## Start all services (--profile full, detached)
	@$(PREFLIGHT) --profile full
	@$(IMAGE_PREFLIGHT) --profile full
	@$(COMPOSE) -f $(COMPOSE_FILE) --profile full up -d
	@echo -e "$(GREEN)Services starting. Run 'make logs' to follow output.$(RESET)"

down:  ## Stop and remove all containers
	@$(COMPOSE) -f $(COMPOSE_FILE) --profile full --profile demo --profile dev --profile test --profile observability down

restart:  ## Restart all services
	@$(COMPOSE) -f $(COMPOSE_FILE) restart

demo: prepare-secrets ## Start demo stack (auto-configured CasCor training)
	@$(PREFLIGHT) --profile demo
	@$(IMAGE_PREFLIGHT) --profile demo
	@$(COMPOSE) -f $(COMPOSE_FILE) --profile demo up -d
	@echo -e "$(GREEN)Demo stack starting. Run 'make logs' to follow output.$(RESET)"

dev: prepare-secrets ## Start dev stack (real data + cascor, canopy in demo mode)
	@$(PREFLIGHT) --profile dev
	@$(IMAGE_PREFLIGHT) --profile dev
	@$(COMPOSE) -f $(COMPOSE_FILE) --profile dev up -d
	@echo -e "$(GREEN)Dev stack starting. Run 'make logs' to follow output.$(RESET)"

test:  ## Run integration tests (starts services + test-runner)
	@$(COMPOSE) -f $(COMPOSE_FILE) --profile test up --abort-on-container-exit --exit-code-from test-runner

monitor: prepare-secrets ## Start full stack with observability (Prometheus + Grafana)
	@$(PREFLIGHT) --env-file .env.observability --profile full --profile observability
	@$(IMAGE_PREFLIGHT) --env-file .env.observability --profile full --profile observability
	@$(COMPOSE) -f $(COMPOSE_FILE) \
		--env-file .env.observability \
		--profile full --profile observability up -d
	@echo -e "$(GREEN)Full stack + observability starting. Prometheus: http://localhost:9090, Grafana: http://localhost:$${GRAFANA_HOST_PORT:-3001}$(RESET)"

obs: monitor  ## Alias for `make monitor` (referenced from .env.observability)

obs-demo: prepare-secrets  ## Start demo stack with observability (scrapes juniper-{cascor,canopy}-demo via prometheus.demo.yml)
	@PROMETHEUS_CONFIG_FILE=prometheus.demo.yml \
		$(PREFLIGHT) --env-file .env.observability --profile demo --profile observability
	@PROMETHEUS_CONFIG_FILE=prometheus.demo.yml \
		$(IMAGE_PREFLIGHT) --env-file .env.observability --profile demo --profile observability
	@PROMETHEUS_CONFIG_FILE=prometheus.demo.yml \
		$(COMPOSE) -f $(COMPOSE_FILE) \
		--env-file .env.observability \
		--profile demo --profile observability up -d
	@echo -e "$(GREEN)Demo stack + observability starting. Prometheus: http://localhost:9090 (scraping -demo-suffixed services), Grafana: http://localhost:$${GRAFANA_HOST_PORT:-3001}$(RESET)"

# ═══════════════════════════════════════════════════════════════════════════
# Logs
# ═══════════════════════════════════════════════════════════════════════════

logs:  ## Tail logs from all services (follow)
	@$(COMPOSE) -f $(COMPOSE_FILE) logs -f

logs-data:  ## Tail JuniperData logs
	@$(COMPOSE) -f $(COMPOSE_FILE) logs -f juniper-data

logs-cascor:  ## Tail JuniperCascor logs
	@$(COMPOSE) -f $(COMPOSE_FILE) logs -f juniper-cascor

logs-canopy:  ## Tail JuniperCanopy logs
	@$(COMPOSE) -f $(COMPOSE_FILE) logs -f juniper-canopy

# ═══════════════════════════════════════════════════════════════════════════
# Status and Health
# ═══════════════════════════════════════════════════════════════════════════

status:  ## Show container status
	@$(COMPOSE) -f $(COMPOSE_FILE) ps

ps:  ## Compact container listing
	@$(COMPOSE) -f $(COMPOSE_FILE) ps --format table

health:  ## Detailed health report for all services
	@bash scripts/health_check.sh

wait:  ## Block until all services are healthy
	@bash scripts/wait_for_services.sh

doctor:  ## Detect stale images: built/running revision vs source HEAD (FRESH/STALE/UNKNOWN)
	@bash scripts/doctor.sh

# ═══════════════════════════════════════════════════════════════════════════
# Build
# ═══════════════════════════════════════════════════════════════════════════

# Build provenance (juniper-ml notes/BUILD_PROVENANCE_DESIGN_2026-06-14.md):
# stamp each image with ITS OWN source repo's short git SHA (a single global
# GIT_SHA would mislabel a multi-service build), a shared ISO-8601 build date,
# and the per-repo package version. docker-compose interpolates these per
# service via `build.args`. The companion `make doctor` compares the running
# image revision against the source HEAD to surface stale images. A missing
# sibling repo resolves to an empty string (image built with empty provenance
# → reported UNKNOWN, "rebuild"). `scripts/provenance_sha.sh` appends `-dirty`
# when a repo's working tree has uncommitted *tracked* changes (OQ-2), so an
# image built from uncommitted code is reported DIRTY rather than FRESH.
PROVENANCE_ENV = BUILD_DATE="$$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
	GIT_SHA_DATA="$$(bash scripts/provenance_sha.sh ../juniper-data)" \
	GIT_SHA_CASCOR="$$(bash scripts/provenance_sha.sh ../juniper-cascor)" \
	GIT_SHA_CANOPY="$$(bash scripts/provenance_sha.sh ../juniper-canopy)" \
	GIT_SHA_WORKER="$$(bash scripts/provenance_sha.sh ../juniper-cascor-worker)" \
	GIT_SHA_RECURRENCE="$$(bash scripts/provenance_sha.sh ../juniper-recurrence)" \
	APP_VERSION_DATA="$$(sed -nE 's/^version = \"(.+)\"/\1/p' ../juniper-data/pyproject.toml 2>/dev/null | head -1)" \
	APP_VERSION_CASCOR="$$(sed -nE 's/^version = \"(.+)\"/\1/p' ../juniper-cascor/pyproject.toml 2>/dev/null | head -1)" \
	APP_VERSION_CANOPY="$$(sed -nE 's/^version = \"(.+)\"/\1/p' ../juniper-canopy/pyproject.toml 2>/dev/null | head -1)" \
	APP_VERSION_WORKER="$$(sed -nE 's/^version = \"(.+)\"/\1/p' ../juniper-cascor-worker/pyproject.toml 2>/dev/null | head -1)" \
	APP_VERSION_RECURRENCE="$$(sed -nE 's/^__version__ = \"(.+)\"/\1/p' ../juniper-recurrence/juniper-recurrence/juniper_recurrence/_version.py 2>/dev/null | head -1)"

build-preflight:  ## Verify every compose build-context checkout is current with its origin (JUNIPER_BUILD_STALE_OK=1 to bypass)
	@$(BUILD_PREFLIGHT) --profile full --profile demo --profile dev --profile test --profile observability

build:  ## Build/rebuild all images (stamped with per-repo git SHA + build date)
	@$(BUILD_PREFLIGHT) --profile full --profile demo --profile dev --profile test --profile observability
	@$(PROVENANCE_ENV) $(COMPOSE) -f $(COMPOSE_FILE) --profile full --profile demo --profile dev --profile test --profile observability build

build-no-cache:  ## Full rebuild without cache (stamped with per-repo git SHA + build date)
	@$(BUILD_PREFLIGHT) --profile full --profile demo --profile dev --profile test --profile observability
	@$(PROVENANCE_ENV) $(COMPOSE) -f $(COMPOSE_FILE) --profile full --profile demo --profile dev --profile test --profile observability build --no-cache

# ═══════════════════════════════════════════════════════════════════════════
# Cleanup
# ═══════════════════════════════════════════════════════════════════════════

clean:  ## Remove containers, volumes, and local images
	@echo -e "$(RED)This will remove all containers, volumes, and locally-built images.$(RESET)"
	@read -p "Continue? [y/N] " confirm && [ "$$confirm" = "y" ] || { echo "Aborted."; exit 1; }
	@$(COMPOSE) -f $(COMPOSE_FILE) down -v --rmi local

# ═══════════════════════════════════════════════════════════════════════════
# Shell Access
# ═══════════════════════════════════════════════════════════════════════════

shell-data:  ## Shell into JuniperData container
	@$(COMPOSE) -f $(COMPOSE_FILE) exec juniper-data bash

shell-cascor:  ## Shell into JuniperCascor container
	@$(COMPOSE) -f $(COMPOSE_FILE) exec juniper-cascor bash

shell-canopy:  ## Shell into JuniperCanopy container
	@$(COMPOSE) -f $(COMPOSE_FILE) exec juniper-canopy bash
