# Environment Setup

## Complete Environment Configuration for juniper-deploy

**Version:** 0.2.1
**Status:** Active
**Last Updated:** July 4, 2026
**Project:** Juniper - Docker Compose Orchestration

---

## Table of Contents

- [Overview](#overview)
- [System Requirements](#system-requirements)
- [Repository Layout](#repository-layout)
- [Environment Configuration](#environment-configuration)
- [Build All Images](#build-all-images)
- [Profile Selection](#profile-selection)
- [Observability Setup](#observability-setup)
- [Security Configuration](#security-configuration)
- [Verification](#verification)
- [Troubleshooting](#troubleshooting)

---

## Overview

This guide walks through complete environment setup for juniper-deploy, from prerequisites to a fully running Juniper stack. Estimated time: 15-20 minutes (mostly Docker build time).

---

## System Requirements

| Requirement | Minimum | Recommended |
|-------------|---------|-------------|
| Docker | 24.0+ | Latest |
| Docker Compose | v2.20+ | Latest |
| RAM | 4 GB | 8 GB |
| Disk | 5 GB (images) | 10 GB |
| OS | Linux, macOS, Windows (WSL2) | Linux |

---

## Repository Layout

juniper-deploy builds services from sibling directories. Ensure this structure:

```
Juniper/
├── juniper-data/          # Dataset service (must exist)
├── juniper-cascor/        # Training service (must exist)
├── juniper-canopy/        # Dashboard (must exist)
├── juniper-deploy/        # This project
│   ├── docker-compose.yml
│   ├── Makefile
│   ├── .env.example
│   ├── .env.secrets.example
│   ├── prometheus/
│   └── grafana/
└── ...
```

---

## Environment Configuration

### Step 1: Create `.env` File

```bash
cd juniper-deploy
cp .env.example .env
```

### Step 2: Review Defaults

The `.env.example` contains all configurable variables with sensible defaults. Key settings:

**Service Binding (usually no change needed):**

```bash
BIND_HOST=127.0.0.1
JUNIPER_DATA_HOST=0.0.0.0
JUNIPER_DATA_PORT=8100
CASCOR_HOST=0.0.0.0
CASCOR_PORT=8200
CANOPY_HOST=0.0.0.0
CANOPY_PORT=8050
```

`BIND_HOST` controls the host-side bind address for published ports and defaults to loopback for safety. Do not set `BIND_HOST=0.0.0.0` unless the stack is behind a fronting authenticating proxy; the compose stack does not provide that proxy by itself.

**Logging (adjust per environment):**

```bash
JUNIPER_DATA_LOG_LEVEL=INFO        # DEBUG, INFO, WARNING, ERROR
CASCOR_LOG_LEVEL=INFO
JUNIPER_DATA_LOG_FORMAT=text       # text or json
JUNIPER_CASCOR_LOG_FORMAT=text
CANOPY_LOG_FORMAT=text
```

**Metrics (enable for observability profile):**

```bash
JUNIPER_DATA_METRICS_ENABLED=false
JUNIPER_CASCOR_METRICS_ENABLED=false
CANOPY_METRICS_ENABLED=false
```

### Step 3: Configure Secrets (Optional)

```bash
cp .env.secrets.example .env.secrets
```

Edit `.env.secrets` with API keys if you want authentication:

```bash
JUNIPER_DATA_API_KEYS=your-data-api-key
JUNIPER_CASCOR_API_KEYS=your-cascor-api-key
CANOPY_API_KEY=your-canopy-api-key
JUNIPER_DATA_API_KEY=your-data-api-key      # cascor → data
JUNIPER_CASCOR_API_KEY=your-cascor-api-key  # canopy → cascor
```

Leave empty to disable authentication.

### Step 4: Configure Docker Secret Files (Optional)

`docker-compose.yml` can also mount secrets from local files in `./secrets/`:

```bash
mkdir -p secrets
cp secrets.example/*.txt secrets/
```

Populate these files with real values:

- `secrets/juniper_data_api_keys.txt`
- `secrets/juniper_cascor_api_keys.txt`
- `secrets/canopy_api_key.txt`
- `secrets/grafana_admin_password.txt`

Compose mounts these as `/run/secrets/*` and passes them via `*_FILE` variables (for example, `JUNIPER_DATA_API_KEYS_FILE` and `GF_SECURITY_ADMIN_PASSWORD__FILE`). The regular `.env` values are still available.

---

## Build All Images

```bash
# Standard build
make build

# Full rebuild (no cache)
make build-no-cache
```

This builds images for juniper-data, juniper-cascor, and juniper-canopy from their respective Dockerfiles in sibling directories.

---

## Profile Selection

Choose a profile based on your use case:

### Full Stack

```bash
make up
```

Starts juniper-data, juniper-cascor, and juniper-canopy with real backend services.

### Demo

```bash
make demo
```

Starts the demo profile which:
1. Launches juniper-data
2. Runs `demo-seed` to create a spiral dataset
3. Starts `juniper-cascor-demo` with auto-training enabled
4. Starts `juniper-canopy-demo` pointed at the demo CasCor instance

### Dev (Frontend Development)

```bash
make dev
```

Starts juniper-data and juniper-cascor as real services, but runs juniper-canopy in demo mode (`JUNIPER_CANOPY_DEMO_MODE=true`) so the dashboard works without depending on backend state.

---

## Observability Setup

### Enable Metrics on Services

In `.env`, set:

```bash
JUNIPER_DATA_METRICS_ENABLED=true
JUNIPER_CASCOR_METRICS_ENABLED=true
CANOPY_METRICS_ENABLED=true
```

### Start Prometheus, AlertManager, and Grafana

```bash
docker compose --profile observability up -d
```

**Access:**

| Service | URL | Credentials |
|---------|-----|-------------|
| Prometheus | http://localhost:9090 | None |
| AlertManager | http://localhost:9093 | None |
| Grafana | http://localhost:3001 | admin / value from `secrets/grafana_admin_password.txt` |

Prometheus scrapes all three services at `/metrics` every 15 seconds.
Prometheus, AlertManager, and Grafana use a dedicated `monitoring` network. Prometheus also joins `backend`, `data`, and `frontend` to scrape internal service endpoints.

The observability env file also widens the service metrics allowlists from loopback to the pinned compose subnets:

- juniper-data: `172.28.0.0/16` (`backend`) and `172.29.0.0/16` (`data`)
- juniper-cascor / juniper-canopy: `172.28.0.0/16`, `172.29.0.0/16`, and `172.30.0.0/16` (`frontend`)

Keep those values aligned with `docker-compose.yml`; `tests/test_compose_metrics_subnet_alignment.py` checks for drift. Do not add `172.31.0.0/16` (`monitoring`) unless a metrics target is intentionally moved onto that network.

---

## Security Configuration

### API Keys

Each service can independently enforce API key authentication. Set keys in `.env`:

| Variable | Protects | Consumers |
|----------|----------|-----------|
| `JUNIPER_DATA_API_KEYS` | juniper-data endpoints | External clients |
| `JUNIPER_CASCOR_API_KEYS` | juniper-cascor endpoints | External clients |
| `CANOPY_API_KEY` | juniper-canopy endpoints | External clients |
| `JUNIPER_DATA_API_KEY` | cascor's requests to data | Internal (cascor → data) |
| `JUNIPER_CASCOR_API_KEY` | canopy's requests to cascor | Internal (canopy → cascor) |

### Rate Limiting

```bash
JUNIPER_CASCOR_RATE_LIMIT_ENABLED=true
JUNIPER_CASCOR_RATE_LIMIT_REQUESTS_PER_MINUTE=60
CANOPY_RATE_LIMIT_ENABLED=true
CANOPY_RATE_LIMIT_REQUESTS_PER_MINUTE=60
```

Rate limits and per-IP WebSocket caps dampen accidental or abusive load, but they are not authentication. Inside Docker networking, client IPs can collapse to a bridge gateway address.

---

## Verification

### Step 1: Start the Stack

```bash
make up && make wait
```

### Step 2: Health Check

```bash
make health
```

Expected output shows all services with `ok` status.

### Step 3: Verify Endpoints

```bash
curl http://localhost:8100/v1/health   # {"status": "ok", "version": "..."}
curl http://localhost:8200/v1/health   # {"status": "success", "data": {...}}
curl http://localhost:8050/v1/health   # {"status": "healthy", "version": "..."}
```

### Step 4: Check Container Status

```bash
make ps
```

All containers should show `healthy` status.

---

## Troubleshooting

### Build Fails

- Ensure sibling repos exist: `ls ../juniper-data ../juniper-cascor ../juniper-canopy`
- Try `make build-no-cache` for a clean rebuild

### Service Won't Start

- Check logs: `make logs-data`, `make logs-cascor`, `make logs-canopy`
- Verify ports aren't in use: `ss -tlnp | grep -E '8100|8200|8050'`

### Services Unhealthy

- Check dependency chain: juniper-data must be healthy before cascor starts
- Increase start periods in `docker-compose.yml` if services are slow to initialize
- Run `make health` for a detailed report

### Demo Seed Fails

- Check demo-seed logs: `docker compose --profile demo logs demo-seed`
- Ensure juniper-data is reachable on port 8100 within the Docker network

---

**Last Updated:** July 4, 2026
**Version:** 0.2.1
**Maintainer:** Paul Calnon
