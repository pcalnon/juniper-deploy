# AGENTS.md Drift Analysis — juniper-deploy

**Date**: 2026-04-02
**Auditor**: Claude Code (Opus 4.6)
**Scope**: Full audit of `AGENTS.md` v0.1.0 (2026-02-25) against current repository state (commit `8e6883b`)
**Severity Levels**: CRITICAL (security/correctness), HIGH (missing major section), MEDIUM (incomplete/outdated), LOW (minor cosmetic)

---

## Executive Summary

The `AGENTS.md` file (v0.1.0, last updated 2026-02-25) has significant drift from the current repository state. Since the initial release, the project has undergone security hardening (PRs #6–#12), observability infrastructure additions, CI/CD pipeline creation, and multiple environment variable changes. The file is missing 6 major sections and contains 24 discrete discrepancies across existing sections.

**Finding counts by severity:**

| Severity | Count |
|----------|-------|
| CRITICAL | 2 |
| HIGH | 8 |
| MEDIUM | 10 |
| LOW | 4 |
| **Total** | **24** |

---

## Section-by-Section Analysis

### 1. Header/Metadata

| ID | Severity | Finding |
|----|----------|---------|
| META-01 | LOW | Version still `0.1.0` — should be bumped to reflect post-release changes (security hardening, observability, CI/CD) |
| META-02 | LOW | Last Updated `2026-02-25` — 12+ PRs merged since then; date is stale |

---

### 2. Quick Reference > Essential Commands (Lines 15–43)

| ID | Severity | Finding |
|----|----------|---------|
| CMD-01 | HIGH | `Makefile` is the primary developer interface but is not mentioned anywhere in AGENTS.md. All `make` targets (`make up`, `make demo`, etc.) are absent from Essential Commands |
| CMD-02 | MEDIUM | Missing commands: `make obs`, `make obs-demo` (observability), `make health`, `make wait`, `make ps`, `make status`, `make build`, `make build-no-cache`, `make clean`, `make prepare-secrets` |
| CMD-03 | MEDIUM | Missing shell access commands: `make shell-data`, `make shell-cascor`, `make shell-canopy` |
| CMD-04 | LOW | Missing script: `bash scripts/test_health_enhanced.sh` (enhanced health validation) |

**Current state**: The Essential Commands section shows raw `docker compose` commands alongside `make` shortcuts but does not document the full Makefile target inventory. The Makefile (169 lines, 19 targets) is the canonical developer interface.

---

### 3. Quick Reference > Service Ports (Lines 46–53)

| ID | Severity | Finding |
|----|----------|---------|
| PORT-01 | MEDIUM | Table only shows 3 core services. Missing infrastructure services added during observability and security hardening work |

**Missing services:**

| Service | Host Port | Container Port | Health Endpoint | Profile |
|---------|-----------|----------------|-----------------|---------|
| Prometheus | 127.0.0.1:9090 | 9090 | `/-/healthy` | observability |
| AlertManager | 127.0.0.1:9093 | 9093 | `/-/healthy` | observability |
| Grafana | 127.0.0.1:3000 | 3000 | `/api/health` | observability |
| Redis | 127.0.0.1:6379 | 6379 | `redis-cli ping` | full, demo |
| Cassandra | 127.0.0.1:9042 | 9042 | `cqlsh` | full |

**Note**: juniper-data is now bound to `127.0.0.1` (security hardening PR #6), which is not reflected in the current table. juniper-cascor port mapping is `${CASCOR_HOST_PORT:-8201}:${CASCOR_PORT:-8200}` without `127.0.0.1` binding.

---

### 4. Quick Reference > Key Files (Lines 55–72)

| ID | Severity | Finding |
|----|----------|---------|
| FILE-01 | HIGH | `Makefile` not listed — it is the primary developer CLI |
| FILE-02 | HIGH | `CHANGELOG.md` not listed — release history |
| FILE-03 | MEDIUM | `.github/workflows/ci.yml` not listed — CI/CD pipeline (v0.2.0) |
| FILE-04 | MEDIUM | Missing test files: `tests/test_availability.py`, `tests/test_compose_security_config.py`, `tests/constants.py` |
| FILE-05 | MEDIUM | Missing scripts: `scripts/health_check.sh`, `scripts/test_health_enhanced.sh` |
| FILE-06 | MEDIUM | Missing infrastructure configs: `alertmanager/alertmanager.yml`, `prometheus/alert_rules.yml`, `prometheus/recording_rules.yml` |
| FILE-07 | LOW | Missing build/config files: `pyproject.toml`, `requirements-test.txt`, `.pre-commit-config.yaml`, `.github/CODEOWNERS`, `.github/dependabot.yml` |
| FILE-08 | MEDIUM | Missing directories: `secrets/` (Docker secret files), `secrets.example/` (templates) |

---

### 5. Project Overview (Lines 75–90)

| ID | Severity | Finding |
|----|----------|---------|
| ARCH-01 | HIGH | No mention of Docker Compose profiles (full, demo, dev, observability) — this is the defining architectural feature |
| ARCH-02 | HIGH | Service Dependency Graph only shows 3 services. Missing: redis, cassandra, demo-seed, prometheus, alertmanager, grafana, and profile-specific service variants (juniper-cascor-demo, juniper-canopy-demo, juniper-canopy-dev) |

---

### 6. Environment Variables (Lines 98–139)

| ID | Severity | Finding |
|----|----------|---------|
| ENV-01 | CRITICAL | Line 134: `GRAFANA_ADMIN_PASSWORD` listed with default `admin`. This was removed in PR #12 (`fix/grafana-default-password`). Grafana now uses `GF_SECURITY_ADMIN_PASSWORD__FILE` Docker secret. Documenting a predictable default password is a security issue. |
| ENV-02 | CRITICAL | Line 117: `JUNIPER_CASCOR_RATE_LIMIT_ENABLED` default shown as `false`. Docker-compose.yml (line 98) now defaults to `true`. CHANGELOG confirms "Changed rate limiting defaults to enabled for all services." Incorrect default could lead operators to believe rate limiting is off when it's on, or vice versa. |
| ENV-03 | MEDIUM | Missing env vars for infrastructure services: `REDIS_PORT`, `REDIS_MAX_MEMORY`, `REDIS_URL`, `CASSANDRA_PORT`, `CASSANDRA_MAX_HEAP`, `CASSANDRA_HEAP_NEW` |
| ENV-04 | MEDIUM | Missing Docker secret file env vars: `JUNIPER_DATA_API_KEYS_FILE`, `JUNIPER_CASCOR_API_KEYS_FILE`, `JUNIPER_DATA_API_KEY_FILE`, `CANOPY_API_KEY_FILE`, `JUNIPER_CASCOR_API_KEY_FILE` |
| ENV-05 | MEDIUM | Missing Canopy env vars: `CANOPY_API_KEY`, `JUNIPER_CANOPY_RATE_LIMIT_ENABLED` (compose uses this name), `JUNIPER_CANOPY_RATE_LIMIT_REQUESTS_PER_MINUTE` |
| ENV-06 | MEDIUM | `CASCOR_LOG_LEVEL` vs `JUNIPER_CASCOR_LOG_LEVEL` inconsistency: `.env.example` uses `CASCOR_LOG_LEVEL`, docker-compose maps it to `JUNIPER_CASCOR_LOG_LEVEL`. CHANGELOG documents the prefix update. AGENTS.md shows the service-side name but does not clarify the .env mapping. |

---

### 7. Missing Sections

| ID | Severity | Missing Section | Justification |
|----|----------|----------------|---------------|
| SEC-01 | HIGH | **Directory Layout** | Repository structure is undocumented. Critical for navigation. |
| SEC-02 | HIGH | **Security Architecture** | Network isolation (4 networks, 2 internal), Docker secrets (4 secret files), container hardening (`no-new-privileges`, `cap_drop: ALL`), localhost port binding — all added in PRs #6–#12, entirely undocumented in AGENTS.md. |
| SEC-03 | HIGH | **CI/CD Pipeline** | `.github/workflows/ci.yml` (v0.2.0) with 4 jobs: pre-commit, validate-compose, docker-integration, quality gate. Not documented. |
| SEC-04 | MEDIUM | **Docker Compose Profiles** | Profile-to-service mapping (which services run in which profile). Currently embedded in docker-compose.yml comments but not in AGENTS.md. |
| SEC-05 | MEDIUM | **Network Architecture** | 4 Docker networks: `frontend` (bridge), `backend` (internal), `data` (internal), `monitoring` (bridge). Service-to-network assignments critical for troubleshooting. |
| SEC-06 | MEDIUM | **Testing Architecture** | 6 test files, 4 shell scripts, 3 pytest markers, conftest fixtures, test constants. Only partially documented. |
| SEC-07 | MEDIUM | **Documentation Index** | 8 files in `docs/` directory. No pointer to documentation from AGENTS.md beyond individual file mentions. |
| SEC-08 | MEDIUM | **Makefile Targets Reference** | 19 targets in Makefile. None documented in AGENTS.md. |

---

## Cross-Reference: CHANGELOG vs AGENTS.md

The CHANGELOG documents the following changes that are NOT reflected in AGENTS.md:

| CHANGELOG Entry | AGENTS.md Status |
|-----------------|-----------------|
| `CASCOR_HOST_PORT` env var introduction | Partially reflected (port table shows 8201) |
| Canopy env vars updated to `JUNIPER_CANOPY_*` prefix | Not reflected in env table |
| Enhanced Prometheus scrape configuration | Not documented |
| Grafana datasource updates (stable UID, POST, timeInterval) | Not documented |
| `CASCOR_HOST` → `JUNIPER_CASCOR_HOST` prefix updates | Partially reflected |
| Docker network isolation | Not documented |
| Restricted port bindings to 127.0.0.1 | Not documented |
| Container security options (no-new-privileges, cap_drop) | Not documented |
| SHA-pinned Docker images | Not documented |
| Grafana password changed to required/secret | **Contradicted** (AGENTS.md shows default `admin`) |
| Rate limiting defaults changed to enabled | **Contradicted** (AGENTS.md shows `false`) |
| API key header in Prometheus scrape config | Not documented |

---

## Files Present in Repository but Absent from AGENTS.md

| File/Directory | Purpose | Priority to Document |
|----------------|---------|---------------------|
| `Makefile` | Primary developer CLI | P0 |
| `CHANGELOG.md` | Release history | P1 |
| `.github/workflows/ci.yml` | CI/CD pipeline | P1 |
| `scripts/health_check.sh` | Health report formatter | P1 |
| `scripts/test_health_enhanced.sh` | Enhanced health validation | P2 |
| `tests/test_availability.py` | Availability fixtures | P2 |
| `tests/test_compose_security_config.py` | Security regression tests | P1 |
| `tests/constants.py` | Shared test constants | P2 |
| `alertmanager/alertmanager.yml` | AlertManager config | P1 |
| `prometheus/alert_rules.yml` | Alert rules | P1 |
| `prometheus/recording_rules.yml` | Recording rules | P2 |
| `secrets/` | Docker secret files | P1 |
| `secrets.example/` | Secret file templates | P1 |
| `pyproject.toml` | Pytest configuration | P2 |
| `requirements-test.txt` | Test dependencies | P2 |
| `.pre-commit-config.yaml` | Pre-commit hooks | P2 |
| `.github/CODEOWNERS` | Code ownership | P2 |
| `.github/dependabot.yml` | Dependabot | P2 |

---

## Recommendations

1. **Immediate** (CRITICAL): Fix the Grafana password documentation and rate limiting defaults
2. **High Priority**: Add missing sections (Directory Layout, Security Architecture, CI/CD, Profiles)
3. **Medium Priority**: Complete the Key Files table, Environment Variables table, and Service Ports table
4. **Low Priority**: Update version, date, and cosmetic items

---

## Appendix: Verification Commands

```bash
# Verify GRAFANA_ADMIN_PASSWORD handling
grep -n "GRAFANA_ADMIN_PASSWORD" docker-compose.yml
# Expected: Only GF_SECURITY_ADMIN_PASSWORD__FILE reference

# Verify rate limit defaults
grep -n "RATE_LIMIT_ENABLED" docker-compose.yml
# Expected: default true for cascor and canopy

# Verify network declarations
grep -n "internal:" docker-compose.yml
# Expected: backend and data networks are internal

# Verify security options
grep -n "no-new-privileges" docker-compose.yml
# Expected: present on all Juniper service containers

# List all Makefile targets
grep -E '^[a-zA-Z_-]+:' Makefile
```
