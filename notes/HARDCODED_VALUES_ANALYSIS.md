# Hardcoded Values Analysis — juniper-deploy

**Version**: 0.2.0
**Analysis Date**: 2026-04-08
**Analyst**: Claude Code (Automated Code Review)
**Status**: PLANNING ONLY — No source code modifications

---

## Executive Summary

The juniper-deploy repository is a Docker Compose orchestration project with **110+ identified hardcoded values** across `docker-compose.yml`, Prometheus/Grafana configs, alert rules, shell scripts, and Python tests. Approximately **24 values are environment-configurable** (via `.env.example`), while **85+ values remain hardcoded** — primarily health check timings, Prometheus scrape intervals, alert thresholds, container/network/volume names, and shell script timeouts.

---

## 1. Existing Constants Infrastructure

| File | Purpose | Coverage |
|------|---------|----------|
| `.env.example` | 44 environment variable templates | Good — service ports, URLs, log levels, rate limits |
| `.env.demo` | 11 demo profile overrides | Good |
| `.env.observability` | 6 observability overrides | Good |
| `tests/constants.py` | 1 test constant (`DEFAULT_TIMEOUT=10`) | Minimal |

---

## 2. Hardcoded Values — NOT COVERED

### 2.1 Health Check Configuration (`docker-compose.yml`) — Repeated across 7+ services

| Service | Interval | Timeout | Start Period | Retries |
|---------|----------|---------|-------------|---------|
| juniper-data | `15s` | `10s` | `10s` | `5` |
| juniper-cascor | `15s` | `10s` | `15s` | `5` |
| juniper-cascor-demo | `15s` | `10s` | `20s` | `5` |
| juniper-demo-seed | `15s` | `10s` | `10s` | `5` |
| juniper-canopy | `15s` | `10s` | `15s` | `5` |
| juniper-cascor-worker | `30s` | `10s` | `15s` | `3` |
| redis | `10s` | `5s` | `5s` | `5` |

**Proposed**: `HEALTHCHECK_INTERVAL`, `HEALTHCHECK_TIMEOUT`, `HEALTHCHECK_START_PERIOD`, `HEALTHCHECK_RETRIES` as `.env` variables or Compose extension fields (`x-healthcheck-defaults`)

### 2.2 Prometheus Configuration (`prometheus/prometheus.yml`)

| Line | Value | Context | Proposed Variable |
|------|-------|---------|-------------------|
| 3 | `15s` | Global scrape interval | `PROMETHEUS_SCRAPE_INTERVAL` |
| 4 | `15s` | Evaluation interval | `PROMETHEUS_EVAL_INTERVAL` |
| 5 | `10s` | Scrape timeout | `PROMETHEUS_SCRAPE_TIMEOUT` |
| 23 | `10s` | juniper-data scrape interval | `DATA_SCRAPE_INTERVAL` |
| 32 | `10s` | juniper-cascor scrape interval | `CASCOR_SCRAPE_INTERVAL` |
| 41 | `15s` | juniper-canopy scrape interval | `CANOPY_SCRAPE_INTERVAL` |
| 10 | `alertmanager:9093` | AlertManager target | `ALERTMANAGER_TARGET` |

### 2.3 Alert Rules (`prometheus/alert_rules.yml`)

| Value | Context | Proposed Constant |
|-------|---------|-------------------|
| `0.05` | Error rate threshold (5%) | `ERROR_RATE_THRESHOLD` |
| `2.0` | Data service P95 latency threshold (sec) | `LATENCY_THRESHOLD_DATA` |
| `5.0` | CasCor P95 latency threshold (sec) | `LATENCY_THRESHOLD_CASCOR` |
| `30.0` | Dataset generation latency threshold (sec) | `DATASET_GEN_LATENCY_THRESHOLD` |
| `0.01` | Low correlation threshold | `CORRELATION_ALERT_THRESHOLD` |
| `3` | Restart count threshold (in 30 min) | `RESTART_COUNT_THRESHOLD` |
| `1m`, `5m`, `10m`, `15m`, `30m` | Various alert evaluation windows | Multiple window constants |

### 2.4 Grafana Configuration

| Value | Context | Proposed Variable |
|-------|---------|-------------------|
| `admin` | Default admin user | `GRAFANA_ADMIN_USER` (exists in `.env`) |
| `false` | Disable sign-up | `GRAFANA_ALLOW_SIGNUP` |
| `http://prometheus:9090` | Datasource URL | `GRAFANA_PROMETHEUS_URL` |
| `10s` | Min scrape interval | `GRAFANA_MIN_INTERVAL` |
| Dashboard JSON path | Home dashboard | `GRAFANA_HOME_DASHBOARD` |

### 2.5 Container/Network/Volume Names

**Container names** (8): `juniper-data`, `juniper-cascor`, `juniper-cascor-demo`, `juniper-demo-seed`, `juniper-canopy`, `juniper-prometheus`, `juniper-grafana`, `juniper-redis`, `juniper-test-runner`

**Network names** (4): `backend`, `data`, `frontend`, `monitoring`

**Volume names** (4): `juniper-data-datasets`, `juniper-cascor-snapshots`, `juniper-cascor-logs`, `grafana-data`

### 2.6 Docker Image Versions

