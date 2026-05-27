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
        status build build-no-cache clean \
        shell-data shell-cascor shell-canopy \
        health wait ps demo dev test monitor obs

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

up: prepare-secrets ## Start all services (--profile full, detached)
	@$(COMPOSE) -f $(COMPOSE_FILE) --profile full up -d
	@echo -e "$(GREEN)Services starting. Run 'make logs' to follow output.$(RESET)"

down:  ## Stop and remove all containers
	@$(COMPOSE) -f $(COMPOSE_FILE) --profile full --profile demo --profile dev --profile test --profile observability down

restart:  ## Restart all services
	@$(COMPOSE) -f $(COMPOSE_FILE) restart

demo: prepare-secrets ## Start demo stack (auto-configured CasCor training)
	@$(COMPOSE) -f $(COMPOSE_FILE) --profile demo up -d
	@echo -e "$(GREEN)Demo stack starting. Run 'make logs' to follow output.$(RESET)"

dev: prepare-secrets ## Start dev stack (real data + cascor, canopy in demo mode)
	@$(COMPOSE) -f $(COMPOSE_FILE) --profile dev up -d
	@echo -e "$(GREEN)Dev stack starting. Run 'make logs' to follow output.$(RESET)"

test:  ## Run integration tests (starts services + test-runner)
	@$(COMPOSE) -f $(COMPOSE_FILE) --profile test up --abort-on-container-exit --exit-code-from test-runner

monitor: prepare-secrets ## Start full stack with observability (Prometheus + Grafana)
	@$(COMPOSE) -f $(COMPOSE_FILE) \
		--env-file .env.observability \
		--profile full --profile observability up -d
	@echo -e "$(GREEN)Full stack + observability starting. Prometheus: http://localhost:9090, Grafana: http://localhost:$${GRAFANA_HOST_PORT:-3001}$(RESET)"

obs: monitor  ## Alias for `make monitor` (referenced from .env.observability)

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

# ═══════════════════════════════════════════════════════════════════════════
# Build
# ═══════════════════════════════════════════════════════════════════════════

build:  ## Build/rebuild all images
	@$(COMPOSE) -f $(COMPOSE_FILE) --profile full --profile demo --profile dev --profile test --profile observability build

build-no-cache:  ## Full rebuild without cache
	@$(COMPOSE) -f $(COMPOSE_FILE) --profile full --profile demo --profile dev --profile test --profile observability build --no-cache

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
