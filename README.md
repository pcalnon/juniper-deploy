# juniper-deploy

Docker Compose and integration tests for the Juniper ML ecosystem.

## Overview

This repository provides a single `make up` command that boots the entire Juniper stack locally — JuniperData, JuniperCascor, and JuniperCanopy — with proper dependency ordering, health checks, and environment wiring.

## Prerequisites

- [Docker](https://docs.docker.com/get-docker/) >= 24.0 with Compose v2 >= 2.20
- [GNU Make](https://www.gnu.org/software/make/) >= 4.0
- All Juniper service repositories cloned as siblings of this directory:
  ```
  Juniper/
  ├── juniper-deploy/          ← this repo
  ├── juniper-data/
  ├── juniper-cascor/
  └── JuniperCanopy/
      └── juniper_canopy/
  ```

## Quick Start

```bash
# Build and start all services
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

### Available Targets

| Target | Description |
|--------|-------------|
| `make help` | Show all available targets |
| `make up` | Start all services (detached) |
| `make down` | Stop and remove all containers |
| `make restart` | Restart all services |
| `make logs` | Tail logs from all services (follow) |
| `make logs-data` | Tail JuniperData logs |
| `make logs-cascor` | Tail JuniperCascor logs |
| `make logs-canopy` | Tail JuniperCanopy logs |
| `make status` | Show container status |
| `make ps` | Compact container listing |
| `make health` | Detailed health report for all services |
| `make wait` | Block until all services are healthy |
| `make build` | Build/rebuild all images |
| `make build-no-cache` | Full rebuild without cache |
| `make clean` | Remove containers, volumes, and local images |
| `make shell-data` | Shell into JuniperData container |
| `make shell-cascor` | Shell into JuniperCascor container |
| `make shell-canopy` | Shell into JuniperCanopy container |

You can also use `docker compose` commands directly — the Makefile is a convenience wrapper.

## Services

| Service | URL | Description |
|---------|-----|-------------|
| JuniperData | http://localhost:8100 | Dataset generation REST API |
| JuniperCascor | http://localhost:8200 | CasCor neural network training service |
| JuniperCanopy | http://localhost:8050 | Real-time monitoring dashboard |

## Health Endpoints

All services expose standardized health endpoints:

```bash
curl http://localhost:8100/v1/health        # juniper-data liveness
curl http://localhost:8100/v1/health/ready  # juniper-data readiness
curl http://localhost:8200/v1/health        # juniper-cascor liveness
curl http://localhost:8200/v1/health/ready  # juniper-cascor readiness
curl http://localhost:8050/v1/health        # juniper-canopy liveness
curl http://localhost:8050/v1/health/ready  # juniper-canopy readiness
```

## Integration Tests

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
| `CASCOR_PORT` | `8200` | JuniperCascor port |
| `CASCOR_LOG_LEVEL` | `INFO` | JuniperCascor log level |
| `CANOPY_HOST` | `0.0.0.0` | JuniperCanopy bind address |
| `CANOPY_PORT` | `8050` | JuniperCanopy port |
| `JUNIPER_DATA_URL` | `http://juniper-data:8100` | Inter-service URL for JuniperData |
| `CASCOR_SERVICE_URL` | `http://juniper-cascor:8200` | Inter-service URL for JuniperCascor |

## Troubleshooting

**Services fail to start**: Ensure all sibling repos are cloned and have Dockerfiles. Run `make build` to see build errors.

**Health check fails**: Run `make status` to see container state. Check logs with `make logs-<service>` for the failing service.

**Port conflicts**: If default ports are in use, copy `.env.example` to `.env` and change port values.

**`make clean` won't release disk**: Named volumes may persist. Use `docker volume prune` to clean orphaned volumes.

## Ecosystem Compatibility

See the [compatibility matrix](https://github.com/pcalnon/juniper-ml#ecosystem-compatibility) for verified compatible versions.

## License

MIT License — Copyright (c) 2024-2026 Paul Calnon
