# Reference

## juniper-deploy Technical Reference

**Version:** 0.1.0
**Status:** Active
**Last Updated:** April 1, 2026
**Project:** Juniper - Docker Compose Orchestration

---

## Table of Contents

- [Service Reference](#service-reference)
- [Profile Reference](#profile-reference)
- [Environment Variables](#environment-variables)
- [Makefile Targets](#makefile-targets)
- [Health Endpoints](#health-endpoints)
- [Docker Healthcheck Configuration](#docker-healthcheck-configuration)
- [Network Architecture](#network-architecture)
- [Scripts Reference](#scripts-reference)
- [Prometheus Configuration](#prometheus-configuration)
- [Grafana Configuration](#grafana-configuration)
- [Test Configuration](#test-configuration)

---

## Service Reference

### Core Services

| Service | Image Source | Host Port | Container Port | Health Endpoint |
|---------|-------------|-----------|---------------|-----------------|
| `juniper-data` | `../juniper-data/Dockerfile` | 8100 | 8100 | `/v1/health` |
| `juniper-cascor` | `../juniper-cascor/Dockerfile` | 8201 (default) | 8200 | `/v1/health` |
| `juniper-cascor-demo` | `../juniper-cascor/Dockerfile` | 8201 (default) | 8200 | `/v1/health` |
| `juniper-canopy` | `../juniper-canopy/Dockerfile` | 8050 | 8050 | `/v1/health` |
| `juniper-canopy-demo` | `../juniper-canopy/Dockerfile` | 8050 | 8050 | `/v1/health` |
| `juniper-canopy-dev` | `../juniper-canopy/Dockerfile` | 8050 | 8050 | `/v1/health` |
| `demo-seed` | `python:3.12-slim` | -- | -- | -- |

### Observability Services

| Service | Image | Host Port | Purpose |
|---------|-------|-----------|---------|
| `prometheus` | `prom/prometheus:latest` | 9090 | Metrics collection |
| `grafana` | `grafana/grafana:latest` | 3000 | Metrics visualization |

### Dependency Chain

| Service | Depends On | Condition |
|---------|-----------|-----------|
| `juniper-cascor` | `juniper-data` | `service_healthy` |
| `juniper-cascor-demo` | `juniper-data`, `demo-seed` | `service_healthy`, `service_completed_successfully` |
| `juniper-canopy` | `juniper-data`, `juniper-cascor` | `service_healthy` |
| `juniper-canopy-demo` | `juniper-data`, `juniper-cascor-demo` | `service_healthy` |
| `demo-seed` | `juniper-data` | `service_healthy` |
| `grafana` | `prometheus` | `service_started` |

---

## Profile Reference

| Profile | Services Included |
|---------|-------------------|
| `full` | juniper-data, juniper-cascor, juniper-canopy |
| `demo` | juniper-data, juniper-cascor-demo, juniper-canopy-demo, demo-seed |
| `dev` | juniper-data, juniper-cascor, juniper-canopy-dev |
| `observability` | prometheus, grafana |

---

## Environment Variables

### Service Binding

| Variable | Default | Service |
|----------|---------|---------|
| `JUNIPER_DATA_HOST` | `0.0.0.0` | juniper-data |
| `JUNIPER_DATA_PORT` | `8100` | juniper-data |
| `CASCOR_HOST` | `0.0.0.0` | juniper-cascor |
| `CASCOR_PORT` | `8200` | juniper-cascor |
| `CANOPY_HOST` | `0.0.0.0` | juniper-canopy |
| `CANOPY_PORT` | `8050` | juniper-canopy |

### Inter-Service URLs

| Variable | Default | Used By |
|----------|---------|---------|
| `JUNIPER_DATA_URL` | `http://juniper-data:8100` | juniper-cascor |
| `JUNIPER_CANOPY_JUNIPER_DATA_URL` | `http://juniper-data:8100` | juniper-canopy |
| `JUNIPER_CANOPY_CASCOR_SERVICE_URL` | `http://juniper-cascor:8200` | juniper-canopy |

### API Security

| Variable | Default | Purpose |
|----------|---------|---------|
| `JUNIPER_DATA_API_KEYS` | (empty) | Keys accepted by juniper-data |
| `JUNIPER_CASCOR_API_KEYS` | (empty) | Keys accepted by juniper-cascor |
| `CANOPY_API_KEY` | (empty) | Key accepted by juniper-canopy |
| `JUNIPER_DATA_API_KEY` | (empty) | Key sent by cascor to data |
| `JUNIPER_CASCOR_API_KEY` | (empty) | Key sent by canopy to cascor |

### Docker Secret File Variables

| Variable | Service | Secret Name | Mounted Path |
|----------|---------|-------------|--------------|
| `JUNIPER_DATA_API_KEYS_FILE` | juniper-data | `juniper_data_api_keys` | `/run/secrets/juniper_data_api_keys` |
| `JUNIPER_CASCOR_API_KEYS_FILE` | juniper-cascor | `juniper_cascor_api_keys` | `/run/secrets/juniper_cascor_api_keys` |
| `JUNIPER_DATA_API_KEY_FILE` | juniper-cascor | `juniper_data_api_keys` | `/run/secrets/juniper_data_api_keys` |
| `CANOPY_API_KEY_FILE` | juniper-canopy | `canopy_api_key` | `/run/secrets/canopy_api_key` |
| `JUNIPER_CASCOR_API_KEY_FILE` | juniper-canopy | `juniper_cascor_api_keys` | `/run/secrets/juniper_cascor_api_keys` |
| `GF_SECURITY_ADMIN_PASSWORD__FILE` | grafana | `grafana_admin_password` | `/run/secrets/grafana_admin_password` |

Compose secret definitions reference local files in `secrets/`:

- `secrets/juniper_data_api_keys.txt`
- `secrets/juniper_cascor_api_keys.txt`
- `secrets/canopy_api_key.txt`
- `secrets/grafana_admin_password.txt`

### Rate Limiting

| Variable | Default | Service |
|----------|---------|---------|
| `JUNIPER_CASCOR_RATE_LIMIT_ENABLED` | `false` | juniper-cascor |
| `JUNIPER_CASCOR_RATE_LIMIT_REQUESTS_PER_MINUTE` | `60` | juniper-cascor |
| `CANOPY_RATE_LIMIT_ENABLED` | `false` | juniper-canopy |
| `CANOPY_RATE_LIMIT_REQUESTS_PER_MINUTE` | `60` | juniper-canopy |

### Logging

| Variable | Default | Options |
|----------|---------|---------|
| `JUNIPER_DATA_LOG_LEVEL` | `INFO` | DEBUG, INFO, WARNING, ERROR |
| `CASCOR_LOG_LEVEL` | `INFO` | DEBUG, INFO, WARNING, ERROR |
| `JUNIPER_DATA_LOG_FORMAT` | `text` | text, json |
| `JUNIPER_CASCOR_LOG_FORMAT` | `text` | text, json |
| `CANOPY_LOG_FORMAT` | `text` | text, json |

### Observability

| Variable | Default | Purpose |
|----------|---------|---------|
| `JUNIPER_DATA_METRICS_ENABLED` | `false` | Enable /metrics endpoint |
| `JUNIPER_CASCOR_METRICS_ENABLED` | `false` | Enable /metrics endpoint |
| `CANOPY_METRICS_ENABLED` | `false` | Enable /metrics endpoint |
| `JUNIPER_DATA_SENTRY_DSN` | (unset) | Sentry error tracking |
| `JUNIPER_CASCOR_SENTRY_DSN` | (unset) | Sentry error tracking |
| `CANOPY_SENTRY_DSN` | (unset) | Sentry error tracking |

### Demo Auto-Training

| Variable | Value |
|----------|-------|
| `JUNIPER_CASCOR_AUTO_START` | `true` |
| `JUNIPER_CASCOR_AUTO_DATASET` | `spiral` |
| `JUNIPER_CASCOR_AUTO_DATASET_PARAMS` | `{"n_spirals": 2, "n_points_per_spiral": 200, "noise": 0.15, "seed": 42}` |
| `JUNIPER_CASCOR_AUTO_NETWORK` | `{"input_size": 2, "output_size": 2, "learning_rate": 0.01}` |
| `JUNIPER_CASCOR_AUTO_TRAIN_EPOCHS` | `500` |

### Grafana

| Variable | Default | Purpose |
|----------|---------|---------|
| `GRAFANA_ADMIN_USER` | `admin` | Grafana admin username (mapped to `GF_SECURITY_ADMIN_USER`) |
| `GRAFANA_ADMIN_PASSWORD` | `admin` | Grafana admin password fallback value |
| `GF_SECURITY_ADMIN_PASSWORD__FILE` | `/run/secrets/grafana_admin_password` | Preferred password source via Docker secret |

---

## Makefile Targets

### Lifecycle

| Target | Description |
|--------|-------------|
| `make up` | Start full stack (detached) |
| `make down` | Stop all containers (all profiles) |
| `make restart` | Restart all services |
| `make demo` | Start demo profile |
| `make dev` | Start dev profile |

### Logs

| Target | Description |
|--------|-------------|
| `make logs` | Tail all service logs (follow) |
| `make logs-data` | Tail juniper-data logs |
| `make logs-cascor` | Tail juniper-cascor logs |
| `make logs-canopy` | Tail juniper-canopy logs |

### Health and Status

| Target | Description |
|--------|-------------|
| `make status` | Show container status |
| `make ps` | Compact container listing |
| `make health` | Detailed health report (runs health_check.sh) |
| `make wait` | Block until all services healthy (90s timeout) |

### Build

| Target | Description |
|--------|-------------|
| `make build` | Build/rebuild all images |
| `make build-no-cache` | Full rebuild without Docker cache |

### Shell and Cleanup

| Target | Description |
|--------|-------------|
| `make shell-data` | Exec into juniper-data container |
| `make shell-cascor` | Exec into juniper-cascor container |
| `make shell-canopy` | Exec into juniper-canopy container |
| `make clean` | Remove containers, volumes, local images (confirmation prompt) |

---

## Health Endpoints

### Per-Service Endpoints

| Endpoint | Purpose | Response Key |
|----------|---------|-------------|
| `/v1/health` | Liveness probe | `status` |
| `/v1/health/live` | Liveness alias | `status` |
| `/v1/health/ready` | Readiness probe | `status`, dependencies |

### Response Formats

**juniper-data:**
```json
{"status": "ok", "version": "0.4.x"}
```

**juniper-cascor:**
```json
{"status": "success", "data": {"status": "ready", "version": "0.3.x"}, "meta": {...}}
```

**juniper-canopy:**
```json
{"status": "healthy", "version": "0.2.x", "active_connections": 0, "demo_mode": false}
```

---

## Docker Healthcheck Configuration

| Setting | Value |
|---------|-------|
| Interval | 15 seconds |
| Timeout | 10 seconds |
| Start period | 10-20 seconds (varies by service) |
| Retries | 5 |
| Command | Python `urllib.request.urlopen` to `/v1/health` |

---

## Network Architecture

### Docker Internal DNS

| Service Name | Internal URL |
|-------------|--------------|
| `juniper-data` | `http://juniper-data:8100` |
| `juniper-cascor` | `http://juniper-cascor:8200` |
| `juniper-canopy` | `http://juniper-canopy:8050` |
| `prometheus` | `http://prometheus:9090` |

### Docker Networks

| Network | Type | Services |
|---------|------|----------|
| `frontend` | bridge | juniper-canopy, juniper-canopy-demo, juniper-canopy-dev |
| `backend` | bridge, internal | juniper-cascor, juniper-cascor-demo, juniper-canopy, juniper-canopy-demo, redis, cassandra, prometheus |
| `data` | bridge, internal | juniper-data, juniper-cascor, juniper-cascor-demo, juniper-canopy, juniper-canopy-demo, prometheus |
| `monitoring` | bridge | prometheus, grafana |

### Host-Side URLs

| Service | URL |
|---------|-----|
| juniper-data | http://localhost:8100 |
| juniper-cascor | http://localhost:8201 |
| juniper-canopy | http://localhost:8050 |
| Prometheus | http://localhost:9090 |
| Grafana | http://localhost:3000 |

---

## Scripts Reference

| Script | Purpose | Default Timeout |
|--------|---------|-----------------|
| `scripts/health_check.sh` | Formatted health report for all services | 5s per service |
| `scripts/wait_for_services.sh [TIMEOUT]` | Block until all services healthy | 90s |
| `scripts/test_demo_profile.sh` | End-to-end demo profile test (7 steps) | 120s |
| `scripts/test_health_enhanced.sh` | Enhanced health response validation (8 steps) | -- |

---

## Prometheus Configuration

**File:** `prometheus/prometheus.yml`

| Setting | Value |
|---------|-------|
| Global scrape interval | 15 seconds |
| Metrics path | `/metrics` |

### Scrape Targets

| Job | Target |
|-----|--------|
| `juniper-data` | `juniper-data:8100` |
| `juniper-cascor` | `juniper-cascor:8200` |
| `juniper-canopy` | `juniper-canopy:8050` |

---

## Grafana Configuration

**File:** `grafana/provisioning/datasources/prometheus.yml`

| Setting | Value |
|---------|-------|
| Datasource name | Prometheus |
| Type | prometheus |
| Access | proxy |
| URL | `http://prometheus:9090` |
| Default | Yes |

---

## Test Configuration

### Test Dependencies

```
pytest>=7.4
requests>=2.31
numpy>=1.24
```

### Test Environment Variables

| Variable | Default | Purpose |
|----------|---------|---------|
| `JUNIPER_TEST_DATA_URL` | `http://localhost:8100` | Override data service URL |
| `JUNIPER_TEST_CASCOR_URL` | `http://localhost:8200` | Override cascor service URL |
| `JUNIPER_TEST_CANOPY_URL` | `http://localhost:8050` | Override canopy service URL |
| `JUNIPER_TEST_DATA_API_KEY` | (empty) | API key for test requests to data |
| `JUNIPER_TEST_CASCOR_API_KEY` | (empty) | API key for test requests to cascor |
| `JUNIPER_TEST_CANOPY_API_KEY` | (empty) | API key for test requests to canopy |

### Test Markers

| Marker | Purpose |
|--------|---------|
| `@pytest.mark.health` | Health endpoint tests |
| `@pytest.mark.data` | Data service tests |
| `@pytest.mark.full_stack` | Full stack integration tests |

### Test Files

| File | Tests | Purpose |
|------|-------|---------|
| `tests/test_health.py` | ~25 | Health endpoints for all services |
| `tests/test_data_service.py` | ~20 | Dataset lifecycle and generator tests |
| `tests/test_full_stack.py` | ~25 | Cross-service integration (data → cascor → canopy) |

---

**Last Updated:** April 1, 2026
**Version:** 0.1.0
**Maintainer:** Paul Calnon