| Image | Tag | Status |
|-------|-----|--------|
| `prom/prometheus` | `v3.10.0` | Pinned (good) |
| `grafana/grafana` | `12.4.0` | Pinned (good) |
| `redis` | `7-alpine` | Pinned (good) |

### 2.7 Shell Script Timeouts

| Script | Value | Context | Proposed Constant |
|--------|-------|---------|-------------------|
| `wait_for_services.sh` | `90` | Service wait timeout | `WAIT_TIMEOUT_DEFAULT` |
| `wait_for_services.sh` | `3` | Poll interval | `POLL_INTERVAL_DEFAULT` |
| `wait_for_services.sh` | `3` | curl timeout | `CURL_TIMEOUT` |
| `health_check.sh` | `5` | Health check timeout | `HEALTH_TIMEOUT` |
| `test_demo_profile.sh` | `120` | Demo test timeout | `DEMO_TIMEOUT` |
| `test_demo_profile.sh` | `3` | Demo poll interval | `DEMO_POLL_INTERVAL` |
| `test_demo_profile.sh` | `5` | Training start wait | `TRAINING_START_WAIT` |
| `test_health_enhanced.sh` | `90` | Enhanced test timeout | `ENHANCED_TIMEOUT` |

### 2.8 Demo Dataset Parameters

| Value | Context |
|-------|---------|
| `n_spirals=2` | Demo spiral dataset |
| `n_points_per_spiral=200` | Demo spiral dataset |
| `noise=0.15` | Demo spiral dataset |
| `seed=42` | Demo spiral dataset |
| `input_size=2, output_size=2` | Demo network config |
| `learning_rate=0.01` | Demo network config |
| `500` | Demo training epochs |

### 2.9 Infrastructure Defaults

| Value | Context | Proposed |
|-------|---------|----------|
| `30d` | Prometheus data retention | `PROMETHEUS_RETENTION` |
| `2` | Worker replicas | `WORKER_REPLICAS` |

---

## 3. Coverage Summary

| Category | Total | Covered | Not Covered | Priority |
|----------|-------|---------|-------------|----------|
| Service Ports/URLs | 12 | 12 | 0 | — |
| Log Levels/Formats | 8 | 8 | 0 | — |
| Rate Limits | 4 | 4 | 0 | — |
| Health Check Timings | 28 | 0 | 28 | **HIGH** |
| Prometheus Config | 7 | 0 | 7 | **HIGH** |
| Alert Thresholds | 10+ | 0 | 10+ | **MEDIUM** |
| Container/Network/Volume Names | 17 | 0 | 17 | **MEDIUM** |
| Shell Script Timeouts | 8 | 0 | 8 | **MEDIUM** |
| Demo Parameters | 7 | 0 | 7 | **LOW** |
| Image Versions | 3 | 0 | 3 | **LOW** (pinned OK) |
| Grafana Config | 5 | 1 | 4 | **LOW** |
| **TOTAL** | **~110** | **~25** | **~85** | — |

---

## 4. Remediation Approaches

### Approach A: Docker Compose Extension Fields + `.env` Expansion (RECOMMENDED)

Use YAML anchors and Compose `x-` extension fields for shared values (health check templates), and expand `.env.example` for remaining configurable values.

```yaml
x-healthcheck-defaults: &healthcheck-defaults
  interval: ${HEALTHCHECK_INTERVAL:-15s}
  timeout: ${HEALTHCHECK_TIMEOUT:-10s}
  retries: ${HEALTHCHECK_RETRIES:-5}
```

**For scripts**: Create `scripts/config.sh` sourced by all scripts for shared defaults.

**For Prometheus/Grafana**: These configs don't support environment variable substitution natively. Document values clearly; consider `envsubst` preprocessing for deployment flexibility.

**Strengths**:
- Docker Compose best practices
- DRY health check configuration
- Environment-configurable for different deployment targets

**Weaknesses**:
- Prometheus/Grafana configs remain static
- Some Docker Compose interpolation limitations

### Approach B: Template-Based Configuration

Use `envsubst` or a templating tool to generate `prometheus.yml` and `alertmanager.yml` from templates.

**Strengths**: Full configurability for all files
**Weaknesses**: Adds build step; more complex deployment

### Recommended: **A** — Compose extensions + `.env` expansion

---

## 5. Files Requiring Modification

| File | Action |
|------|--------|
| `docker-compose.yml` | Add `x-healthcheck-defaults`, use `.env` interpolation |
| `.env.example` | Add ~20 new variable templates |
| `scripts/config.sh` | **NEW** — shared script configuration |
| `scripts/wait_for_services.sh` | Source `config.sh` |
| `scripts/health_check.sh` | Source `config.sh` |
| `scripts/test_demo_profile.sh` | Source `config.sh` |
| `scripts/test_health_enhanced.sh` | Source `config.sh` |
| `tests/constants.py` | Expand with additional test constants |
| `prometheus/prometheus.yml` | Document all values; consider templating |
| `prometheus/alert_rules.yml` | Document thresholds; consider templating |

---

## 6. Risk Assessment

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Docker Compose interpolation issues | Low | Medium | Test with `docker compose config` |
| Breaking existing deployments | Low | High | Default values match current hardcoded values |
| Prometheus config regression | Low | Medium | Validate with `promtool check config` |
| Script behavior changes | Very Low | Low | Defaults match current values |
