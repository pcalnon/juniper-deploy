# Container Validation & CI Integration Plan

**Project**: juniper-deploy
**Author**: Paul Calnon (via Claude Code)
**Date**: 2026-03-05
**Branch**: feature/docker/python-3.14

---

## Overview

Validate that all three Juniper service containers (juniper-data, juniper-cascor, juniper-canopy) launch correctly on Python 3.14, pass health checks, and add a GitHub Actions CI workflow to automate this validation on every push/PR.

---

## Phase 1: Local Container Validation

### Step 1.1 — Build all images (no cache)

```bash
cd juniper-deploy && make build-no-cache
```

Verify all three Dockerfiles build successfully against python:3.14-slim.

### Step 1.2 — Validate `make dev` profile

```bash
make dev
# Wait for health
bash scripts/wait_for_services.sh
# Check health endpoints
curl -s http://localhost:8100/v1/health | python3 -m json.tool
curl -s http://localhost:8201/v1/health | python3 -m json.tool
curl -s http://localhost:8050/v1/health | python3 -m json.tool
make down
```

**Expected services**: juniper-data, juniper-cascor, juniper-canopy-dev (demo mode)

### Step 1.3 — Validate `make demo` profile

```bash
make demo
bash scripts/wait_for_services.sh
curl -s http://localhost:8100/v1/health | python3 -m json.tool
curl -s http://localhost:8201/v1/health | python3 -m json.tool
curl -s http://localhost:8050/v1/health | python3 -m json.tool
# Check demo-seed completed
docker compose ps demo-seed
make down
```

**Expected services**: juniper-data, demo-seed (exited), juniper-cascor-demo, juniper-canopy-demo

### Step 1.4 — Validate `make up` (full) profile

```bash
make up
bash scripts/wait_for_services.sh
curl -s http://localhost:8100/v1/health | python3 -m json.tool
curl -s http://localhost:8201/v1/health | python3 -m json.tool
curl -s http://localhost:8050/v1/health | python3 -m json.tool
make down
```

**Expected services**: juniper-data, juniper-cascor, juniper-canopy

### Step 1.5 — Validate clean teardown

After each `make down`, verify no orphan containers remain:
```bash
docker compose ps -a  # Should show no containers
```

---

## Phase 2: GitHub Actions CI Workflow

### Step 2.1 — Create `.github/workflows/ci.yml`

Create juniper-deploy's first CI workflow following ecosystem conventions (SHA-pinned actions, quality gate).

**File**: `juniper-deploy/.github/workflows/ci.yml`

**Triggers**:
- push to `main`, `develop`, `feature/**`, `fix/**`
- pull_request
- workflow_dispatch

**Jobs**:

#### Job 1: `validate-compose`
- Runs `docker compose --profile full config`, `--profile demo config`, `--profile dev config`
- Verifies compose file syntax without building images
- Fast feedback (no Docker build required)

#### Job 2: `docker-integration`
- Requires: `validate-compose`
- Builds all images: `docker compose --profile full --profile demo --profile dev build`
- Starts the `dev` profile (fastest — no demo-seed wait, canopy in demo mode)
- Waits for services using `scripts/wait_for_services.sh`
- Curls all three `/v1/health` endpoints, asserts HTTP 200
- Runs `make down` for teardown
- On failure: captures `docker compose ps` and `docker compose logs --tail 50` as artifacts

#### Job 3: `required-checks` (quality gate)
- Aggregates `validate-compose` and `docker-integration`
- Follows ecosystem pattern: `if: always()`, checks each job result

**Runner**: `ubuntu-latest` (GitHub-hosted, has Docker pre-installed)

**Key decisions**:
- Use `dev` profile for CI (not `full` or `demo`) because:
  - `dev` starts canopy in demo mode — no dependency on real CasCor training state
  - `demo` requires demo-seed + auto-start training — slow and fragile for CI
  - `full` is identical to `dev` for health check purposes but has real canopy ↔ cascor coupling
