# Quick Start Guide

## Start the Juniper Stack in 5 Minutes

**Version:** 0.1.0
**Status:** Active
**Last Updated:** March 3, 2026
**Project:** Juniper - Docker Compose Orchestration

---

## Table of Contents

- [Prerequisites](#prerequisites)
- [Start the Stack](#1-start-the-stack)
- [Verify Services](#2-verify-services)
- [Access Services](#3-access-services)
- [Stop the Stack](#4-stop-the-stack)
- [Other Profiles](#5-other-profiles)
- [Next Steps](#6-next-steps)

---

## Prerequisites

- **Docker** with Docker Compose v2 (`docker compose version`)
- **Sibling repos** cloned: `juniper-data/`, `juniper-cascor/`, `juniper-canopy/` alongside `juniper-deploy/`

---

## 1. Start the Stack

### Full Stack (Production-Like)

```bash
cd juniper-deploy
make build && make up
```

### Self-Running Demo

```bash
make demo
```

This starts all services, seeds a spiral dataset, and begins training automatically.

---

## 2. Verify Services

```bash
# Wait for all services to be healthy
make wait

# Check health status
make health
```

Or verify manually:

```bash
curl http://localhost:8100/v1/health   # juniper-data
curl http://localhost:8200/v1/health   # juniper-cascor
curl http://localhost:8050/v1/health   # juniper-canopy
```

---

## 3. Access Services

| Service | URL | Description |
|---------|-----|-------------|
| **juniper-data** | http://localhost:8100 | Dataset generation API |
| **juniper-cascor** | http://localhost:8200 | Neural network training API |
| **juniper-canopy** | http://localhost:8050 | Real-time monitoring dashboard |

---

## 4. Stop the Stack

```bash
make down
```

---

## 5. Other Profiles

```bash
# Frontend development (canopy in demo mode, no backend dependency)
make dev

# Monitoring add-on (Prometheus + Grafana)
docker compose --profile observability up -d
# Prometheus: http://localhost:9090
# Grafana: http://localhost:3000 (admin/admin)
```

---

## 6. Next Steps

- [Documentation Overview](DOCUMENTATION_OVERVIEW.md) -- navigation index
- [Environment Setup](ENVIRONMENT_SETUP.md) -- complete environment configuration
- [User Manual](USER_MANUAL.md) -- profiles, monitoring, security, troubleshooting
- [Reference](REFERENCE.md) -- all env vars, Makefile targets, services, ports
- [Testing Quick Start](testing/TESTING_QUICK_START.md) -- run integration tests

---

**Last Updated:** March 3, 2026
**Version:** 0.1.0
**Status:** Active
