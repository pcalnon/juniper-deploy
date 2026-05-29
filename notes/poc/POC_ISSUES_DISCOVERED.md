# Issues discovered while standing up the Prometheus → Grafana PoC

**Date**: 2026-05-27
**Parent doc**: [`POC_PROMETHEUS_GRAFANA_2026-05-27.md`](POC_PROMETHEUS_GRAFANA_2026-05-27.md)

Each issue was surfaced organically by the PoC workflow. Severity reflects
operator impact, not engineering effort. "Workaround" describes what the PoC
applied locally; "Suggested permanent fix" describes the lasting change that
removes the trap for future operators.

**Status (2026-05-29)**: all five issues are now RESOLVED across six PRs in
three repos. Each section below carries a `**Status**:` line linking to the
landing PR; the rollout sequence and validator evidence are in
[`POC_REMEDIATION_PLAN_2026-05-27.md`](POC_REMEDIATION_PLAN_2026-05-27.md).
After rebuilding the juniper-data and juniper-cascor images
(`make build` from `juniper-deploy/`), the PoC `.env.local` +
`docker-compose.override.yml` workarounds documented in
[`POC_LOCAL_ENV_TEMPLATE.md`](POC_LOCAL_ENV_TEMPLATE.md) are no longer
required — `make monitor` from a clean checkout yields all four
Prometheus targets `up`.

---

## Issue 1 — `.env.observability` is not loaded by `make monitor`

**Severity**: high (every fresh `make monitor` ships a broken observability
stack with all three Juniper targets down).

