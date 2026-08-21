# AGENTS.md - Juniper Deploy

**Project**: juniper-deploy — Docker Compose Orchestration for Juniper Stack
**Repository**: pcalnon/juniper-deploy
**Author**: Paul Calnon
**License**: MIT License
**Version**: 0.2.1
**Last Updated**: 2026-08-21

---

## Quick Reference

### Essential Commands

```bash
# === Lifecycle (via Makefile) ===
make up           # Start full stack (all real services, detached)
make demo         # Start demo stack (auto-configured CasCor training)
make dev          # Start dev stack (canopy in demo mode)
make down         # Stop and remove all containers
make restart      # Restart all services

# === Observability ===
make monitor      # Full stack + Prometheus + Grafana

# === Monitoring ===
make health       # Detailed health report for all services
make wait         # Block until all services are healthy (90s timeout)
make status       # Show container status
make ps           # Compact container listing

# === Logs ===
make logs         # Tail all service logs (follow)
make logs-data    # Tail JuniperData logs
make logs-cascor  # Tail JuniperCascor logs
make logs-canopy  # Tail JuniperCanopy logs

# === Build ===
make build          # Build/rebuild all images
make build-no-cache # Full rebuild without cache

# === Shell Access ===
make shell-data     # Shell into JuniperData container
make shell-cascor   # Shell into JuniperCascor container
make shell-canopy   # Shell into JuniperCanopy container

# === Cleanup ===
make clean          # Remove containers, volumes, and local images (interactive)

# === Direct Docker Compose (when Makefile is insufficient) ===
docker compose --profile full config    # Validate compose configuration
docker compose logs -f                  # Follow logs (all profiles)

# === Integration Tests ===
pip install -r requirements-test.txt
bash scripts/wait_for_services.sh       # Poll until services healthy
pytest tests/ -v                        # Run full test suite
bash scripts/test_demo_profile.sh       # Demo profile integration test
bash scripts/test_health_enhanced.sh    # Enhanced health check validation
```

### Service Ports

| Service | Host Binding | Container Port | Health Endpoint | Profile(s) |
|---------|-------------|----------------|-----------------|------------|
| juniper-data | 127.0.0.1:8100 | 8100 | `/v1/health` | full, demo, dev |
| juniper-cascor | 0.0.0.0:8201 | 8200 | `/v1/health` | full, dev |
| juniper-cascor-demo | 0.0.0.0:8201 | 8200 | `/v1/health` | demo |
| juniper-canopy | 0.0.0.0:8050 | 8050 | `/v1/health` | full |
| juniper-canopy-demo | 0.0.0.0:8050 | 8050 | `/v1/health` | demo |
| juniper-canopy-dev | 0.0.0.0:8050 | 8050 | `/v1/health` | dev |
| Prometheus | 127.0.0.1:9090 | 9090 | `/-/healthy` | observability |
| AlertManager | 127.0.0.1:9093 | 9093 | `/-/healthy` | observability |
| Grafana | 127.0.0.1:3000 | 3000 | `/api/health` | observability |
| Redis | *(no host binding)* | 6379 | `redis-cli ping` | full, test |

### Key Files

