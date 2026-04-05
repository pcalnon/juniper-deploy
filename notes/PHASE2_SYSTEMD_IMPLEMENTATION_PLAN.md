# Phase 2: systemd Service Units — Implementation Plan

**Author**: Paul Calnon
**Date**: 2026-03-02
**Source**: Microservices Architecture Development Roadmap, Phase 2 (Sections 2.1–2.11)
**Status**: Planning

---

## 1. Overview

Phase 2 implements native host deployment for the Juniper platform using systemd user units. This provides:

- Zero containerization overhead (native process execution)
- Direct GPU/CUDA access for JuniperCascor training workloads
- Dependency ordering via systemd `After=`/`Requires=` directives
- Health monitoring via timer-triggered one-shot services
- Per-service resource accounting and limits via cgroups v2
- Security hardening (filesystem isolation, privilege restriction)
- Centralized management via `juniper-ctl` CLI

### Why systemd?

Docker Compose (Phase 3) provides portable, reproducible deployments. systemd provides maximum performance for native host development and production on bare-metal servers. Both deployment methods coexist — `juniper-deploy` supports Docker **and** systemd.

---

## 2. Prerequisites

| Requirement | Version | Verification |
|-------------|---------|--------------|
| systemd | >= 250 | `systemctl --version` |
| Python (conda) | >= 3.12 | `/opt/miniforge3/envs/JuniperData/bin/python --version` |
| curl or Python 3 | any | For health check scripts |
| User lingering | — | `loginctl enable-linger pcalnon` |

### Conda Environments

