# Pull Request: Security Hardening — Docker Network Isolation and Container Hardening

**Date:** 2026-03-03
**Version(s):** Unreleased
**Author:** Paul Calnon
**Status:** READY_FOR_MERGE

---

## Summary

Docker Compose security hardening for the Juniper deployment stack. Adds network isolation between services, restricts port bindings to localhost, adds container security options, pins third-party images, removes default Grafana password, and configures restrictive security defaults.

---

## Context / Motivation

A full security audit identified that Docker services were running with no network isolation, ports bound to all interfaces, unpinned third-party images, and insecure defaults (Grafana admin password, CORS wildcard, rate limiting disabled).

---

## Changes

### Security

- Added Docker network isolation: `frontend`, `backend` (internal), `data` (internal) networks
- Restricted port bindings to `127.0.0.1` for internal services
- Added `no-new-privileges:true` and `cap_drop: ALL` for all Juniper services
- SHA-pinned Prometheus (v3.2.1) and Grafana (11.5.2) images
- Require explicit `GRAFANA_ADMIN_PASSWORD` (no default)
- Changed rate limiting and CORS defaults to secure values
- Added API key header to Prometheus scrape config

---

## Impact & SemVer

- **SemVer impact:** N/A (Docker Compose orchestration)
- **User-visible behavior change:** YES — Services now on isolated networks; ports bound to localhost
- **Breaking changes:** YES — `GRAFANA_ADMIN_PASSWORD` must be set explicitly
- **Security/privacy impact:** HIGH — Network isolation, container hardening, credential management

---

## Verification Checklist

- [x] `docker compose --profile full config` validates
- [x] Network isolation prevents unauthorized cross-service access
- [x] Port bindings restricted to localhost for internal services
- [x] Container security options applied

---

## Files Changed

- `docker-compose.yml` — Network definitions, port bindings, security_opt, cap_drop, image pins, environment defaults

---

## Risks & Rollback Plan

- **Key risks:** Existing deployments need `GRAFANA_ADMIN_PASSWORD` env var; localhost port binding changes external access
- **Rollback plan:** Revert `docker-compose.yml` to previous version

---

## Related Issues / Tickets

- Phase Documentation: `juniper-ml/notes/SECURITY_AUDIT_PLAN.md`

---

## Notes for Release

Docker security hardening: network isolation, localhost port binding, container security options, pinned images, required Grafana password. Part of cross-ecosystem security audit.
