# Juniper Deploy v0.2.1 Release Notes

**Release Date:** 2026-04-09
**Version:** 0.2.1
**Codename:** Helm Chart Convergence
**Release Type:** PATCH

---

## Overview

This patch release aligns the Helm chart version with the application version (going-forward convention) and corrects a Redis image version label in the v0.2.0 changelog entry. No runtime behavior changes.

> **Status:** STABLE — Patch release; consumers can upgrade in-place.

---

## Release Summary

- **Release type:** PATCH
- **Primary focus:** Helm chart version alignment, changelog accuracy
- **Breaking changes:** No
- **Priority summary:** One Helm chart version bump (0.1.0 → 0.2.1) and one CHANGELOG label correction

---

## Changes

### Helm Chart Version Alignment

`k8s/helm/juniper/Chart.yaml` `version` is now bumped to `0.2.1` to match `appVersion`. This establishes the going-forward convention that **the Juniper Helm chart `version` and `appVersion` track together** with the application's semver.

**Why this convention:** A single version number is simpler for operators auditing the deployed stack than the standard Helm split between chart-template version and app version. All Juniper Helm charts will follow this rule going forward.

**Migration**: None required. Existing deployments continue to work; the next `helm upgrade` will pick up `0.2.1`.

```yaml
# k8s/helm/juniper/Chart.yaml
version: 0.2.1      # was 0.2.0 (and 0.1.0 prior to PR #29)
appVersion: "0.2.1" # was "0.2.0"
```

### CHANGELOG Image Version Correction

The v0.2.0 changelog entry referenced "Redis 7-alpine" but `docker-compose.yml` actually pins `redis:7.4-alpine`. The label has been corrected to match the pinned image, eliminating an audit-trail discrepancy for operators reviewing the deployed image set.

```diff
- - Pinned all third-party Docker images to specific versions (Prometheus v3.10.0, Grafana 12.4.0, Redis 7-alpine)
+ - Pinned all third-party Docker images to specific versions (Prometheus v3.10.0, Grafana 12.4.0, Redis 7.4-alpine)
```

---

## What's Not Changed

This release intentionally contains **no compose changes, no service additions, no behavior changes, no Docker image rebuilds**. It is purely a metadata cleanup release.

| Surface           | Status        |
| ----------------- | ------------- |
| `docker-compose.yml` | Unchanged    |
| Service set       | Unchanged    |
| Image pins        | Unchanged    |
| Network topology  | Unchanged    |
| Secrets layout    | Unchanged    |
| Helm templates    | Unchanged    |
| Helm values       | Unchanged    |

---

## Upgrade Notes

This is a backward-compatible patch release. No migration steps are required.

```bash
# Pull the new tag
git fetch origin
git checkout v0.2.1

# Optional: re-apply Helm chart to pick up the new chart version
helm upgrade juniper k8s/helm/juniper/

# Validate
docker compose config --quiet
helm lint k8s/helm/juniper/
```

---

## Validation

| Check                        | Result    |
| ---------------------------- | --------- |
| `pre-commit run --all-files` | ✅ Passed |
| `docker compose config`      | ✅ Passed |
| `helm lint k8s/helm/juniper/`| ✅ Passed |

---

## Known Issues

None known at time of release.

---

## What's Next

### Planned for future versions

- Additional ecosystem hardening (rate limiter TTL eviction in juniper-data, AlertManager routing refinement, demo-seed/test-runner network placement)
- Automatic image digest pinning across all third-party services
- Helm chart values overhaul to reduce per-environment override surface

### Roadmap

See [Cross-Project Release Roadmap](https://github.com/pcalnon/juniper-ml) (in `juniper-ml/notes/code-review/`) for the ecosystem-wide release queue.

---

## Cross-Ecosystem Context

This release ships alongside the following coordinated ecosystem releases:

| Repo                   | Version | Status                         |
| ---------------------- | ------- | ------------------------------ |
| juniper-data           | 0.6.0   | Released 2026-04-09            |
| juniper-data-client    | 0.4.0   | Released 2026-04-09            |
| juniper-cascor-client  | 0.3.0   | Released 2026-04-09 (backfill) |
| juniper-cascor-worker  | 0.3.0   | Released 2026-04-09 (backfill) |
| **juniper-deploy**     | **0.2.1** | **This release**             |
| juniper-ml             | 0.4.0   | Released 2026-04-09            |

---

## Contributors

- Paul Calnon

---

## Version History

| Version | Date       | Description                                                                       |
| ------- | ---------- | --------------------------------------------------------------------------------- |
| 0.2.0   | 2026-04-08 | Demo / dev / full Compose profiles, observability stack, Helm chart, Docker secrets |
| 0.2.1   | 2026-04-09 | Helm chart version alignment with appVersion + CHANGELOG Redis label correction   |

---

## Links

- [Full Changelog](../../CHANGELOG.md)
- [Pull Request #29](https://github.com/pcalnon/juniper-deploy/pull/29) — chore: align Helm chart version with app; fix Redis label in CHANGELOG
- [Previous Release: v0.2.0](https://github.com/pcalnon/juniper-deploy/releases/tag/v0.2.0)
