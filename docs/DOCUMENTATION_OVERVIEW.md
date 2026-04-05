# Documentation Overview

## Navigation Guide to juniper-deploy Documentation

**Version:** 0.1.0
**Status:** Active
**Last Updated:** March 3, 2026
**Project:** Juniper - Docker Compose Orchestration

---

## Table of Contents

- [Quick Navigation](#quick-navigation)
- [Document Index](#document-index)
- [Ecosystem Context](#ecosystem-context)
- [Related Documentation](#related-documentation)

---

## Quick Navigation

### I Want To

| Goal | Document | Location |
|------|----------|----------|
| **Start the stack quickly** | [QUICK_START.md](QUICK_START.md) | docs/ |
| **Set up the full environment** | [ENVIRONMENT_SETUP.md](ENVIRONMENT_SETUP.md) | docs/ |
| **Understand all features** | [USER_MANUAL.md](USER_MANUAL.md) | docs/ |
| **Look up profiles, env vars, ports** | [REFERENCE.md](REFERENCE.md) | docs/ |
| **Run integration tests** | [TESTING_QUICK_START.md](testing/TESTING_QUICK_START.md) | docs/testing/ |
| **See development conventions** | [AGENTS.md](../AGENTS.md) | Root |
| **Quick-reference dev tasks** | [DEVELOPER_CHEATSHEET.md](DEVELOPER_CHEATSHEET.md) | docs/ |
| **See version history** | [CHANGELOG.md](../CHANGELOG.md) | Root |

---

## Document Index

### docs/ Directory

| File | Lines | Type | Purpose |
|------|-------|------|---------|
| **DOCUMENTATION_OVERVIEW.md** | ~200 | Overview | This file -- navigation index |
| **QUICK_START.md** | ~130 | Tutorial | Start the Juniper stack in 5 minutes |
| **ENVIRONMENT_SETUP.md** | ~310 | Setup | Complete environment configuration from scratch |
| **USER_MANUAL.md** | ~450 | Manual | Comprehensive usage guide for all profiles and features |
| **REFERENCE.md** | ~380 | Reference | Profiles, services, env vars, ports, Makefile targets |
| **DEVELOPER_CHEATSHEET.md** | ~100 | Cheatsheet | Quick-reference card for common development tasks |
| **OBSERVABILITY_GUIDE.md** | ~200 | Guide | Prometheus, Grafana, metrics, and structured logging guide |

### docs/testing/ Directory

| File | Lines | Type | Purpose |
|------|-------|------|---------|
| **TESTING_QUICK_START.md** | ~120 | Tutorial | Run integration tests in 5 minutes |

### Root Directory

| File | Lines | Type | Purpose |
|------|-------|------|---------|
| **README.md** | ~100 | Overview | Project overview and quick examples |
| **AGENTS.md** | ~200 | Guide | Development conventions and worktree setup |
| **CHANGELOG.md** | ~50 | History | Version history and release notes |

---

## Ecosystem Context

`juniper-deploy` orchestrates the full Juniper stack using Docker Compose. It builds and runs all three core services plus optional monitoring infrastructure.

### Services Orchestrated

| Service | Source Repo | Default Port |
|---------|------------|--------------|
| **juniper-data** | `../juniper-data/` | 8100 |
| **juniper-cascor** | `../juniper-cascor/` | 8200 |
| **juniper-canopy** | `../juniper-canopy/` | 8050 |
| **Prometheus** | Official image | 9090 |
| **Grafana** | Official image | 3000 |

### Deployment Profiles

| Profile | Services | Use Case |
|---------|----------|----------|
| `full` | data + cascor + canopy | Production-like deployment |
| `demo` | data + cascor-demo + canopy-demo + seed | Self-running demonstration |
| `dev` | data + cascor + canopy-dev (demo mode) | Frontend development |
| `observability` | prometheus + grafana | Monitoring add-on |

### Dependency Graph

```
juniper-canopy (8050)
  └── depends_on: juniper-cascor (healthy), juniper-data (healthy)
juniper-cascor (8200)
  └── depends_on: juniper-data (healthy)
juniper-data (8100)
  └── no dependencies (starts first)
```

---

## Related Documentation

### Service Repos

- **juniper-data** -- [Dataset Service](https://github.com/pcalnon/juniper-data) (FastAPI, port 8100)
- **juniper-cascor** -- [Training Service](https://github.com/pcalnon/juniper-cascor) (CasCor, port 8200)
- **juniper-canopy** -- [Dashboard](https://github.com/pcalnon/juniper-canopy) (Dash/FastAPI, port 8050)

### Client Libraries

- **juniper-data-client** -- [Docs](https://github.com/pcalnon/juniper-data-client) (HTTP client for juniper-data)
- **juniper-cascor-client** -- [Docs](https://github.com/pcalnon/juniper-cascor-client) (HTTP/WS client for juniper-cascor)
- **juniper-ml** -- [Meta-package](https://github.com/pcalnon/juniper-ml) (`pip install juniper-ml[all]`)

### Monitoring

- **Prometheus** -- [prometheus.io](https://prometheus.io/)
- **Grafana** -- [grafana.com](https://grafana.com/)

---

**Last Updated:** March 3, 2026
**Version:** 0.1.0
**Maintainer:** Paul Calnon

> See the [Juniper Ecosystem Guide](../../CLAUDE.md) for the full project map and dependency graph.