| File | Purpose |
|------|---------|
| **Core Configuration** | |
| `docker-compose.yml` | Service orchestration with profiles (`full`, `demo`, `dev`, `observability`) |
| `Makefile` | Developer CLI — 23 targets wrapping Docker Compose commands |
| `.env.example` | All configurable environment variables (copy to `.env`) |
| `.env.demo` | Demo profile environment overrides |
| `.env.observability` | Observability profile overrides (auto-enables metrics) |
| `pyproject.toml` | Pytest configuration (test paths, markers, pythonpath) |
| `requirements-test.txt` | Test dependencies (requests, pytest) |
| `.pre-commit-config.yaml` | Pre-commit hooks (YAML, shell, markdown, Python, Docker Compose) |
| **Scripts** | |
| `scripts/health_check.sh` | Health report formatter — queries `/v1/health/ready` with colored output |
| `scripts/wait_for_services.sh` | Polls health endpoints until ready (default 90s timeout) |
| `scripts/test_demo_profile.sh` | Demo profile integration test (7-step validation) |
| `scripts/test_health_enhanced.sh` | Enhanced health check validation (8-step schema checks) |
| **Tests** | |
| `tests/conftest.py` | Shared fixtures (configurable via `JUNIPER_TEST_*` env vars) |
| `tests/constants.py` | Shared test constants (`DEFAULT_TIMEOUT = 10`) |
| `tests/test_health.py` | Health endpoint + schema validation tests |
| `tests/test_data_service.py` | Dataset lifecycle integration tests |
| `tests/test_full_stack.py` | Cross-service end-to-end tests |
| `tests/test_availability.py` | Availability checking fixtures and skip logic |
| `tests/test_compose_security_config.py` | Docker security regression tests (secrets, networks, hardening) |
| **Observability Infrastructure** | |
| `prometheus/prometheus.yml` | Prometheus scrape configuration (3 services + self) |
| `prometheus/alert_rules.yml` | Prometheus alert rules |
| `prometheus/recording_rules.yml` | Prometheus recording rules |
| `grafana/provisioning/dashboards/` | 4 auto-provisioned Grafana dashboards (overview, data, cascor, canopy) |
| `grafana/provisioning/datasources/prometheus.yml` | Grafana datasource (Prometheus, stable UID) |
| `alertmanager/alertmanager.yml` | AlertManager alert routing configuration |
| **Secrets** | |
| `secrets/` | Docker secret files (git-ignored, created by `make prepare-secrets`) |
| `secrets.example/` | Secret file templates (copy to `secrets/`) |
| **Documentation** | |
| `README.md` | Quickstart, profiles, service discovery |
| `CHANGELOG.md` | Release history (Keep a Changelog format) |
| `docs/` | 8 documentation files (see Documentation section) |
| **CI/CD** | |
| `.github/workflows/ci.yml` | GitHub Actions pipeline (pre-commit, compose validation, Docker integration) |
| `.github/workflows/sequence-safety.yml` | Per-PR ADVISORY sequence-safety screens (symbol-loss + docs deletion-magnitude via `juniper-ci-tools`) |
| `.github/workflows/main-verify.yml` | Post-merge bypass-proof sequence-safety net (screens-only; stable-title tracking issue) |
| `.github/CODEOWNERS` | Code ownership rules |
| `.github/dependabot.yml` | Dependabot configuration |

---

## Project Overview

`juniper-deploy` orchestrates the full Juniper stack via Docker Compose. It manages service dependencies, health checks, environment variable wiring, security hardening, and observability infrastructure for the Juniper platform.

### Docker Compose Profiles

| Service | full | demo | dev | observability |
|---------|:----:|:----:|:---:|:-------------:|
| juniper-data | x | x | x | |
| juniper-cascor | x | | x | |
| juniper-cascor-demo | | x | | |
| demo-seed (init container) | | x | | |
| juniper-canopy | x | | | |
| juniper-canopy-demo | | x | | |
| juniper-canopy-dev | | | x | |
| redis | x | | | |
| prometheus | | | | x |
| alertmanager | | | | x |
| grafana | | | | x |

**Profile descriptions:**

- **full** — All real services with Redis (production-like)
- **demo** — Auto-configured CasCor training with seeded dataset
- **dev** — Real data + cascor services, canopy in demo mode (frontend development)
- **observability** — Add-on profile: Prometheus, AlertManager, Grafana (combine with `full` or `demo`)

> **Note**: Demo variants (`juniper-canopy-demo`, `juniper-cascor-demo`) are designed for local demonstration only. They do not include Docker secrets for API keys, rate limiting configuration, or observability environment variables. Do not use demo variants for production or security-sensitive deployments.

### Service Dependency Graph

```text
# Full profile
juniper-canopy (8050)
  ├── depends_on: juniper-cascor (healthy)
  ├── depends_on: juniper-data (healthy)
  └── depends_on: redis (healthy)

juniper-cascor (8200)
  └── depends_on: juniper-data (healthy)

juniper-data (8100)
  └── no dependencies

redis (6379)
  └── no dependencies

# Demo profile
juniper-canopy-demo (8050)
  ├── depends_on: juniper-cascor-demo (healthy)
  └── depends_on: juniper-data (healthy)

juniper-cascor-demo (8200)
  ├── depends_on: juniper-data (healthy)
  └── depends_on: demo-seed (completed_successfully)

demo-seed (init container)
  └── depends_on: juniper-data (healthy)

# Dev profile
juniper-canopy-dev (8050)
  └── depends_on: juniper-data (healthy)

juniper-cascor (8200)
  └── depends_on: juniper-data (healthy)

# Observability (add-on)
grafana (3000)
  └── depends_on: prometheus (healthy)

prometheus (9090)
  └── depends_on: alertmanager (healthy)

alertmanager (9093)
  └── no dependencies
```

---

## Directory Layout

