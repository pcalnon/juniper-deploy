# Changelog

All notable changes to `juniper-deploy` will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Changed

- **CASCOR-PORT-001: juniper-cascor host port remapped to 8201** — Introduced `CASCOR_HOST_PORT` env var (default: `8201`) to avoid host port conflicts with other services on port 8200. The container-internal port remains `8200` via `CASCOR_PORT`. Inter-container Docker networking is unaffected.
- Updated canopy environment variables to `JUNIPER_CANOPY_*` prefix (Phase 9)
- Updated health scripts for enhanced ReadinessResponse format
- Updated JuniperCanopy references to juniper-canopy
- Enhanced Prometheus scrape configuration with per-job intervals, service/environment labels, and self-monitoring
- Updated Grafana datasource with stable UID (`prometheus`), `httpMethod: POST`, and `timeInterval: 10s`
- Updated environment variable prefixes: `CASCOR_HOST` → `JUNIPER_CASCOR_HOST`, `CASCOR_PORT` → `JUNIPER_CASCOR_PORT`, `CASCOR_LOG_LEVEL` → `JUNIPER_CASCOR_LOG_LEVEL`

### Added

- Demo, dev, and full Docker Compose profiles
- Observability stack configuration (Prometheus, Grafana)
- Auto-provisioned Grafana dashboards for all Juniper services (overview, data, cascor, canopy)
- Grafana dashboard provider configuration (`grafana/provisioning/dashboards/`)
- Grafana home dashboard set to Juniper Overview
- Comprehensive observability documentation (`docs/OBSERVABILITY_GUIDE.md`)
- API security configuration for all services
- Makefile developer interface and health check script
- SOPS config and secrets template for Docker Compose
- AGENTS.md with thread handoff and worktree procedures
- This CHANGELOG

### Security

- Added Docker network isolation: `frontend`, `backend` (internal), `data` (internal) networks with service-specific assignments
- Restricted port bindings to `127.0.0.1` for internal services (juniper-data, juniper-cascor, Prometheus, Grafana)
- Added container security options: `no-new-privileges:true` and `cap_drop: ALL` for all Juniper services
- SHA-pinned third-party Docker images (Prometheus v3.2.1, Grafana 11.5.2)
- Changed Grafana admin password from `admin` default to required `${GRAFANA_ADMIN_PASSWORD:?...}`
- Changed rate limiting defaults to enabled for all services
- Changed CORS origins defaults to empty (restrictive) for all services
- Added API key header to Prometheus scrape configuration
