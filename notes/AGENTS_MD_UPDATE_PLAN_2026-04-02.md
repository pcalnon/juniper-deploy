# AGENTS.md Update Plan — juniper-deploy

**Date**: 2026-04-02
**Based On**: `AGENTS_MD_AUDIT_ANALYSIS_2026-04-02.md`
**Objective**: Bring `AGENTS.md` into full alignment with the current repository state

---

## Phase 1: Critical Fixes (Security/Correctness)

**Priority**: P0 — Must be addressed immediately

### Step 1.1: Fix Grafana Password Documentation

- **Finding**: ENV-01 (CRITICAL)
- **Current**: Line 134 shows `GRAFANA_ADMIN_PASSWORD` with default `admin`
- **Required**: Replace with `GF_SECURITY_ADMIN_PASSWORD__FILE` referencing Docker secret
- **Verification**: `grep "GF_SECURITY_ADMIN_PASSWORD__FILE" docker-compose.yml`

### Step 1.2: Fix Rate Limiting Defaults

- **Finding**: ENV-02 (CRITICAL)
- **Current**: Line 117 shows `JUNIPER_CASCOR_RATE_LIMIT_ENABLED` default `false`; Line 119 shows `CANOPY_RATE_LIMIT_ENABLED` default `false`
- **Required**: Update both defaults to `true` (matches docker-compose.yml)
- **Verification**: `grep "RATE_LIMIT_ENABLED" docker-compose.yml`

---

## Phase 2: Add Missing Major Sections

**Priority**: P1 — High-impact structural gaps

### Step 2.1: Add Directory Layout Section

- **Finding**: SEC-01 (HIGH)
- **Task**: Add complete repository tree showing all directories and key files
- **Source**: `ls -R` output from repository exploration

### Step 2.2: Add Security Architecture Section

- **Finding**: SEC-02 (HIGH)
- **Task**: Document:
  - Docker network isolation (4 networks: frontend, backend/internal, data/internal, monitoring)
  - Container hardening (no-new-privileges, cap_drop: ALL)
  - Port binding restrictions (127.0.0.1 for internal services)
  - Docker secrets management (4 secret files, secret file env vars)
  - SHA-pinned third-party images
- **Source**: `docker-compose.yml` networks/secrets sections, PR #6 and #12 notes

### Step 2.3: Add CI/CD Pipeline Section

- **Finding**: SEC-03 (HIGH)
- **Task**: Document:
  - 4 CI jobs: pre-commit, validate-compose, docker-integration, quality gate
  - Multi-repo checkout strategy (requires juniper-data, juniper-cascor, juniper-canopy)
  - SHA-pinned GitHub Actions
- **Source**: `.github/workflows/ci.yml`

### Step 2.4: Add Docker Compose Profiles Section

- **Finding**: SEC-04, ARCH-01 (HIGH)
- **Task**: Document profile-to-service mapping matrix
- **Source**: `docker-compose.yml` service profiles

### Step 2.5: Add Network Architecture Section

- **Finding**: SEC-05 (MEDIUM)
- **Task**: Document network topology with service assignments
- **Source**: `docker-compose.yml` networks section

### Step 2.6: Add Makefile Targets Reference

- **Finding**: SEC-08, CMD-01 (HIGH)
- **Task**: Document all 19 Makefile targets with descriptions
- **Source**: `Makefile`

---

## Phase 3: Complete Existing Sections

**Priority**: P1–P2 — Fill gaps in existing sections

### Step 3.1: Expand Service Ports Table

- **Finding**: PORT-01
- **Task**: Add Prometheus, AlertManager, Grafana, Redis, Cassandra to ports table
- **Include**: Profile column, 127.0.0.1 binding notation

### Step 3.2: Expand Key Files Table

- **Findings**: FILE-01 through FILE-08
- **Task**: Add all missing files to Key Files table, organized by category
- **Categories**: Core Config, Scripts, Tests, Infrastructure, CI/CD, Build

### Step 3.3: Update Service Dependency Graph

- **Finding**: ARCH-02
- **Task**: Show complete dependency graph including all services and profile context

### Step 3.4: Complete Environment Variables Table

- **Findings**: ENV-03 through ENV-06
- **Task**: Add missing env vars (Redis, Cassandra, Canopy, Docker secrets, Grafana)
- **Clarify**: .env name vs. container env name mapping where they differ

### Step 3.5: Update Essential Commands

- **Findings**: CMD-01 through CMD-04
- **Task**: Reorganize around Makefile targets as primary interface
- **Include**: Observability, health, build, shell access, cleanup commands

---

## Phase 4: Metadata and Documentation

**Priority**: P2 — Cleanup

### Step 4.1: Bump Version and Date

- **Finding**: META-01, META-02
- **Task**: Update version to `0.2.0`, date to `2026-04-02`

### Step 4.2: Add Documentation Index

- **Finding**: SEC-07
- **Task**: Add section pointing to `docs/` directory contents

### Step 4.3: Add Testing Architecture Section

- **Finding**: SEC-06
- **Task**: Document test files, markers, fixtures, shell scripts

---

## Implementation Order

```
Phase 1 (Critical)  →  immediate, blocks all other work
Phase 2 (Sections)  →  parallel across steps 2.1–2.6
Phase 3 (Complete)  →  parallel across steps 3.1–3.5
Phase 4 (Cleanup)   →  final pass
```

---

## Validation Checklist

After all phases are complete:

- [ ] Every file in the repository is accounted for in AGENTS.md (Directory Layout or Key Files)
- [ ] Every docker-compose.yml service is documented (Ports, Profiles, Dependencies)
- [ ] Every environment variable in docker-compose.yml and .env.example appears in the env table
- [ ] Security architecture matches docker-compose.yml (networks, secrets, hardening)
- [ ] CI/CD pipeline section matches .github/workflows/ci.yml
- [ ] Rate limiting defaults match docker-compose.yml (`true`)
- [ ] Grafana password uses Docker secrets (no `admin` default)
- [ ] Makefile targets match actual Makefile
- [ ] No stale references to removed or renamed features
- [ ] Version and date updated
