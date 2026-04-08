# Changelog

All notable changes to `juniper-deploy` will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

## [0.2.0] - 2026-04-08

### Added

- Demo, dev, and full Docker Compose profiles for different operational modes
- Observability stack: Prometheus v3.10.0, AlertManager v0.28.1, Grafana 12.4.0 with `observability` profile
- Auto-provisioned Grafana dashboards for all Juniper services (overview, data, cascor, canopy)
- Grafana dashboard provider configuration and home dashboard (`juniper-overview.json`)
- Grafana datasource with stable UID (`prometheus`), `httpMethod: POST`, and `timeInterval: 10s`
- Prometheus alerting rules, recording rules, and AlertManager routing configuration
- Enhanced Prometheus scrape configuration with per-job intervals, service/environment labels, and self-monitoring
- Redis service for juniper-canopy session/cache store (full and test profiles)
- `juniper-cascor-worker` service for distributed training (Phase 3, full and test profiles)
- Kubernetes Helm chart for Juniper stack deployment (Phase 4)
- Docker secrets support for API keys and Grafana admin password (`secrets/` directory)
- SOPS encryption configuration for environment secret files
- `Makefile` developer interface with 23 targets wrapping Docker Compose commands
- `make monitor` target for full stack with observability (Prometheus + Grafana)
- `make prepare-secrets` target to create placeholder secret files
- `health_check.sh` script for formatted health report output
- `wait_for_services.sh` script for polling health endpoints until ready
- `test_demo_profile.sh` integration test script (7-step demo validation)
- `test_health_enhanced.sh` enhanced health check validation (8-step schema checks)
- `Dockerfile.test` for containerized integration test execution via `test` profile
- Integration test suite: `test_health.py`, `test_data_service.py`, `test_full_stack.py`, `test_availability.py`
- `test_compose_security_config.py` Docker security regression tests
- CI/CD pipeline (`.github/workflows/ci.yml`) with pre-commit, compose validation, and Docker integration jobs
- Dependabot configuration for pip and GitHub Actions dependency updates
- CODEOWNERS file for code review routing
- Comprehensive documentation suite: `QUICK_START.md`, `ENVIRONMENT_SETUP.md`, `USER_MANUAL.md`, `DEVELOPER_CHEATSHEET.md`, `OBSERVABILITY_GUIDE.md`, `REFERENCE.md`, `TESTING_QUICK_START.md`
- `AGENTS.md` with thread handoff and worktree procedures
- This CHANGELOG

### Changed

- Remapped juniper-cascor host port from 8200 to 8201 (`CASCOR_HOST_PORT` env var) to avoid conflicts
- Updated canopy environment variables to `JUNIPER_CANOPY_*` prefix
- Updated cascor environment variable prefixes: `CASCOR_HOST` -> `JUNIPER_CASCOR_HOST`, `CASCOR_PORT` -> `JUNIPER_CASCOR_PORT`, `CASCOR_LOG_LEVEL` -> `JUNIPER_CASCOR_LOG_LEVEL`
- Updated JuniperCanopy references to juniper-canopy (naming convention alignment)
- Updated health scripts for enhanced ReadinessResponse format
- Pinned all third-party Docker images to specific versions (Prometheus v3.10.0, Grafana 12.4.0, Redis 7-alpine)
- SHA-pinned all GitHub Actions (checkout@v6.0.2, setup-python@v6.2.0, cache@v5.0.4)

### Fixed

- Enforced network isolation on backend and data Docker networks (marked as `internal: true`)
- Defined `SECRETS_DIR` and `SECRETS_FILES` Makefile variables used by `prepare-secrets` target
- Removed non-existent `COPY conftest.py .` from `Dockerfile.test` (conftest.py is inside `tests/`)
- Corrected AGENTS.md profile table: removed Cassandra (not in compose), fixed Redis profile assignment
- Corrected AGENTS.md port binding documentation: Redis has no host port binding
- Corrected AGENTS.md Makefile target references: `make obs`/`make obs-demo` -> `make monitor`
- Removed predictable Grafana admin password fallback (now requires Docker secret)
- Prevented compose startup failures when secrets directory is missing
- Closed secret-leak bypass and shell injection vulnerabilities
- Strengthened SOPS validation for encrypted environment files
- Added missing redis service and secret definitions
- Resolved pre-commit failures (check-yaml, shellcheck, yamllint)
- Fixed per-service skip-gating in integration tests
- Aligned compose security tests with actual docker-compose configuration

### Security

- Docker network isolation: `frontend` (bridge), `backend` (internal), `data` (internal), `monitoring` (bridge)
- Restricted port bindings to `127.0.0.1` for internal services (juniper-data, Prometheus, AlertManager, Grafana)
- Container hardening: `no-new-privileges:true` and `cap_drop: ALL` for all Juniper application containers
- Redis accessible only within Docker network (no host port binding)
- Grafana admin password via Docker secret only (no environment variable fallback)
- Rate limiting enabled by default for juniper-cascor and juniper-canopy
- CORS origins defaults set to empty (restrictive) for all services
- API key headers added to Prometheus scrape configuration
- SOPS pre-commit hook blocks unencrypted `.env` files from commit
