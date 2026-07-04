<!-- markdownlint-disable MD013 MD033 MD041 -->
<!--
  MD013 (line-length): operator-runbook prose intentionally exceeds the 512-char
                       ecosystem limit; wrapping mid-sentence harms rendering.
  MD033/MD041: the markdownlint-disable comment precedes the H1 by design.
-->

# juniper-deploy

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](#license)
[![Docker Compose](https://img.shields.io/badge/Docker_Compose-stack-2496ED?logo=docker)](https://docs.docker.com/compose/)

**One-command Docker-Compose orchestration for the full Juniper stack.**

> **Part of the Juniper platform.** juniper-deploy is the Docker-Compose orchestration for [Juniper](https://github.com/pcalnon/juniper-ml) — a multi-package ML research platform built around constructive (Cascade-Correlation) and recurrent neural networks. It assembles the platform's services into a runnable stack.

`juniper-deploy` is the **Docker Compose orchestration repository** for the full Juniper stack. It manages service dependency ordering, health-gated startup, environment-variable wiring, Docker-secret distribution, network isolation, container hardening, and the observability stack (Prometheus, AlertManager, Grafana) across five Docker Compose profiles — `full`, `demo`, `dev`, `test`, and the additive `observability` profile. The repository is consumed directly via `git clone`; it is not distributed as a Python package, and it does not own service code. Operators interact with it through a 23-target Makefile that wraps Docker Compose; integration tests run either inside a `test-runner` container or against a started stack from the host.

> **⚠️ Before deploying anywhere reachable from a network**
>
> The `secrets.example/` directory ships placeholder files whose contents
> are the literal string `CHANGE_BEFORE_PRODUCTION_USE`. The Docker
> Compose `secrets:` block falls back to these placeholders when their
> real counterparts in `secrets/` are absent, so the stack will boot
> out-of-the-box for local experimentation — but the following files
> **must** be populated with real values before exposing the stack
> beyond `127.0.0.1`:
>
> - `secrets/juniper_data_api_keys.txt`
> - `secrets/juniper_cascor_api_keys.txt` (and `juniper_cascor_api_key.txt`)
> - `secrets/canopy_api_key.txt`
> - `secrets/cascor_auth_token.txt`
> - `secrets/cascor_sentry_dsn.txt` (only if Sentry is enabled)
> - `secrets/grafana_admin_password.txt` (only if running the
>   `observability` profile)
> - `secrets/alertmanager_smtp_password.txt` (only if alert email
>   delivery is enabled)
>
> Run `make prepare-secrets` to scaffold the directory, then see
> [`docs/SECRETS_ONBOARDING.md`](docs/SECRETS_ONBOARDING.md) for the
> SOPS-encrypted-canonical-copy workflow. Default `BIND_HOST=127.0.0.1`
> keeps published ports loopback-only until you opt in via `.env`.

## Architecture

`juniper-deploy` orchestrates the Juniper platform across five Docker Compose profiles (`full`, `demo`, `dev`, `test`, and the additive `observability`). The diagram below shows the core runtime dependency spine of the production-like `full` profile, plus the additive `observability` profile.

```text
        ┌─────────────────────────────────────────────────────┐
        │                  observability (add-on)             │
        │                                                     │
        │   alertmanager (9093) ◀── prometheus (9090)         │
        │                                  │                  │
        │                                  ▼                  │
        │                            grafana (3000)           │
        └─────────────────────────────────────────────────────┘
                                  ▲ scrape
                                  │
        ┌─────────────────────────┴───────────────────────────┐
        │                       full                          │
        │                                                     │
        │   juniper-canopy (8050) ──▶ juniper-cascor (8201)   │
        │            │                       │                │
        │            │                       ▼                │
        │            └────────────▶ juniper-data (8100)       │
        │                                                     │
        │                            redis (6379)             │
        └─────────────────────────────────────────────────────┘
```

Beyond the spine shown, the `full` profile also starts **`juniper-cascor-worker`** (which connects outbound to `juniper-cascor` over the `/ws/v1/workers` protocol to parallelise candidate-unit training) and **`juniper-recurrence`** (the Δt-native LMU model service on `8211`, monitored by `juniper-canopy` alongside `juniper-cascor`).

The `demo`, `dev`, and `test` profiles substitute service variants — `juniper-cascor-demo` and `juniper-canopy-demo` for `demo`, `juniper-canopy-dev` for `dev` — but preserve the dependency shape: every variant of canopy depends on a healthy data service, and every variant of cascor depends on a healthy data service. Published Juniper service ports use `${BIND_HOST:-127.0.0.1}` and therefore bind to loopback by default; setting `BIND_HOST=0.0.0.0` is supported only behind a fronting authenticating proxy. Four Docker networks (`frontend`, `backend` — internal, `data` — internal, `monitoring`) enforce service-to-service communication boundaries.

## Related Services

| Component | Relationship | Notes |
|-----------|-------------|-------|
| [juniper-data](https://github.com/pcalnon/juniper-data) | Orchestrated service — dataset generation REST API on `127.0.0.1:8100` | Profiles: `full`, `demo`, `dev`, `test` |
| [juniper-cascor](https://github.com/pcalnon/juniper-cascor) | Orchestrated service — CasCor training service on `0.0.0.0:8201` | Profiles: `full`, `dev`, `test`; `demo` uses `juniper-cascor-demo` variant |
| [juniper-canopy](https://github.com/pcalnon/juniper-canopy) | Orchestrated service — real-time monitoring dashboard on `0.0.0.0:8050` | Profiles: `full`, `test`; `demo` uses `juniper-canopy-demo`; `dev` uses `juniper-canopy-dev` |
| [juniper-cascor-worker](https://github.com/pcalnon/juniper-cascor-worker) | Orchestrated service — distributed candidate-training worker (`WORKER_REPLICAS=2` by default) | Mounted into the cascor backend network |
| [juniper-ml](https://github.com/pcalnon/juniper-ml) | Platform meta-package on PyPI — `pip install juniper-ml[all]` for standalone client work against the running stack | The repository's `clients` extra resolves `juniper-data-client` + `juniper-cascor-client` against the same compatibility row as this orchestration |

## Service Configuration

All values use `${VAR:-default}` substitution in [`docker-compose.yml`](docker-compose.yml). Copy `.env.example` to `.env` to override.

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
| `BIND_HOST` | all published ports | `127.0.0.1` | Loopback-only by default; set to `0.0.0.0` to expose on all interfaces |

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
| `CANOPY_API_KEY` | juniper-canopy | *(unset — auth disabled)* | Also distributed via Docker secret |
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

`.env.observability` flips the three `*_METRICS_ENABLED` flags to `true` and is loaded automatically by `make monitor` / `make obs` / `make obs-demo`.

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
| `REDIS_PORT` | redis | `6379` | No host binding — accessible only on the `backend` network |
| `REDIS_MAX_MEMORY` | redis | `100mb` | |
| `WORKER_REPLICAS` | juniper-cascor-worker | `2` | Number of worker replicas |

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
| `GF_SECURITY_ADMIN_PASSWORD__FILE` | grafana | `/run/secrets/grafana_admin_password` |

The Grafana admin password is **Docker-secret-only** — there is no environment-variable fallback. Set the password by writing it to `secrets/grafana_admin_password.txt` before starting the `observability` profile.

### Healthcheck Tuning

All container healthchecks reference shared YAML anchors (`x-healthcheck-defaults`, `x-healthcheck-cascor`, `x-healthcheck-canopy`, `x-healthcheck-worker`, `x-healthcheck-redis`). Override the interval/timeout/retries/start-period values via `HEALTHCHECK_*`, `CASCOR_HEALTHCHECK_*`, `CANOPY_HEALTHCHECK_*`, `WORKER_HEALTHCHECK_*`, and `REDIS_HEALTHCHECK_*` environment variables. See [`docs/REFERENCE.md`](docs/REFERENCE.md) for the full list of overrideable healthcheck variables.

## Docker Deployment

`juniper-deploy` is itself the canonical Docker Compose orchestration for the Juniper platform — every other repository's Docker-Deployment section points back here. The configuration of record is [`docker-compose.yml`](docker-compose.yml); operator-facing commands are wrapped by the [Makefile](Makefile).

### Profiles

| Profile | Command | Services | Use Case |
|---------|---------|----------|----------|
| `full` | `make up` | juniper-data, juniper-cascor, juniper-canopy, redis | Production-like stack |
| `demo` | `make demo` | juniper-data, demo-seed, juniper-cascor-demo, juniper-canopy-demo | Self-running demo with auto-configured training |
| `dev` | `make dev` | juniper-data, juniper-cascor, juniper-canopy-dev | Frontend development (canopy in demo mode) |
| `test` | `make test` | juniper-data, juniper-cascor, juniper-canopy, test-runner | Integration test suite |
| `observability` | `make monitor` | prometheus, alertmanager, grafana (additive — combine with `full` or `demo`) | Prometheus + AlertManager + Grafana monitoring |

The `demo` and `full` profiles cannot be run simultaneously — they bind to the same host ports. The `observability` profile is additive.

#### Demo Profile Startup Sequence

```text
1. juniper-data starts and becomes healthy
2. demo-seed seeds a canonical spiral dataset (2-spiral, 400 points, seed=42)
3. juniper-cascor-demo starts with JUNIPER_CASCOR_AUTO_START=true,
   creates a network, and begins training automatically
4. juniper-canopy-demo connects to juniper-cascor-demo and renders live metrics
```

Demo auto-start parameters (dataset, network config, epochs) are tuned in `.env.demo`.

### Profile Service Matrix

| Service | `full` | `demo` | `dev` | `test` | `observability` |
|---------|--------|--------|-------|--------|-----------------|
| juniper-data | yes | yes | yes | yes | — |
| juniper-cascor | yes | — | yes | yes | — |
| juniper-cascor-demo | — | yes | — | — | — |
| juniper-canopy | yes | — | — | yes | — |
| juniper-canopy-demo | — | yes | — | — | — |
| juniper-canopy-dev | — | — | yes | — | — |
| demo-seed | — | yes | — | — | — |
| test-runner | — | — | — | yes | — |
| redis | yes | — | — | — | — |
| prometheus | — | — | — | — | yes |
| alertmanager | — | — | — | — | yes |
| grafana | — | — | — | — | yes |

### Makefile Targets

| Target | Description |
|--------|-------------|
| `make help` | Show all available targets |
| `make up` | Start full stack (detached) |
| `make demo` | Start demo stack (auto-configured training) |
| `make dev` | Start dev stack (canopy in demo mode) |
| `make test` | Run integration tests (starts services + test-runner) |
| `make monitor` / `make obs` | Start full stack with observability (Prometheus + Grafana) |
| `make obs-demo` | Start demo stack with observability |
| `make down` | Stop and remove all containers |
| `make restart` | Restart all services |
| `make build` / `make build-no-cache` | Build/rebuild all images |
| `make logs` / `make logs-{data,cascor,canopy}` | Tail logs |
| `make status` / `make ps` | Container status |
| `make health` / `make wait` | Health report / block until healthy |
| `make shell-{data,cascor,canopy}` | Shell into a container |
| `make prepare-secrets` | Scaffold `secrets/` from `secrets.example/` |
| `make clean` | Remove containers, volumes, and local images |

You can also use `docker compose` commands directly — the Makefile is a convenience wrapper.

### Service Discovery and Health Endpoints

Inside the Docker network, services communicate via Docker DNS:

| From | To | Internal URL |
|------|----|--------------|
| juniper-cascor | juniper-data | `http://juniper-data:8100` |
| juniper-canopy | juniper-data | `http://juniper-data:8100` |
| juniper-canopy | juniper-cascor | `http://juniper-cascor:8200` |

All services expose `/v1/health` (liveness) and `/v1/health/ready` (readiness):

```bash
curl http://localhost:8100/v1/health        # juniper-data
curl http://localhost:8201/v1/health        # juniper-cascor (host port)
curl http://localhost:8050/v1/health        # juniper-canopy
curl http://localhost:9090/-/healthy        # prometheus  (observability profile)
curl http://localhost:9093/-/healthy        # alertmanager (observability profile)
curl http://localhost:3001/api/health       # grafana      (observability profile)
```

### Security Architecture

| Concern | Implementation |
|---------|----------------|
| **Network isolation** | Four networks: `frontend` (bridge), `backend` (internal), `data` (internal), `monitoring` (bridge). Internal networks have no external connectivity. |
| **Container hardening** | All Juniper application containers set `security_opt: no-new-privileges:true` and `cap_drop: ALL`. |
| **Port binding** | Published Juniper service ports default to `127.0.0.1` through `${BIND_HOST:-127.0.0.1}`. `BIND_HOST=0.0.0.0` is an explicit escape hatch for deployments with a fronting authenticating proxy. Redis has no host binding. |
| **Secrets** | API keys, the Grafana admin password, and the cascor auth token are distributed via Docker secrets mounted at `/run/secrets/<name>`. |
| **Pinned third-party images** | `prom/prometheus:v3.10.0`, `prom/alertmanager:v0.27.0`, `grafana/grafana:12.4.0`, `redis:7.4-alpine`. |

### Integration Tests

Two execution modes are supported:

```bash
# Containerized (recommended)
make test                                                # starts services + test-runner

# Host-based
make build && make up && make wait
pip install -r requirements-test.txt
pytest tests/ -v
make down
```

Test markers (`health`, `data`, `full_stack`) and configurable service URLs (`JUNIPER_TEST_{DATA,CASCOR,CANOPY}_URL`) are documented in [`docs/testing/TESTING_QUICK_START.md`](docs/testing/TESTING_QUICK_START.md).

### Observability Stack

The `observability` profile attaches Prometheus, AlertManager, and Grafana to a dedicated `monitoring` Docker network; Prometheus additionally joins `backend`, `data`, and `frontend` so it can scrape internal service endpoints. The compose networks have static subnets (`backend` `172.28.0.0/16`, `data` `172.29.0.0/16`, `frontend` `172.30.0.0/16`, `monitoring` `172.31.0.0/16`), and `.env.observability` pins each `*_METRICS_TRUSTED_IPS` allowlist to the subnets each target shares with Prometheus. Four dashboards auto-provision into the "Juniper" folder on startup: **Juniper Overview**, **JuniperData**, **JuniperCascor**, **JuniperCanopy**. Dashboard JSON files live in [`grafana/provisioning/dashboards/`](grafana/provisioning/dashboards/).

```bash
make obs        # Full stack + Prometheus + AlertManager + Grafana
make obs-demo   # Demo stack + Prometheus + AlertManager + Grafana
```

Access:

- **Grafana**: <http://localhost:3001> (login: `admin`; password from `secrets/grafana_admin_password.txt`)
- **Prometheus**: <http://localhost:9090>
- **AlertManager**: <http://localhost:9093>

For per-service metrics catalogues, Sentry wiring, structured-JSON logging, and AlertManager routing, see [`docs/OBSERVABILITY_GUIDE.md`](docs/OBSERVABILITY_GUIDE.md).

## Stack Composition

> **Note** — per §10.8 of [`../juniper-ml/notes/JUNIPER_2026-05-19_JUNIPER-ECOSYSTEM_README-NORMALIZATION-PLAN.md`](../juniper-ml/notes/JUNIPER_2026-05-19_JUNIPER-ECOSYSTEM_README-NORMALIZATION-PLAN.md), the **Active Research Components** section is replaced by **Stack Composition** for this repository. `juniper-deploy` does not host research code of its own; its role is to assemble the platform's research components into a runnable stack and to expose the operational surface (profiles, secrets, networks, healthchecks, observability) under which those components are exercised.

| Layer | Components Orchestrated | Profile(s) | Where the research lives |
|-------|------------------------|------------|--------------------------|
| **Training service** | [juniper-cascor](https://github.com/pcalnon/juniper-cascor), `juniper-cascor-demo` | `full`, `dev`, `test`, `demo` | Cascade-Correlation reference implementation, candidate-pool training, multi-network orchestration |
| **Dataset service** | [juniper-data](https://github.com/pcalnon/juniper-data) | `full`, `demo`, `dev`, `test` | Named-version registry; ARC-AGI dataset families; canonical spiral seed dataset for the `demo` profile |
| **Monitoring surface** | [juniper-canopy](https://github.com/pcalnon/juniper-canopy), `juniper-canopy-demo`, `juniper-canopy-dev` | `full`, `demo`, `dev`, `test` | Real-time training-dynamics visualisation, network-topology renderer, WebSocket control surface |
| **Distributed worker** | [juniper-cascor-worker](https://github.com/pcalnon/juniper-cascor-worker) | `full` (via `WORKER_REPLICAS`) | Distributed candidate-unit training over the WebSocket worker protocol |
| **Infrastructure** | `redis:7.4-alpine` | `full`, `test` | Canopy WebSocket cache and pub/sub fan-out |
| **Observability** | `prom/prometheus:v3.10.0`, `prom/alertmanager:v0.28.1`, `grafana/grafana:12.4.0` | `observability` (additive) | Scrape configuration, alert rules, recording rules, and four auto-provisioned dashboards live under `prometheus/`, `alertmanager/`, and `grafana/provisioning/` in this repository |

## Quick Start Guide

### Prerequisites

- [Docker](https://docs.docker.com/get-docker/) ≥ 24.0 with Compose v2 ≥ 2.20
- [GNU Make](https://www.gnu.org/software/make/) ≥ 4.0
- All Juniper service repositories cloned as siblings of this directory:

  ```text
  Juniper/
  ├── juniper-deploy/          ← this repo
  ├── juniper-data/
  ├── juniper-cascor/
  └── juniper-canopy/
  ```

- A populated `secrets/` directory before exposing any port beyond `127.0.0.1` — see the safety callout at the top of this README and [`docs/SECRETS_ONBOARDING.md`](docs/SECRETS_ONBOARDING.md).

### Installation

```bash
git clone https://github.com/pcalnon/juniper-deploy.git
cd juniper-deploy
make prepare-secrets       # scaffold secrets/ from secrets.example/
make build                 # build all images
```

### Verification

Bring up the self-running demo stack and watch it train:

```bash
make demo
make wait                  # block until all services healthy
make health                # detailed health report
# open http://localhost:8050  for the live dashboard
make down
```

For the full profile / dev profile / per-profile service listings, see the [Docker Deployment](#docker-deployment) section above — in particular the [Profiles](#profiles) and [Profile Service Matrix](#profile-service-matrix) tables.

### Next Steps

- [`docs/QUICK_START.md`](docs/QUICK_START.md) — 5-minute quickstart
- [`docs/USER_MANUAL.md`](docs/USER_MANUAL.md) — profiles, monitoring, security, logging, scripts
- [`docs/SECRETS_ONBOARDING.md`](docs/SECRETS_ONBOARDING.md) — SOPS-encrypted-canonical-copy workflow for the `secrets/` directory
- [`docs/OBSERVABILITY_GUIDE.md`](docs/OBSERVABILITY_GUIDE.md) — Prometheus, Grafana, AlertManager, Sentry
- [`docs/testing/TESTING_QUICK_START.md`](docs/testing/TESTING_QUICK_START.md) — integration test guide

## Documentation

| Document | Purpose |
|----------|---------|
| [`docs/DOCUMENTATION_OVERVIEW.md`](docs/DOCUMENTATION_OVERVIEW.md) | Navigation index — start here |
| [`docs/QUICK_START.md`](docs/QUICK_START.md) | Start the Juniper stack in 5 minutes |
| [`docs/ENVIRONMENT_SETUP.md`](docs/ENVIRONMENT_SETUP.md) | Complete environment configuration guide |
| [`docs/USER_MANUAL.md`](docs/USER_MANUAL.md) | Profiles, monitoring, security, logging, scripts |
| [`docs/DEVELOPER_CHEATSHEET.md`](docs/DEVELOPER_CHEATSHEET.md) | Common commands quick-reference |
| [`docs/OBSERVABILITY_GUIDE.md`](docs/OBSERVABILITY_GUIDE.md) | Prometheus, Grafana, AlertManager, Sentry documentation |
| [`docs/REFERENCE.md`](docs/REFERENCE.md) | Technical reference (services, env vars, networks, healthchecks) |
| [`docs/SECRETS_ONBOARDING.md`](docs/SECRETS_ONBOARDING.md) | SOPS-encrypted-canonical-copy workflow for `secrets/` |
| [`docs/testing/TESTING_QUICK_START.md`](docs/testing/TESTING_QUICK_START.md) | Integration test guide |
| [`CHANGELOG.md`](CHANGELOG.md) | Release history (Keep a Changelog format) |

## License

MIT License — Copyright (c) 2024-2026 Paul Calnon
