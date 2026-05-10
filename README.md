# juniper-deploy

Docker Compose and integration tests for the Juniper ML ecosystem.

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

## Overview

This repository provides a single `make up` command that boots the entire Juniper stack locally — JuniperData, JuniperCascor, and juniper-canopy — with proper dependency ordering, health checks, and environment wiring.

## Prerequisites

- [Docker](https://docs.docker.com/get-docker/) >= 24.0 with Compose v2 >= 2.20
- [GNU Make](https://www.gnu.org/software/make/) >= 4.0
- All Juniper service repositories cloned as siblings of this directory:

  ```text
  Juniper/
  ├── juniper-deploy/          ← this repo
  ├── juniper-data/
  ├── juniper-cascor/
  └── juniper-canopy/
  ```

## Quick Start

```bash
# Build and start all services (full stack)
make build && make up

# Check health
make health

# Follow logs
make logs

# Stop all services
make down

# See all available targets
make help
```

## Profiles

Docker Compose profiles control which services start for each operational mode:

| Profile | Command | Services | Use Case |
|---------|---------|----------|----------|
| `full` | `make up` | juniper-data, juniper-cascor, juniper-canopy | Production-like stack |
| `demo` | `make demo` | juniper-data, demo-seed, juniper-cascor-demo, juniper-canopy-demo | Self-running demo with auto-configured training |
| `dev` | `make dev` | juniper-data, juniper-cascor, juniper-canopy-dev | Frontend development (canopy in demo mode) |
| `test` | `make test` | juniper-data, juniper-cascor, juniper-canopy, test-runner | Integration test suite |
| `observability` | `make monitor` | prometheus, grafana (additive — use with `full`) | Prometheus + Grafana monitoring |

### Demo Profile

The demo profile starts a fully self-running demo stack. On startup:

1. **juniper-data** starts and becomes healthy
2. **demo-seed** seeds a canonical spiral dataset (2-spiral, 400 points, seed=42)
3. **juniper-cascor-demo** starts with auto-start training enabled — creates a network and begins training automatically
4. **juniper-canopy-demo** connects to the demo CasCor and shows live training metrics

```bash
# Start the demo
make demo

# Follow logs to watch training progress
make logs

# Open the dashboard
# http://localhost:8050

# Stop the demo
make down
```

The demo auto-start parameters (dataset, network config, epochs) can be customized in `.env.demo`.

### Dev Profile

The dev profile runs real data and CasCor services with Canopy in demo mode (no backend dependency). Useful for frontend development on juniper-canopy.

```bash
make dev
```

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
| prometheus | — | — | — | — | yes |
| grafana | — | — | — | — | yes |

> **Note**: Do not run `demo` and `full` profiles simultaneously — they bind to the same host ports. The `observability` profile is additive — combine it with `full` or `demo`.

### Available Targets

| Target | Description |
|--------|-------------|
| `make help` | Show all available targets |
| `make up` | Start full stack (detached) |
| `make demo` | Start demo stack (auto-configured training) |
| `make dev` | Start dev stack (canopy in demo mode) |
| `make test` | Run integration tests (starts services + test-runner) |
| `make monitor` | Start full stack with observability (Prometheus + Grafana) |
| `make down` | Stop and remove all containers |
| `make restart` | Restart all services |
| `make logs` | Tail logs from all services (follow) |
| `make logs-data` | Tail JuniperData logs |
| `make logs-cascor` | Tail JuniperCascor logs |
| `make logs-canopy` | Tail juniper-canopy logs |
| `make status` | Show container status |
| `make ps` | Compact container listing |
| `make health` | Detailed health report for all services |
| `make wait` | Block until all services are healthy |
| `make build` | Build/rebuild all images |
| `make build-no-cache` | Full rebuild without cache |
| `make clean` | Remove containers, volumes, and local images |
| `make obs` | Start full stack with observability (Prometheus + Grafana) |
| `make obs-demo` | Start demo stack with observability (Prometheus + Grafana) |
| `make shell-data` | Shell into JuniperData container |
| `make shell-cascor` | Shell into JuniperCascor container |
| `make shell-canopy` | Shell into juniper-canopy container |

You can also use `docker compose` commands directly — the Makefile is a convenience wrapper.

## Services

| Service | URL | Description |
|---------|-----|-------------|
| JuniperData | <http://localhost:8100> | Dataset generation REST API |
| JuniperCascor | <http://localhost:8201> | CasCor neural network training service |
| juniper-canopy | <http://localhost:8050> | Real-time monitoring dashboard |

## Health Endpoints

All services expose standardized health endpoints:

```bash
curl http://localhost:8100/v1/health        # juniper-data liveness
curl http://localhost:8100/v1/health/ready  # juniper-data readiness
curl http://localhost:8201/v1/health        # juniper-cascor liveness
curl http://localhost:8201/v1/health/ready  # juniper-cascor readiness
curl http://localhost:8050/v1/health        # juniper-canopy liveness
curl http://localhost:8050/v1/health/ready  # juniper-canopy readiness
```

## Integration Tests

### Containerized (recommended)

```bash
# Build and run tests in a container — services start automatically
make test
```

The `test` profile starts juniper-data, juniper-cascor, and juniper-canopy, waits for healthy status, then runs the test suite in a `test-runner` container.

### Host-based

```bash
# Start services and wait for healthy
make build && make up && make wait

# Run integration tests
pip install -r requirements-test.txt
pytest tests/ -v

# Teardown
make down
```

## Service Discovery

Inside the Docker network, services communicate using Docker DNS. Each service name in `docker-compose.yml` becomes a hostname:

| From | To | Internal URL |
|------|----|--------------|
| juniper-cascor | juniper-data | `http://juniper-data:8100` |
| juniper-canopy | juniper-data | `http://juniper-data:8100` |
| juniper-canopy | juniper-cascor | `http://juniper-cascor:8200` |

These URLs are set automatically via `JUNIPER_DATA_URL` and `CASCOR_SERVICE_URL` environment variables. Override them in `.env` only if running services outside Docker or on a custom network.

## Environment Variables

Copy `.env.example` to `.env` to override defaults. All values use `${VAR:-default}` substitution in `docker-compose.yml`.

| Variable | Default | Description |
|----------|---------|-------------|
| `JUNIPER_DATA_HOST` | `0.0.0.0` | JuniperData bind address |
| `JUNIPER_DATA_PORT` | `8100` | JuniperData port |
| `JUNIPER_DATA_LOG_LEVEL` | `INFO` | JuniperData log level |
| `CASCOR_HOST` | `0.0.0.0` | JuniperCascor bind address |
| `CASCOR_PORT` | `8200` | JuniperCascor internal container port |
| `CASCOR_HOST_PORT` | `8201` | JuniperCascor host-exposed port (avoids conflicts with other services on 8200) |
| `CASCOR_LOG_LEVEL` | `INFO` | JuniperCascor log level |
| `CANOPY_HOST` | `0.0.0.0` | juniper-canopy bind address |
| `CANOPY_PORT` | `8050` | juniper-canopy port |
| `JUNIPER_DATA_URL` | `http://juniper-data:8100` | Inter-service URL for JuniperData |
| `CASCOR_SERVICE_URL` | `http://juniper-cascor:8200` | Inter-service URL for JuniperCascor |
| `JUNIPER_DATA_API_KEYS` | *(unset)* | API key(s) for juniper-data (comma-separated) |
| `JUNIPER_CASCOR_API_KEYS` | *(unset)* | API key(s) for juniper-cascor (comma-separated) |
| `JUNIPER_CANOPY_API_KEY` | *(unset)* | API key for juniper-canopy |
| `JUNIPER_CASCOR_RATE_LIMIT_ENABLED` | `false` | Enable rate limiting for juniper-cascor |
| `JUNIPER_CASCOR_RATE_LIMIT_REQUESTS_PER_MINUTE` | `60` | Rate limit for juniper-cascor |
| `JUNIPER_CANOPY_RATE_LIMIT_ENABLED` | `false` | Enable rate limiting for juniper-canopy |
| `JUNIPER_CANOPY_RATE_LIMIT_REQUESTS_PER_MINUTE` | `60` | Rate limit for juniper-canopy |

## Authentication

API key authentication can be enabled per service by setting the corresponding environment variable in `.env`. When no key is configured for a service, all endpoints are open (development mode).

### Docker Secret Files

`docker-compose.yml` now mounts Docker secrets for API keys and Grafana admin credentials from local files in `secrets/`:

```bash
mkdir -p secrets
cp secrets.example/*.txt secrets/
```

Expected local files:

- `secrets/juniper_data_api_keys.txt`
- `secrets/juniper_cascor_api_keys.txt`
- `secrets/canopy_api_key.txt`
- `secrets/grafana_admin_password.txt`

These files are consumed via `*_FILE` environment variables (for example, `JUNIPER_DATA_API_KEYS_FILE=/run/secrets/juniper_data_api_keys` and `GF_SECURITY_ADMIN_PASSWORD__FILE=/run/secrets/grafana_admin_password`) while the existing env-var-based settings remain available in `.env`.

### Enabling API Keys

```bash
# .env
JUNIPER_DATA_API_KEYS=my-data-secret-key
JUNIPER_CASCOR_API_KEYS=my-cascor-secret-key
JUNIPER_CANOPY_API_KEY=my-canopy-secret-key
```

Clients authenticate by including the key in the `X-API-Key` HTTP header:

```bash
curl -H "X-API-Key: my-data-secret-key" http://localhost:8100/v1/datasets
```

### Exempt Endpoints

Health, documentation, and monitoring endpoints are always accessible without authentication:

| Endpoint Pattern | Exempt? |
|-----------------|---------|
| `/v1/health`, `/v1/health/live`, `/v1/health/ready` | Yes |
| `/docs`, `/redoc`, `/openapi.json` | Yes |
| `/dashboard/*` (juniper-canopy only) | Yes |

### Inter-Service Authentication

When API keys are enabled, downstream services automatically receive the upstream API key via environment variables in `docker-compose.yml`:

| From | To | Env Var |
|------|----|---------|
| juniper-cascor | juniper-data | `JUNIPER_DATA_API_KEY` |
| juniper-canopy | juniper-cascor | `JUNIPER_CASCOR_API_KEY` |

### Rate Limiting

Optional rate limiting can be enabled alongside API key authentication:

```bash
# .env
JUNIPER_CASCOR_RATE_LIMIT_ENABLED=true
JUNIPER_CASCOR_RATE_LIMIT_REQUESTS_PER_MINUTE=60
JUNIPER_CANOPY_RATE_LIMIT_ENABLED=true
JUNIPER_CANOPY_RATE_LIMIT_REQUESTS_PER_MINUTE=60
```

### WebSocket Authentication

JuniperCascor WebSocket endpoints (`/ws/*`) require the `X-API-Key` header during the connection handshake when authentication is enabled. Connections without a valid key are closed with code `4001`.

### Docker Compose Secrets

For production deployments, sensitive values (API keys, DSNs) can be provided via Docker Compose file-based secrets instead of environment variables:

1. Copy the template directory:

   ```bash
   cp -r secrets.example/ secrets/
   ```

2. Edit each file in `secrets/` with real values

3. Secrets are mounted at `/run/secrets/<name>` inside the container

The `secrets/` directory is git-ignored. See `secrets.example/` for the available secret files.

### Integration Tests with Authentication

When running tests against services with authentication enabled, pass API keys via environment variables:

```bash
JUNIPER_TEST_DATA_API_KEY=my-data-secret-key \
JUNIPER_TEST_CASCOR_API_KEY=my-cascor-secret-key \
JUNIPER_TEST_JUNIPER_CANOPY_API_KEY=my-canopy-secret-key \
pytest tests/ -v
```

## Development

For local development with hot-reloading, copy the override template:

```bash
cp docker-compose.override.yml.example docker-compose.override.yml
```

Edit the override file to bind-mount source directories from sibling repos. Docker Compose automatically merges `docker-compose.override.yml` with `docker-compose.yml`. The override file is git-ignored.

## Observability

The Juniper stack supports structured JSON logging, Prometheus metrics with 23 custom application metrics, auto-provisioned Grafana dashboards, and Sentry error tracking. These features are disabled by default and can be enabled per service via environment variables.

For comprehensive documentation, see [docs/OBSERVABILITY_GUIDE.md](docs/OBSERVABILITY_GUIDE.md).

### Quick Start (Recommended)

Use Makefile targets to start the stack with observability enabled:

```bash
make obs        # Full stack + Prometheus + Grafana
make obs-demo   # Demo stack + Prometheus + Grafana
```

These targets automatically load `.env.observability`, which enables metrics on all services.

Access dashboards:

- **Grafana**: <http://localhost:3000> (default login: `admin` / `admin`, unless overridden via `secrets/grafana_admin_password.txt`)
- **Prometheus**: <http://localhost:9090>

Prometheus and Grafana are attached to a dedicated `monitoring` Docker network. Prometheus also joins `backend` and `data` so it can scrape internal service endpoints.

### Grafana Dashboards

Four dashboards auto-provision into the "Juniper" folder on startup:

| Dashboard | Description |
|-----------|-------------|
| **Juniper Overview** (home) | Cross-service health, request rates, error rates, latency percentiles |
| **JuniperData** | Dataset generation metrics, cache status, HTTP breakdown |
| **JuniperCascor** | Training sessions, loss/accuracy, hidden units, inference metrics |
| **JuniperCanopy** | WebSocket connections/messages, demo mode status |

Dashboard JSON files are in `grafana/provisioning/dashboards/`.

### Custom Metrics

Each service exposes namespaced metrics (e.g., `juniper_data_dataset_generations_total`, `juniper_cascor_training_loss`, `juniper_canopy_websocket_connections_active`). See [docs/OBSERVABILITY_GUIDE.md](docs/OBSERVABILITY_GUIDE.md) for the full metrics catalog.

### Structured JSON Logging

Set `*_LOG_FORMAT=json` in `.env` to enable JSON-structured log output for a service:

```bash
JUNIPER_DATA_LOG_FORMAT=json
JUNIPER_CASCOR_LOG_FORMAT=json
JUNIPER_CANOPY_LOG_FORMAT=json
```

### Manual Metrics Setup

If not using `make obs`, enable metrics manually:

1. Enable the `/metrics` endpoint on each service:

   ```bash
   JUNIPER_DATA_METRICS_ENABLED=true
   JUNIPER_CASCOR_METRICS_ENABLED=true
   JUNIPER_CANOPY_METRICS_ENABLED=true
   ```

2. Start the observability stack:

   ```bash
   docker compose --profile full --profile observability up -d
   ```

### Sentry Error Tracking

Set the Sentry DSN for each service to enable error reporting:

```bash
JUNIPER_DATA_SENTRY_DSN=https://examplePublicKey@o0.ingest.sentry.io/0
JUNIPER_CASCOR_SENTRY_DSN=https://examplePublicKey@o0.ingest.sentry.io/0
JUNIPER_CANOPY_SENTRY_DSN=https://examplePublicKey@o0.ingest.sentry.io/0
```

## Troubleshooting

**Services fail to start**: Ensure all sibling repos are cloned and have Dockerfiles. Run `make build` to see build errors.

**Health check fails**: Run `make status` to see container state. Check logs with `make logs-<service>` for the failing service.

**Port conflicts**: If default ports are in use, copy `.env.example` to `.env` and change port values. The juniper-cascor host port defaults to 8201 (via `CASCOR_HOST_PORT`) to avoid conflicts with other services commonly bound to 8200. Set `CASCOR_HOST_PORT=8200` in `.env` if port 8200 is available.

**`make clean` won't release disk**: Named volumes (`juniper-data-datasets`, `juniper-cascor-snapshots`, `juniper-cascor-logs`, `grafana-data`) may persist after `make down`. Use `docker volume prune` to clean orphaned volumes, or `make clean` to remove everything including volumes.

## Ecosystem Compatibility

See the [compatibility matrix](https://github.com/pcalnon/juniper-ml#ecosystem-compatibility) for verified compatible versions.

## License

MIT License — Copyright (c) 2024-2026 Paul Calnon
