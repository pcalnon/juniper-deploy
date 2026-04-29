# Juniper Probe Graph — Health-readiness Dependency Topology

**Owner:** Paul Calnon
**Last updated:** 2026-04-29
**Closes:** METRICS-MON R2.3 (seed-15) probe-direction symmetry. See [`notes/code-review/METRICS_MONITORING_ROADMAP_2026-04-25.md`](https://github.com/pcalnon/juniper-ml/blob/main/notes/code-review/METRICS_MONITORING_ROADMAP_2026-04-25.md) §5 R2.3 in juniper-ml.

This is the operator-facing reference for **who probes whom** at `/v1/health/ready` time across the Juniper service graph, plus the severity policy each server applies when a probed dependency is unhealthy. Keep this doc in sync with the per-repo readiness handlers.

---

## 1. The graph

```
                 ┌─────────────────────────┐
                 │     juniper-canopy      │
                 │    (Dash UI, FastAPI)   │
                 │                         │
                 │  status policy on a     │
                 │  failed upstream:       │
                 │     "degraded" / 200    │
                 └────────────┬────────────┘
                              │
              probes both     │
                              │
              ┌───────────────┴───────────────┐
              ▼                               ▼
   ┌──────────────────────┐        ┌──────────────────────┐
   │   juniper-cascor     │        │   juniper-data       │
   │  (FastAPI server)    │        │  (FastAPI server)    │
   │                      │        │                      │
   │ status policy on a   │        │ status policy on a   │
   │ failed upstream:     │        │ failed upstream:     │
   │   "not_ready" / 503  │        │   "not_ready" / 503  │
   └──────────┬───────────┘        └──────────────────────┘
              │                              ▲
              └─ probes (when                │
                JUNIPER_DATA_URL set) ───────┘

   ┌──────────────────────┐
   │ juniper-cascor-worker│
   │ (asyncio HTTP probe) │
   │                      │
   │ status policy:       │
   │   "not_ready" / 503  │
   │   on local liveness/ │
   │   readiness fail     │
   │                      │
   │ Probes no upstreams  │
   │ — workers attach to  │
   │ cascor via WebSocket │
   │ and the WS client is │
   │ the upstream surface │
   └──────────────────────┘
```

Plain reading:

- **canopy** probes **both** juniper-data and juniper-cascor on every readiness call. JuniperCascor is conditional on `JUNIPER_CANOPY_CASCOR_SERVICE_URL` being set (demo mode leaves it unset → reported as `not_configured`).
- **cascor** probes **juniper-data** when `JUNIPER_DATA_URL` is set. Always probes its own internal `lifecycle` manager as a required dep.
- **data** probes only its **storage** dependency (filesystem path; an in-process check, not a network call). It is a leaf in the network probe graph.
- **worker** probes nothing externally at HTTP-readiness time. Its readiness tick consults the WebSocket connection state to cascor (the worker's only upstream). The worker is reachable via HTTP probes for orchestrator restart decisions; it does not propagate upstream cascor health to its own readiness.

---

## 2. Severity policy per server

The two servers that **gate traffic shedding** (cascor, data) return `503 not_ready` when a required upstream is unhealthy so that load balancers and Kubernetes endpoints controllers can pull them out of rotation. Canopy stays at `200 degraded` to keep the dashboard reachable, since the dashboard's job during an outage is to **show** the operator what is broken — making it itself unreachable would be the second failure on top of the first.

| Server | Required deps | Status when required dep healthy | Status when required dep unhealthy | HTTP code on unhealthy | Rationale |
|---|---|---|---|---|---|
| juniper-data | storage | `ready` | `not_ready` | **503** | Without storage the service cannot serve dataset reads or accept generations. LBs must stop routing traffic. |
| juniper-cascor | lifecycle (always); juniper-data (when URL set) | `ready` | `not_ready` | **503** | Without lifecycle the training control plane is dead. Without juniper-data (when configured) the worker pool cannot fetch artifacts. |
| juniper-canopy | (none gate to 503) | `ready` | `degraded` | **200** | Dashboard must remain reachable so operators can read the diagnostic body. Severity is conveyed via `status` field, not HTTP status. |
| juniper-cascor-worker | local liveness tick (250 ms budget) | `ready` | `not_ready` | **503** | k8s probe-driven restart: a wedged worker should be replaced, not retried in place. Worker has no probed network upstream — the WS connection to cascor is the worker's "upstream" but is not surfaced via `/v1/health/ready` (would tightly couple every worker pod's restart fate to cascor). |

The asymmetry between cascor (503) and canopy (200/degraded) is **intentional**, not a bug. Tests in each repo pin both behaviors:

| Repo | Test asserting the policy | Asserts |
|---|---|---|
| juniper-data | `juniper_data/tests/unit/test_health_enhanced.py::test_readiness_503_when_required_dep_unhealthy` | storage missing → 503 + `status=not_ready` |
| juniper-cascor | `src/tests/unit/api/test_api_health.py::test_readiness_503_when_juniper_data_unhealthy` | data probe unhealthy → 503 + `status=not_ready` |
| juniper-canopy | `src/tests/unit/test_health.py::TestReadinessDownstreamInjection` | upstream probe unhealthy → 200 + `status=degraded`; explicit `test_canopy_never_returns_503_on_upstream_down` regression guard |
| juniper-cascor-worker | `juniper_cascor_worker/tests/test_http_health.py::TestReadiness` | local readiness tick raise → 503 + `X-Juniper-Readiness: not_ready` |

If the asymmetry ever needs to flip, change the test FIRST and only then the handler — the regression guard exists precisely to make accidental drift loud.

---

## 3. Probe payload — `X-Juniper-Readiness` header

All four services emit the `X-Juniper-Readiness: ready | degraded | not_ready` response header on `/v1/health/ready`. The header mirrors the body `status` field byte-for-byte; operators who want a fast probe (e.g. `curl -I`) can read the header without parsing JSON.

The header constant is single-sourced in [`juniper-observability`](https://pypi.org/project/juniper-observability/) (`READINESS_HEADER`). The cascor-worker uses the same literal but does not import the lib — see [`METRICS_MONITORING_R2_EXIT_GATE_WORKER_ADOPTION_2026-04-29.md`](https://github.com/pcalnon/juniper-ml/blob/main/notes/code-review/METRICS_MONITORING_R2_EXIT_GATE_WORKER_ADOPTION_2026-04-29.md) for the rationale.

---

## 4. Adding a new probed dependency

When a server gains a new upstream:

1. Decide whether it is **required** (gates 503/not_ready) or **optional** (gates degraded/200). Default: required.
2. Add the probe call inside the readiness handler using `juniper_observability.probe_dependency` (sync) or canopy's async wrapper.
3. Add the dep key to the response `dependencies` dict — kebab-cased lowercase identifier.
4. Add a regression test that injects the dep as unhealthy and asserts the documented severity (503 for cascor/data, 200/degraded for canopy).
5. Update §1 graph, §2 severity table, and §3 in this file.
6. If the new edge introduces a cycle (e.g. cascor probes canopy), **stop and reconsider** — cycles in the readiness graph cause cascading false-503s during a single-service outage. The current graph is a DAG and should remain one.

---

## 5. Re-evaluation triggers

This document should be revisited when **any** of the following becomes true:

- A new service joins the Juniper ecosystem.
- An existing server gains a probed upstream not listed above.
- Severity policy needs to change (e.g. canopy starts returning 503 on a critical-path failure).
- The R2.1 shared `juniper-observability` lib changes the contract constants (`READINESS_HEADER`) — every probe-emitting site needs to be re-validated.
- A cross-cutting bug (analogous to BUG-JD-06) requires a parallel patch in more than one server.

---

## 6. Operator runbook — checking the graph in production

```bash
# Each service's readiness, headers only:
for svc_url in \
  http://juniper-data:8100/v1/health/ready \
  http://juniper-cascor:8200/v1/health/ready \
  http://juniper-canopy:8050/v1/health/ready ; do
    echo "=== ${svc_url} ==="
    curl -sI "$svc_url" | grep -iE "X-Juniper-Readiness|HTTP/"
done

# Workers (one per pod, in-cluster):
kubectl exec <worker-pod> -- curl -sI http://127.0.0.1:8210/v1/health/ready | grep -iE "X-Juniper-Readiness|HTTP/"
```

Expected when everything is healthy:

```
=== http://juniper-data:8100/v1/health/ready ===
HTTP/1.1 200 OK
X-Juniper-Readiness: ready

=== http://juniper-cascor:8200/v1/health/ready ===
HTTP/1.1 200 OK
X-Juniper-Readiness: ready

=== http://juniper-canopy:8050/v1/health/ready ===
HTTP/1.1 200 OK
X-Juniper-Readiness: ready
```

If juniper-data is down: cascor flips to `503 / not_ready`, canopy stays at `200` but its body's `dependencies.juniper_data.status` becomes `unhealthy` and overall `status` becomes `degraded`.

---

## 7. Changelog

| Date | Change | Source |
|---|---|---|
| 2026-04-29 | Initial document | METRICS-MON R2.3 / seed-15 (juniper-ml) — closes the R2 phase exit gate on probe-direction symmetry |