**Status**: RESOLVED in [juniper-deploy#96](https://github.com/pcalnon/juniper-deploy/pull/96)
(Wave 0). `monitor:` now loads `.env.observability`, chains
`prepare-secrets`, prints the correct port (3001), and has an `obs` alias.
`tests/test_makefile_observability_entrypoint.py` pins the wiring.

**Observed**: With the stack started via `make monitor`, every Juniper service
target reports `down`. Prometheus + Grafana are healthy; only the scraped apps
fail. `JUNIPER_*_METRICS_ENABLED` resolves to `false` in each container.

**Root cause**: `Makefile:101-103`

```makefile
monitor:  ## Start full stack with observability (Prometheus + Grafana)
    @$(COMPOSE) -f $(COMPOSE_FILE) --profile full --profile observability up -d
```

`make monitor` passes the `observability` profile (so Prometheus + Grafana +
Alertmanager containers come up) but does **not** pass
`--env-file .env.observability`, which is the only place
`JUNIPER_*_METRICS_ENABLED=true` is set. The three flags fall back to their
`${...:-false}` defaults in `docker-compose.yml`, so the apps never mount their
`/metrics` endpoints.

There is a second drift here too: the header of `.env.observability` advertises
`make obs` / `make obs-demo` targets that do not exist in the current Makefile.
Either the file is stale, or the Makefile lost the targets in a refactor.

**Workaround applied by the PoC**:

```bash
docker compose --env-file .env.observability --profile full --profile observability up -d
```

**Suggested permanent fix**: pick one of —

1. Update `make monitor` to load `.env.observability`:

   ```makefile
   monitor: prepare-secrets
       @$(COMPOSE) -f $(COMPOSE_FILE) \
           --env-file .env.observability \
           --profile full --profile observability up -d
   ```

2. Or, fold the three `*_METRICS_ENABLED` defaults straight into the
   `observability` profile in `docker-compose.yml` and delete
   `.env.observability` entirely.

3. Either way, reconcile the `make obs` / `make obs-demo` references in
   `.env.observability` with the Makefile (add the targets, or update the
   comment).

---

## Issue 2 — `SecurityMiddleware` gates `/metrics` on cascor and data

**Severity**: medium (any operator who actually sets API keys — i.e. anyone
operating the stack the way it's documented — will get 401 on every scrape).

**Status**: RESOLVED in [juniper-data#155](https://github.com/pcalnon/juniper-data/pull/155)
(Wave 1, data side) and
[juniper-cascor#313](https://github.com/pcalnon/juniper-cascor/pull/313)
(Wave 2, cascor side). Both repos now exempt `/metrics` and `/metrics/`
from `EXEMPT_PATHS`. The trailing-slash entry is required because
`prometheus_client.make_asgi_app` is mounted as an ASGI sub-app and
FastAPI 307-redirects `/metrics → /metrics/`. The cascor PR also added a
duplicate-inline `MetricsAuthMiddleware` (parallel to juniper-data's
SEC-16) so bare-exempt doesn't widen the unintentional-exposure surface
— validator A's strongest finding from the plan.

**Observed**: With `JUNIPER_*_METRICS_ENABLED=true`, `juniper-canopy` is
scrape-able but `juniper-cascor` and `juniper-data` return `401 Unauthorized`.
Health endpoints (`/v1/health`, `/v1/health/live`, `/v1/health/ready`) work,
so the apps are healthy — only `/metrics` is gated.

**Root cause**: the API-key auth middleware in both services applies to every
route except an explicit allow-list:

- `juniper-data/juniper_data/api/constants.py:23-32` — `EXEMPT_PATHS`.
- `juniper-cascor/src/api/middleware.py:12-19` — same shape.

Neither set contains `/metrics`. When the secret file mounted at
`/run/secrets/juniper_{data,cascor}_api_keys` is non-empty (the default,
because the compose `secrets:` block falls back to `./secrets.example/*.txt`
unless `*_API_KEYS_FILE` is overridden — see the canopy memory
`secrets.example fallback enables canopy auth 2026-05-10`), the middleware
activates and rejects unauthenticated calls to `/metrics`.

Prometheus v3.10 does **not** support an arbitrary HTTP header
(e.g. `X-API-Key`) in `scrape_configs`; it only supports `basic_auth` and
`authorization` (Bearer-style). So passing the key from the scraper side is
not viable without a sidecar proxy.

**Workaround applied by the PoC**: point `*_API_KEYS_FILE` at the empty files
in `./secrets/` so the middleware deactivates. Implemented via `.env.local`
(see [`POC_LOCAL_ENV_TEMPLATE.md`](POC_LOCAL_ENV_TEMPLATE.md)). This matches
canopy's existing default-dev posture.

**Suggested permanent fix**: add `/metrics` to `EXEMPT_PATHS` in both
juniper-cascor and juniper-data. That preserves all existing access control
for real API routes while letting Prometheus scrape unconditionally. The
existing SEC-16 `MetricsAuthMiddleware` IP allowlist on juniper-data already
provides defense-in-depth for the metrics surface, so removing API-key gating
there does not weaken the security posture.

If retaining API-key auth on `/metrics` is desired, the alternative is to
ship a per-service `metrics_password_file` (basic-auth credentials) and use
Prometheus's `basic_auth` block in `scrape_configs`. That is a heavier change
and crosses the SEC-16 contract; not recommended.

---

## Issue 3 — `JUNIPER_DATA_METRICS_TRUSTED_IPS` is not plumbed through `docker-compose.yml`

**Severity**: high (silently no-ops; an operator following the prometheus.yml
comment will lose hours).

**Status**: RESOLVED in [juniper-deploy#98](https://github.com/pcalnon/juniper-deploy/pull/98)
(Wave 0). `JUNIPER_DATA_METRICS_TRUSTED_IPS` is now declared on
`services.juniper-data.environment` in `docker-compose.yml`,
documented in `.env.example`, and the stale `_ALLOW_IPS` references
have been corrected across `prometheus.yml`, `METRICS_AUTH_RATIONALE.md`,
and the Helm chart. `tests/test_compose_metrics_trusted_ips_wired.py`
asserts the declaration is present and no `_ALLOW_IPS` references remain.

**Observed**: After fixing Issue 2, `juniper-data` still returned `403
Forbidden` from `MetricsAuthMiddleware`. Setting
`JUNIPER_DATA_METRICS_TRUSTED_IPS=[…]` in `.env.local` had no effect — the
variable never appeared in the container env (`docker inspect`).

**Root cause**: `docker-compose.yml` declares
`JUNIPER_DATA_METRICS_ENABLED` (line 141) but **not**
`JUNIPER_DATA_METRICS_TRUSTED_IPS`. Compose `--env-file` substitution only
fills in `${VAR:-default}` placeholders that exist in the YAML; without a
declaration in the service's `environment:` block, the variable is dropped
on the floor.

The misleading comment in `prometheus/prometheus.yml:34-36` makes this worse:
it references `JUNIPER_DATA_METRICS_ALLOW_IPS` (not the actual
`JUNIPER_DATA_METRICS_TRUSTED_IPS` consumed by
`juniper_data.api.settings.Settings.metrics_trusted_ips`).

**Workaround applied by the PoC**: gitignored `docker-compose.override.yml`
adds:

```yaml
services:
  juniper-data:
    environment:
      JUNIPER_DATA_METRICS_TRUSTED_IPS: "${JUNIPER_DATA_METRICS_TRUSTED_IPS:-[\"127.0.0.1\",\"::1\"]}"
```

**Suggested permanent fix**:

1. Add the variable to `juniper-data`'s `environment:` block in
   `docker-compose.yml` (with `${...:-["127.0.0.1","::1"]}` for safe defaults).
2. Add a matching commented entry in `.env.example` so operators can find it.
3. Correct the name in `prometheus/prometheus.yml:34-36`
   (`JUNIPER_DATA_METRICS_ALLOW_IPS` → `JUNIPER_DATA_METRICS_TRUSTED_IPS`).

---

## Issue 4 — Prometheus container's docker-bridge IPs are not stable

**Severity**: low (cosmetic for dev; would be high if `MetricsAuthMiddleware`
were enforced in production-like environments).

**Status**: RESOLVED in [juniper-data#156](https://github.com/pcalnon/juniper-data/pull/156)
(Wave 1). `MetricsAuthMiddleware` now compiles each entry via
`ipaddress.ip_network(entry, strict=False)` so CIDR ranges like
`172.18.0.0/16` are accepted alongside bare IPs. IPv6 zone-ids are
stripped and IPv4-mapped IPv6 clients are unwrapped before membership
checks. Bad entries raise `ValueError` at `Settings` construction
(fail-loud) instead of silently producing an empty allowlist. The cascor
side (PR 313) carries the same implementation.

**Observed**: `JUNIPER_DATA_METRICS_TRUSTED_IPS` requires an exact IP-string
match (no CIDR support — see
`juniper-data/juniper_data/api/observability.py:75-93`). The prometheus
container holds four IPs (one per attached docker network); each can change
on `docker compose down/up` because docker assigns IPs sequentially as
containers come up.

**Root cause**: the middleware uses a `frozenset` of literal strings and
checks `client_ip in self.trusted_ips`. There is no IP-range or hostname
resolution.

**Workaround applied by the PoC**: enumerate all four current prometheus IPs
(`172.18.0.8`, `172.19.0.5`, `172.20.0.4`, `172.21.0.3`) in `.env.local`.
Works today, breaks if the stack is torn fully down and recreated in a
different order.

**Suggested permanent fixes** (any one is sufficient):

1. Extend `MetricsAuthMiddleware` to accept CIDR ranges via `ipaddress.ip_network`.
2. Or: resolve the `prometheus` container hostname at startup (it is reachable
   from juniper-data over the `data` and `backend` networks) and add the
   resolved IP to the allowlist on each restart.
3. Or: replace the IP allowlist with mutual TLS / a shared bearer token
   stored as a docker secret.

Option 1 is the smallest change and matches typical Prometheus security
patterns (kube-prometheus uses CIDR allowlists for its scrape proxies).

---

## Issue 5 — Provisioned dashboards lack stable panel IDs

**Severity**: low (cosmetic; complicates deep-linking and screenshot
automation).

**Status**: RESOLVED in [juniper-deploy#99](https://github.com/pcalnon/juniper-deploy/pull/99)
(Wave 0). Sequential `1..N` integer panel IDs assigned across all four
dashboards (74 panels total) via a regex insertion that produced zero
formatting churn. `tests/test_grafana_dashboard_ids.py` enforces
integer + uniqueness without monotonicity, so future panel insertions
do not cascade-renumber.

**Observed**: the panels in `juniper-overview.json` carry no explicit `"id"`
field. Grafana auto-assigns IDs on render, so `?viewPanel=<n>` and `d-solo`
panel-render URLs cannot target a specific panel from the JSON.

**Root cause**: dashboard authoring style — none of the existing 15 panels
have IDs either, and the new PoC panel followed suit.

**Workaround**: scroll to the bottom of the dashboard, take a viewport
screenshot. Works for this PoC; awkward for headless regression screenshots.

**Suggested permanent fix**: assign stable integer `id` fields to every panel
in every checked-in dashboard JSON, and add a lint test under `tests/` to
enforce uniqueness and monotonicity. Aligns with the lint discipline already
present in juniper-ml (`tests/test_workflow_script_paths.py`,
`tests/test_pyproject_extras.py`, etc.) and would unlock automation.
