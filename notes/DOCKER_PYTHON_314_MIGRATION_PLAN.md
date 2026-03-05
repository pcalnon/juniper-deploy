# Docker Python 3.14 Migration Plan

**Created**: 2026-03-04
**Implemented**: 2026-03-05
**Status**: Implemented
**Branch**: `feature/docker-python-314` (per repo)

---

## Context

All 3 Juniper service Dockerfiles use `python:3.12-slim`. Local conda environments already run Python 3.14. This migration aligns Docker with local dev. PyTorch 2.10.0 has cp314 CPU wheels on `manylinux_2_28_x86_64` — no blockers.

## Scope

4 repos, consistent branch `feature/docker-python-314` with worktrees in each.

## Phase 1: Create Worktrees (4 repos)

Create worktrees in juniper-data, juniper-cascor, juniper-canopy, and juniper-deploy with branch `feature/docker-python-314`.

```bash
# For each repo:
cd /home/pcalnon/Development/python/Juniper/<repo>
git fetch origin && git checkout main && git pull origin main
BRANCH_NAME="feature/docker-python-314"
git branch "$BRANCH_NAME" main
REPO_NAME=$(basename "$(pwd)")
SAFE_BRANCH=$(echo "$BRANCH_NAME" | sed 's|/|--|g')
WORKTREE_DIR="/home/pcalnon/Development/python/Juniper/worktrees/${REPO_NAME}--${SAFE_BRANCH}--$(date +%Y%m%d-%H%M)--$(git rev-parse --short=8 HEAD)"
git worktree add "$WORKTREE_DIR" "$BRANCH_NAME"
```

## Phase 2: Update Dockerfiles (3 files)

### juniper-data/Dockerfile

| Line | Current | New |
|------|---------|-----|
| 12 | `FROM python:3.12-slim AS builder` | `FROM python:3.14-slim AS builder` |
| 31 | `FROM python:3.12-slim AS runtime` | `FROM python:3.14-slim AS runtime` |
| 48 | `python3.12/site-packages` | `python3.14/site-packages` |

### juniper-cascor/Dockerfile

| Line | Current | New |
|------|---------|-----|
| 12 | `FROM python:3.12-slim AS builder` | `FROM python:3.14-slim AS builder` |
| 34 | `FROM python:3.12-slim AS runtime` | `FROM python:3.14-slim AS runtime` |
| 49 | `python3.12/site-packages` | `python3.14/site-packages` |

### juniper-canopy/Dockerfile

| Line | Current | New |
|------|---------|-----|
| 15 | `FROM python:3.12-slim AS builder` | `FROM python:3.14-slim AS builder` |
| 33 | `FROM python:3.12-slim AS runtime` | `FROM python:3.14-slim AS runtime` |
| 48 | `python3.12/site-packages` | `python3.14/site-packages` |

All changes are `3.12` → `3.14` replacements. No structural changes.

## Phase 3: Update pyproject.toml Files (3 files)

### juniper-data/pyproject.toml

| Line | Current | New | Rationale |
|------|---------|-----|-----------|
| 84 | `target-version = "py311"` | `"py312"` | Align ruff target with requires-python >=3.12 |

No other changes needed — requires-python already `>=3.12`, mypy already `3.14`.

### juniper-cascor/pyproject.toml

| Line | Current | New | Rationale |
|------|---------|-----|-----------|
| 85 | `target-version = ["py311", "py312", "py313"]` | `["py312", "py313", "py314"]` | Add py314, drop py311 (Docker now 3.14) |
| 186 | `python_version = "3.13"` | `"3.14"` | mypy should target latest |

### juniper-canopy/pyproject.toml

| Line | Current | New | Rationale |
|------|---------|-----|-----------|
| 98 | `target-version = ['py311', 'py312', 'py313']` | `['py312', 'py313', 'py314']` | Add py314, drop py311 |
| 143 | `python_version = "3.13"` | `"3.14"` | mypy should target latest |

## Phase 4: Validate Builds

Docker requires `sudo` on this system (user not in docker group).

```bash
# 1. Validate compose config
cd <juniper-deploy-worktree>
sudo docker compose --profile full config

# 2. Build each image
sudo docker build -t juniper-data:test <juniper-data-worktree>
sudo docker build -t juniper-cascor:test <juniper-cascor-worktree>
sudo docker build -t juniper-canopy:test <juniper-canopy-worktree>

# 3. Verify Python version
sudo docker run --rm juniper-data:test python --version
sudo docker run --rm juniper-cascor:test python --version
sudo docker run --rm juniper-canopy:test python --version
```

## Phase 5: Commit in Each Worktree

Commit changes in each repo's worktree with message:

```
Update Docker base image from Python 3.12 to 3.14

Migrate Dockerfile FROM python:3.12-slim to python:3.14-slim.
Update site-packages copy path from python3.12 to python3.14.
Update linter target-version and mypy python_version settings.
```

## Phase 6: Integration Validation (Optional)

```bash
# Full stack test
sudo docker compose --profile demo up -d
# Wait for health checks
sudo docker compose ps
# Verify all services healthy, then tear down
sudo docker compose down
```

## Risk Assessment

| Risk | Severity | Status |
|------|----------|--------|
| PyTorch cp314 CPU wheel missing | **BLOCKER** | **CLEAR** — torch 2.10.0+cpu cp314 manylinux_2_28_x86_64 available |
| python:3.14-slim image availability | High | **CLEAR** — confirmed on Docker Hub |
| Dependency compatibility (numpy, fastapi, dash, etc.) | Medium | All major deps support 3.14 |
| Site-packages path mismatch | High | Covered by plan (3 explicit path updates) |

## Files Modified Summary

| File | Changes |
|------|---------|
| `juniper-data/Dockerfile` | 3.12 → 3.14 (3 occurrences) |
| `juniper-cascor/Dockerfile` | 3.12 → 3.14 (3 occurrences) |
| `juniper-canopy/Dockerfile` | 3.12 → 3.14 (3 occurrences) |
| `juniper-data/pyproject.toml` | ruff target-version py311 → py312 |
| `juniper-cascor/pyproject.toml` | black target-version +py314 -py311, mypy 3.13 → 3.14 |
| `juniper-canopy/pyproject.toml` | black target-version +py314 -py311, mypy 3.13 → 3.14 |
