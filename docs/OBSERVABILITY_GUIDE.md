# Juniper Observability Guide

**Last Updated**: 2026-03-05
**Version**: 1.0.0
**Status**: Current

---

## Overview

The Juniper observability stack provides monitoring, metrics, and dashboarding across all three services using:

- **Prometheus** — Metrics collection and time-series storage (port 9090)
- **Grafana** — Pre-built dashboards and visualization (port 3000)
- **Structured JSON logging** — Per-service structured log output
- **Sentry** — Error tracking and alerting (optional, requires DSN)

All services expose a `/metrics` endpoint with namespaced Prometheus metrics. The observability stack runs as a composable Docker Compose profile alongside `full`, `demo`, or `dev` profiles.

---

## Quick Start

```bash
# Start full stack with monitoring
make obs

# Or start demo stack with monitoring
make obs-demo

# Access dashboards
# Grafana:    http://localhost:3000  (admin / admin)
# Prometheus: http://localhost:9090

# Stop everything
make down
```

The `make obs` and `make obs-demo` targets automatically:
- Load `.env.observability` which sets `*_METRICS_ENABLED=true` for all services
- Activate the `observability` profile (Prometheus + Grafana)
- Activate the `full` or `demo` profile respectively

---

## Architecture

```
                                 ┌──────────────┐
                                 │   Grafana     │
                                 │  :3000        │
                                 │  (dashboards) │
                                 └──────┬───────┘
                                        │ queries
                                 ┌──────▼───────┐
                                 │  Prometheus   │
                                 │  :9090        │
                                 │  (storage)    │
                                 └──┬───┬───┬───┘
                        scrape /    │   │   │    \ scrape
                   ┌────────────────┘   │   └────────────────┐
                   │                    │                     │
            ┌──────▼───────┐    ┌──────▼───────┐    ┌───────▼──────┐
            │ juniper-data │    │juniper-cascor│    │juniper-canopy│
            │ :8100        │    │ :8200        │    │ :8050        │
            │ /metrics     │    │ /metrics     │    │ /metrics     │
            └──────────────┘    └──────────────┘    └──────────────┘
```

**Data flow**:
1. Each service exposes a `/metrics` endpoint (gated by `*_METRICS_ENABLED=true`)
2. Prometheus scrapes each service at configured intervals (10-15s)
3. Grafana queries Prometheus and renders pre-built dashboards
4. Dashboards auto-provision on startup from JSON files

---

## Metrics Catalog

All metrics use a service namespace prefix: `juniper_data_`, `juniper_cascor_`, `juniper_canopy_`.

### juniper-data (6 metrics)

| Metric | Type | Labels | Description |
|--------|------|--------|-------------|
| `juniper_data_http_requests_total` | Counter | `method`, `endpoint`, `status_code` | Total HTTP requests |
| `juniper_data_http_request_duration_seconds` | Histogram | `method`, `endpoint` | HTTP request latency |
| `juniper_data_dataset_generations_total` | Counter | `generator`, `status` | Dataset generation requests |
| `juniper_data_dataset_generation_duration_seconds` | Histogram | `generator` | Dataset generation duration |
| `juniper_data_datasets_cached` | Gauge | — | Datasets currently cached |
| `juniper_data_build_info` | Info | `version`, `python_version` | Build metadata |

### juniper-cascor (11 metrics)

| Metric | Type | Labels | Description |
|--------|------|--------|-------------|
| `juniper_cascor_http_requests_total` | Counter | `method`, `endpoint`, `status_code` | Total HTTP requests |
| `juniper_cascor_http_request_duration_seconds` | Histogram | `method`, `endpoint` | HTTP request latency |
| `juniper_cascor_training_sessions_active` | Gauge | — | Active training sessions |
| `juniper_cascor_training_epochs_total` | Counter | `phase` | Completed training epochs |
| `juniper_cascor_training_loss` | Gauge | `phase`, `loss_type` | Current training loss |
| `juniper_cascor_training_accuracy_ratio` | Gauge | `phase` | Current accuracy (0-1) |
| `juniper_cascor_hidden_units_total` | Gauge | — | Hidden units in cascade network |
| `juniper_cascor_candidate_correlation` | Gauge | — | Best candidate correlation |
| `juniper_cascor_inference_requests_total` | Counter | — | Inference requests processed |
| `juniper_cascor_inference_duration_seconds` | Histogram | — | Inference latency |
| `juniper_cascor_build_info` | Info | `version`, `python_version` | Build metadata |

### juniper-canopy (6 metrics)