```text
juniper-deploy/
├── docker-compose.yml              # Service orchestration (12 services, 4 profiles)
├── Makefile                        # Developer CLI (23 targets)
├── .env.example                    # Environment variable template
├── .env.demo                       # Demo profile overrides
├── .env.observability              # Observability profile overrides
├── AGENTS.md                       # Agent instructions (this file)
├── CLAUDE.md                       # Symlink → AGENTS.md
├── CHANGELOG.md                    # Release history
├── README.md                       # Quickstart guide
├── pyproject.toml                  # Pytest configuration
├── requirements-test.txt           # Test dependencies
├── .pre-commit-config.yaml         # Pre-commit hooks
├── .gitignore                      # Git ignore rules
│
├── scripts/
│   ├── health_check.sh             # Health report formatter
│   ├── wait_for_services.sh        # Service readiness poller
│   ├── test_demo_profile.sh        # Demo profile integration test
│   └── test_health_enhanced.sh     # Enhanced health check validation
│
├── tests/
│   ├── __init__.py
│   ├── conftest.py                 # Shared fixtures (JUNIPER_TEST_* env vars)
│   ├── constants.py                # Shared constants (DEFAULT_TIMEOUT)
│   ├── test_health.py              # Health endpoint tests (3 services)
│   ├── test_data_service.py        # Dataset lifecycle tests
│   ├── test_full_stack.py          # Cross-service integration tests
│   ├── test_availability.py        # Availability checking fixtures
│   └── test_compose_security_config.py  # Docker security regression tests
│
├── docs/
│   ├── DOCUMENTATION_OVERVIEW.md   # Navigation index
│   ├── QUICK_START.md              # 5-minute quickstart
│   ├── ENVIRONMENT_SETUP.md        # Complete env var setup guide
│   ├── USER_MANUAL.md              # Profiles, monitoring, security
│   ├── DEVELOPER_CHEATSHEET.md     # Common commands reference
│   ├── OBSERVABILITY_GUIDE.md      # Prometheus/Grafana documentation
│   ├── REFERENCE.md                # Technical reference
│   └── testing/
│       └── TESTING_QUICK_START.md  # Integration test guide
│
├── notes/                          # Development notes and procedures
│   ├── WORKTREE_SETUP_PROCEDURE.md
│   ├── WORKTREE_CLEANUP_PROCEDURE_V2.md
│   ├── THREAD_HANDOFF_PROCEDURE.md
│   ├── FIX_FAILING_TESTS_PLAN.md
│   ├── CONTAINER_VALIDATION_CI_PLAN.md
│   ├── JUNIPER-DEPLOY_POST-RELEASE_DEVELOPMENT-ROADMAP.md
│   ├── history/                    # Archived/completed plans
│   └── pull_requests/              # PR description archives
│
├── prometheus/
│   ├── prometheus.yml              # Scrape configuration
│   ├── alert_rules.yml             # Alert rules
│   └── recording_rules.yml         # Recording rules
│
├── grafana/
│   └── provisioning/
│       ├── dashboards/
│       │   ├── dashboard-providers.yml
│       │   ├── juniper-overview.json
│       │   ├── juniper-data.json
│       │   ├── juniper-cascor.json
│       │   └── juniper-canopy.json
│       └── datasources/
│           └── prometheus.yml
│
├── alertmanager/
│   └── alertmanager.yml            # Alert routing configuration
│
├── secrets/                        # Docker secret files (git-ignored)
│   ├── juniper_data_api_keys.txt
│   ├── juniper_cascor_api_keys.txt
│   ├── cascor_auth_token.txt
│   ├── canopy_api_key.txt
│   └── grafana_admin_password.txt
│
├── secrets.example/                # Secret file templates
│   ├── juniper_data_api_keys.txt
│   ├── juniper_cascor_api_keys.txt
│   ├── cascor_auth_token.txt
│   ├── canopy_api_key.txt
│   └── grafana_admin_password.txt
│
└── .github/
    ├── workflows/
    │   ├── ci.yml                  # CI/CD pipeline (v0.2.0)
    │   ├── sequence-safety.yml     # Per-PR ADVISORY sequence-safety screens
    │   └── main-verify.yml         # Post-merge bypass-proof sequence-safety net
    ├── CODEOWNERS
    └── dependabot.yml
```

---

## Script Placement

**Permanent utilities** live in `util/`. **Single-use / temporary / unfinished scripts** go in `util/ad-hoc/` (create on first use). See [`util/ad-hoc/README.md`](util/ad-hoc/README.md) for the per-script header / lifecycle conventions.

`/tmp/` is **prohibited** as the home for any script that produces, modifies, or analyzes repository content. `/tmp/` is reaped when sessions / sandboxes / containers end, and scripts placed there are lost (irrecoverable). `/tmp/` remains fine as a scratch *workspace* for intermediate artifacts the script itself creates and reads — the prohibition is on script *source files*.

This is an ecosystem-wide rule restated in the parent `Juniper/AGENTS.md` "Cross-Project Conventions" section. Motivating incident: irrecoverable loss of `phase4_consolidate.py` and `v2_citation_validate.py` from the juniper-ml requirements-snapshot effort.

---

## Ecosystem Context

