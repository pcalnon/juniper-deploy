# Verbatim local overrides used by the Prometheus PoC

**Date**: 2026-05-27
**Parent doc**: [`POC_PROMETHEUS_GRAFANA_2026-05-27.md`](POC_PROMETHEUS_GRAFANA_2026-05-27.md)

> **Obsolescence note (2026-05-29)**: after Wave 1 + Wave 2 of the remediation
> plan landed (see [`POC_ISSUES_DISCOVERED.md`](POC_ISSUES_DISCOVERED.md)
> status lines), both overrides below are **no longer required** for
> stacks running juniper-data and juniper-cascor images built from
> current main. From a clean checkout, `make build && make monitor`
> yields all four Prometheus targets `up`.
>
> The file content is kept here verbatim for two reasons:
>
> 1. Stacks running older image pins (e.g. pre-2026-05-29 builds of
>    juniper-data or juniper-cascor) still need the workaround.
> 2. The `JUNIPER_DATA_METRICS_TRUSTED_IPS` override pattern remains the
>    documented way to allowlist non-default scraper IPs / CIDRs —
>    operators just no longer need it for the docker-compose
>    loopback case.

Both files below are gitignored (`.env.local`, `docker-compose.override.yml`
are in `.gitignore`). Copy them into the `juniper-deploy/` root to reproduce
the pre-Wave-3 PoC end-state, then re-up the stack as described in the
parent doc §5.2.

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
