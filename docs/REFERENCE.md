# Reference

## juniper-deploy Technical Reference

**Version:** 0.2.2
**Status:** Active
**Last Updated:** October 8, 2026
**Project:** Juniper - Docker Compose & Kubernetes Orchestration

---

## Table of Contents

- [Service Reference](#service-reference)
- [Profile Reference](#profile-reference)
- [Environment Variables](#environment-variables)
- [Makefile Targets](#makefile-targets)
- [Health Endpoints](#health-endpoints)
- [Docker Healthcheck Configuration](#docker-healthcheck-configuration)
- [Network Architecture](#network-architecture)
- [Helm Chart Reference](#helm-chart-reference)
- [Scripts Reference](#scripts-reference)
- [Prometheus Configuration](#prometheus-configuration)
- [Grafana Configuration](#grafana-configuration)
- [Environment Variable Reference](#environment-variable-reference)
- [Directory Layout Reference](#directory-layout-reference)
- [Claude Code Workflow](#claude-code-workflow)
- [Security Architecture Reference](#security-architecture-reference)
- [Testing Reference](#testing-reference)
- [Documentation Reference](#documentation-reference)
- [Test Configuration](#test-configuration)

---

## Project Overview Reference

Relocated verbatim from `AGENTS.md` (P3 of the shared-session-memory plan) so it is read on demand rather than loaded into every session.

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

> **Correction (2026-09-02): the three reasons above are mostly out of date — the advice is not.**
> Checked against `docker-compose.yml` rather than inherited: both `juniper-cascor-demo` and
> `juniper-canopy-demo` **do** carry a `secrets:` block and an `*_API_KEY_FILE` var, and **do** set
> `*_RATE_LIMIT_ENABLED` / `*_RATE_LIMIT_REQUESTS_PER_MINUTE`. Only the observability claim still
> partly holds: the demo services set `*_METRICS_ENABLED` / `*_METRICS_TRUSTED_IPS` but, unlike
> their non-demo counterparts, set neither `*_LOG_FORMAT` nor `*_SENTRY_DSN`.
>
> Keep the directive — demo profiles seed a dataset and auto-start training, which is reason enough
> — but do not rely on the secrets/rate-limit justification, and re-derive from the compose file
> before quoting it. This note was nearly promoted into `AGENTS.md` § Hazards on the strength of its
> stated reasons; a resident directive built on a stale premise is worse than no directive.

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
| `juniper-cascor-worker` | `../juniper-cascor-worker/Dockerfile` | -- | -- | process (`kill -0 1`) |
| `demo-seed` | `python:3.12-slim` | -- | -- | -- |

### Observability Services

| Service | Image | Host Port | Purpose |
|---------|-------|-----------|---------|
| `prometheus` | `prom/prometheus:v3.10.0` | 9090 | Metrics collection |
| `alertmanager` | `prom/alertmanager:v0.27.0` | 9093 | Alert routing |
| `grafana` | `grafana/grafana:12.4.0` | 3001 (host) / 3000 (container) | Metrics visualization |

### Dependency Chain

| Service | Depends On | Condition |
|---------|-----------|-----------|
| `juniper-cascor` | `juniper-data` | `service_healthy` |
| `juniper-cascor-demo` | `juniper-data`, `demo-seed` | `service_healthy`, `service_completed_successfully` |
| `juniper-canopy` | `juniper-data`, `juniper-cascor` | `service_healthy` |
| `juniper-canopy-demo` | `juniper-data`, `juniper-cascor-demo` | `service_healthy` |
| `juniper-cascor-worker` | `juniper-cascor` | `service_healthy` |
| `demo-seed` | `juniper-data` | `service_healthy` |
| `grafana` | `prometheus` | `service_started` |

---

## Profile Reference

| Profile | Services Included |
|---------|-------------------|
| `full` | juniper-data, juniper-cascor, juniper-canopy, juniper-cascor-worker |
| `demo` | juniper-data, juniper-cascor-demo, juniper-canopy-demo, demo-seed |
| `dev` | juniper-data, juniper-cascor, juniper-canopy-dev |
| `observability` | prometheus, alertmanager, grafana |

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
| `BIND_HOST` | `127.0.0.1` | host-side bind for published ports |

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
| `JUNIPER_DATA_METRICS_TRUSTED_IPS` | loopback | Trusted CIDRs/IPs for juniper-data /metrics |
| `JUNIPER_CASCOR_METRICS_TRUSTED_IPS` | loopback | Trusted CIDRs/IPs for juniper-cascor /metrics |
| `JUNIPER_CANOPY_METRICS_TRUSTED_IPS` | loopback | Trusted CIDRs/IPs for juniper-canopy /metrics |
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

| Network | Type | Static subnet | Services |
|---------|------|---------------|----------|
| `frontend` | bridge | `172.30.0.0/16` | juniper-canopy, juniper-canopy-demo, juniper-canopy-dev, prometheus |
| `backend` | bridge, internal | `172.28.0.0/16` | juniper-cascor, juniper-cascor-demo, juniper-canopy, juniper-canopy-demo, juniper-cascor-worker, redis, prometheus |
| `data` | bridge, internal | `172.29.0.0/16` | juniper-data, juniper-cascor, juniper-cascor-demo, juniper-canopy, juniper-canopy-demo, prometheus |
| `monitoring` | bridge | `172.31.0.0/16` | prometheus, alertmanager, grafana |
| `data-egress` | bridge | `172.27.0.0/16` | juniper-data (only; its outbound route for the equities, mnist and arc_agi fetches) |

The static subnets keep Prometheus's scrape source address deterministic. `data-egress` is not a scrape path; it is pinned so dynamic IPAM cannot land on one of the other four. The CIDRs in `.env.observability` must match the pinned subnets each target shares with Prometheus:

| Metrics target | Shared networks with Prometheus | Trusted CIDRs in `.env.observability` |
|----------------|---------------------------------|----------------------------------------|
| `juniper-data` | `backend`, `data` | `172.28.0.0/16`, `172.29.0.0/16`, loopback |
| `juniper-cascor` | `backend`, `data`, `frontend` | `172.28.0.0/16`, `172.29.0.0/16`, `172.30.0.0/16`, loopback |
| `juniper-canopy` | `backend`, `data`, `frontend` | `172.28.0.0/16`, `172.29.0.0/16`, `172.30.0.0/16`, loopback |

The `monitoring` subnet is intentionally absent from those allowlists because no scrape target attaches to `monitoring`. `tests/test_compose_metrics_subnet_alignment.py` fails if a network is declared without being listed in its `EXPECTED_NETWORKS`, if a network loses its static subnet, or if the allowlist CIDRs drift from the shared-network set.

These metrics allowlists are network-scope authorization, not per-host authentication. Docker NAT can collapse clients to a bridge gateway address, so individual client identity must not be inferred from these CIDRs.

### Host-Side URLs

| Service | URL |
|---------|-----|
| juniper-data | http://localhost:8100 |
| juniper-cascor | http://localhost:8201 |
| juniper-canopy | http://localhost:8050 |
| Prometheus | http://localhost:9090 |
| AlertManager | http://localhost:9093 |
| Grafana | http://localhost:3001 |

Juniper service ports use `${BIND_HOST:-127.0.0.1}` and therefore publish to loopback by default. Setting `BIND_HOST=0.0.0.0` exposes the control surface on all host interfaces and is supported only behind a fronting authenticating proxy; see `notes/DEPLOYMENT_TRUST_CONTRACT_2026-07-04.md`.

---

## Helm Chart Reference

The Kubernetes Helm chart is located at `k8s/helm/juniper/`.

### Chart Metadata

| Field | Value |
|-------|-------|
| Chart name | `juniper` |
| API version | v2 |
| App version | 0.4.0 |
| Chart version | 0.1.0 |

### Kubernetes Resources

| Resource | Name Pattern | Condition |
|----------|-------------|-----------|
| Deployment | `<release>-juniper-data` | `data.enabled` |
| Deployment | `<release>-juniper-cascor` | `cascor.enabled` |
| Deployment | `<release>-juniper-canopy` | `canopy.enabled` |
| Deployment | `<release>-juniper-worker` | `worker.enabled` |
| Service | `<release>-juniper-data` (:8100) | `data.enabled` |
| Service | `<release>-juniper-cascor` (:8200) | `cascor.enabled` |
| Service | `<release>-juniper-canopy` (:8050) | `canopy.enabled` |
| Ingress | `<release>-juniper` | `canopy.ingress.enabled` |
| Secret | `<release>-juniper` | `secrets.create` |
| PVC | `<release>-juniper-data-datasets` | `data.persistence.datasets.enabled` |
| PVC | `<release>-juniper-cascor-snapshots` | `cascor.persistence.snapshots.enabled` — mounts `/app/cascor-snapshots`; **not** captured by the whole-tree offline backup, unlike the host/compose bind mount (accepted exception, see `values.yaml`) |
| PVC | `<release>-juniper-cascor-logs` | `cascor.persistence.logs.enabled` |
| HPA | `<release>-juniper-worker` | `worker.autoscaling.enabled` |
| NetworkPolicy | `<release>-juniper-deny-all` | `networkPolicies.enabled` |
| NetworkPolicy | `<release>-juniper-data` | `networkPolicies.enabled` + `data.enabled` |
| NetworkPolicy | `<release>-juniper-cascor` | `networkPolicies.enabled` + `cascor.enabled` |
| NetworkPolicy | `<release>-juniper-canopy` | `networkPolicies.enabled` + `canopy.enabled` |
| NetworkPolicy | `<release>-juniper-worker` | `networkPolicies.enabled` + `worker.enabled` |
| ServiceMonitor | `<release>-juniper-data` | `serviceMonitor.enabled` + `data.enabled` |
| ServiceMonitor | `<release>-juniper-cascor` | `serviceMonitor.enabled` + `cascor.enabled` |
| ServiceMonitor | `<release>-juniper-canopy` | `serviceMonitor.enabled` + `canopy.enabled` |

### Subchart Dependencies

| Subchart | Repository | Condition | Default |
|----------|-----------|-----------|---------|
| redis (Bitnami) | `oci://registry-1.docker.io/bitnamicharts` | `redis.enabled` | true |
| cassandra (Bitnami) | `oci://registry-1.docker.io/bitnamicharts` | `cassandra.enabled` | false |
| kube-prometheus-stack | `https://prometheus-community.github.io/helm-charts` | `kube-prometheus-stack.enabled` | false |

### Value Files

| File | Purpose |
|------|---------|
| `values.yaml` | Default configuration for all services and subcharts |
| `values-production.yaml` | Production overlay: JSON logs, metrics, TLS, scaled workers |
| `values-demo.yaml` | Demo overlay: auto-start training, no workers |

### Kubernetes Secret Keys

| Key | Mounted By | Env Var |
|-----|-----------|---------|
| `juniper_data_api_keys` | data, cascor | `JUNIPER_DATA_API_KEYS_FILE` |
| `juniper_cascor_api_keys` | cascor, canopy | `JUNIPER_CASCOR_API_KEYS_FILE` |
| `canopy_api_key` | canopy | `CANOPY_API_KEY_FILE` |
| `cascor_sentry_dsn` | cascor | file-mounted |
| `juniper_data_api_key` | cascor | `JUNIPER_DATA_API_KEY_FILE` |
| `cascor_auth_token` | worker | `JUNIPER_CASCOR_WORKER_AUTH_TOKEN` (env via secretKeyRef, not file) |
| `grafana_admin_password` | grafana (subchart) | -- |

All file-based secrets are mounted at `/etc/juniper/secrets/` (read-only).

### Security Context (All Pods)

| Setting | Value |
|---------|-------|
| `runAsNonRoot` | true |
| `runAsUser` | 1000 |
| `runAsGroup` | 1000 |
| `fsGroup` | 1000 |
| `readOnlyRootFilesystem` | true |
| `allowPrivilegeEscalation` | false |
| `capabilities.drop` | ALL |

---

## Scripts Reference

| Script | Purpose | Default Timeout |
|--------|---------|-----------------|
| `scripts/health_check.sh` | Formatted health report for all services | 5s per service |
| `scripts/wait_for_services.sh [TIMEOUT]` | Block until all services healthy | 90s |
| `scripts/test_demo_profile.sh` | End-to-end demo profile test (7 steps) | 120s |
| `scripts/test_health_enhanced.sh` | Enhanced health response validation (8 steps) | -- |
| `scripts/test_recurrence_snapshots.sh [--timeout SECONDS] [--keep]` | Recurrence snapshot persistence smoke: save → restart → recreate → list → restore (8 steps) | 120s per health wait |
| `scripts/test_canopy_recurrence_smoke.sh [--published] [--image SERVICE=REF] [--data-image REF] [--runner-image REF] [--timeout SECONDS] [--fit-timeout SECONDS] [--keep]` | W1.11 canopy → recurrence → juniper-data smoke: runs `tests/test_canopy_recurrence_equities_smoke.py` in the test-runner against an isolated, unpublished, renamed copy of the stack (5 steps) | 300s bring-up; 360s fit |
| `scripts/test_k8s.sh [--driver kind\|minikube] [--no-teardown]` | Kubernetes integration test (local cluster) | 300s |

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

## Environment Variable Reference

Relocated verbatim from `AGENTS.md` (P3 of the shared-session-memory plan) so it is read on demand rather than loaded into every session.

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

### Snapshot Storage

Snapshot roots are bind mounts of host directories. Each host directory must exist and be writable by the containers' uid 1000 before bring-up; `make snapshot-preflight` checks them. Persistence semantics, including juniper-recurrence's no-restore-on-boot contract: [README § Persistent Storage](../README.md#persistent-storage).

| Variable | Service | Default | Notes |
|----------|---------|---------|-------|
| `JUNIPER_CASCOR_SNAPSHOTS_HOST_DIR` | juniper-cascor, juniper-canopy | `../juniper-cascor/cascor-snapshots` | Host side of `/app/cascor-snapshots` |
| `JUNIPER_CASCOR_DEMO_SNAPSHOTS_HOST_DIR` | juniper-cascor-demo | `JUNIPER_CASCOR_SNAPSHOTS_HOST_DIR` | Demo-only override |
| `JUNIPER_RECURRENCE_SNAPSHOTS_HOST_DIR` | juniper-recurrence | `../juniper-recurrence/recurrence-snapshots` | Host side of `/app/recurrence-snapshots` (W1.12) |
| `JUNIPER_CASCOR_SNAPSHOTS_DIR` | juniper-cascor, juniper-cascor-demo | `/app/cascor-snapshots` | Set in `docker-compose.yml`; equals the mount target |
| `JUNIPER_CANOPY_SNAPSHOT_DIR` | juniper-canopy | `/app/cascor-snapshots` | Set in `docker-compose.yml`; canopy lists cascor's snapshots from here |
| `JUNIPER_RECURRENCE_SNAPSHOTS_DIR` | juniper-recurrence | `/app/recurrence-snapshots` | Set in `docker-compose.yml`; equals the mount target. Ignored by the pinned 0.5.0 image, which predates the snapshot routes |

---

---

## Directory Layout Reference

Relocated verbatim from `AGENTS.md` (P3 of the shared-session-memory plan) so it is read on demand rather than loaded into every session.

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
│   ├── test_canopy_recurrence_equities_smoke.py  # W1.11 canopy -> recurrence -> data smoke
│   ├── test_live_suite_wiring.py   # The live-module lists agree; the smoke's key wiring
│   ├── test_availability.py        # Availability checking fixtures
│   ├── test_compose_security_config.py  # Docker security regression tests
│   ├── test_compose_data_egress.py      # juniper-data's outbound-only network
│   └── test_helm_networkpolicy_data_egress.py  # the Helm half: data's 443 egress rule
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
    │   ├── claude.yml              # @claude assistant (see Claude Code workflow)
    │   ├── sequence-safety.yml     # Per-PR REQUIRED sequence-safety screens
    │   └── main-verify.yml         # Post-merge bypass-proof sequence-safety net
    ├── CODEOWNERS
    └── dependabot.yml
```

---

---

## Claude Code Workflow

`.github/workflows/claude.yml` is the `@claude` assistant for this repo. The version in force is the `# vX.Y.Z` comment on the action's `uses:` line. Dependabot's `github-actions` updates group only `github/codeql-action` (`.github/dependabot.yml`), so a bump of `anthropics/claude-code-action` arrives as its own pull request. The second gate below lives in the action's own source, so any SHA bump can change it (defaults, matcher, check order, messages, branch naming) even when the events, the job `if`, the permissions, and the `with:` inputs stay the same; re-check it at the new SHA. Verified at `v1.0.240`; `v1.0.237` behaves the same.

The file header says `ANTHROPIC_API_KEY` is an org-level secret and that this repo must be able to read it. The job passes `secrets.ANTHROPIC_API_KEY` as the action's only input, `anthropic_api_key`. The header also names `juniper-ml/.github/workflows/claude.yml` as the fleet source of truth. The behavior below is this repo's file.

### What starts the job

Workflow name `Claude Code`, job id `claude`, runner `ubuntu-latest`. The job `if` uses GitHub's `contains`, which is a case-insensitive substring test: `@Claude` starts the job too.

| Event | Types that run | Text the `if` reads |
|-------|----------------|---------------------|
| `issue_comment` | `created` | `github.event.comment.body` |
| `pull_request_review_comment` | `created` | `github.event.comment.body` |
| `pull_request_review` | `submitted` | `github.event.review.body` |
| `issues` | `opened`, `assigned` | issue `body` or `title` |

Those four texts are the whole surface. A mention in a pull request title or body has no event here (`pull_request` is not subscribed). Editing a comment or a review has no event here either.

### Permissions and checkout

| Permission | Level |
|------------|-------|
| `contents` | `write` |
| `pull-requests` | `write` |
| `issues` | `write` |
| `id-token` | `write` |
| `actions` | `read` |

The checkout step is SHA-pinned `actions/checkout` with `fetch-depth: 1`. Its version record is the comment on that `uses:` line.

`id-token: write` is used on every run that starts: no `github_token` input is passed, so the action trades the job's OIDC token for a Claude GitHub App installation token, which makes the GitHub API calls and pushes. The Claude GitHub App must be installed on this repo. The model authenticates with `ANTHROPIC_API_KEY`.

### Second gate inside the action

`contains('@claude')` only decides whether the job starts. The pinned action then applies its own checks. Inputs left unset keep the action defaults: `trigger_phrase` is `@claude`, `allowed_bots` is empty, `assignee_trigger` is empty, `prompt` is empty, `branch_prefix` is `claude/`, and `branch_name_template` is empty.

After that token exchange (a workflow-validation rejection there, expected while the workflow file itself is changing, exits green with `Skipping action due to workflow validation:`), write access is checked for `github.actor` (this workflow has no `workflow_run` event, so that is the only account):

- An admin or a writer continues.
- A login ending in `[bot]` passes this check with no API lookup.
- Anyone else fails the step with `Actor does not have write permissions to the repository`. `allowed_non_write_users` is unset, and the workflow does not pass `github_token`, so that bypass stays off.

When the actor may continue, the action looks for `@claude` as its own token. The match is case-insensitive. The token must start the text or follow whitespace, and it must end the text or be followed by whitespace or one of `. , ! ? ; :`. A miss logs `No trigger found, skipping remaining steps` and the step returns success, so the job is green and Claude does not reply.

| Text | Job | Action |
|------|-----|--------|
| `@claude please check the health endpoint` in a new comment | starts | runs |
| `@Claude` | starts | runs (both checks ignore case) |
| `see@claude` in a comment | starts | skips green for a writer (no boundary before the token); anyone else fails the write check first |
| `@claude.com` | starts | runs (`.` is an allowed terminator) |

`issues: assigned` is the sharp case. The job starts when the title or body already contains `@claude`. The action's assignee path fires only when `assignee_trigger` is set, and the title/body path runs only for `opened`. With `assignee_trigger` empty, assignment hits the successful skip above.

A `[bot]` login that passed the write check and matched the token then hits the human-actor check. Empty `allowed_bots` allows no bot, and the step throws `Workflow initiated by non-human actor:`.

A match selects tag mode (`prompt` is empty). On an open pull request Claude works on that PR's own head branch; pushes go only to this repo, so a fork PR's branch is never updated. On an issue, or a closed or merged pull request, the empty branch template becomes `claude/issue-<number>-<YYYYMMDD-HHmm>` or `claude/pr-<number>-<YYYYMMDD-HHmm>`, cut from the default branch, with a timestamp from the runner's local clock. The action's default `label_trigger` is `claude`, and this workflow has no `labeled` event, so a label alone does not start the job.

---

## Security Architecture Reference

Relocated verbatim from `AGENTS.md` (P3 of the shared-session-memory plan) so it is read on demand rather than loaded into every session.

### Network Isolation

Five Docker networks enforce service-to-service communication boundaries:

| Network | Type | Purpose | Services |
|---------|------|---------|----------|
| `frontend` | bridge | Public-facing dashboard | juniper-canopy, juniper-canopy-demo, juniper-canopy-dev |
| `backend` | **internal** | CasCor + infrastructure (no external access) | juniper-cascor, redis, prometheus |
| `data` | **internal** | JuniperData access (no external access) | juniper-data, juniper-cascor, juniper-canopy, prometheus |
| `monitoring` | bridge | Observability stack | prometheus, grafana |
| `data-egress` | bridge | juniper-data's outbound route: the `equities` / `equities_seq` generators fetch from Yahoo Finance and SEC EDGAR | juniper-data only |

Networks marked **internal** have no external connectivity — containers on these networks can only communicate with other containers on the same network. `data-egress` exists because of that (owner ruling 2026-09-24): without it, every equities request failed at DNS with a `400`, and every mnist and arc_agi request failed with a `500` after about 23 s. juniper-data publishes no port on it. Its egress is unrestricted (any port, any destination), and on Docker older than 28 with a FORWARD policy of ACCEPT a LAN host routing `172.27.0.0/16` via the Docker host could reach it. Both that protection and the internal networks' isolation assume Docker manages the host firewall (`"iptables": false` removes both). See the network's definition in `docker-compose.yml`. `tests/test_compose_data_egress.py` checks the compose file as written. It pins who attaches (with no `extends`, `include` or external alias to hide an attachment), the network's whole definition, that every service attaches to declared networks by name, that juniper-data publishes no port and overrides no DNS, and that `backend` / `data` stay internal. It is not a Compose engine.

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

---

## Testing Reference

Relocated verbatim from `AGENTS.md` (P3 of the shared-session-memory plan) so it is read on demand rather than loaded into every session.

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
| `test_canopy_recurrence_equities_smoke.py` | `full_stack` | W1.11, authenticated: select Recurrence, stage `equities_seq`, Start → 200 and a regression metrics block; juniper-data minted the staged request; juniper-data labels the dataset `regression` at generator ≥ 6.0.0. The last check FAILS against published juniper-data ≤ 0.16.0 by design, naming the version and label it saw |
| `test_live_suite_wiring.py` | — | `Dockerfile.test`'s CMD, `publish-image.yml`'s `LIVE_MODULES` and `util/check_image_test_suite.py`'s `MODULES` are identical; the test-runner's `*_API_KEY_FILE` variables name secrets it mounts, the same ones canopy and juniper-data validate; conftest's `*_FILE` parse |
| `test_availability.py` | — | Skip mechanism validation, fixture scope checks |
| `test_compose_security_config.py` | — | Docker secret wiring, network isolation, Grafana secret-only password |
| `test_compose_data_egress.py` | — | `data-egress`'s definition is pinned exactly and it is juniper-data-only; every service attaches to networks the file declares; no `extends`, `include` or external alias; juniper-data publishes no port and overrides no DNS; `backend` / `data` stay internal |
| `test_helm_networkpolicy_data_egress.py` | — | A static model of NetworkPolicy semantics (the union per pod, namespaces, `policyTypes` defaulting), failing on constructs it does not model: the data pod's effective egress is exactly DNS plus TCP 443 to public IPv4; every other Juniper pod is governed with no `ipBlock` or peerless non-DNS egress; the data pod mounts no service-account token (skips without `helm`) |

**Configurable service URLs** (via environment variables):

| Variable | Default |
|----------|---------|
| `JUNIPER_TEST_DATA_URL` | `http://localhost:8100` |
| `JUNIPER_TEST_CASCOR_URL` | `http://localhost:8201` |
| `JUNIPER_TEST_CANOPY_URL` | `http://localhost:8050` |
| `JUNIPER_TEST_DATA_API_KEY` | *(unset)* |
| `JUNIPER_TEST_CASCOR_API_KEY` | *(unset)* |
| `JUNIPER_TEST_CANOPY_API_KEY` | *(unset)* |
| `JUNIPER_TEST_DATA_API_KEY_FILE` | *(unset)*: read when the plain variable is unset; first non-comment line, first comma-separated entry. The compose `test-runner` sets it to `/run/secrets/juniper_data_api_keys` |
| `JUNIPER_TEST_CASCOR_API_KEY_FILE` | *(unset)*: as above |
| `JUNIPER_TEST_CANOPY_API_KEY_FILE` | *(unset)*: as above. The compose `test-runner` sets it to `/run/secrets/canopy_api_key` |
| `JUNIPER_TEST_RECURRENCE_SMOKE_TIMEOUT` | `360`: seconds from Start to a terminal fit status in the W1.11 smoke |

### Shell Script Tests

| Script | Purpose |
|--------|---------|
| `scripts/test_demo_profile.sh` | 7-step demo profile validation (config, start, wait, seed check, training, canopy, shutdown) |
| `scripts/test_health_enhanced.sh` | 8-step health check validation (config, start, liveness, readiness, schema, dependencies, Docker healthcheck) |
| `scripts/test_recurrence_snapshots.sh` | 8-step recurrence snapshot persistence smoke (render, bring-up, routes, train, save, restart, recreate, restore) under its own compose project, with a scratch snapshot root and throwaway keys |
| `scripts/test_canopy_recurrence_smoke.sh` | 5-step W1.11 smoke (render check, images, bring-up, images under test, the pytest module in the test-runner). Its own compose project, with every container renamed, no host port published, subnets unpinned, scratch snapshot roots and throwaway keys, so it runs beside a live stack. `--published` runs each pin by the digest GHCR serves for its tag, because a local tag can be a dev build. `--data-image` is the slip rule's "juniper-data `main`" run |

---

---

## Documentation Reference

Relocated verbatim from `AGENTS.md` (P3 of the shared-session-memory plan) so it is read on demand rather than loaded into every session.

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
| `tests/test_canopy_recurrence_equities_smoke.py` | 3 | W1.11 canopy → recurrence → juniper-data smoke (`equities_seq`) |

---

**Last Updated:** October 8, 2026
**Version:** 0.2.2
**Maintainer:** Paul Calnon
