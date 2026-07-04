# User Manual

## Comprehensive Guide to juniper-deploy

**Version:** 0.2.1
**Status:** Active
**Last Updated:** July 4, 2026
**Project:** Juniper - Docker Compose & Kubernetes Orchestration

---

## Table of Contents

- [Introduction](#introduction)
- [Profiles](#profiles)
- [Service Management](#service-management)
- [Demo Mode](#demo-mode)
- [Kubernetes Deployment](#kubernetes-deployment)
- [Monitoring and Observability](#monitoring-and-observability)
- [Security](#security)
- [Logging](#logging)
- [Health Checks](#health-checks)
- [Scripts](#scripts)
- [Container Shell Access](#container-shell-access)
- [Cleanup](#cleanup)
- [Advanced Configuration](#advanced-configuration)
- [Troubleshooting](#troubleshooting)

---

## Introduction

juniper-deploy orchestrates the full Juniper stack using Docker Compose and Kubernetes (Helm). It provides multiple deployment profiles, health monitoring, observability infrastructure, and integration testing.

### What It Manages

- **juniper-data** (port 8100) -- Dataset generation REST API
- **juniper-cascor** (port 8200) -- CasCor neural network training service
- **juniper-canopy** (port 8050) -- Real-time monitoring dashboard
- **juniper-cascor-worker** -- Distributed training workers (WebSocket clients, no exposed port)
- **Prometheus** (port 9090) -- Metrics collection
- **Grafana** (host port 3001 by default; container port 3000) -- Metrics visualization

### Deployment Modes

| Mode | Tool | Location |
|------|------|----------|
| **Docker Compose** | `docker compose` / `make` | `docker-compose.yml` |
| **Kubernetes** | `helm` | `k8s/helm/juniper/` |

---

## Profiles

juniper-deploy uses Docker Compose profiles to support different deployment scenarios.

### Full Stack

```bash
make up
```

Starts all three core services in production-like configuration. Services start in dependency order: data -> cascor -> canopy.

### Demo

```bash
make demo
```

Self-running demonstration:

1. **juniper-data** starts and becomes healthy
2. **demo-seed** creates a spiral dataset (2 spirals, 200 points, noise=0.15, seed=42) and exits
3. **juniper-cascor-demo** starts with auto-training enabled (500 epochs)
4. **juniper-canopy-demo** connects to the demo CasCor instance

The demo profile is fully self-contained -- no manual interaction required.

### Dev

```bash
make dev
```

Frontend development mode. Starts juniper-data and juniper-cascor as real services, but runs juniper-canopy in demo mode (`JUNIPER_CANOPY_DEMO_MODE=true`). The dashboard generates synthetic data locally and does not depend on backend state.

### Observability

```bash
docker compose --profile observability up -d
```

Adds Prometheus, AlertManager, and Grafana. Can be combined with any other profile.

### Profile Matrix

| Service | full | demo | dev | observability |
|---------|------|------|-----|---------------|
| juniper-data | Y | Y | Y | -- |
| juniper-cascor | Y | -- | Y | -- |
| juniper-cascor-demo | -- | Y | -- | -- |
| juniper-canopy | Y | -- | -- | -- |
| juniper-canopy-demo | -- | Y | -- | -- |
| juniper-canopy-dev | -- | -- | Y | -- |
| juniper-cascor-worker | Y | -- | -- | -- |
| demo-seed | -- | Y | -- | -- |
| prometheus | -- | -- | -- | Y |
| grafana | -- | -- | -- | Y |

---

## Service Management

### Start

```bash
make up          # Full stack
make demo        # Demo profile
make dev         # Dev profile
```

### Stop

```bash
make down        # Stops all profiles
```

### Restart

```bash
make restart     # Restart all services
```

### Status

```bash
make status      # Container status with health
make ps          # Compact listing
```

### Build

```bash
make build           # Build/rebuild images
make build-no-cache  # Full rebuild without cache
```

---

## Demo Mode

### How Demo Seeding Works

The `demo-seed` container:

1. Waits for juniper-data health (up to 30 retries, 2s apart)
2. Creates a spiral dataset via `POST /v1/datasets` with `persist=True`
3. Exits with code 0 on success

### Auto-Training Configuration

`juniper-cascor-demo` starts training automatically using these environment variables:

| Variable | Value |
|----------|-------|
| `JUNIPER_CASCOR_AUTO_START` | `true` |
| `JUNIPER_CASCOR_AUTO_DATASET` | `spiral` |
| `JUNIPER_CASCOR_AUTO_DATASET_PARAMS` | `{"n_spirals": 2, "n_points_per_spiral": 200, "noise": 0.15, "seed": 42}` |
| `JUNIPER_CASCOR_AUTO_NETWORK` | `{"input_size": 2, "output_size": 2, "learning_rate": 0.01}` |
| `JUNIPER_CASCOR_AUTO_TRAIN_EPOCHS` | `500` |

### Verifying Demo State

```bash
# Check demo-seed completed
docker compose --profile demo ps demo-seed
# Should show Exited (0)

# Check training is active
curl http://localhost:8200/v1/training/status
```

---

## Kubernetes Deployment

The Juniper stack can be deployed to Kubernetes using the Helm chart at `k8s/helm/juniper/`.

### Prerequisites

- Helm >= 3.0
- A Kubernetes cluster (kind, minikube, EKS, GKE, AKS, etc.)
- Container images built and accessible to the cluster

### Installation

```bash
# Build subchart dependencies (Redis, etc.)
helm dependency build k8s/helm/juniper/

# Install with defaults
helm install juniper k8s/helm/juniper/

# Install with production overlay (JSON logs, metrics, TLS, scaled workers)
helm install juniper k8s/helm/juniper/ -f k8s/helm/juniper/values-production.yaml

# Install in demo mode (auto-start training, no workers)
helm install juniper k8s/helm/juniper/ -f k8s/helm/juniper/values-demo.yaml
```

### What Gets Deployed

| Resource | Count | Details |
|----------|-------|---------|
| Deployments | 4 | data, cascor, canopy, worker |
| Services | 3 | ClusterIP for data (:8100), cascor (:8200), canopy (:8050) |
| Ingress | 1 | canopy (public) + optional cascor |
| PVCs | 3 | datasets (5Gi), snapshots (10Gi), logs (2Gi) |
| Secret | 1 | 7 keys, file-mounted at `/etc/juniper/secrets/` |
| HPA | 1 | Worker auto-scaling (2-8 replicas, CPU-based) |
| NetworkPolicies | 5 | Default deny + per-service allowlists |
| ServiceMonitors | 3 | Prometheus Operator (conditional) |

### Dependency Ordering

Kubernetes does not have Docker Compose's `depends_on`. Instead, each Deployment uses **initContainers** that poll upstream health endpoints before the main container starts:

| Service | Waits For |
|---------|-----------|
| juniper-data | Nothing (starts first) |
| juniper-cascor | juniper-data `/v1/health` |
| juniper-canopy | juniper-data + juniper-cascor `/v1/health` |
| juniper-cascor-worker | juniper-cascor `/v1/health` |

### Secrets

The Helm chart preserves the existing `_FILE` env var pattern from Docker Compose. Secrets are mounted as files at `/etc/juniper/secrets/` (instead of Docker's `/run/secrets/`):

```bash
# Provide secrets at install time
helm install juniper k8s/helm/juniper/ \
  --set-file secrets.data.juniper_data_api_keys=secrets/juniper_data_api_keys.txt \
  --set-file secrets.data.juniper_cascor_api_keys=secrets/juniper_cascor_api_keys.txt

# Or use a pre-existing Kubernetes Secret
helm install juniper k8s/helm/juniper/ \
  --set secrets.create=false \
  --set secrets.existingSecret=my-vault-secret
```

### Worker Auto-Scaling

Workers scale automatically via HPA based on CPU utilization:

```yaml
# values.yaml (defaults)
worker:
  replicaCount: 2
  autoscaling:
    enabled: true
    minReplicas: 2
    maxReplicas: 8
    targetCPUUtilizationPercentage: 70
```

### Network Policies

When `networkPolicies.enabled: true` (default), the chart enforces network segmentation matching the Docker Compose network topology:

| Pod | Ingress From | Egress To |
|-----|-------------|-----------|
| data | cascor, canopy, prometheus | DNS |
| cascor | canopy, worker, prometheus | data, DNS |
| canopy | all (ingress controller) | data, cascor, redis, DNS |
| worker | none | cascor, DNS |

### Subchart Dependencies

| Subchart | Default | Purpose |
|----------|---------|---------|
| Redis (Bitnami) | enabled | Session/cache for canopy |
| Cassandra (Bitnami) | disabled | Metrics storage |
| kube-prometheus-stack | disabled | Prometheus + Grafana |

### Managing the Release

```bash
# Check status
helm status juniper

# Upgrade with new values
helm upgrade juniper k8s/helm/juniper/ -f k8s/helm/juniper/values-production.yaml

# Run connectivity tests
helm test juniper

# Uninstall
helm uninstall juniper
```

### Local Cluster Testing

```bash
# Automated test with kind (builds images, installs chart, validates health)
bash scripts/test_k8s.sh --driver kind

# Keep cluster running after test for debugging
bash scripts/test_k8s.sh --driver kind --no-teardown
```

---

## Monitoring and Observability

### Enabling Metrics

Set these in `.env`:

```bash
JUNIPER_DATA_METRICS_ENABLED=true
JUNIPER_CASCOR_METRICS_ENABLED=true
CANOPY_METRICS_ENABLED=true
```

All services expose metrics at `/metrics`.

When using `make obs` or `make obs-demo`, `.env.observability` also sets the metrics trusted-IP allowlists. Those allowlists are pinned to the static Docker subnets in `docker-compose.yml`:

| Target | Trusted networks |
|--------|------------------|
| juniper-data | `backend` (`172.28.0.0/16`) + `data` (`172.29.0.0/16`) + loopback |
| juniper-cascor | `backend` + `data` + `frontend` (`172.30.0.0/16`) + loopback |
| juniper-canopy | `backend` + `data` + `frontend` + loopback |

Treat these CIDRs as **network-scope authorization** for Prometheus scraping, not per-host authentication. The `monitoring` subnet (`172.31.0.0/16`) is intentionally not trusted by the service metrics endpoints because no scrape target lives there.

### Prometheus

- **URL**: http://localhost:9090
- **Config**: `prometheus/prometheus.yml`
- **Scrape interval**: 15 seconds
- **Targets**: juniper-data:8100, juniper-cascor:8200, juniper-canopy:8050

### Grafana

- **URL**: http://localhost:3001
- **Default credentials**: admin / value from `secrets/grafana_admin_password.txt`
- **Datasource**: Prometheus (pre-configured)
- **Dashboards**: Auto-provisioned into the "Juniper" folder

### Sentry Integration

Optional error tracking. Set DSN per service:

```bash
JUNIPER_DATA_SENTRY_DSN=https://...@sentry.io/...
JUNIPER_CASCOR_SENTRY_DSN=https://...@sentry.io/...
CANOPY_SENTRY_DSN=https://...@sentry.io/...
```

---

## Security

### Deployment Trust Boundary

Published Juniper service ports bind to `127.0.0.1` by default through `${BIND_HOST:-127.0.0.1}`. This loopback bind is part of the stack's current trust boundary: the browser-facing training-control surface is intended for single-user or trusted-host operation unless a fronting authenticating proxy is present.

Set `BIND_HOST=0.0.0.0` only when an authenticating reverse proxy is the only external entry point. The proxy requirement is not provided by this compose stack today; see `notes/DEPLOYMENT_TRUST_CONTRACT_2026-07-04.md` for the full contract and deferred bind-guard/proxy work.

### API Key Authentication

Each service can independently require API keys:

```bash
# Service-level keys (protect external access)
JUNIPER_DATA_API_KEYS=key1,key2
JUNIPER_CASCOR_API_KEYS=key1
CANOPY_API_KEY=key1

# Inter-service keys (internal communication)
JUNIPER_DATA_API_KEY=data-key       # cascor → data
JUNIPER_CASCOR_API_KEY=cascor-key   # canopy → cascor
```

Leave empty to disable authentication.

### Rate Limiting

```bash
JUNIPER_CASCOR_RATE_LIMIT_ENABLED=true
JUNIPER_CASCOR_RATE_LIMIT_REQUESTS_PER_MINUTE=60
CANOPY_RATE_LIMIT_ENABLED=true
CANOPY_RATE_LIMIT_REQUESTS_PER_MINUTE=60
```

### Secrets Management

juniper-deploy supports SOPS encryption for secrets:

```bash
cp .env.secrets.example .env.secrets
# Edit with your keys
# Encrypt: sops -e .env.secrets > .env.secrets.enc
```

---

## Logging

### Log Levels

```bash
JUNIPER_DATA_LOG_LEVEL=INFO    # DEBUG, INFO, WARNING, ERROR
CASCOR_LOG_LEVEL=INFO
```

### Log Format

```bash
JUNIPER_DATA_LOG_FORMAT=text   # text (human-readable) or json (structured)
JUNIPER_CASCOR_LOG_FORMAT=text
CANOPY_LOG_FORMAT=text
```

### Viewing Logs

```bash
make logs           # All services (follow)
make logs-data      # juniper-data only
make logs-cascor    # juniper-cascor only
make logs-canopy    # juniper-canopy only
```

---

## Health Checks

### Docker-Level Health

Each service has a Docker healthcheck configured:

| Setting | Value |
|---------|-------|
| Interval | 15 seconds |
| Timeout | 10 seconds |
| Start period | 10-20 seconds |
| Retries | 5 |

### Application-Level Health

| Endpoint | Purpose |
|----------|---------|
| `/v1/health` | Liveness probe |
| `/v1/health/live` | Liveness alias |
| `/v1/health/ready` | Readiness probe (includes dependency status) |

### Health Commands

```bash
make health   # Detailed report (runs health_check.sh)
make wait     # Block until all services healthy (90s timeout)
```

---

## Scripts

### health_check.sh

Queries `/v1/health/ready` on all services and displays a formatted report with status, version, latency, and dependency health.

```bash
bash scripts/health_check.sh
```

### wait_for_services.sh

Polls health endpoints until all services are healthy or timeout.

```bash
bash scripts/wait_for_services.sh [TIMEOUT_SECONDS]
# Default: 90 seconds, poll interval: 3 seconds
```

### test_demo_profile.sh

End-to-end test of the demo profile (7 steps: config validation, start, wait, seed check, training check, dashboard check, shutdown).

```bash
bash scripts/test_demo_profile.sh
```

### test_health_enhanced.sh

Validates enhanced health check response format across all services (8 steps).

```bash
bash scripts/test_health_enhanced.sh
```

---

## Container Shell Access

```bash
make shell-data      # Exec into juniper-data container
make shell-cascor    # Exec into juniper-cascor container
make shell-canopy    # Exec into juniper-canopy container
```

---

## Cleanup

```bash
make clean    # Remove containers, volumes, and local images (prompts for confirmation)
```

---

## Advanced Configuration

### Inter-Service URLs

Docker Compose creates an internal network. Services reference each other by container name:

| From | To | URL |
|------|----|-----|
| juniper-cascor | juniper-data | `http://juniper-data:8100` |
| juniper-canopy | juniper-data | `http://juniper-data:8100` |
| juniper-canopy | juniper-cascor | `http://juniper-cascor:8200` |
| Prometheus | All services | Container name + port |

### Custom Service Ports

Override in `.env`:

```bash
JUNIPER_DATA_PORT=9100
CASCOR_PORT=9200
CANOPY_PORT=9050
```

### Combining Profiles

```bash
# Full stack with monitoring
docker compose --profile full --profile observability up -d

# Demo with monitoring
docker compose --profile demo --profile observability up -d
```

---

## Troubleshooting

### Service Dependency Failures

Services start in dependency order. If cascor fails to start, check that juniper-data is healthy:

```bash
docker compose logs juniper-data
curl http://localhost:8100/v1/health
```

### Port Conflicts

```bash
ss -tlnp | grep -E '8100|8200|8050|9090|9093|3001'
```

Stop conflicting services or change ports in `.env`.

### Image Build Failures

Ensure sibling repos are checked out:

```bash
ls ../juniper-data/Dockerfile ../juniper-cascor/Dockerfile ../juniper-canopy/Dockerfile
```

If builds fail, try a clean rebuild:

```bash
make build-no-cache
```

### Demo Seed Not Working

```bash
docker compose --profile demo logs demo-seed
```

The seed container retries up to 30 times. If it fails, juniper-data may not be healthy.

### Memory Issues

If services are killed by OOM, increase Docker's memory limit. The full stack requires approximately 4 GB RAM.

---

**Last Updated:** July 4, 2026
**Version:** 0.2.1
**Maintainer:** Paul Calnon
