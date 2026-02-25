# juniper-deploy

Docker Compose and integration tests for the Juniper ML ecosystem.

## Overview

This repository provides a single `docker compose up` command that boots the entire Juniper stack locally — JuniperData, JuniperCascor, and JuniperCanopy — with proper dependency ordering, health checks, and environment wiring.

## Prerequisites

- [Docker](https://docs.docker.com/get-docker/) with Compose v2
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
docker compose up --build

# Start in detached mode
docker compose up -d --build

# Follow logs
docker compose logs -f

# Stop all services
docker compose down
```

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
# Start services
docker compose up -d

# Wait for all services to be healthy
bash scripts/wait_for_services.sh

# Run integration tests
pip install pytest requests
pytest tests/ -v

# Teardown
docker compose down
```

## Environment Variables

Copy `.env.example` to `.env` to override defaults:

| Variable | Default | Description |
|----------|---------|-------------|
| `JUNIPER_DATA_PORT` | 8100 | JuniperData port |
| `CASCOR_PORT` | 8200 | JuniperCascor port |
| `CANOPY_PORT` | 8050 | JuniperCanopy port |

## Ecosystem Compatibility

See the [compatibility matrix](https://github.com/pcalnon/juniper-ml#ecosystem-compatibility) for verified compatible versions.

## License

MIT License — Copyright (c) 2024-2026 Paul Calnon
