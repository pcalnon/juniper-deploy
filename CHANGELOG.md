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