Part of the Juniper ecosystem. See the parent directory's `CLAUDE.md` at `/home/pcalnon/Development/python/Juniper/CLAUDE.md` for the full project map, dependency graph, shared conventions, and conda environment details.

---

## Environment Variables

All values use `${VAR:-default}` substitution in `docker-compose.yml`. Copy `.env.example` to `.env` to override.

### Core Service Configuration

| Variable | Service | Default | Notes |
|----------|---------|---------|-------|
| `JUNIPER_DATA_HOST` | juniper-data | `0.0.0.0` | |
| `JUNIPER_DATA_PORT` | juniper-data | `8100` | |
| `JUNIPER_DATA_LOG_LEVEL` | juniper-data | `INFO` | |
| `CASCOR_HOST` | juniper-cascor | `0.0.0.0` | Maps to `JUNIPER_CASCOR_HOST` in container |
| `CASCOR_PORT` | juniper-cascor | `8200` | Internal container port; maps to `JUNIPER_CASCOR_PORT` |
| `CASCOR_HOST_PORT` | juniper-cascor | `8201` | Host-exposed port (avoids port 8200 conflicts) |
| `CASCOR_LOG_LEVEL` | juniper-cascor | `INFO` | Maps to `JUNIPER_CASCOR_LOG_LEVEL` in container |
| `CANOPY_HOST` | juniper-canopy | `0.0.0.0` | |
| `CANOPY_PORT` | juniper-canopy | `8050` | |

### Inter-Service URLs

| Variable | Service | Default |
|----------|---------|---------|
| `JUNIPER_DATA_URL` | juniper-cascor, juniper-canopy | `http://juniper-data:8100` |
| `CASCOR_SERVICE_URL` | juniper-canopy | `http://juniper-cascor:8200` |

### API Security

| Variable | Service | Default | Notes |
|----------|---------|---------|-------|
| `JUNIPER_DATA_API_KEYS` | juniper-data | *(unset — auth disabled)* | |
| `JUNIPER_CASCOR_API_KEYS` | juniper-cascor | *(unset — auth disabled)* | |
| `CANOPY_API_KEY` | juniper-canopy | *(unset — auth disabled)* | Via Docker secret |
| `JUNIPER_CASCOR_RATE_LIMIT_ENABLED` | juniper-cascor | `true` | |
| `JUNIPER_CASCOR_RATE_LIMIT_REQUESTS_PER_MINUTE` | juniper-cascor | `60` | |
| `CANOPY_RATE_LIMIT_ENABLED` | juniper-canopy | `true` | Maps to `JUNIPER_CANOPY_RATE_LIMIT_ENABLED` |
| `CANOPY_RATE_LIMIT_REQUESTS_PER_MINUTE` | juniper-canopy | `60` | Maps to `JUNIPER_CANOPY_RATE_LIMIT_REQUESTS_PER_MINUTE` |
| `JUNIPER_DATA_API_KEY` | juniper-cascor | *(from `JUNIPER_DATA_API_KEYS`)* | CasCor's credential for JuniperData |
| `JUNIPER_CASCOR_API_KEY` | juniper-canopy | *(from `JUNIPER_CASCOR_API_KEYS`)* | Canopy's credential for CasCor |

### Observability

| Variable | Service | Default |
|----------|---------|---------|
| `JUNIPER_DATA_LOG_FORMAT` | juniper-data | `text` |
| `JUNIPER_DATA_SENTRY_DSN` | juniper-data | *(unset)* |
| `JUNIPER_DATA_METRICS_ENABLED` | juniper-data | `false` |
| `JUNIPER_CASCOR_LOG_FORMAT` | juniper-cascor | `text` |
| `JUNIPER_CASCOR_SENTRY_DSN` | juniper-cascor | *(unset)* |
| `JUNIPER_CASCOR_METRICS_ENABLED` | juniper-cascor | `false` |
| `CANOPY_LOG_FORMAT` | juniper-canopy | `text` |
| `CANOPY_SENTRY_DSN` | juniper-canopy | *(unset)* |
| `CANOPY_METRICS_ENABLED` | juniper-canopy | `false` |

> **Tip**: Use `.env.observability` to auto-enable metrics when running with the observability profile. See `make monitor`.

### Grafana

| Variable | Service | Default | Notes |
|----------|---------|---------|-------|
| `GRAFANA_ADMIN_USER` | grafana | `admin` | |
| `GF_SECURITY_ADMIN_PASSWORD__FILE` | grafana | `/run/secrets/grafana_admin_password` | **Docker secret only** — no env var fallback. Set password in `secrets/grafana_admin_password.txt` |

### Demo Profile

