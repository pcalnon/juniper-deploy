# Changelog

All notable changes to `juniper-deploy` will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Changed

- Updated canopy environment variables to `JUNIPER_CANOPY_*` prefix (Phase 9)
- Updated health scripts for enhanced ReadinessResponse format
- Updated JuniperCanopy references to juniper-canopy

### Added

- Demo, dev, and full Docker Compose profiles
- Observability stack configuration (Prometheus, Grafana)
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