Each service uses its own conda environment (correcting the roadmap's assumption of a single `JuniperPython` env):

| Service | Conda Env | Python Path |
|---------|-----------|-------------|
| juniper-data | `JuniperData` | `/opt/miniforge3/envs/JuniperData/bin/python` |
| juniper-cascor | `JuniperCascor` | `/opt/miniforge3/envs/JuniperCascor/bin/python` |
| juniper-canopy | `JuniperPython` | `/opt/miniforge3/envs/JuniperPython/bin/python` |

### Service Entry Points

| Service | Working Directory | Entry Point |
|---------|------------------|-------------|
| juniper-data | `juniper-data/` | `python -m juniper_data` |
| juniper-cascor | `juniper-cascor/` | `python src/server.py` (with `PYTHONPATH=src`) |
| juniper-canopy | `juniper-canopy/` | `python src/main.py` (with `PYTHONPATH=src`) |

---

## 3. File Layout

```
juniper-deploy/
├── systemd/
│   ├── user/                              # Unit file source (committed to repo)
│   │   ├── juniper.target                 # Target grouping all services
│   │   ├── juniper-data.service           # JuniperData service unit
│   │   ├── juniper-cascor.service         # JuniperCascor service unit
│   │   ├── juniper-canopy.service         # JuniperCanopy service unit
│   │   ├── juniper-data-health.service    # One-shot health check
│   │   ├── juniper-data-health.timer      # Periodic health timer
│   │   ├── juniper-cascor-health.service  # One-shot health check
│   │   ├── juniper-cascor-health.timer    # Periodic health timer
│   │   ├── juniper-canopy-health.service  # One-shot health check
│   │   └── juniper-canopy-health.timer    # Periodic health timer
│   └── install.sh                         # Symlinks units into ~/.config/systemd/user/
├── scripts/
│   ├── juniper-ctl                        # Management CLI wrapper
│   ├── wait_for_health.sh                 # Reusable health wait (ExecStartPre/Post)
│   └── health_check_systemd.sh            # Health check for timer units
└── conf/
    └── juniper.env.example                # Environment template (committed)
    # juniper.env                          # Actual env file (git-ignored, chmod 600)
```

**Total new files**: 10 unit files + 3 scripts + 1 install script + 1 env template = **15 files**

---

## 4. Implementation Tasks

### Task 2.1 — Create `juniper.target`

**File**: `systemd/user/juniper.target`

```ini
[Unit]
Description=Juniper ML Platform — All Services
Documentation=https://github.com/pcalnon/juniper
After=network-online.target
Wants=network-online.target

[Install]
WantedBy=default.target
```

**Purpose**: Groups all services so `systemctl --user start juniper.target` starts everything.

---

### Task 2.2 — Create `juniper-data.service`

**File**: `systemd/user/juniper-data.service`

Key directives:

| Directive | Value | Rationale |
|-----------|-------|-----------|
| `Type` | `exec` | Modern tracking (systemd >= 240) |
| `ExecStart` | `/opt/miniforge3/envs/JuniperData/bin/python -m juniper_data` | Uses JuniperData conda env |
| `ExecStartPost` | `wait_for_health.sh http://localhost:8100/v1/health 30` | Blocks until healthy |
| `EnvironmentFile` | `juniper-deploy/conf/juniper.env` | Shared env vars |
| `MemoryMax` | `2G` | Dataset generation is I/O-bound |
| `CPUQuota` | `200%` | 2 cores |
| `Restart` | `on-failure` | Auto-restart on crash |
| `RestartSec` | `5` | Prevents tight restart loops |
| `ReadWritePaths` | `juniper-data/data` | Only directory needing write access |

Security hardening: `NoNewPrivileges=true`, `ProtectSystem=strict`, `ProtectHome=read-only`, `PrivateTmp=true`.

---

### Task 2.3 — Create `juniper-cascor.service`

**File**: `systemd/user/juniper-cascor.service`

Key differences from juniper-data:

| Directive | Value | Rationale |
|-----------|-------|-----------|
| `After` | `juniper-data.service` | Start order |
| `Requires` | `juniper-data.service` | Hard dependency — stops if data stops |
| `ExecStart` | `/opt/miniforge3/envs/JuniperCascor/bin/python src/server.py` | Uses JuniperCascor conda env |
| `Environment` | `PYTHONPATH=src` | CasCor entry point is in `src/` |
| `ExecStartPre` | `wait_for_health.sh http://localhost:8100/v1/health 30` | Gates on data health |
| `MemoryMax` | `8G` | ML training needs more memory |
| `CPUQuota` | `400%` | 4 cores for training |
| `ReadWritePaths` | `juniper-cascor/logs`, `juniper-cascor/data` | Training artifacts + logs |

---

### Task 2.4 — Create `juniper-canopy.service`

**File**: `systemd/user/juniper-canopy.service`

Key differences:

| Directive | Value | Rationale |
|-----------|-------|-----------|
| `After` | `juniper-data.service juniper-cascor.service` | Start order |
| `Requires` | `juniper-data.service` | Hard dependency on data |
| `Wants` | `juniper-cascor.service` | **Soft** dependency — Canopy falls back to demo mode |
| `ExecStart` | `/opt/miniforge3/envs/JuniperPython/bin/python src/main.py` | Uses JuniperPython conda env |
| `Environment` | `PYTHONPATH=src` | Canopy entry point is in `src/` |
| `ReadWritePaths` | `juniper-canopy/logs` | Log output only |

---

### Task 2.5 — Create `scripts/wait_for_health.sh`

**File**: `scripts/wait_for_health.sh`

Reusable script used by `ExecStartPre` and `ExecStartPost` directives.

```bash
#!/usr/bin/env bash
# Usage: wait_for_health.sh <url> <timeout_seconds>
# Exit 0 if healthy within timeout, exit 1 otherwise.
```

- Polls the given health URL every 2 seconds
- Uses `python3 -c "import urllib.request; ..."` (no external dependencies)
- Returns 0 on success, 1 on timeout
- Logs timeout errors to stderr (captured by systemd journal)

---

### Task 2.6 — Create health timer + one-shot units (6 files)

For each service (`juniper-data`, `juniper-cascor`, `juniper-canopy`):

**Timer** (`<service>-health.timer`):

```ini
[Timer]
OnActiveSec=30
OnUnitActiveSec=30
AccuracySec=5
```

Fires every 30 seconds after activation, triggering the paired one-shot service.

**One-shot** (`<service>-health.service`):

```ini
[Service]
Type=oneshot
ExecStart=health_check_systemd.sh <service-name> <health-url>
```

Health results are logged to the journal, viewable via `journalctl --user -u <service>-health.service`.

---

### Task 2.7 — Create `scripts/health_check_systemd.sh`

**File**: `scripts/health_check_systemd.sh`

- Queries `/v1/health/ready` endpoint
- Parses ReadinessResponse JSON (status, version, latency, dependencies)
- Outputs structured JSON to stdout (captured by systemd journal)
- Returns non-zero exit code if unhealthy (enables `OnFailure=` triggers)

---

### Task 2.8 — Create `conf/juniper.env.example`

**File**: `conf/juniper.env.example` (committed) → copied to `conf/juniper.env` (git-ignored, `chmod 600`)

Contents mirror `docker-compose.yml` environment variables:

```bash
# Server Configuration
JUNIPER_DATA_HOST=127.0.0.1
JUNIPER_DATA_PORT=8100
JUNIPER_DATA_LOG_LEVEL=INFO

CASCOR_HOST=127.0.0.1
CASCOR_PORT=8200
CASCOR_LOG_LEVEL=INFO

CANOPY_HOST=127.0.0.1
CANOPY_PORT=8050

# Inter-service URLs (localhost for native deployment)
JUNIPER_DATA_URL=http://localhost:8100
CASCOR_SERVICE_URL=http://localhost:8200

# API Security (uncomment to enable)
# JUNIPER_DATA_API_KEYS=
# JUNIPER_CASCOR_API_KEYS=
# JUNIPER_DATA_API_KEY=
```

**Key difference from Docker**: Default hosts are `127.0.0.1` (not `0.0.0.0`), inter-service URLs use `localhost` (not Docker DNS names).

---

### Task 2.9 — Create `scripts/juniper-ctl`

**File**: `scripts/juniper-ctl`

Management CLI wrapping `systemctl --user` commands:

| Command | Action |
|---------|--------|
| `juniper-ctl start` | Start all services via `juniper.target` |
| `juniper-ctl stop` | Stop all services |
| `juniper-ctl restart [service]` | Restart one or all services |
| `juniper-ctl status` | Show status of all services |
| `juniper-ctl logs [service]` | Follow journal logs |
| `juniper-ctl health` | Show latest health check results |
| `juniper-ctl resources` | Show CPU/memory/IO usage per service |
| `juniper-ctl install` | Symlink unit files + daemon-reload |
| `juniper-ctl enable` | Enable auto-start on login |
| `juniper-ctl disable` | Disable auto-start |

---

### Task 2.10 — Create `systemd/install.sh`

**File**: `systemd/install.sh`

- Creates `~/.config/systemd/user/` if needed
- Symlinks all unit files from `systemd/user/` into the user unit directory
- Runs `systemctl --user daemon-reload`
- Verifies units are recognized via `systemctl --user list-unit-files 'juniper*'`

---

### Task 2.11 — Enable user lingering

```bash
loginctl enable-linger pcalnon
```

This is a one-time system configuration step (not a file). Required so systemd user services persist after logout.

---

### Task 2.12 — Full lifecycle validation

Verify the complete workflow:

```bash
# Install
juniper-ctl install

# Verify 10 unit files recognized
systemctl --user list-unit-files 'juniper*'

# Start all services
juniper-ctl start

# Verify startup order (data → cascor → canopy)
journalctl --user -u juniper-data -u juniper-cascor -u juniper-canopy \
    --since "1 minute ago" --no-pager -o short-iso

# Verify all healthy
juniper-ctl status
juniper-ctl health

# Test auto-restart
kill -9 $(systemctl --user show juniper-data.service --property=MainPID --value)
sleep 10 && systemctl --user is-active juniper-data.service  # Should be "active"

# Test dependency behavior
systemctl --user stop juniper-data.service
systemctl --user is-active juniper-cascor.service  # Should be "inactive"

# Clean stop
juniper-ctl stop
```

---

### Task 2.13 — Resource monitoring validation

```bash
juniper-ctl resources
# Expected: Non-zero CPU, Memory, IO values for each service

systemctl --user show juniper-cascor.service \
    --property=CPUUsageNSec,MemoryCurrent,MemoryPeak,IOReadBytes,IOWriteBytes
```

---

### Task 2.14 — README documentation

Add a `## systemd Deployment` section to `juniper-deploy/README.md` covering:

- Prerequisites (systemd >= 250, user lingering)
- Installation (`juniper-ctl install`)
- Starting/stopping services
- Viewing logs (`journalctl`)
- Health monitoring
- Resource monitoring
- Comparison with Docker deployment

---

## 5. Implementation Order

The dependency graph determines the implementation order:

```
Phase A: Foundation (no dependencies)
  2.1  juniper.target
  2.5  wait_for_health.sh
  2.7  health_check_systemd.sh
  2.8  juniper.env.example
  2.11 Enable user lingering

Phase B: Service units (depends on 2.1)
  2.2  juniper-data.service
  2.3  juniper-cascor.service
  2.4  juniper-canopy.service

Phase C: Health monitoring (depends on 2.2-2.4)
  2.6  Health timer + one-shot units (6 files)

Phase D: Management (depends on all above)
  2.9  juniper-ctl
  2.10 install.sh

Phase E: Validation & Docs
  2.12 Full lifecycle validation
  2.13 Resource monitoring validation
  2.14 README documentation
```

**Estimated scope**: Phases A-D can be implemented in a single focused session. Phase E is validation and documentation.

---

## 6. Corrections from Roadmap

The following corrections should be applied during implementation:

| Roadmap Reference | Issue | Correction |
|-------------------|-------|------------|
| All service unit `ExecStart` paths | Uses single `JuniperPython` conda env | Each service uses its own env: `JuniperData`, `JuniperCascor`, `JuniperPython` |
| `juniper-canopy.service` WorkingDirectory | References `JuniperCanopy/juniper_canopy` | Correct path: `juniper-canopy/` |
| `juniper-canopy.service` PYTHONPATH | References `JuniperCanopy/juniper_canopy/src` | Correct: `juniper-canopy/src` |
| Default host in `juniper.env` | Roadmap doesn't specify | Use `127.0.0.1` for native deployment (not `0.0.0.0` from Docker defaults) |
| `WatchdogSec=60` on all services | Requires `sd_notify` integration in applications | Remove initially; add in a follow-up after implementing `sd_notify` in each service |

---

## 7. Risk Assessment

| Risk | Impact | Mitigation |
|------|--------|------------|
| `WatchdogSec` without `sd_notify` causes false SIGABRT | Services killed despite being healthy | Omit `WatchdogSec` until `sd_notify` is implemented in each service |
| `ProtectHome=read-only` blocks conda package installs | Cannot pip install during development | Only enable `ProtectHome` in production; omit for development |
| `Requires=juniper-data` stops cascor on data restart | Brief cascor downtime during data updates | Acceptable for dev; consider `BindsTo=` for more nuanced control in production |
| `MemoryMax=8G` for cascor may be insufficient for large training | OOM kill during training | Monitor `MemoryPeak` and adjust; start without limit in dev |
| Different conda envs may have dependency drift | Version mismatches between services | Covered by existing CI/CD; conda environment YAML files in each repo |

---

## 8. Testing Strategy

### Unit-level tests

- `systemd-analyze verify` on each unit file (syntax validation)
- `install.sh` creates correct symlinks
- `wait_for_health.sh` times out correctly on unreachable endpoints
- `health_check_systemd.sh` outputs valid JSON

### Integration tests

- Start `juniper.target` and verify all 3 services reach healthy state
- Stop `juniper-data.service` and verify `juniper-cascor` stops (Requires dependency)
- Kill a service process and verify auto-restart within `RestartSec` window
- Verify health timers fire and produce journal entries
- Verify resource accounting shows non-zero values

### Regression tests

- Verify Docker Compose deployment still works after adding systemd files
- Verify `make up`, `make demo`, `make test` are unaffected

---

## 9. Notes

- **sd_notify watchdog**: The roadmap includes `WatchdogSec=60` on all units, which requires application-level `sd_notify` integration. This should be deferred to a follow-up task after the basic systemd deployment is working. Remove `WatchdogSec` from initial unit files.
- **Development vs production**: The initial implementation targets development use (user units, relaxed security). Production hardening (`SystemCallFilter`, `CapabilityBoundingSet`, `RestrictNamespaces`) is documented in the roadmap Section 2.10 and can be enabled incrementally.
- **Coexistence with Docker**: The systemd and Docker deployments are independent. The same `juniper-deploy` repo supports both. Users choose based on their deployment target.