| Variable | Service | Default |
|----------|---------|---------|
| `JUNIPER_CANOPY_DEMO_MODE` | juniper-canopy-dev | `true` |
| `JUNIPER_CASCOR_AUTO_START` | juniper-cascor-demo | `true` |
| `JUNIPER_CASCOR_AUTO_DATASET` | juniper-cascor-demo | `spiral` |
| `JUNIPER_CASCOR_AUTO_DATASET_PARAMS` | juniper-cascor-demo | JSON params |
| `JUNIPER_CASCOR_AUTO_NETWORK` | juniper-cascor-demo | JSON config |
| `JUNIPER_CASCOR_AUTO_TRAIN_EPOCHS` | juniper-cascor-demo | `500` |

### Infrastructure Services

| Variable | Service | Default | Notes |
|----------|---------|---------|-------|
| `REDIS_PORT` | redis | `6379` | |
| `REDIS_MAX_MEMORY` | redis | `100mb` | |
| `WORKER_REPLICAS` | juniper-cascor-worker | `2` | Number of worker replicas in the deployment |

### Healthcheck Tuning

All container healthchecks reference shared YAML anchors (`x-healthcheck-defaults`, `x-healthcheck-cascor`, `x-healthcheck-canopy`, `x-healthcheck-worker`, `x-healthcheck-redis`) merged into each service via `<<: *anchor`. The interval/timeout/retries/start_period values can be overridden via environment variables:

| Variable | Default | Notes |
|----------|---------|-------|
| `HEALTHCHECK_INTERVAL` | `30s` | Default interval used by `x-healthcheck-defaults` and most services |
| `HEALTHCHECK_TIMEOUT` | `10s` | Default timeout |
| `HEALTHCHECK_RETRIES` | `3` | Default retry count |
| `HEALTHCHECK_START_PERIOD` | `30s` | Default startup grace period |
| `CASCOR_HEALTHCHECK_*` | (per-service) | Cascor-specific overrides via `x-healthcheck-cascor` |
| `CANOPY_HEALTHCHECK_*` | (per-service) | Canopy-specific overrides via `x-healthcheck-canopy` |
| `WORKER_HEALTHCHECK_*` | (per-service) | Worker-specific overrides via `x-healthcheck-worker` |
| `REDIS_HEALTHCHECK_*` | (per-service) | Redis-specific overrides via `x-healthcheck-redis` |

### Docker Secret File Variables

These environment variables point containers to their mounted Docker secret files. They are set automatically in `docker-compose.yml` and should not need manual configuration.

| Variable | Service | Value |
|----------|---------|-------|
| `JUNIPER_DATA_API_KEYS_FILE` | juniper-data | `/run/secrets/juniper_data_api_keys` |
| `JUNIPER_CASCOR_API_KEYS_FILE` | juniper-cascor | `/run/secrets/juniper_cascor_api_keys` |
| `JUNIPER_DATA_API_KEY_FILE` | juniper-cascor | `/run/secrets/juniper_data_api_keys` |
| `CANOPY_API_KEY_FILE` | juniper-canopy | `/run/secrets/canopy_api_key` |
| `JUNIPER_CASCOR_API_KEY_FILE` | juniper-canopy | `/run/secrets/juniper_cascor_api_keys` |
| `CASCOR_AUTH_TOKEN_FILE` | juniper-cascor-worker | `/run/secrets/cascor_auth_token` |

---

## Security Architecture

### Network Isolation

Four Docker networks enforce service-to-service communication boundaries:

| Network | Type | Purpose | Services |
|---------|------|---------|----------|
| `frontend` | bridge | Public-facing dashboard | juniper-canopy, juniper-canopy-demo, juniper-canopy-dev |
| `backend` | **internal** | CasCor + infrastructure (no external access) | juniper-cascor, redis, prometheus |
| `data` | **internal** | JuniperData access (no external access) | juniper-data, juniper-cascor, juniper-canopy, prometheus |
| `monitoring` | bridge | Observability stack | prometheus, grafana |

Networks marked **internal** have no external connectivity — containers on these networks can only communicate with other containers on the same network.

### Container Hardening

All Juniper application containers (juniper-data, juniper-cascor, juniper-canopy variants) have:

- `security_opt: no-new-privileges:true` — prevents privilege escalation
- `cap_drop: ALL` — drops all Linux capabilities

### Port Binding Restrictions

Internal and infrastructure services bind to `127.0.0.1` (localhost only):

- `juniper-data` → `127.0.0.1:8100`
- `prometheus` → `127.0.0.1:9090`
- `alertmanager` → `127.0.0.1:9093`
- `grafana` → `127.0.0.1:3000`

Note: Redis has no host port binding and is only accessible from within the Docker network.

External-facing services (cascor host port, canopy) bind to `0.0.0.0` by default.

### Docker Secrets

API keys and the Grafana admin password are managed via Docker secrets (mounted as files at `/run/secrets/`):

