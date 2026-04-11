# Hardcoded Values Refactor Plan — juniper-deploy

**Version**: 0.2.0
**Created**: 2026-04-08
**Status**: PLANNING — No source code modifications
**Companion Document**: `HARDCODED_VALUES_ANALYSIS.md`

---

## Phase 1: Docker Compose Consolidation (Priority: HIGH)

### Step 1.1: Create Compose Extension Fields

**Task**: Add YAML anchor definitions for shared health check configurations:

```yaml
x-healthcheck-defaults: &healthcheck-defaults
  interval: ${HEALTHCHECK_INTERVAL:-15s}
  timeout: ${HEALTHCHECK_TIMEOUT:-10s}
  retries: ${HEALTHCHECK_RETRIES:-5}

x-healthcheck-worker: &healthcheck-worker
  interval: ${WORKER_HEALTHCHECK_INTERVAL:-30s}
  timeout: ${HEALTHCHECK_TIMEOUT:-10s}
  retries: ${WORKER_HEALTHCHECK_RETRIES:-3}
```

### Step 1.2: Expand `.env.example`

**Task**: Add ~20 new environment variable templates:
- Health check: `HEALTHCHECK_INTERVAL`, `HEALTHCHECK_TIMEOUT`, `HEALTHCHECK_RETRIES`
- Prometheus: `PROMETHEUS_RETENTION`, `PROMETHEUS_SCRAPE_INTERVAL`
- Grafana: `GRAFANA_ALLOW_SIGNUP`
- Worker: `WORKER_REPLICAS`

### Step 1.3: Create Script Configuration

**Task**: Create `scripts/config.sh` with shared defaults:
```bash
WAIT_TIMEOUT=${WAIT_TIMEOUT:-90}
POLL_INTERVAL=${POLL_INTERVAL:-3}
CURL_TIMEOUT=${CURL_TIMEOUT:-3}
HEALTH_TIMEOUT=${HEALTH_TIMEOUT:-5}
```

---

## Phase 2: Script Refactor (Priority: MEDIUM)

### Step 2.1: Update Shell Scripts

**Files**: `wait_for_services.sh`, `health_check.sh`, `test_demo_profile.sh`, `test_health_enhanced.sh`
**Changes**: Source `config.sh` at top of each script, replace hardcoded values

### Step 2.2: Expand Test Constants

**File**: `tests/constants.py`
**Changes**: Add timeout, polling, and configuration constants for Python tests

---

## Phase 3: Observability Configuration (Priority: LOW)

### Step 3.1: Document Prometheus Values

**Task**: Add inline documentation comments in `prometheus.yml` and `alert_rules.yml` explaining each threshold and interval. Consider creating `prometheus/README.md` with tuning guidance.

### Step 3.2: Evaluate Template Approach

**Task**: Assess whether `envsubst`-based templating for `prometheus.yml` would benefit deployment flexibility. Document decision.

---

## Phase 4: Validation (Priority: HIGH)

### Step 4.1: Validate Docker Compose

```bash
docker compose config
docker compose --profile demo config
docker compose --profile observability config
```

### Step 4.2: Run Integration Tests

```bash
pytest tests/ -v
```

### Step 4.3: Validate Prometheus Config

```bash
promtool check config prometheus/prometheus.yml
promtool check rules prometheus/alert_rules.yml
```

---

## Phase 5: Documentation & Release (Priority: MEDIUM)

### Step 5.1: Update AGENTS.md — Document new `.env` variables and `config.sh`
### Step 5.2: Update CHANGELOG.md
### Step 5.3: Create Release Description