- Build context requires sibling repos — CI will checkout all three service repos into the expected directory structure
- Health check script (`wait_for_services.sh`) already uses `CASCOR_HOST_PORT:-8201`

**Multi-repo checkout strategy**:
```yaml
steps:
  - uses: actions/checkout@<sha>  # juniper-deploy
    with:
      path: juniper-deploy
  - uses: actions/checkout@<sha>
    with:
      repository: pcalnon/juniper-data
      path: juniper-data
  - uses: actions/checkout@<sha>
    with:
      repository: pcalnon/juniper-cascor
      path: juniper-cascor
  - uses: actions/checkout@<sha>
    with:
      repository: pcalnon/juniper-canopy
      path: juniper-canopy
```

The docker-compose.yml uses `context: ../juniper-*` relative paths, so setting up the directory structure as:
```
$GITHUB_WORKSPACE/
├── juniper-deploy/
├── juniper-data/
├── juniper-cascor/
└── juniper-canopy/
```
...will match exactly. The `working-directory: juniper-deploy` directive makes compose commands find the correct `docker-compose.yml`.

---

## Phase 3: Documentation Updates

### Step 3.1 — Update `juniper-ml/notes/DEVELOPER_CHEATSHEET.md`

**Changes needed**:

1. **Service Ports table** (line ~714-718): Change juniper-cascor port from `8200` to `8201` with note "(Docker host port)"

2. **"Start the Full Stack (Docker)"** (line ~309): Change `juniper-cascor (8200)` → `juniper-cascor (8201)` in the dependency chain description

3. **"Check Service Health"** (line ~397): Change the `for port in 8100 8200 8050` loop to `for port in 8100 8201 8050`

4. **"Run a Service Natively"** (line ~379): No change needed — native runs still use port 8200 directly

5. **"Upgrade Python Version in Docker"** section (line ~792-820): Add a note that all three services are now on Python 3.14 (completed)

6. **CI/CD section — "Add a CI Job"** (line ~621-629): Mention juniper-deploy now has its own `ci.yml` for Docker integration testing

### Step 3.2 — Update `juniper-deploy/AGENTS.md`

No changes needed — already shows correct port 8201 and has CASCOR_HOST_PORT documented.

### Step 3.3 — Update `juniper-deploy/README.md`

No changes needed — already shows port 8201 for JuniperCascor.

### Step 3.4 — Update parent `Juniper/AGENTS.md`

No changes needed — already shows 8201 in the service ports table.

---

## Phase 4: Commit & Merge

### Step 4.1 — Commit CI workflow + doc updates

Commit all changes to the `feature/docker/python-3.14` branch:
- `.github/workflows/ci.yml` (new)
- `juniper-ml/notes/DEVELOPER_CHEATSHEET.md` (updated)

### Step 4.2 — Push branch

```bash
git push origin feature/docker/python-3.14
```

### Step 4.3 — Verify CI runs

Check that the new workflow triggers on push and passes.

### Step 4.4 — Merge to main

After CI passes, merge the feature branch to main following worktree cleanup procedure.

---

## File Inventory

| File | Action | Description |
|------|--------|-------------|
| `juniper-deploy/.github/workflows/ci.yml` | **Create** | Docker integration CI workflow |
| `juniper-ml/notes/DEVELOPER_CHEATSHEET.md` | **Edit** | Update ports (8200→8201 in Docker sections), note Python 3.14 complete, mention deploy CI |
| `juniper-deploy/notes/CONTAINER_VALIDATION_CI_PLAN.md` | **Create** | This plan |

---

## Success Criteria

1. All three profiles (`dev`, `demo`, `full`) start and pass health checks locally
2. `ci.yml` exists and validates compose config + builds + health checks in CI
3. Cheatsheet reflects port 8201 for Docker access and Python 3.14 completion
4. Clean teardown leaves no orphan containers