| Secret | File | Used By |
|--------|------|---------|
| `juniper_data_api_keys` | `secrets/juniper_data_api_keys.txt` | juniper-data, juniper-cascor |
| `juniper_cascor_api_keys` | `secrets/juniper_cascor_api_keys.txt` | juniper-cascor, juniper-canopy |
| `cascor_auth_token` | `secrets/cascor_auth_token.txt` | juniper-cascor-worker |
| `canopy_api_key` | `secrets/canopy_api_key.txt` | juniper-canopy |
| `grafana_admin_password` | `secrets/grafana_admin_password.txt` | grafana |

Run `make prepare-secrets` to create placeholder secret files. See `secrets.example/` for templates.

### Pinned Third-Party Images

| Image | Version | Service |
|-------|---------|---------|
| `prom/prometheus` | v3.10.0 | prometheus |
| `prom/alertmanager` | v0.28.1 | alertmanager |
| `grafana/grafana` | 12.4.0 | grafana |
| `redis` | 7.4-alpine | redis |

---

## CI/CD Pipeline

GitHub Actions workflow (`.github/workflows/ci.yml`, v0.2.0):

**Triggers**: push to `main`, `develop`, `feature/**`, `fix/**`; pull requests; manual dispatch

**Jobs**:

| Job | Purpose | Dependencies |
|-----|---------|-------------|
| `pre-commit` | YAML, shell, markdown, Python validation | — |
| `validate-compose` | Compose config validation (full, demo, dev profiles) | pre-commit |
| `docker-integration` | Build dev profile, start services, verify health endpoints (15min timeout) | validate-compose |
| `required-checks` | Quality gate enforcement (all jobs must pass) | all |

**Notes**:

- Multi-repo checkout: CI checks out `juniper-data`, `juniper-cascor`, and `juniper-canopy` as sibling directories (required for `docker compose build`)
- All GitHub Actions are SHA-pinned (checkout@v6.0.2, setup-python@v6.2.0, cache@v5.0.4)
- `docker-compose-check` pre-commit hook is skipped in CI (handled by dedicated `validate-compose` job)

### Sequence-Safety Advisory Net (rollout W2, 2026-08-08)

Two **advisory** workflows port the ecosystem sequence-safety screens (the 2026-07-28 Cursor-PR-flood remediation) into juniper-deploy as the final consumer of the rollout (8th of 8 repos). Both consume the published `juniper-ci-tools>=0.8.0,<0.9.0` package — no inline copy lives in this repo.

| Workflow | Trigger | Role |
|----------|---------|------|
| `.github/workflows/sequence-safety.yml` | `pull_request` | Per-PR AST symbol-loss + docs deletion-magnitude screens over the PR's `base..HEAD`; uploads a `sequence-safety-report` JSON artifact. |
| `.github/workflows/main-verify.yml` | `push: main` | Post-merge, bypass-proof re-screen of the merged range (per-SHA, no-cancel; catch-up base); upserts a stable-title tracking issue on failure. |

**Scope (owner decision, option b):** the symbol screen is scoped to `tests/**/*.py` (the security-wiring tests) and `scripts/**/*.bash` (operational bash); the docs deletion-magnitude screen uses the universal default (`AGENTS.md` + `docs/**/*.md` + `notes/**/*.md`).

**Advisory only:** neither workflow is wired into the `required-checks` quality gate, and this rollout makes **no** branch-ruleset change. The escape hatches are the `Allow-Symbol-Loss:` / `Allow-Docs-Rewrite:` commit trailers (primary) and the `allow-symbol-loss` / `docs-rewrite` PR labels (WARN-only downgrade).

---

### PR base-branch guard (required check)

`.github/workflows/pr-base-branch-guard.yml` fails any PR whose base branch is not the
default branch. Its job name -- **`Guard PR base branch`** -- is a **required status check**
in this repo's ruleset, so renaming the job or deleting the file makes `main` unmergeable
until the context is un-required first.

**What it protects against.** A PR based on another feature branch can squash-merge into
that branch, stranding its content off `main` behind a green **MERGED** badge. It has
happened three times in this ecosystem (`juniper-recurrence#7`/`#8`, `juniper-canopy#365`).

**Why it matters more than it looks.** Both rulesets here are scoped to `~DEFAULT_BRANCH`, so
a PR whose base is a feature branch is governed by **no ruleset at all** -- it has zero
required status checks and merges clean with nothing having run:

```bash
gh api repos/pcalnon/<repo>/rules/branches/feature%2Fanything --jq length   # -> 0
gh api repos/pcalnon/<repo>/rules/branches/main               --jq length   # -> 9
```

This workflow carries no `branches:` filter, so it is the **only** check that runs on such a
PR. It cannot block the merge there -- no ruleset applies -- but it turns a silent merge into
a visibly red one.

