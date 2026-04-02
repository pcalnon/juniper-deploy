# AGENTS.md Update Development Roadmap — juniper-deploy

**Date**: 2026-04-02
**Based On**: `AGENTS_MD_AUDIT_ANALYSIS_2026-04-02.md`, `AGENTS_MD_UPDATE_PLAN_2026-04-02.md`
**Deliverable**: Updated `AGENTS.md` fully aligned with repository state at commit `8e6883b`

---

## Roadmap Summary

| Phase | Priority | Description | Tasks | Status |
|-------|----------|-------------|-------|--------|
| 1 | P0 | Critical security/correctness fixes | 2 | Pending |
| 2 | P1 | Add missing major sections | 6 | Pending |
| 3 | P1–P2 | Complete existing sections | 5 | Pending |
| 4 | P2 | Metadata, documentation index, testing | 3 | Pending |
| 5 | — | Validation and finalization | 3 | Pending |

**Total tasks**: 19

---

## Phase 1: Critical Fixes (P0)

> These tasks address security and correctness issues. They must be completed before any other work.

### Task 1.1: Fix Grafana Password Documentation

- **Finding**: ENV-01 (CRITICAL)
- **Action**: Remove `GRAFANA_ADMIN_PASSWORD | grafana | admin` row. Replace with documentation of `GF_SECURITY_ADMIN_PASSWORD__FILE` Docker secret mechanism.
- **Risk**: Operators reading stale docs may assume a predictable default password exists

### Task 1.2: Fix Rate Limiting Defaults

- **Finding**: ENV-02 (CRITICAL)
- **Action**: Update `JUNIPER_CASCOR_RATE_LIMIT_ENABLED` default from `false` to `true`. Update `CANOPY_RATE_LIMIT_ENABLED` (now `JUNIPER_CANOPY_RATE_LIMIT_ENABLED`) default from `false` to `true`.
- **Risk**: Operators may misconfigure rate limiting based on stale defaults

---

## Phase 2: Add Missing Major Sections (P1)

> These tasks add entirely new sections to AGENTS.md that reflect capabilities added since v0.1.0.

### Task 2.1: Add Directory Layout Section

- **Action**: Insert after Project Overview. Show complete repository tree.
- **Content**:
  ```
  juniper-deploy/
  ├── docker-compose.yml          # Service orchestration
  ├── Makefile                    # Developer CLI
  ├── .env.example                # Environment variable template
  ├── .env.demo                   # Demo profile overrides
  ├── .env.observability          # Observability profile overrides
  ├── AGENTS.md / CLAUDE.md       # Agent instructions
  ├── CHANGELOG.md                # Release history
  ├── README.md                   # Quickstart
  ├── pyproject.toml              # Pytest configuration
  ├── requirements-test.txt       # Test dependencies
  ├── .pre-commit-config.yaml     # Pre-commit hooks
  ├── scripts/                    # Shell scripts (4 files)
  ├── tests/                      # Integration tests (6 files)
  ├── docs/                       # Documentation (8 files)
  ├── notes/                      # Development notes
  ├── prometheus/                 # Prometheus config (3 files)
  ├── grafana/provisioning/       # Grafana dashboards + datasources
  ├── alertmanager/               # AlertManager config
  ├── secrets/                    # Docker secret files (git-ignored)
  ├── secrets.example/            # Secret file templates
  └── .github/                    # CI/CD workflows, CODEOWNERS, Dependabot
  ```

### Task 2.2: Add Security Architecture Section

- **Action**: Insert new section after Environment Variables
- **Content**: Document 5 security layers:
  1. Docker network isolation (4 networks, 2 internal)
  2. Container hardening (no-new-privileges, cap_drop: ALL)
  3. Port binding restrictions (127.0.0.1)
  4. Docker secrets management (4 secret files)
  5. SHA-pinned images (Prometheus, Grafana, AlertManager)

### Task 2.3: Add CI/CD Pipeline Section

- **Action**: Insert new section after Security Architecture
- **Content**: Document workflow jobs, triggers, multi-repo checkout, SHA-pinned actions

### Task 2.4: Add Docker Compose Profiles Matrix