| Metric | Type | Labels | Description |
|--------|------|--------|-------------|
| `juniper_canopy_http_requests_total` | Counter | `method`, `endpoint`, `status_code` | Total HTTP requests |
| `juniper_canopy_http_request_duration_seconds` | Histogram | `method`, `endpoint` | HTTP request latency |
| `juniper_canopy_websocket_connections_active` | Gauge | `channel` | Active WebSocket connections |
| `juniper_canopy_websocket_messages_total` | Counter | `channel`, `type` | WebSocket messages sent/received |
| `juniper_canopy_demo_mode_active` | Gauge | — | Demo mode status (1=active, 0=inactive) |
| `juniper_canopy_build_info` | Info | `version`, `python_version` | Build metadata |

---

## Grafana Dashboards

Four dashboards are auto-provisioned into the "Juniper" folder on startup. All use template variables `$datasource` and `$interval` for flexibility.

### Juniper Overview (Home Dashboard)

**UID**: `juniper-overview`
**File**: `grafana/provisioning/dashboards/juniper-overview.json`

Cross-service overview with four rows:
- **Service Status** — UP/DOWN stat panels for each service
- **Request Rate** — HTTP requests per second across all services
- **Error Rate** — 4xx/5xx error percentage per service
- **Latency** — p50, p95, p99 response time percentiles

### JuniperData

**UID**: `juniper-data`
**File**: `grafana/provisioning/dashboards/juniper-data.json`

Service-specific dashboard:
- RED overview stats (rate, errors, duration)
- HTTP metrics by endpoint with duration heatmap
- Dataset generation metrics (by generator type, duration distribution)
- Cached datasets gauge
- Build info

### JuniperCascor

**UID**: `juniper-cascor`
**File**: `grafana/provisioning/dashboards/juniper-cascor.json`

Service-specific dashboard:
- RED overview stats
- HTTP metrics by endpoint with duration heatmap
- Training metrics (active sessions, hidden units, epochs)
- Loss by phase/loss_type and accuracy by phase
- Candidate correlation
- Inference rate and latency
- Build info

### JuniperCanopy

**UID**: `juniper-canopy`
**File**: `grafana/provisioning/dashboards/juniper-canopy.json`

Service-specific dashboard:
- RED overview stats
- HTTP metrics by endpoint with duration heatmap
- WebSocket metrics (active connections by channel, messages by channel/type)
- Demo mode status (LIVE/DEMO indicator)
- Build info

---

## Adding Custom Metrics

### Step 1: Define the metric

In the service's `observability.py` (or equivalent module):

```python
from prometheus_client import Counter, Gauge, Histogram, Info

# Use the service namespace prefix
my_counter = Counter(
    "juniper_data_my_operations_total",
    "Total operations processed",
    ["operation_type"],
)
```

### Step 2: Instrument the code

In the route handler or business logic:

```python
from .observability import my_counter

@router.post("/v1/my-endpoint")
async def my_endpoint(request: Request):
    my_counter.labels(operation_type="create").inc()
    # ... handler logic
```

### Step 3: Verify

```bash
# Start the stack with observability
make obs

# Check the metric appears
curl -s http://localhost:8100/metrics | grep my_operations
```

### Metric type selection guide

| Type | Use When | Example |
|------|----------|---------|
| **Counter** | Value only goes up | Request counts, error counts |
| **Gauge** | Value goes up and down | Active connections, cache size |
| **Histogram** | Measuring distributions | Request duration, payload size |
| **Info** | Static key-value labels | Version, build metadata |

---

## Adding a Grafana Dashboard

1. Create a JSON file in `juniper-deploy/grafana/provisioning/dashboards/`
2. Set a unique `uid` and `title` in the dashboard JSON
3. Reference the Prometheus datasource by UID:
   ```json
   "datasource": {
     "type": "prometheus",
     "uid": "prometheus"
   }
   ```
4. Include template variables for `$datasource` and `$interval`
5. Use schema version 39 for compatibility
6. The dashboard auto-loads within 30 seconds (configurable via `updateIntervalSeconds` in `dashboard-providers.yml`)

Tip: Export an existing dashboard from the Grafana UI (Dashboard Settings > JSON Model) as a starting point.

---

## Prometheus Configuration

**File**: `juniper-deploy/prometheus/prometheus.yml`

### Global settings

```yaml
global:
  scrape_interval: 15s       # Default scrape interval
  evaluation_interval: 15s   # Rule evaluation interval
  scrape_timeout: 10s        # Per-scrape timeout
```

### Scrape jobs