**If it fails.** Re-open the work against the default branch. The house practice is
**close and re-open** a fresh PR titled `[retarget #NNN]`. Retargeting in place is *not*
sufficient on its own: every `ci*.yml` here uses the default `pull_request` types
`[opened, synchronize, reopened]`, which exclude `edited`, so a retarget re-runs this guard
and nothing else -- the PR stays blocked on its other required contexts until a push or a
close/re-open.

**`stacked-pr` label.** Silences this guard for a deliberate stack. It does **not** make the
PR mergeable into `main`, and it does **not** re-land the stack -- do that separately.

Rollout and rationale: [juniper-ml#434](https://github.com/pcalnon/juniper-ml/issues/434).

## Testing

### Python Integration Tests

```bash
pip install -r requirements-test.txt
make up                              # or make demo / make dev
bash scripts/wait_for_services.sh    # Wait for services to be healthy
pytest tests/ -v                     # Run all tests
pytest tests/ -v -m health           # Health endpoint tests only
pytest tests/ -v -m data             # Dataset tests only
pytest tests/ -v -m full_stack       # Cross-service tests only
```

**Test files**:

| File | Markers | Tests |
|------|---------|-------|
| `test_health.py` | `health` | Liveness, readiness, schema, content-type for all 3 services |
| `test_data_service.py` | `data` | Generators, dataset lifecycle (create, read, download, delete), stats |
| `test_full_stack.py` | `full_stack` | CasCor-Data integration, Canopy dashboard, 3-service pipeline |
| `test_availability.py` | — | Skip mechanism validation, fixture scope checks |
| `test_compose_security_config.py` | — | Docker secret wiring, network isolation, Grafana secret-only password |

**Configurable service URLs** (via environment variables):

| Variable | Default |
|----------|---------|
| `JUNIPER_TEST_DATA_URL` | `http://localhost:8100` |
| `JUNIPER_TEST_CASCOR_URL` | `http://localhost:8201` |
| `JUNIPER_TEST_CANOPY_URL` | `http://localhost:8050` |
| `JUNIPER_TEST_DATA_API_KEY` | *(unset)* |
| `JUNIPER_TEST_CASCOR_API_KEY` | *(unset)* |
| `JUNIPER_TEST_CANOPY_API_KEY` | *(unset)* |

### Shell Script Tests

| Script | Purpose |
|--------|---------|
| `scripts/test_demo_profile.sh` | 7-step demo profile validation (config, start, wait, seed check, training, canopy, shutdown) |
| `scripts/test_health_enhanced.sh` | 8-step health check validation (config, start, liveness, readiness, schema, dependencies, Docker healthcheck) |

---

## Documentation

| Document | Purpose |
|----------|---------|
| `docs/DOCUMENTATION_OVERVIEW.md` | Navigation index — start here |
| `docs/QUICK_START.md` | Start the Juniper stack in 5 minutes |
| `docs/ENVIRONMENT_SETUP.md` | Complete environment configuration guide |
| `docs/USER_MANUAL.md` | Profiles, monitoring, security, logging, scripts |
| `docs/DEVELOPER_CHEATSHEET.md` | Common commands quick-reference |
| `docs/OBSERVABILITY_GUIDE.md` | Prometheus, Grafana, AlertManager, Sentry documentation |
| `docs/REFERENCE.md` | Technical reference (services, env vars, networks, healthchecks) |
| `docs/testing/TESTING_QUICK_START.md` | Integration test guide |

---

## Worktree Procedures (Mandatory — Task Isolation)

> **OPERATING INSTRUCTION**: All feature, bugfix, and task work SHOULD use git worktrees for isolation. Worktrees keep the main working directory on the default branch while task work proceeds in a separate checkout.

### What This Is

Git worktrees allow multiple branches of a repository to be checked out simultaneously in separate directories. For the Juniper ecosystem, all worktrees are centralized in **`/home/pcalnon/Development/python/Juniper/worktrees/`** using a standardized naming convention.

The full setup and cleanup procedures are defined in:

- **`notes/WORKTREE_SETUP_PROCEDURE.md`** — Creating a worktree for a new task
- **`notes/WORKTREE_CLEANUP_PROCEDURE_V2.md`** — Merging, removing, and pushing after task completion (V2 — fixes CWD-trap bug)

Read the appropriate file when starting or completing a task.

### Worktree Directory Naming

Format: `<repo-name>--<branch-name>--<YYYYMMDD-HHMM>--<short-hash>`

Example: `juniper-deploy--feature--add-monitoring--20260225-1430--50700461`

- Slashes in branch names are replaced with `--`
- All worktrees reside in `/home/pcalnon/Development/python/Juniper/worktrees/`

### When to Use Worktrees

| Scenario | Use Worktree? |
| -------- | ------------- |
| Feature development (new feature branch) | **Yes** |
| Bug fix requiring a dedicated branch | **Yes** |
| Quick single-file documentation fix on main | No |
| Exploratory work that may be discarded | **Yes** |
| Hotfix requiring immediate merge | **Yes** |

### Quick Reference

**Setup** (full procedure in `notes/WORKTREE_SETUP_PROCEDURE.md`):

```bash
cd /home/pcalnon/Development/python/Juniper/juniper-deploy
git fetch origin && git checkout main && git pull origin main
BRANCH_NAME="feature/my-task"
git branch "$BRANCH_NAME" main
REPO_NAME=$(basename "$(pwd)")
SAFE_BRANCH=$(echo "$BRANCH_NAME" | sed 's|/|--|g')
WORKTREE_DIR="/home/pcalnon/Development/python/Juniper/worktrees/${REPO_NAME}--${SAFE_BRANCH}--$(date +%Y%m%d-%H%M)--$(git rev-parse --short=8 HEAD)"
git worktree add "$WORKTREE_DIR" "$BRANCH_NAME"
cd "$WORKTREE_DIR"
```

**Cleanup** (full procedure in `notes/WORKTREE_CLEANUP_PROCEDURE_V2.md`):

```bash
# Phase 1: Push current work
cd "$OLD_WORKTREE_DIR" && git push origin "$OLD_BRANCH"
# Phase 2: Create new worktree BEFORE removing old (prevents CWD-trap)
git fetch origin
git worktree add "$NEW_WORKTREE_DIR" -b "$NEW_BRANCH" origin/main
cd "$NEW_WORKTREE_DIR"
# Phase 3: Create PR (do NOT merge directly to main)
gh pr create --base main --head "$OLD_BRANCH" --title "<title>" --body "<body>"
# Phase 4: Cleanup
git worktree remove "$OLD_WORKTREE_DIR"
git branch -d "$OLD_BRANCH"
git worktree prune
```

### Rules

- **Centralized location**: All worktrees go in `/home/pcalnon/Development/python/Juniper/worktrees/`. Never create worktrees inside the repo directory.
- **Clean before you start**: Ensure the main working directory is clean before creating a worktree.
- **Push before you merge**: Always push the working branch to remote before merging (backup).
- **Prune after cleanup**: Run `git worktree prune` after removing a worktree to clean metadata.
- **Do not leave stale worktrees**: Clean up worktrees promptly after merging.

---

## Thread Handoff (Mandatory — Replaces Thread Compaction)

> **CRITICAL OPERATING INSTRUCTION**: Thread handoff MUST be performed instead of thread compaction. This section defines mandatory behavior that overrides Claude Code's default compaction process.

### What This Is

When a long-running conversation approaches context limits, Claude Code normally performs **thread compaction** — summarizing prior context to free token capacity. This introduces information loss. Instead, Claude Code instances working on this project MUST perform a **proactive thread handoff**: transferring a curated, high-signal summary to a fresh thread with full context capacity.

The full handoff protocol is defined in **`notes/THREAD_HANDOFF_PROCEDURE.md`**. Read that file when a handoff is triggered.

### When to Trigger a Handoff

**Automatic trigger (pre-compaction threshold):** Initiate a thread handoff when token utilization reaches **95% to 99%** of the level at which thread compaction would normally be triggered.

**Additional triggers**:

| Condition | Indicator |
| --------- | --------- |
| **Context saturation** | Thread has performed 15+ tool calls or edited 5+ files |
| **Phase boundary** | A logical phase of work is complete |
| **Degraded recall** | Re-reading a file already read, or re-asking a resolved question |
| **Multi-module transition** | Moving between major components |
| **User request** | User says "hand off", "new thread", or similar |

**Do NOT handoff** when:

- The task is nearly complete (< 2 remaining steps)
- The current thread is still sharp and producing correct output
- The work is tightly coupled and splitting would lose critical in-flight state

### How to Execute a Handoff

1. **Checkpoint**: Inventory what was done, what remains, what was discovered, and what files are in play
2. **Compose the handoff goal**: Write a concise, actionable summary (see templates in `notes/THREAD_HANDOFF_PROCEDURE.md`)
3. **Present to user**: Output the handoff goal to the user and recommend starting a new thread with that goal as the initial prompt
4. **Include verification commands**: Always specify how the new thread should verify its starting state
5. **State git status**: Mention branch, staged files, and any uncommitted work

### Rules

- **This is not optional.** Every Claude Code instance on this project must follow these rules.
- **Handoff early, not late.** A handoff at 70% context usage is better than compaction at 95%.
- **Do not duplicate CLAUDE.md content** in the handoff goal — the new thread reads CLAUDE.md automatically.
- **Be specific** in the handoff goal: include file paths, decisions made, and test status.