- **Action**: Insert into Project Overview section
- **Content**: Profile-to-service mapping table

  | Service | full | demo | dev | observability |
  |---------|------|------|-----|---------------|
  | juniper-data | x | x | x | |
  | juniper-cascor | x | | x | |
  | juniper-cascor-demo | | x | | |
  | demo-seed | | x | | |
  | juniper-canopy | x | | | |
  | juniper-canopy-demo | | x | | |
  | juniper-canopy-dev | | | x | |
  | redis | x | x | | |
  | cassandra | x | | | |
  | prometheus | | | | x |
  | alertmanager | | | | x |
  | grafana | | | | x |

### Task 2.5: Add Network Architecture Section

- **Action**: Include within Security Architecture section
- **Content**: Network topology table

  | Network | Type | Services |
  |---------|------|----------|
  | frontend | bridge | canopy variants |
  | backend | internal | cascor, redis, cassandra, prometheus |
  | data | internal | data, cascor, canopy, prometheus |
  | monitoring | bridge | prometheus, grafana |

### Task 2.6: Add Makefile Targets Reference

- **Action**: Add to Quick Reference section or new dedicated section
- **Content**: All 19 Makefile targets with descriptions (from `make help` output)

---

## Phase 3: Complete Existing Sections (P1–P2)

> These tasks fill gaps in sections that already exist but are incomplete.

### Task 3.1: Expand Service Ports Table

- **Action**: Add 5 infrastructure services to the ports table
- **Include**: Profile column and 127.0.0.1 binding notation

### Task 3.2: Expand Key Files Table

- **Action**: Add 18 missing files/directories, organized by category
- **Categories**: Core, Scripts, Tests, Infrastructure, CI/CD

### Task 3.3: Update Service Dependency Graph

- **Action**: Replace simplified graph with complete per-profile dependency trees
- **Include**: redis, cassandra, demo-seed, observability services

### Task 3.4: Complete Environment Variables Table

- **Action**: Add Redis, Cassandra, Canopy, Docker secret file, and Grafana secret vars
- **Clarify**: `.env` name vs container env name where they differ (e.g., `CASCOR_LOG_LEVEL` → `JUNIPER_CASCOR_LOG_LEVEL`)

### Task 3.5: Update Essential Commands

- **Action**: Reorganize to lead with Makefile targets
- **Include**: Full lifecycle (up/down/restart), profiles (demo/dev/obs), monitoring (health/wait/status), build, shell, cleanup

---

## Phase 4: Metadata and Documentation (P2)

### Task 4.1: Bump Version and Date

- **Action**: Version `0.1.0` → `0.2.0`, date `2026-02-25` → `2026-04-02`

### Task 4.2: Add Documentation Index

- **Action**: Add section listing all 8 docs/ files with purpose
- **Format**: Quick-reference table with goal-based navigation

### Task 4.3: Add Testing Architecture Summary

- **Action**: Add section covering test files, markers, fixtures, shell test scripts
- **Include**: How to run different test categories

---

## Phase 5: Validation and Finalization

### Task 5.1: Cross-Reference Validation

- **Action**: Verify every docker-compose.yml service, env var, network, secret, and file is documented
- **Method**: Diff-based comparison against source files

### Task 5.2: Run Pre-commit Hooks

- **Action**: Run `pre-commit run --all-files` on the updated AGENTS.md
- **Validates**: Markdown lint, YAML lint, trailing whitespace, line length

### Task 5.3: Run Test Suites

- **Action**: Run `python -m unittest -v tests/test_wake_the_claude.py` (juniper-ml) and `bash scripts/test_resume_file_safety.bash` (juniper-ml)
- **Note**: juniper-deploy tests require running Docker containers; validate compose config instead: `docker compose --profile full config --quiet`

---

## Dependencies

```
Phase 1 ──blocks──> Phase 2, Phase 3, Phase 4
Phase 2 + Phase 3 ──blocks──> Phase 5
Phase 4 ──blocks──> Phase 5
```

---

## Risk Assessment

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| Docker-compose.yml changes between audit and update | Low | Medium | Use worktree on fixed commit |
| Markdown formatting breaks pre-commit | Medium | Low | Run markdownlint before commit |
| Missing env vars not caught in audit | Low | Medium | Cross-reference .env.example systematically |
| Stale notes/ docs reference removed features | Low | Low | Limit audit scope to AGENTS.md |
