<!-- markdownlint-disable MD013 -->
# Juniper SLO Catalog

| Field         | Value                                                                                                |
| ------------- | ---------------------------------------------------------------------------------------------------- |
| **Project**   | Juniper                                                                                              |
| **File Name** | `notes/SLO_CATALOG_2026-05-03.md`                                                                    |
| **Description** | Source-of-truth SLO/SLI catalog for the Juniper observability stack. Defines the 5 user-facing release-blocking SLIs and the 8 internal-supporting SLIs that the R5.4 burn-rate alert rules and the 4 Grafana dashboards reference. |
| **Author**    | Paul Calnon                                                                                          |
| **Version**   | v1.0.0                                                                                               |
| **License**   | MIT License                                                                                          |
| **Status**    | Initial — first authoring; numeric targets are provisional and require a 30-day soak before R5.4 burn-rate alerts are taken out of "log-only" severity. See §3 caveat. |
| **Closes**    | METRICS-MON R5 entry plan Q1 (user-facing primary + internal-supporting) and Q3 (single juniper-deploy doc). |
| **Forward-references** | R5.4 (`prometheus/alert_rules.yml` burn-rate refactor), R5.3 (Grafana dashboard refresh — `grafana/provisioning/dashboards/`). |

---

## Table of Contents

1. [Purpose](#1-purpose)
2. [Conventions](#2-conventions)
3. [User-facing primary SLIs (release-blocking)](#3-user-facing-primary-slis-release-blocking)
   - [3.1 Canopy dashboard availability](#31-canopy-dashboard-availability)
   - [3.2 Canopy dashboard render latency](#32-canopy-dashboard-render-latency)
   - [3.3 Cascor train-job success](#33-cascor-train-job-success)
   - [3.4 Cascor train-epoch p95 latency](#34-cascor-train-epoch-p95-latency)
   - [3.5 Data-service POST availability](#35-data-service-post-availability)
4. [Internal-supporting SLIs (graphed only)](#4-internal-supporting-slis-graphed-only)
   - [4.1 Worker heartbeat freshness](#41-worker-heartbeat-freshness)
   - [4.2 Cascor pending-task queue depth](#42-cascor-pending-task-queue-depth)
   - [4.3 Cascor broadcast fan-out p95](#43-cascor-broadcast-fan-out-p95)
   - [4.4 Cascor command-handler p95 latency](#44-cascor-command-handler-p95-latency)
   - [4.5 Data-client request latency (canopy → data)](#45-data-client-request-latency-canopy--data)
   - [4.6 Data-client error rate by status\_class](#46-data-client-error-rate-by-status_class)
   - [4.7 Dataset POST cache-hit ratio](#47-dataset-post-cache-hit-ratio)
   - [4.8 HTTP error rate (5xx) per service](#48-http-error-rate-5xx-per-service)
5. [Cross-references](#5-cross-references)
6. [Open questions and future work](#6-open-questions-and-future-work)

---

## 1. Purpose

This catalog is the **single source of truth** for the Juniper service-level
objectives. Three downstream artifacts derive from this document and must
not redefine SLOs in a different place:

1. **R5.4 burn-rate alerts** in `prometheus/alert_rules.yml` consume the
   target percentages and burn-rate windows defined in §3 below. Every
   SLO-coupled alert rule must reference an SLI by section number in its
   annotation block. Threshold-based health alerts (`ServiceDown`,
   `ServiceRestartLoop`) are out of scope for this catalog and stay in
   place per R5 entry plan Q7 (c).
2. **Dashboard panel definitions** in
   `grafana/provisioning/dashboards/{juniper-overview,juniper-canopy,juniper-cascor,juniper-data}.json`
   surface the 5 user-facing SLIs as the headline tile on the overview
   dashboard and as the top row of each per-service dashboard. The 8
   internal-supporting SLIs appear on the per-service dashboards as
   second-row panels with no alert wiring.
3. **Incident-response paging policy** keys off the user-facing/internal
   split. Only user-facing SLO breaches (§3) page on-call; internal
   SLI degradations (§4) raise a ticket and surface in the next-business-day
   triage queue.

Per R5 entry plan Q1 resolution (c) — *user-facing primary +
internal-supporting* — the catalog deliberately splits the "wakes someone
up at 3 a.m." set from the "graphed but not paged" set. The user-facing
set is intentionally small (5 SLIs) so the on-call rotation has a
manageable signal surface; the internal-supporting set is broader (8
SLIs) and exists to give engineers context when triaging an incident
flagged by the user-facing set.

---

## 2. Conventions

### 2.1 SLI vs SLO

- **SLI (Service Level Indicator):** a quantitative measurement of a
  user-visible aspect of service behaviour, expressed as a PromQL
  expression in this catalog.
- **SLO (Service Level Objective):** a target value or range for an SLI
  over a stated rolling window, expressed as `<target>% over <window>`
  in this catalog.

### 2.2 Target windows

| Window           | Use                                                                                       |
| ---------------- | ----------------------------------------------------------------------------------------- |
| 30-day rolling   | Headline availability and success-ratio SLIs. Matches the calendar-quarter review cadence. |
| 7-day rolling    | Latency p95 SLIs. Latency distributions shift faster than availability and a 30-day window over-smooths regressions. |
| 5 m / 30 m / 2 h / 6 h | Burn-rate alerting windows (§2.4). Not user-facing target windows; only used by R5.4. |

### 2.3 Error budget

For an availability SLO of `T%` over window `W`, the error budget is
`(1 - T/100) * total_events_in_W`. For `T = 99.5%` over a 30-day window
with `100k` total events, the error budget is `500` failed events. Burn-rate
alerts compare instantaneous burn against the rate at which the budget
would be consumed in `W`.

### 2.4 Burn-rate alerts (Multi-Window Multi-Burn-Rate, MWMBR)

Per R5 entry plan Q7 (c), SLO-coupled alerts use the
**Multi-Window Multi-Burn-Rate** pattern (Google SRE workbook §5):

| Severity   | Short window | Long window | Short burn | Long burn | % of 30 d budget consumed if sustained |
| ---------- | ------------ | ----------- | ---------- | --------- | -------------------------------------- |
| Fast-burn  | 5 m          | 1 h         | 14.4×      | 14.4×     | 2 % in 1 h                              |
| Mid-burn   | 30 m         | 6 h         | 6×         | 6×        | 5 % in 6 h                              |
| Slow-burn  | 2 h          | 24 h        | 3×         | 3×        | 10 % in 24 h                            |
| Long-burn  | 6 h          | 72 h        | 1×         | 1×        | 10 % in 72 h                            |

A burn rate of `B` against an SLO of `T = 99.5%` (error budget 0.005)
fires when `failure_rate > 0.005 * B` measured over both the short
*and* the long window simultaneously. Both windows must agree, which
suppresses single-window flapping under low-traffic conditions
(R5 entry plan Risk 4). For example, fast-burn fires when:

```promql
(
  failure_ratio_5m  > 0.005 * 14.4
  AND
  failure_ratio_1h  > 0.005 * 14.4
)
```

R5.4 implements this pattern; this catalog supplies the `B`-thresholds.

### 2.5 Action policy

| Tier                     | Fast-burn | Mid-burn | Slow-burn | Long-burn |
| ------------------------ | --------- | -------- | --------- | --------- |
| User-facing primary (§3) | Page      | Page     | Ticket    | Ticket    |
| Internal-supporting (§4) | Ticket (log-only severity) | Ticket | Ticket | None |

User-facing SLOs page on-call; internal-supporting SLIs route to the
ticketing queue. R5.4 wires the routing in `alertmanager/alertmanager.yml`.

### 2.6 Provisional-targets caveat

This is the **first authoring** of the catalog. There is no production
traffic baseline against which to validate the targets. Per R5 entry
plan Risk 1, every SLO target below is marked **"initial — to revisit
after 30-day soak"**. R5.4 ships the burn-rate alerts in **log-only
severity** for the first 30 days; once a baseline exists, the targets
get tightened or relaxed and the alerts move to paging severity. Where
a target is more conservative than industry convention (e.g. `99.5%`
where Google SRE workbook examples cite `99.9%`), the rationale appears
inline. **Do not interpret the absolute numbers below as expressing
high confidence; interpret the *shape* (latency vs availability,
30-day vs 7-day) as expressing high confidence.**

### 2.7 Cardinality discipline

Every PromQL expression below uses closed-set labels only (per R1.1
cardinality discipline). The `status_class` label is bucketed to
`{2xx, 4xx, 5xx, transport_error}` (data-client) and `status` is
bucketed to `{success, error}` (data POST counter). The shared
`PrometheusMiddleware` HTTP histogram uses `{method, endpoint}` only;
`status` is a separate counter (`juniper_<svc>_http_requests_total`).

### 2.8 Service / job labels

Per `prometheus/prometheus.yml` post-R5.2, every scrape target carries
`service={juniper-data,juniper-cascor,juniper-canopy,prometheus}` and
`environment={docker,kubernetes}` labels. The PromQL expressions below
filter by `service` rather than `job` because the catalog must target
the same SLI definitions across docker-compose and k8s deployment
topologies (R5 entry plan Q4 (c) — dual scrape surfaces).

---

## 3. User-facing primary SLIs (release-blocking)

These 5 SLIs are **release-blocking**: a regression that pushes any of
them outside its SLO target should block the next release until it is
explained or remediated. Each one fires the MWMBR burn-rate alert
from §2.4 at the targets given. Action policy is per §2.5.

### 3.1 Canopy dashboard availability

**What it measures.** Whether a researcher loading the canopy dashboard
in a browser actually receives an HTML page (not a 5xx, not a transport
error). The user-visible behaviour is *"the dashboard loads when I
navigate to it"*.

**Metric source.** `juniper_canopy_http_requests_total{endpoint="/", status=~"2xx|3xx"}`
counter, populated by `PrometheusMiddleware` in
`juniper-canopy/src/observability.py` (re-export from
`juniper-observability`). The middleware uses the closed-set
`UNMATCHED_ENDPOINT_LABEL` discipline so dashboard route templates
collapse cleanly. Page-load attempts also include the canopy SPA
top-level routes (`/dashboard`, `/training`, `/datasets`); R5.3 will
expose the exact endpoint set in the panel definition.

**SLI (PromQL).**

```promql
sum by (service) (
  rate(juniper_canopy_http_requests_total{
    service="juniper-canopy",
    endpoint=~"/|/dashboard|/training|/datasets",
    status=~"2..|3.."
  }[5m])
)
/
sum by (service) (
  rate(juniper_canopy_http_requests_total{
    service="juniper-canopy",
    endpoint=~"/|/dashboard|/training|/datasets"
  }[5m])
)
```

**SLO target.** `99.5% over 30d rolling`.

**Reasoning for 99.5% (not 99.9%).** This is a research-platform
dashboard, not a transactional consumer site. Canopy has historically
restarted on config-reload (`make restart`) and the bridge-network
isolation in docker-compose can cause brief unavailability during
Prometheus scrape config reload. `99.5%` allows ~3.6 hours of
unavailability per 30 days, which comfortably covers the planned-restart
budget. Tighten to `99.9%` only after R3 readiness probe SLOs
(juniper-ml#136 follow-up) demonstrate the deployment can sustain it.

**Burn-rate thresholds (per §2.4, error budget = `0.005`).**

| Window  | Burn rate | PromQL trip threshold |
| ------- | --------- | --------------------- |
| 5 m / 1 h  | 14.4×    | `failure_ratio > 0.072` |
| 30 m / 6 h | 6×       | `failure_ratio > 0.030` |
| 2 h / 24 h | 3×       | `failure_ratio > 0.015` |
| 6 h / 72 h | 1×       | `failure_ratio > 0.005` |

**Action policy.** Fast-burn / mid-burn → page on-call. Slow-burn /
long-burn → ticket.

### 3.2 Canopy dashboard render latency

**What it measures.** How long the canopy server takes to assemble and
return the dashboard HTML for a top-level route. p95 captures the tail
that frustrates researchers without being noise-dominated like p99.

**Metric source.** `juniper_canopy_http_request_duration_seconds_bucket`
histogram (shared `PrometheusMiddleware`), labelled by
`{method, endpoint}`. The `PrometheusMiddleware` histogram uses the
default Prometheus latency buckets (5 ms → 10 s). R5.1 ratifies this
layout; the canopy R4.1 rationale doc (juniper-canopy#216) covers the
per-boundary reasoning.

**SLI (PromQL).**

```promql
histogram_quantile(0.95,
  sum by (le, service) (
    rate(juniper_canopy_http_request_duration_seconds_bucket{
      service="juniper-canopy",
      method="GET",
      endpoint=~"/|/dashboard|/training|/datasets"
    }[5m])
  )
)
```

**SLO target.** `p95 < 500 ms over 7d rolling`.

**Reasoning.** A 500 ms server-render budget leaves headroom for
network RTT + browser paint within the conventional 1-second
"interactive" budget (Nielsen / Google RAIL). The dashboard renders
server-side from cached state — sub-100 ms is the steady-state
expectation; 500 ms is the regression boundary. The 7-day window is
short enough to catch a regression introduced by a release without
being noise-dominated by single requests (latency distributions shift
faster than availability).

**Burn-rate thresholds (per §2.4, against `slow-event-fraction`).**

For latency SLOs, burn-rate is computed against the *fraction of
slow events* rather than failed events. A "slow event" is one whose
duration exceeds the SLO target; the SLO target functions as a
fast/slow boundary. The error budget is `(1 - 0.95) = 0.05` (5% of
events are allowed to exceed 500 ms).

| Window  | Burn rate | PromQL trip threshold (slow_fraction) |
| ------- | --------- | ------------------------------------- |
| 5 m / 1 h  | 14.4×    | `slow_fraction > 0.72` |
| 30 m / 6 h | 6×       | `slow_fraction > 0.30` |
| 2 h / 24 h | 3×       | `slow_fraction > 0.15` |

`slow_fraction` is computed as `1 - histogram_fraction(0.5, …)` against
the `+Inf - 500ms` bucket boundary. R5.4 will define the recording
rule that materializes this; this catalog only specifies the target.

**Action policy.** Fast-burn / mid-burn → page. Slow-burn → ticket.

### 3.3 Cascor train-job success

**What it measures.** The fraction of submitted training jobs that
complete successfully (not crashed, not aborted, not stuck). The
user-visible behaviour is *"the train run I kicked off finished
without me having to baby-sit it"*.

**Metric source.** `juniper_cascor_training_sessions_completed_total{status}`
counter (closed-set `status ∈ {success, failure, cancelled}`) shipped
in juniper-cascor#188 (R5.4-pre). The label-set authority is the
cascor source: `src/api/observability.py` (the
`_TRAINING_SESSION_STATUSES` constant and `inc_training_session_completed`
emitter). R5.4 ships the burn-rate alerts at `severity: page` /
`severity: ticket`; the catalog §2.6 30-day soak gate and the
log-only severity caveat noted below remain in force until the soak
window completes.

**SLI (PromQL).**

```promql
sum by (service) (
  rate(juniper_cascor_training_sessions_completed_total{
    service="juniper-cascor", status="success"
  }[5m])
)
/
sum by (service) (
  rate(juniper_cascor_training_sessions_completed_total{
    service="juniper-cascor"
  }[5m])
)
```

**SLO target.** `99.0% over 30d rolling`.

**Reasoning for 99.0% (not 99.5% or 99.9%).** Train-jobs are bounded
by user-supplied datasets and configurations. A non-trivial fraction of
real-world failures are user-error (NaN losses, exhausted GPU memory,
malformed network specs) — these surface as `status="failure"` and
would unfairly count against the SLO if the target were tighter.
`99.0%` over 30 days admits ~7.2 hours of cumulative training-failure
time and is the right shape for "the platform itself is reliable;
user-error is a different category". Once cascor classifies user-error
vs platform-error within the `status="failure"` bucket (a future
juniper-cascor PR — likely a sub-label or a refined closed set), the
target tightens to `99.5%` filtered to platform-error only.

**Burn-rate thresholds (per §2.4, error budget = `0.01`).**

| Window  | Burn rate | PromQL trip threshold |
| ------- | --------- | --------------------- |
| 5 m / 1 h  | 14.4×    | `failure_ratio > 0.144` |
| 30 m / 6 h | 6×       | `failure_ratio > 0.060` |
| 2 h / 24 h | 3×       | `failure_ratio > 0.030` |

**Action policy.** Fast-burn / mid-burn → page (when counter ships and
log-only severity is lifted). Slow-burn → ticket.

### 3.4 Cascor train-epoch p95 latency

**What it measures.** How long a single training epoch takes inside the
cascor training loop. The user-visible behaviour is *"my training run
isn't stuck"* and the secondary signal is *"the platform isn't
silently slowing my training"*.

**Granularity caveat.** This SLI currently measures **per-epoch
wall-clock** because cascor's api-lifecycle layer surfaces only
epoch-boundary callbacks (no per-mini-batch hooks are exposed at that
layer as of R5.4-pre / juniper-cascor#188). The metric name
`juniper_cascor_training_step_duration_seconds` is retained for forward
compatibility but its current observation point is the epoch boundary.
True per-mini-batch granularity requires deeper trainer instrumentation
inside cascor's training internals — see the forthcoming design doc
`juniper-ml/notes/code-review/METRICS_MONITORING_MINI_BATCH_INSTRUMENTATION_DESIGN_2026-05-03.md`
*(juniper-ml repo, forthcoming — link target may 404 until that PR
merges)*. Tracked in §6 open question Q2 below.

**Metric source.** `juniper_cascor_training_step_duration_seconds_bucket`
histogram (R5.4-pre / juniper-cascor#188), bucket layout
`{50ms, 100ms, 500ms, 1s, 2s, 5s, 10s, 30s, +inf}` (`_TRAINING_STEP_DURATION_BUCKETS`
in `juniper-cascor/src/api/observability.py`). Observation is emitted at
epoch boundaries from the api-lifecycle layer; the metric name is unchanged
from R5.4-pre but the documented semantics here correctly reflect the
per-epoch granularity. The histogram has **no `phase` label** post
OBS-WIRE-01 (juniper-cascor#204) — the cascor api-lifecycle layer only
ever emits an `output`-phase observation, so the previously documented
`phase=~"input|candidate|output"` regex was effectively a constant filter
and was dropped along with the label itself.

**SLI (PromQL).**

```promql
histogram_quantile(0.95,
  sum by (le, service) (
    rate(juniper_cascor_training_step_duration_seconds_bucket{
      service="juniper-cascor"
    }[5m])
  )
)
```

**SLO target.** Initial target: `p95 < 5s / 7d rolling` (per-epoch
granularity) — to revisit after 30-day soak AND once per-mini-batch
instrumentation lands (see §6 mini-batch follow-up bullet).

**Reasoning for 5s.** Train-epoch duration is dataset- and
architecture-bound, not platform-bound, but a 5-second p95 cap catches
the platform pathologies that are observably platform-bound: GIL
contention from the WS broadcast loop, replay-buffer back-pressure, and
candidate-correlation aggregation cost. The R5.1b-rebucketed
`command_handler_seconds` (`100µs → 100ms`) is sub-ms in healthy
operation; a 5-second train-epoch cap is loose enough to admit reasonable
training workloads yet tight enough to catch a regression where the
broadcast loop is starving the training thread. Once true per-mini-batch
instrumentation lands, the target will be re-derived against the
finer-grained distribution.

**Burn-rate thresholds.** Latency-style (slow-event-fraction) per §3.2
above, against the 5-second boundary. Concrete trip thresholds will be
emitted by R5.4.

**Action policy.** Fast-burn / mid-burn → page (after 30-day soak lifts
log-only severity).

### 3.5 Data-service POST availability

**What it measures.** Whether a `POST /v1/datasets` request submitted
by a researcher (directly or via cascor's juniper-data-client) succeeds.
The user-visible behaviour is *"the dataset I asked for got generated
without an error"*.

**Metric source.** `juniper_data_dataset_post_total{generator, status, cache}`
counter (R4.5 / R3.1 follow-up; juniper-data#66 documents bucket
rationale). The `status` label is closed-set `{success, error}`; the
`cache` label is closed-set `{hit, miss}`. The counter is incremented on
every POST regardless of cache outcome, so this SLI captures both
generator failures (cache miss → error) and route-layer failures (cache
hit returning 5xx, which is rare but possible).

**SLI (PromQL).**

```promql
sum by (service) (
  rate(juniper_data_dataset_post_total{
    service="juniper-data", status="success"
  }[5m])
)
/
sum by (service) (
  rate(juniper_data_dataset_post_total{
    service="juniper-data"
  }[5m])
)
```

**SLO target.** `99.5% over 30d rolling`.

**Reasoning for 99.5%.** Same reasoning as §3.1: `99.5%` is the right
shape for a research-platform service that allows planned restarts and
config reloads. Tighten only after a soak. The counter splits on
`generator` so an SLI variant per generator is possible; we keep the
catalog SLI generator-agnostic to avoid a per-generator alert
proliferation.

**Burn-rate thresholds.** Same MWMBR layout as §3.1 (error budget
`0.005`). `failure_ratio > 0.072 / 0.030 / 0.015 / 0.005` for the
four window pairs.

**Action policy.** Fast-burn / mid-burn → page. Slow-burn / long-burn
→ ticket.

---

## 4. Internal-supporting SLIs (graphed only)

These 8 SLIs surface on the per-service Grafana dashboards as
second-row panels with no paging wiring. Per §2.5, R5.4 may emit
log-only-severity alerts for these but they do not page on-call.

### 4.1 Worker heartbeat freshness

**What it measures.** Time since the most recent heartbeat from each
registered cascor-worker. A heartbeat older than the threshold means
the worker is stuck or partitioned.

**Metric source.** **STATUS 2026-05-04: bridged.** R5.4-pre
(juniper-cascor#188) shipped a `WorkerRegistryCollector` at
`juniper-cascor/src/api/workers/metrics.py` that exposes the worker
registry state as Prometheus gauges, including
`juniper_cascor_worker_heartbeat_age_seconds{worker_id}`. The earlier
"pre-condition gap" framing (preserved in §6 Q3 below for history) is
resolved for this SLI. Original R4.4 worker heartbeat fields are
populated by the same collector from the in-process state that backs
`GET /v1/workers`.

**SLI (PromQL).**

```promql
max by (worker_id) (
  juniper_cascor_worker_heartbeat_age_seconds{
    service="juniper-cascor"
  }
)
```

**SLO target.** `max worker heartbeat age < 30s, all workers`.

**Reasoning.** Workers heartbeat at 5-second cadence. A 30-second
threshold tolerates 5 missed heartbeats (one-by-one, not a coherent
network blip); fewer missed heartbeats than that is normal jitter.

**Action policy.** Ticket (log-only) when threshold breached. No paging.

### 4.2 Cascor pending-task queue depth

**What it measures.** Backlog of training tasks awaiting worker pickup.

**Metric source.** **Pre-condition gap:** `coordinator._pending_tasks`
is a Python dict not bridged to Prometheus (same bridge gap as §4.1).
References the planned `juniper_cascor_pending_tasks` Gauge.

**SLI (PromQL — once gauge ships).**

```promql
juniper_cascor_pending_tasks{service="juniper-cascor"}
```

**SLO target.** `pending_tasks < 10 sustained over 5m`.

**Reasoning.** With `WORKER_REPLICAS=2` (default), a sustained queue
depth above 10 indicates either workers are stuck (4.1) or task
scheduling is broken. Burst above 10 is acceptable (e.g. demo
auto-start submitting 5 tasks at once); sustained 5-minute breach is
the alert shape.

**Action policy.** Ticket (log-only).

### 4.3 Cascor broadcast fan-out p95

**What it measures.** How long a single WS broadcast `send` takes —
the per-connection write latency, not the across-the-fanout time.

**Metric source.** `cascor_ws_broadcast_send_duration_seconds_bucket`
histogram (R5.1b re-bucketed to sub-ms layout; juniper-cascor#185
documents the per-boundary rationale). Buckets:
`100µs / 500µs / 1ms / 5ms / 10ms / 50ms / 100ms / +inf`.

**SLI (PromQL).**

```promql
histogram_quantile(0.95,
  sum by (le, service, type) (
    rate(cascor_ws_broadcast_send_duration_seconds_bucket{
      service="juniper-cascor"
    }[5m])
  )
)
```

**SLO target.** `p95 < 1ms over 7d rolling`.

**Reasoning.** Healthy WS sends complete in <500 µs (R5.1b §4
rationale). The `5ms` bucket is the regression boundary; `1ms` is
the steady-state SLO. Sustained breach indicates GIL contention or
event-loop starvation.

**Action policy.** Ticket (log-only).

### 4.4 Cascor command-handler p95 latency

**What it measures.** How long the WS command-handler dispatch takes.
Spans `pause` / `resume` (sub-ms) through `update_params` (~50 ms).

**Metric source.** `cascor_ws_command_handler_seconds_bucket`
histogram (R5.1b re-bucketed; same buckets as §4.3).

**SLI (PromQL).**

```promql
histogram_quantile(0.95,
  sum by (le, service, command) (
    rate(cascor_ws_command_handler_seconds_bucket{
      service="juniper-cascor"
    }[5m])
  )
)
```

**SLO target.** `p95 < 50ms over 7d rolling, per command label`.

**Reasoning.** Per-command split is intentional: `pause`/`resume` should
sit in the sub-ms region, `update_params` is allowed up to 50 ms by
design. Aggregating across commands would mask both regressions.

**Action policy.** Ticket (log-only).

### 4.5 Data-client request latency (canopy → data)

**What it measures.** How long the canopy → data hop takes from the
canopy side. Captures the network latency *and* the server-side
duration of the data service.

**Metric source.** `juniper_canopy_data_client_request_duration_ms_bucket`
histogram (R4.3 closure metric; juniper-canopy#216 documents bucket
rationale). Buckets: `1, 5, 10, 25, 50, 100, 250, 500, 1000, 2500, 5000`
(milliseconds). **Tentative pending R5.1** marker on this histogram
is *retained* (not re-bucketed by R5.1b) — see §6 Q4.

**SLI (PromQL).**

```promql
histogram_quantile(0.95,
  sum by (le, service, method) (
    rate(juniper_canopy_data_client_request_duration_ms_bucket{
      service="juniper-canopy"
    }[5m])
  )
)
```

**SLO target.** `p95 < 250ms over 7d rolling`.

**Reasoning.** The canopy → data hop is intra-cluster. 250 ms is a
loose-but-not-permissive boundary that admits the data service's
`/v1/datasets` POST tail under typical generator load while catching
regressions where the data service stalls on cache lookup or
generator pool exhaustion.

**Action policy.** Ticket (log-only).

### 4.6 Data-client error rate by status\_class

**What it measures.** Fraction of canopy → data requests that fail or
return error status, split by `status_class ∈ {2xx, 4xx, 5xx, transport_error}`.

**Metric source.** `juniper_canopy_data_client_requests_total{method, status_class, error_type}`
counter (R4.3 closure metric; same rationale doc as §4.5). Closed-set
`status_class` per R1.1 cardinality discipline.

**SLI (PromQL).**

```promql
sum by (status_class) (
  rate(juniper_canopy_data_client_requests_total{
    service="juniper-canopy",
    status_class=~"5xx|transport_error"
  }[5m])
)
/
sum (
  rate(juniper_canopy_data_client_requests_total{
    service="juniper-canopy"
  }[5m])
)
```

**SLO target.** `5xx + transport_error fraction < 0.5% over 7d rolling`.

**Reasoning.** `4xx` excluded — those are caller errors (malformed
request) and not a server-health signal. `5xx` and `transport_error`
together capture "the data service or the network broke", which is the
right shape for a side-by-side error-rate SLI. `0.5%` matches the §3.5
SLO target so the canopy-side SLI doesn't fire independently of the
data-service SLO.

**Action policy.** Ticket (log-only). User-paging happens via §3.5.

### 4.7 Dataset POST cache-hit ratio

**What it measures.** Fraction of `/v1/datasets` POSTs that hit the
deterministic-dataset cache and short-circuit generation. Capacity-planning
signal — cache-hit ratio drops when researchers introduce non-deterministic
generator parameters or when the cache evicts.

**Metric source.** `juniper_data_dataset_post_total{generator, status, cache}`
counter (R4.5 / R3.1 follow-up). `cache="hit"` ÷ total.

**SLI (PromQL).**

```promql
sum (
  rate(juniper_data_dataset_post_total{
    service="juniper-data", cache="hit"
  }[5m])
)
/
sum (
  rate(juniper_data_dataset_post_total{
    service="juniper-data"
  }[5m])
)
```

**SLO target.** `cache-hit ratio > 50% over 7d rolling` (informational).

**Reasoning.** This is genuinely a capacity-planning metric, not a
reliability one. A healthy demo profile sustains cache-hit > 80% (same
seed, same generator config). A drop below 50% indicates either
researchers are exploring novel parameters (acceptable) or the cache
storage is failing to persist (alertable). Threshold deliberately loose
because the metric is informational; R5.4 may decline to emit even a
log-only alert.

**Action policy.** Ticket (log-only) on sustained breach. May be
upgraded if cache eviction becomes a real cost.

### 4.8 HTTP error rate (5xx) per service

**What it measures.** Service-wide 5xx rate, per service. Catches
regressions in routes that aren't covered by the user-facing SLOs
(e.g. `/v1/health`, `/v1/metrics`, admin endpoints).

**Metric source.** `juniper_<svc>_http_requests_total{method, endpoint, status}`
counter (shared `PrometheusMiddleware`).

**SLI (PromQL — fan out across services).**

```promql
sum by (service) (
  rate(juniper_canopy_http_requests_total{status=~"5.."}[5m])
  or
  rate(juniper_cascor_http_requests_total{status=~"5.."}[5m])
  or
  rate(juniper_data_http_requests_total{status=~"5.."}[5m])
)
/
sum by (service) (
  rate(juniper_canopy_http_requests_total[5m])
  or
  rate(juniper_cascor_http_requests_total[5m])
  or
  rate(juniper_data_http_requests_total[5m])
)
```

R5.4 will likely refactor this with a recording rule that materializes
`juniper:http_5xx_rate:by_service` for cleaner alert authoring.

**SLO target.** `5xx fraction < 1.0% per service over 7d rolling`.

**Reasoning.** Looser than user-facing SLOs by design — admin and
health endpoints are allowed a higher error rate than user-facing
endpoints (e.g. `/v1/health/ready` returning 503 when a dependency is
down is correct behaviour, not a regression). User-facing endpoint
errors are picked up by §3.1, §3.5, etc.

**Action policy.** Ticket (log-only).

---

## 5. Cross-references

### 5.1 R5 entry plan

- `juniper-ml/notes/code-review/METRICS_MONITORING_R5_ENTRY_PLAN_2026-05-02.md`
  *(in the `juniper-ml` repo, not this one)* — Q1 (user-facing primary +
  internal-supporting) and Q3 (single juniper-deploy doc) are closed by
  this catalog.

### 5.2 R5.4 burn-rate alerts (forward-reference)

- `prometheus/alert_rules.yml` — R5.4 PR will populate burn-rate alert
  rules derived from §3 SLO targets. Each alert rule must cite a
  section number from §3 in its annotation block. The threshold-based
  health alerts (`ServiceDown`, `ServiceRestartLoop`) in the existing
  `juniper_service_health` group are out of scope — they remain as-is
  per R5 entry plan Q7 (c).

### 5.3 R5.3 dashboards

- `grafana/provisioning/dashboards/juniper-overview.json` — surface the
  5 user-facing SLIs (§3) as the headline tile.
- `grafana/provisioning/dashboards/juniper-canopy.json` — §3.1, §3.2,
  §4.5, §4.6 panels.
- `grafana/provisioning/dashboards/juniper-cascor.json` — §3.3, §3.4,
  §4.1, §4.2, §4.3, §4.4 panels.
- `grafana/provisioning/dashboards/juniper-data.json` — §3.5, §4.7
  panels.
- §4.8 (HTTP 5xx per service) appears on every per-service dashboard.

### 5.4 Q5 closure (MetricsAuthMiddleware)

- `notes/METRICS_AUTH_RATIONALE.md` — the Q5 (b) decision-doc
  (per-service `MetricsAuthMiddleware`). PromQL expressions in this
  catalog assume the post-R5.2 scrape topology in `prometheus/prometheus.yml`
  where `juniper-data` `/metrics` is gated by IP allowlist and
  `juniper-cascor` / `juniper-canopy` `/metrics` are network-isolated.

### 5.5 Histogram bucket rationale (per-service R4.1 docs)

- `juniper-cascor/notes/observability/HISTOGRAM_BUCKETS_RATIONALE_2026-05-02.md`
  *(in the `juniper-cascor` repo)* — §4 covers the R5.1b sub-ms
  re-bucket layout used by §4.3 and §4.4 above.
- `juniper-canopy/notes/observability/HISTOGRAM_BUCKETS_RATIONALE_2026-05-02.md`
  *(in the `juniper-canopy` repo)* — covers `juniper_canopy_data_client_request_duration_ms`
  used by §4.5 and `canopy_ws_browser_latency_ms` (out-of-scope here).
- `juniper-data/notes/observability/HISTOGRAM_BUCKETS_RATIONALE_2026-05-02.md`
  *(in the `juniper-data` repo)* — covers
  `juniper_data_dataset_generation_duration_seconds`.

### 5.6 Scrape topology

- `prometheus/prometheus.yml` (this repo) — docker-compose scrape config.
- `k8s/helm/juniper/templates/{data,cascor,canopy}-servicemonitor.yaml`
  — k8s ServiceMonitor CRDs. Both surfaces carry the `service` and
  `environment` labels referenced in §2.8.

---

## 6. Open questions and future work

### Q1. Cascor train-job completion counter (blocks §3.3)

**Gap.** §3.3 references `juniper_cascor_training_sessions_completed_total{outcome}`
which **does not exist** as of 2026-05-03. Cascor exposes
`training_sessions_active` (Gauge) and `training_epochs_total` (Counter)
but no completion event counter. The Gauge can detect
*active-session* drops but cannot distinguish a successful completion
from a crash.

**Recommendation.** A small juniper-cascor PR (~50 lines) under R5.4 or
a separate METRICS-MON sub-track (call it R5.5a) should:

1. Add `juniper_cascor_training_sessions_completed_total{outcome}`
   Counter with closed-set `outcome ∈ {success, error, aborted}`.
2. Bump from the training-loop completion handler.
3. Update this catalog §3.3 to remove the *log-only severity* caveat.

R5.4 should reference this gap explicitly when shipping the §3.3 burn-rate
alert in log-only severity.

### Q2. Cascor train-epoch duration histogram (partial — granularity gap)

**Status.** R5.4-pre (juniper-cascor#188) shipped
`juniper_cascor_training_step_duration_seconds_bucket` with the
`{100µs, 1ms, 10ms, 100ms, 1s, 5s, 30s, 60s, +inf}` bucket layout. The
metric name was retained for forward compatibility, but the cascor
api-lifecycle layer surfaces only epoch-boundary callbacks (no
per-mini-batch hooks at that layer). As shipped, the histogram measures
**per-epoch** wall-clock rather than per-mini-batch wall-clock. §3.4 has
been updated (this PR) to reflect the per-epoch granularity honestly.

**Remaining gap.** True per-mini-batch instrumentation requires deeper
trainer internals work — tracked separately in **§6 Q5** (per-mini-batch
training instrumentation) below, with a forthcoming juniper-ml design
doc as the forward reference.

### Q3. R4.4 worker → Prometheus bridge gap (§4.1 RESOLVED · §4.2 still open)

**Status 2026-05-04: partially resolved.** Path A was taken — R5.4-pre
(juniper-cascor#188) shipped `WorkerRegistryCollector` at
`juniper-cascor/src/api/workers/metrics.py` exposing worker heartbeat
fields as Prometheus gauges including
`juniper_cascor_worker_heartbeat_age_seconds{worker_id}`. **§4.1
(worker heartbeat freshness) is now computable** against this gauge.

**§4.2 (pending-task queue depth) is still open.** No
`juniper_cascor_pending_tasks` gauge exists; the §4.2 alert ships in
juniper-deploy `prometheus/alert_rules.yml` guarded by
`absent_over_time(...) == 0` so it stays inert until a bridge ships.

**Original gap framing (preserved for history).** R4.4 added
training-loop instrumentation fields to the worker heartbeat payload
but the heartbeat was exposed only on JSON `GET /v1/workers` from
juniper-cascor — not bridged to Prometheus.

**Recommendation (residual §4.2 work).** Add a
`juniper_cascor_pending_tasks` gauge to the existing
`WorkerRegistryCollector` populated from the worker coordinator's
pending-task queue depth. Track as a small future cascor sub-track.

### Q4. Two cascor histograms still flagged "tentative pending R5.1"

R5.1b re-bucketed `cascor_ws_broadcast_send_duration_seconds` and
`cascor_ws_command_handler_seconds`. The remaining 4 R4.1-flagged
histograms are:

| Histogram | Repo | Status this catalog ratifies |
| --------- | ---- | --------------------------- |
| `juniper_cascor_inference_duration_seconds` | juniper-cascor | **Not ratified** — see below |
| `cascor_ws_resume_replayed_events` | juniper-cascor | **Not ratified** — see below |
| `juniper_canopy_data_client_request_duration_ms` | juniper-canopy | **Ratified** by §4.5 above (HELP string update is a follow-up) |
| `juniper_data_dataset_generation_duration_seconds` | juniper-data | **Ratified** by §3.5 (indirectly, via the `post_total` counter that wraps it) |

The two cascor histograms `inference_duration_seconds` and
`resume_replayed_events` are **not** referenced by any SLI in this
catalog (§3 and §4 above). Their bucket layouts are therefore not
exercised by the SLO catalog and the "tentative pending R5.1" markers
in their HELP strings cannot be definitively resolved here.

**Recommendation.** Two options:

- **Option A — ratify the existing R4.1 layouts as-shipped.** Open a
  small juniper-cascor PR that flips the HELP strings from
  *"R4.1 buckets tentative pending R5.1"* to *"buckets ratified by
  juniper-deploy SLO catalog 2026-05-03"*. No code change to the
  bucket arrays themselves. Closes the markers without forcing a
  re-bucket.
- **Option B — schedule R5.1c.** A follow-up sub-track that authors
  per-boundary justification for the 2 remaining histograms
  (potentially driving SLI definitions for them). Larger scope; only
  worth it if the histograms are likely to grow user-facing SLIs.

**Recommendation: Option A.** Both histograms are internal-supporting
in nature; their bucket layouts have been exercised in production
since R4.1 without complaint. A re-bucket without a driving SLI is
premature optimization. **R5.4 PR or a follow-up doc-only PR should
land Option A.**

### Q5. Per-mini-batch training instrumentation (refines §3.4)

**Gap.** R5.4-pre (juniper-cascor#188) shipped the histogram, but the
api-lifecycle layer exposes only epoch-boundary callbacks — so the
metric currently measures per-epoch wall-clock. A follow-up sub-track
will design and implement true per-mini-batch instrumentation in
cascor's trainer internals. Forward-reference design doc:
`juniper-ml/notes/code-review/METRICS_MONITORING_MINI_BATCH_INSTRUMENTATION_DESIGN_2026-05-03.md`
*(juniper-ml repo, forthcoming — branch
`docs/metrics-mon-mini-batch-instrumentation-design`; cross-repo link
may 404 until that PR merges)*. §3.4 will be revisited once it lands.

### Q6. Soak window before targets become release-blocking

Per §2.6 caveat, every numeric target in §3 is initial. R5.4 ships
burn-rate alerts in log-only severity for the first 30 days of
production traffic. After the soak:

1. Compare actual burn rates against the §3 targets.
2. Tighten or relax targets per the observed distribution.
3. Lift the log-only severity to paging severity for §3.1, §3.2,
   §3.5 (which have all their pre-conditions met today).
4. §3.3 and §3.4 wait on Q1 / Q2 before joining the paging set.

This catalog should be revisited 2026-06-15 with a target-tightening
PR.

---

<!-- markdownlint-enable MD013 -->