| Job | Target | Interval | Labels |
|-----|--------|----------|--------|
| `prometheus` | `localhost:9090` | 15s (default) | — |
| `juniper-data` | `juniper-data:8100` | 10s | `service: juniper-data`, `environment: docker` |
| `juniper-cascor` | `juniper-cascor:8200` | 10s | `service: juniper-cascor`, `environment: docker` |
| `juniper-canopy` | `juniper-canopy:8050` | 15s | `service: juniper-canopy`, `environment: docker` |

### Checking targets

Visit http://localhost:9090/targets to see all scrape targets and their status. All targets should show "UP" when the stack is running.

---

## Environment Variables

### Metrics enablement

| Variable | Service | Default | Description |
|----------|---------|---------|-------------|
| `JUNIPER_DATA_METRICS_ENABLED` | juniper-data | `false` | Enable `/metrics` endpoint |
| `JUNIPER_CASCOR_METRICS_ENABLED` | juniper-cascor | `false` | Enable `/metrics` endpoint |
| `JUNIPER_CANOPY_METRICS_ENABLED` | juniper-canopy | `false` | Enable `/metrics` endpoint |

When using `make obs` or `make obs-demo`, these are automatically set to `true` via `.env.observability`.

### Grafana

| Variable | Default | Description |
|----------|---------|-------------|
| `GRAFANA_ADMIN_USER` | `admin` | Grafana admin username |
| `GRAFANA_ADMIN_PASSWORD` | `admin` | Grafana admin password |

### Logging

| Variable | Service | Default | Description |
|----------|---------|---------|-------------|
| `JUNIPER_DATA_LOG_FORMAT` | juniper-data | `text` | Log format (`text` or `json`) |
| `JUNIPER_CASCOR_LOG_FORMAT` | juniper-cascor | `text` | Log format (`text` or `json`) |
| `JUNIPER_CANOPY_LOG_FORMAT` | juniper-canopy | `text` | Log format (`text` or `json`) |
| `JUNIPER_DATA_LOG_LEVEL` | juniper-data | `INFO` | Log level |
| `JUNIPER_CASCOR_LOG_LEVEL` | juniper-cascor | `INFO` | Log level |

### Sentry

| Variable | Service | Description |
|----------|---------|-------------|
| `JUNIPER_DATA_SENTRY_DSN` | juniper-data | Sentry DSN (unset = disabled) |
| `JUNIPER_CASCOR_SENTRY_DSN` | juniper-cascor | Sentry DSN (unset = disabled) |
| `JUNIPER_CANOPY_SENTRY_DSN` | juniper-canopy | Sentry DSN (unset = disabled) |

---

## Troubleshooting

### Metrics not appearing in Prometheus

1. **Check `*_METRICS_ENABLED`** — Verify the env var is set to `true`. If using `make obs`, this is automatic via `.env.observability`.
2. **Check Prometheus targets** — Visit http://localhost:9090/targets. All jobs should show "UP".
3. **Curl the metrics endpoint** — `curl http://localhost:8100/metrics` should return Prometheus text format.
4. **Check service logs** — `make logs-data` to see if the metrics middleware loaded.

### Grafana shows "No data"

1. **Check time range** — Metrics only exist from when the stack started. Set time range to "Last 15 minutes".
2. **Check datasource** — Go to Settings > Data Sources > Prometheus. Test connection should succeed.
3. **Check PromQL** — Edit the panel and run the query manually in Prometheus (http://localhost:9090/graph).
4. **Check dashboard variables** — Ensure `$datasource` is set to "Prometheus" and `$interval` is reasonable.

### Prometheus target shows "DOWN"

1. **Service not running** — `make ps` to check container status.
2. **Metrics not enabled** — The service's `/metrics` endpoint returns 404 when `METRICS_ENABLED=false`.
3. **Network issue** — Prometheus connects via Docker network using container names (e.g., `juniper-data:8100`). Ensure all services are on the same Docker network.

### Custom metric not being scraped

1. **Metric not registered** — Ensure the metric is defined at module level (not inside a function/class).
2. **Service not restarted** — After adding a metric, rebuild and restart: `make build && make obs`.
3. **Metric name conflict** — Prometheus rejects metrics with duplicate names. Check for collisions.

### Grafana dashboards not loading

1. **Check provisioning** — `docker exec juniper-grafana ls /etc/grafana/provisioning/dashboards/` should list JSON files.
2. **Check dashboard-providers.yml** — Ensure the path points to `/etc/grafana/provisioning/dashboards`.
3. **Check Grafana logs** — `docker logs juniper-grafana` for provisioning errors.
4. **JSON syntax error** — Validate with `python -m json.tool < dashboard.json`.
