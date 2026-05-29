# Verbatim local overrides used by the Prometheus PoC

**Date**: 2026-05-27 (Waves 1+2+3 landed 2026-05-29 — workarounds below
are no longer needed)
**Parent doc**: [`POC_PROMETHEUS_GRAFANA_2026-05-27.md`](POC_PROMETHEUS_GRAFANA_2026-05-27.md)

## Status — historical, kept for reference

The `.env.local` and `docker-compose.override.yml` templates below were
the **local PoC workaround** for three upstream gaps. All three are now
fixed upstream:

| Workaround                                                  | Status                       | Replaced with                                       |
| ----------------------------------------------------------- | ---------------------------- | --------------------------------------------------- |
| `JUNIPER_DATA_METRICS_TRUSTED_IPS` env-var override         | Wired into compose (#98)     | Set in `.env.observability` defaults                |
| `JUNIPER_CASCOR_METRICS_TRUSTED_IPS` env-var override       | Wired into compose (Wave-3)  | Set in `.env.observability` defaults                |
| Literal Prometheus IPs (e.g. `172.18.0.8`)                  | CIDR support (#157, #313)    | `172.18.0.0/16` — stable across `down/up`           |
| `JUNIPER_*_API_KEYS_FILE=./secrets/<empty>` auth-disable    | `/metrics` exempt (#155, #313) | No override — exempt path is upstream             |

After [`POC_PROMETHEUS_GRAFANA_2026-05-27.md` §5](POC_PROMETHEUS_GRAFANA_2026-05-27.md#5-reproduce-the-poc-from-a-clean-checkout)
was updated, the canonical reproduce flow is just `make monitor` — no
hand-written local overrides.

The original templates are kept verbatim below for any future operator
who needs to reconstruct the PoC's exact 2026-05-27 starting state
(e.g., when bisecting a regression).

---

## `juniper-deploy/.env.local`

```bash
# =============================================================================
# .env.local — local Prometheus PoC overrides (gitignored)
#
# Layered on top of .env.observability so Prometheus can scrape /metrics
# on juniper-data and juniper-cascor inside docker-compose.
#
# Compose invocation:
#   docker compose \
#     --env-file .env.observability \
#     --env-file .env.local \
#     --profile full --profile observability up -d
#
# Why each override exists is documented in
# notes/poc/POC_PROMETHEUS_GRAFANA_2026-05-27.md (Issue 2 / Issue 3).
# =============================================================================

# Point compose's `juniper_data_api_keys` / `juniper_cascor_api_keys` secrets
# at the empty files under ./secrets/ so SecurityMiddleware deactivates
# (matches juniper-canopy's default dev-mode behaviour).
JUNIPER_DATA_API_KEYS_FILE=./secrets/juniper_data_api_keys.txt
JUNIPER_CASCOR_API_KEYS_FILE=./secrets/juniper_cascor_api_keys.txt

# Allow Prometheus to reach juniper-data /metrics through SEC-16's
# MetricsAuthMiddleware. JSON list, no CIDR support, exact match against
# scope["client"][0]. Includes all 4 docker-network IPs the prometheus
# container currently holds plus the loopback defaults.
JUNIPER_DATA_METRICS_TRUSTED_IPS=["172.18.0.8","172.19.0.5","172.20.0.4","172.21.0.3","127.0.0.1","::1"]
```

After a `docker compose down` + `up`, regenerate the four IP entries:

```bash
docker inspect juniper-prometheus \
  --format '{{range $k,$v := .NetworkSettings.Networks}}{{$v.IPAddress}}{{"\n"}}{{end}}'
```

and update the `JUNIPER_DATA_METRICS_TRUSTED_IPS` JSON list. See Issue 4 in
[`POC_ISSUES_DISCOVERED.md`](POC_ISSUES_DISCOVERED.md) for the structural fix.

---

## `juniper-deploy/docker-compose.override.yml`

```yaml
# =============================================================================
# docker-compose.override.yml — local Prometheus PoC overrides (gitignored)
#
# Wires JUNIPER_DATA_METRICS_TRUSTED_IPS into the juniper-data container so
# SEC-16's MetricsAuthMiddleware allows the prometheus scraper. The variable
# is not in the base compose file's `environment:` block, so a .env-file
# substitution alone has no effect — the override has to declare it.
#
# See notes/poc/POC_PROMETHEUS_GRAFANA_2026-05-27.md (Issue 3).
# =============================================================================
services:
  juniper-data:
    environment:
      JUNIPER_DATA_METRICS_TRUSTED_IPS: "${JUNIPER_DATA_METRICS_TRUSTED_IPS:-[\"127.0.0.1\",\"::1\"]}"
```

This file is automatically merged by `docker compose` whenever it sits next
to `docker-compose.yml` — no extra flag required.
