# POC Remediation Plan — Prometheus → Grafana Scrape-Path Fixes

**Author**: Claude Code session, supervised by Paul Calnon
**Date**: 2026-05-27
**Parent docs**:
[`POC_PROMETHEUS_GRAFANA_2026-05-27.md`](POC_PROMETHEUS_GRAFANA_2026-05-27.md),
[`POC_ISSUES_DISCOVERED.md`](POC_ISSUES_DISCOVERED.md)
**Status**: drafted + validated by 4 independent sub-agents (see §7); ready for review.
**Outcome (2026-05-29)**: SHIPPED — all 6 PRs merged, see table below for PR references.

---

## 0. TL;DR

Five issues, six PRs across three repos, ~6–10 hours of development total.
Wave-0 (juniper-deploy) is independent of the others and can land immediately;
Wave-1 (juniper-data) and Wave-2 (juniper-cascor) need an image rebuild + deploy
bump but are otherwise independent. Issue 2 expands scope beyond
[`POC_ISSUES_DISCOVERED.md`](POC_ISSUES_DISCOVERED.md) on validator advice
(juniper-cascor needs a parallel `MetricsAuthMiddleware`, not just an exempt
path — otherwise we widen the unintentional-exposure surface).

| # | Issue                                              | Wave | Repo            | PR (merged) | Severity |
| - | -------------------------------------------------- | ---- | --------------- | ----------- | -------- |
| 1 | `make monitor` doesn't load `.env.observability`   | 0    | juniper-deploy  | [#96](https://github.com/pcalnon/juniper-deploy/pull/96) | high |
| 3 | `*_TRUSTED_IPS` not plumbed; doc/Helm drift        | 0    | juniper-deploy  | [#98](https://github.com/pcalnon/juniper-deploy/pull/98) | high |
| 5 | Provisioned dashboards lack stable panel IDs       | 0    | juniper-deploy  | [#99](https://github.com/pcalnon/juniper-deploy/pull/99) | low |
| 2 | `SecurityMiddleware` gates `/metrics` (data)       | 1    | juniper-data    | [#155](https://github.com/pcalnon/juniper-data/pull/155) | medium |
| 4 | `MetricsAuthMiddleware` needs CIDR support         | 1    | juniper-data    | [#156](https://github.com/pcalnon/juniper-data/pull/156) | low |
| 2 | `SecurityMiddleware` gates `/metrics` (cascor) **+ new IP allowlist** | 2 | juniper-cascor | [#313](https://github.com/pcalnon/juniper-cascor/pull/313) | medium |

## 1. Wave-0 — juniper-deploy (3 PRs, independent)

### 1.1 PR `feat(observability): make monitor a working observability entry point` — Issue 1

**Files**:
- `Makefile`
- `.env.observability`

**Changes**:

```diff
 # Makefile
-.PHONY: help up down restart logs logs-data logs-cascor logs-canopy \
-        status build build-no-cache clean \
-        shell-data shell-cascor shell-canopy \
-        health wait ps demo dev test monitor
+.PHONY: help up down restart logs logs-data logs-cascor logs-canopy \
+        status build build-no-cache clean \
+        shell-data shell-cascor shell-canopy \
+        health wait ps demo dev test monitor obs
 ...
-monitor:  ## Start full stack with observability (Prometheus + Grafana)
-    @$(COMPOSE) -f $(COMPOSE_FILE) --profile full --profile observability up -d
-    @echo -e "$(GREEN)Full stack + observability starting. Prometheus: http://localhost:9090, Grafana: http://localhost:3000$(RESET)"
+monitor: prepare-secrets  ## Start full stack with observability (Prometheus + Grafana)
+    @$(COMPOSE) -f $(COMPOSE_FILE) \
+        --env-file .env.observability \
+        --profile full --profile observability up -d
+    @echo -e "$(GREEN)Full stack + observability starting. Prometheus: http://localhost:9090, Grafana: http://localhost:${GRAFANA_HOST_PORT:-3001}$(RESET)"
+
+obs: monitor  ## Alias for `make monitor` (referenced from .env.observability header)
```

```diff
 # .env.observability
-#   Or use the Makefile shortcut:
-#     make obs        # full + observability
-#     make obs-demo   # demo + observability
+#   Or use the Makefile shortcut:
+#     make monitor    # full + observability  (aliased as `make obs`)
+#     make obs-demo is intentionally NOT provided — the `demo` profile
+#     renames cascor/canopy to *-demo and their compose-DNS names break the
+#     prometheus.yml scrape targets. See POC_REMEDIATION_PLAN_2026-05-27.md §1.1.
-# Grafana admin credentials
-GRAFANA_ADMIN_USER=admin
-# Note: GRAFANA_ADMIN_PASSWORD is not used by docker-compose.yml.
+# Grafana admin credentials are managed via the Docker secret
+# (GF_SECURITY_ADMIN_PASSWORD__FILE). The user defaults to "admin" in
+# docker-compose.yml; override there if you want a different username.
```

**Validator findings (compose/Makefile, agent C)**:
- `obs-demo` is structurally valid but functionally degraded under the `demo`
  profile — cascor/canopy demo services have `-demo` suffixed compose names
  and the prometheus.yml scrape targets break. Decision: defer the alias and
  document the degradation in `.env.observability`.
- `Makefile:103` printed `localhost:3000` but actual default is `3001`
  (system-grafana avoidance, per memory). Fixed in the diff above.
- `GRAFANA_ADMIN_USER=admin` line in `.env.observability` is redundant
  (compose defaults). Removed.
- shellcheck doesn't lint Makefiles; yamllint line-length max is 512 so the
  proposed compose edits pass without churn.

**Tests**:
- Add `tests/test_makefile_observability_entrypoint.py`: assert
  `monitor:` target contains `--env-file .env.observability`. Mirrors the
  juniper-ml lint-test pattern (`test_workflow_script_paths.py`).
- Manual verification: `make monitor` from a clean checkout → all 4 prometheus
  targets `up`.

**Risk**: Low. Backward-compatible (anyone running `make monitor` today
gets the same containers plus working scrapes).

---

### 1.2 PR `fix(compose): plumb JUNIPER_DATA_METRICS_TRUSTED_IPS through compose + correct cross-doc drift` — Issue 3

**Files**:
- `docker-compose.yml`
- `.env.example`
- `prometheus/prometheus.yml`
- `notes/METRICS_AUTH_RATIONALE.md`
- `k8s/helm/juniper/templates/data-servicemonitor.yaml`
- `k8s/helm/juniper/values.yaml`

**Changes**:

```diff
 # docker-compose.yml — juniper-data service env block (around line 141)
       JUNIPER_DATA_METRICS_ENABLED: "${JUNIPER_DATA_METRICS_ENABLED:-false}"
+      # SEC-16: IP allowlist for /metrics. JSON list of CIDR strings (or
+      # bare IPs); see notes/METRICS_AUTH_RATIONALE.md.
+      JUNIPER_DATA_METRICS_TRUSTED_IPS: "${JUNIPER_DATA_METRICS_TRUSTED_IPS:-[\"127.0.0.1\",\"::1\"]}"
```

```diff
 # .env.example — after line 88
 # JUNIPER_DATA_METRICS_ENABLED=false
 # JUNIPER_CASCOR_METRICS_ENABLED=false
 # JUNIPER_CANOPY_METRICS_ENABLED=false
+
+# SEC-16: trusted-IP allowlist for juniper-data's /metrics endpoint.
+# JSON list of IP literals or CIDR ranges. Defaults to loopback only.
+# JUNIPER_DATA_METRICS_TRUSTED_IPS=["127.0.0.1","::1","172.18.0.0/16"]
```

```diff
 # prometheus/prometheus.yml — 2 occurrences
-# container's IP must be present in JUNIPER_DATA_METRICS_ALLOW_IPS for scrapes to succeed.
+# container's IP must be present in JUNIPER_DATA_METRICS_TRUSTED_IPS for scrapes to succeed.
```

```diff
 # notes/METRICS_AUTH_RATIONALE.md — 3 occurrences (lines 23, 101, 186)
-JUNIPER_DATA_METRICS_ALLOW_IPS
+JUNIPER_DATA_METRICS_TRUSTED_IPS
```

```diff
 # k8s/helm/juniper/templates/data-servicemonitor.yaml — line 11
-JUNIPER_DATA_METRICS_ALLOW_IPS via the data.env / data.envFrom values.
+JUNIPER_DATA_METRICS_TRUSTED_IPS via the data.env / data.envFrom values.
```

```diff
 # k8s/helm/juniper/values.yaml — add to data.env example block
   data:
     env:
       JUNIPER_DATA_METRICS_ENABLED: "false"
+      # JUNIPER_DATA_METRICS_TRUSTED_IPS: '["127.0.0.1","::1","10.0.0.0/8"]'  # JSON list, set when SEC-16 enforcement is desired in cluster
```

**Validator findings (compose/Makefile, agent C)**:
- **Canonical variable name confirmed**: `JUNIPER_DATA_METRICS_TRUSTED_IPS`
  (per `juniper-data/juniper_data/api/settings.py:162`, with `env_prefix="JUNIPER_DATA_"`).
- **Helm has the same drift**: `data-servicemonitor.yaml:11` references the
  wrong name and no `values*.yaml` actually sets the variable. Bundled here.
- **`notes/METRICS_AUTH_RATIONALE.md` has 3 stale references** (lines 23,
  101, 186) — same PR or future readers will re-introduce the bug.
- All `.pre-commit-config.yaml` lint gates pass on the proposed edits.

**Tests**:
- Add `tests/test_compose_metrics_trusted_ips_wired.py`: assert the env var
  is declared under `services.juniper-data.environment` in
  `docker-compose.yml`. Cheap structural lint.
- Manual: `docker compose config | grep JUNIPER_DATA_METRICS_TRUSTED_IPS`
  shows the resolved value.

**Risk**: Low. Default value preserves current loopback-only behavior.

---

### 1.3 PR `chore(grafana): assign stable panel IDs across all dashboards + lint` — Issue 5

**Files**:
- `grafana/provisioning/dashboards/juniper-overview.json`
- `grafana/provisioning/dashboards/juniper-canopy.json`
- `grafana/provisioning/dashboards/juniper-cascor.json`
- `grafana/provisioning/dashboards/juniper-data.json`
- `tests/test_grafana_dashboard_ids.py` (new)

**Changes**:
- Add sequential `"id": <int>` to every panel (rows included) in all four
  dashboards. 74 panels total.
- Strategy: per-dashboard `1..N`; cross-dashboard uniqueness is irrelevant
  because Grafana's `?viewPanel=N` is scoped to a single dashboard URL.
- Drop monotonic-increasing requirement — unique + integer is enough.
- Add a lint test cloned from `tests/test_alertmanager_config.py`:

  ```python
  # tests/test_grafana_dashboard_ids.py
  import json
  from pathlib import Path
  import pytest

  DASHBOARDS = Path(__file__).parent.parent / "grafana/provisioning/dashboards"

  @pytest.mark.parametrize("path", sorted(DASHBOARDS.glob("*.json")))
  def test_panels_have_unique_integer_ids(path):
      data = json.loads(path.read_text())
      panels = data.get("panels", [])
      ids = [p.get("id") for p in panels]
      assert all(isinstance(i, int) for i in ids), f"non-integer panel id in {path.name}"
      assert len(set(ids)) == len(ids), f"duplicate panel id in {path.name}"
  ```

**Validator findings (dashboard, agent D)**:
- 74 panels across 4 dashboards, 0% with IDs. Authoring oversight, not
  convention. `dashboard-providers.yml` has `allowUiUpdates: true` but that
  doesn't excuse missing IDs.
- Direct test precedent: `tests/test_alertmanager_config.py` does exactly
  this shape (load YAML/JSON, assert invariants). CI auto-discovers via
  `pytest tests/ -v` at `.github/workflows/ci.yml:188-211`.
- Cost/benefit honest call: low-priority but cheap (~30 min). Ship if PoC
  screenshot automation is queued; defer otherwise.

**Tests**: the lint test itself.

**Risk**: Minimal. Cosmetic + lint.

---

## 2. Wave-1 — juniper-data (2 PRs)

### 2.1 PR `feat(security): exempt /metrics from API-key middleware` — Issue 2 (data half)

**Files**:
- `juniper_data/api/constants.py`
- `juniper_data/tests/unit/test_middleware.py`
- `juniper_data/tests/unit/test_phase1d_security.py`

**Changes**:

```diff
 # juniper_data/api/constants.py
 EXEMPT_PATHS: frozenset[str] = frozenset(
     {
         "/v1/health",
         "/v1/health/live",
         "/v1/health/ready",
         "/docs",
         "/openapi.json",
         "/redoc",
+        "/metrics",  # SEC-16 MetricsAuthMiddleware still gates this by IP.
     }
 )
```

**Validator findings (EXEMPT_PATHS, agent A)**:
- `EXEMPT_PATHS` is `path in <set>` (exact match). `prometheus_client.make_asgi_app`
  exposes a single endpoint at `/metrics` with no sub-paths, so the literal
  exempt is correct.
- `EXEMPT_PATHS` is imported only by `SecurityMiddleware` in both repos
  (validator confirmed via grep). No CORS/rate-limit/logging middleware
  consults the set.
- `SecurityHeadersMiddleware`, `PrometheusMiddleware`, and `RequestIdMiddleware`
  still apply to `/metrics` (desirable).
- The existing `MetricsAuthMiddleware` IP allowlist remains the primary
  access control on juniper-data's `/metrics`; this PR does not weaken
  security posture.

**Tests to add**:
- `test_middleware.py`: `assert "/metrics" in EXEMPT_PATHS`.
- `test_phase1d_security.py`: integration test asserting
  `client.get("/metrics")` returns `200` with both
  `api_keys=["secret"]` and `metrics_trusted_ips=["testclient"]` set. The
  existing `test_metrics_allowed_when_testclient_in_allowlist` only proves
  the IP allowlist; this new test pins the exempt + allowlist composition.

**Risk**: Low. Existing IP allowlist (`MetricsAuthMiddleware`) remains in
force.

---

### 2.2 PR `feat(security): MetricsAuthMiddleware accepts CIDR ranges + IPv6 normalization` — Issue 4

**Files**:
- `juniper_data/api/observability.py`
- `juniper_data/api/settings.py`
- `juniper_data/tests/unit/test_phase1d_security.py`

**Changes** (synthesized from agent B's findings):

```python
# juniper_data/api/observability.py
import ipaddress

METRICS_DEFAULT_TRUSTED_IPS = ("127.0.0.1", "::1")


def _parse_trusted_networks(raw):
    """Compile a list of CIDR strings / bare IPs to ipaddress.ip_network objects.

    Bare-IP entries are widened to host networks (/32 or /128). Unparseable
    entries fail loud at init time — operator typos must not silently 403.
    """
    nets = []
    for entry in raw:
        try:
            nets.append(ipaddress.ip_network(entry, strict=False))
        except ValueError as exc:
            raise ValueError(
                f"JUNIPER_DATA_METRICS_TRUSTED_IPS entry {entry!r} is not "
                f"a valid IP or CIDR: {exc}"
            ) from exc
    return tuple(nets)


def _normalize_client_ip(client_ip):
    """Strip IPv6 zone-id and unwrap IPv4-mapped IPv6 to its IPv4 form."""
    if "%" in client_ip:
        client_ip = client_ip.split("%", 1)[0]
    addr = ipaddress.ip_address(client_ip)
    if isinstance(addr, ipaddress.IPv6Address) and addr.ipv4_mapped is not None:
        addr = addr.ipv4_mapped
    return addr


class MetricsAuthMiddleware:
    def __init__(self, app, trusted_ips=None):
        self.app = app
        raw = trusted_ips if trusted_ips is not None else METRICS_DEFAULT_TRUSTED_IPS
        self.networks = _parse_trusted_networks(raw)

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http":
            allowed = False
            client = scope.get("client")
            client_ip = client[0] if client else None
            if client_ip:
                try:
                    addr = _normalize_client_ip(client_ip)
                    allowed = any(addr in net for net in self.networks)
                except ValueError:
                    pass
            if not allowed:
                await send({
                    "type": "http.response.start", "status": 403,
                    "headers": [(b"content-type", b"text/plain; charset=utf-8")],
                })
                await send({"type": "http.response.body", "body": b"Forbidden"})
                return
        await self.app(scope, receive, send)
```

```python
# juniper_data/api/settings.py
from pydantic import field_validator
# ...
class Settings(BaseSettings):
    # ...
    metrics_trusted_ips: list[str] = _JUNIPER_DATA_API_METRICS_TRUSTED_IPS_DEFAULT

    @field_validator("metrics_trusted_ips")
    @classmethod
    def _validate_trusted_ips(cls, v):
        from .observability import _parse_trusted_networks
        _parse_trusted_networks(v)  # raises if any entry is invalid
        return v
```

**Validator findings (CIDR, agent B)**:
- **Collapse the two-stage parse**: `ipaddress.ip_network("127.0.0.1", strict=False)`
  already returns `127.0.0.1/32`. The proposed two-stage `ip_network` →
  `ip_address`-with-/32 fallback in my draft was redundant. Folded into the
  diff above.
- **IPv6 zone-id** (`fe80::1%eth0`): `ipaddress.ip_address()` rejects it.
  Uvicorn surfaces zone-scoped link-local addresses. Strip via
  `split("%")[0]`. Done above.
- **IPv4-mapped IPv6** (`::ffff:172.18.0.5`): membership in an IPv4 network
  returns `False` without unwrapping. Silent rejection in the exact docker
  scenario we're fixing. Done above via `addr.ipv4_mapped`.
- **Fail-loud on bad config**: silent `except ValueError: pass` produces a
  working-but-empty allowlist that 403s everything. Raise at init. Done above.
- **Existing test break**: `test_metrics_allowed_when_testclient_in_allowlist`
  (line 274) uses `metrics_trusted_ips=["testclient"]`. Under fail-loud, this
  raises at Settings construction. Fix in the same PR by updating the test
  to use `"127.0.0.1"` and an explicit `TestClient(..., client=("127.0.0.1", 12345))`.
- **Settings field validator** added above to surface bad config early.
- Stdlib `ipaddress` is the canonical choice; performance non-issue at 0.1 Hz.

**Tests to add**:
- CIDR allow (`172.18.0.5` ∈ `172.18.0.0/16`).
- CIDR reject (`10.0.0.5` ∉ `172.18.0.0/16`).
- Mixed list with CIDR + literal IP.
- IPv6 CIDR (`fd00::/8`).
- IPv4-mapped IPv6 client against an IPv4 CIDR (regression for the bug
  agent B caught).
- Invalid CIDR entry raises at Settings construction.
- Backward-compat: `["127.0.0.1", "::1"]` default behaves identically.

**Migration**:
- juniper-deploy's `.env.local` already uses literal IPs (`172.18.0.8`, etc.);
  those still work. After this PR, `.env.local` can simplify to
  `JUNIPER_DATA_METRICS_TRUSTED_IPS=["172.18.0.0/16","127.0.0.1","::1"]`
  and survive `down/up` cycles. Update the example in
  [`POC_LOCAL_ENV_TEMPLATE.md`](POC_LOCAL_ENV_TEMPLATE.md).

**Risk**: Medium. Touches security-sensitive middleware. Mitigated by
fail-loud + comprehensive tests.

---

## 3. Wave-2 — juniper-cascor (1 PR, larger scope than initially planned)

### 3.1 PR `feat(security): exempt /metrics from API-key middleware + add MetricsAuthMiddleware parity` — Issue 2 (cascor half)

**Why bigger than the data PR**: Validator A's strongest finding is that
shipping cascor's bare exempt — without a parallel IP allowlist — widens
the unintentional-exposure surface. A misconfigured deployment (port
8200 published directly, or running outside compose/K8s) would expose
`/metrics` with zero auth. The SEC-16 promotion is already on the roadmap
(`juniper-data/juniper_data/api/observability.py:62`); this PR is the
natural trigger.

**Files**:
- `src/api/middleware.py` (add `/metrics` to `EXEMPT_PATHS`)
- `src/api/observability.py` (new — copy `MetricsAuthMiddleware` + the two
  helpers from juniper-data, OR import from `juniper-observability` if that
  promotion lands in this same window)
- `src/api/settings.py` (add `metrics_trusted_ips` field with same
  `@field_validator`)
- `src/api/app.py` (mount `MetricsAuthMiddleware(get_prometheus_app(), settings.metrics_trusted_ips)`)
- `src/tests/unit/api/test_api_middleware.py` (assert `/metrics in EXEMPT_PATHS`)
- New cascor-side integration tests for the IP allowlist

**Validator findings (EXEMPT_PATHS, agent A)**:
- Exempt-only ships bare cascor `/metrics` with no auth on the compose
  network. Acceptable today (port 8200 → 8201 host-loopback bind), but
  fragile against deployment topology changes.
- The proper move is to **add `MetricsAuthMiddleware` parity in cascor in
  the same PR**. The agent's literal recommendation: "promote from
  juniper-data or duplicate inline". The promotion is preferred, but
  duplicate-inline is acceptable and matches the comment in
  `observability.py:62` that says promotion will happen as part of
  roadmap §R5.
- If scope expansion is rejected: ship the bare exempt with an explicit
  risk-acceptance comment + tracking issue. **Do not ship cascor's exempt
  silently.**

**Recommendation**: bundle the duplicate-inline `MetricsAuthMiddleware`
into this PR. Marginal cost (~50 LoC + 4 tests) and removes the asymmetry
permanently.

**Tests to add** (cascor side):
- `assert "/metrics" in EXEMPT_PATHS`.
- Integration: `client.get("/metrics")` returns `200` with
  `api_keys=["secret"]` set + `metrics_trusted_ips=["testclient"]`.
- IP-allowlist regression coverage (mirroring juniper-data's
  `test_phase1d_security.py` set).

**Risk**: Medium. New middleware in a security-sensitive surface. Mitigated
by reusing the validated juniper-data implementation verbatim.

---

## 4. Dependency graph

```
              ┌─ Wave 0 — juniper-deploy (any order, no dependencies) ─┐
              │  PR 1.1 — Makefile/.env.observability                  │
              │  PR 1.2 — TRUSTED_IPS plumbing + Helm + doc drift      │
              │  PR 1.3 — dashboard panel IDs + lint                   │
              └────────────────────────────────────────────────────────┘
                                       │
              ┌─ Wave 1 — juniper-data (sequential within wave) ──────┐
              │  PR 2.1 — EXEMPT_PATHS /metrics                       │
              │  PR 2.2 — CIDR support  (depends on 2.1's test infra) │
              └────────────────────────────────────────────────────────┘
                                       │
              ┌─ Wave 2 — juniper-cascor ──────────────────────────────┐
              │  PR 3.1 — EXEMPT_PATHS + IP allowlist parity          │
              └────────────────────────────────────────────────────────┘
                                       │
              ┌─ Wave 3 — juniper-deploy cleanup ─────────────────────┐
              │  bump image tags for juniper-data and juniper-cascor; │
              │  delete .env.local + docker-compose.override.yml from  │
              │  POC_LOCAL_ENV_TEMPLATE.md; update                     │
              │  POC_PROMETHEUS_GRAFANA_2026-05-27.md §5 to reflect    │
              │  that no workaround is needed once Waves 1+2 land.     │
              └────────────────────────────────────────────────────────┘
```

Waves 0 and 1 are independent and can ship in parallel. Wave 2 is independent
of Wave 0 but matches Wave 1's pattern (same exempt + same allowlist shape).
Wave 3 is a one-line cleanup of the PoC docs once Waves 1+2 have been
released and `juniper-deploy` consumes the new image tags.

## 5. Risks and rollback

| Risk                                                                | Likelihood | Mitigation                                                                                              |
| ------------------------------------------------------------------- | ---------- | ------------------------------------------------------------------------------------------------------- |
| CIDR refactor regresses MetricsAuthMiddleware                        | medium     | Validator B caught the `"testclient"` test break in advance; full new-test matrix listed in §2.2.        |
| Cascor `/metrics` exposed without auth on misconfigured deployment   | high if exempt-only | Bundle `MetricsAuthMiddleware` parity into PR 3.1 (validator A's strongest finding).          |
| Helm chart drift remains unfixed                                     | low        | Bundled into PR 1.2.                                                                                    |
| `obs-demo` confusion if anyone documents/uses it                     | medium     | Explicit "not provided" comment in `.env.observability`; defer the alias.                               |
| Provisioning poll picks up dashboard ID changes mid-edit             | low        | Lint catches duplicate/missing IDs; `allowUiUpdates: true` UI edits remain ephemeral (DB-only).        |

**Rollback strategy**: every PR is small and revertable. The local PoC
workaround (`.env.local` + `docker-compose.override.yml`) continues to work
regardless of which wave has landed, so the dashboard panel keeps rendering
throughout the rollout.

## 6. Out of scope (deferred follow-ups, trigger-conditioned)

- **Promote `MetricsAuthMiddleware` to `juniper-observability`** instead of
  duplicating it in cascor. Trigger: next juniper-observability minor
  release that's already touching the security surface.
- **Add `MetricsAuthMiddleware` to juniper-canopy**. Trigger: any future
  topology change that exposes canopy's `/metrics` beyond loopback.
- **A real `obs-demo` Makefile target** with a demo-aware
  `prometheus.demo.yml` that scrapes the `-demo`-suffixed compose names.
  Trigger: demand from anyone debugging metrics under the demo profile.
- **Hostname-based allowlist in `MetricsAuthMiddleware`**
  (resolve `prometheus` via compose DNS at startup, refresh on SIGHUP).
  Trigger: CIDR turns out to be insufficient in shared/CNI environments.

## 7. Independent validations summary

This plan was validated by **four independent sub-agents**, each given the
relevant issue context plus the proposed fix and instructed to form its own
judgment. Their findings are inlined per issue above; quick index:

| Sub-agent | Scope                                       | Verdict                                                                          | Most-impactful finding folded in                                                                  |
| --------- | ------------------------------------------- | -------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------- |
| A         | EXEMPT_PATHS fix (Issue 2, both repos)      | Correct for juniper-data; bare-exempt unsafe for juniper-cascor.                | Cascor must gain a parallel `MetricsAuthMiddleware` (§3.1, scope expansion).                       |
| B         | CIDR refactor (Issue 4)                     | Refactor right in shape; 4 specific correctness fixes + 1 test that would break. | IPv6 zone-id strip + IPv4-mapped IPv6 unwrap + fail-loud on bad config + `"testclient"` test fix. |
| C         | Compose/Makefile plumbing (Issues 1, 3)     | Both fixes correct; Helm + notes drift bundled; `obs-demo` deferred.            | Helm parity (`data-servicemonitor.yaml` + `values.yaml`) folded into §1.2.                          |
| D         | Dashboard panel IDs (Issue 5)               | Worth doing; trivial; lint precedent already in repo.                            | Drop the monotonic-increasing rule; sequential per-dashboard is enough.                            |

Anything that looked likely to ship and break later — silent dropping of
invalid CIDR entries, the `"testclient"` test, cascor's bare exempt, the
Helm-side drift — was caught here, not after merge.

## 8. Reproducibility — how this plan was developed

1. Read `POC_ISSUES_DISCOVERED.md` to enumerate the 5 issues.
2. Drafted a fix-shape per issue from first principles + existing patterns
   in the repos.
3. Dispatched 4 independent sub-agents in parallel, each given a single
   issue + the proposed fix + an instruction to form its own judgment.
4. Folded validator findings into the plan section-by-section, marking
   every accepted change with the source agent.
5. Cross-cut: severity, dependency graph, wave ordering, rollback.

To regenerate or extend this plan, the prompts used for each validator
are preserved in this session's transcript and can be re-issued against
updated code with `Agent({subagent_type: "general-purpose", prompt: ...})`.
