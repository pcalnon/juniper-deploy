# MetricsAuthMiddleware — Per-Service vs. Shared Library Decision

**Status:** Decided — keep per-service.
**Owner:** observability track (METRICS-MON R5.2)
**Decided:** 2026-05-02
**Closes:** R2.1 design Q3 (2026-04-28); R5 entry plan Q5 (2026-05-01)
**Cross-repo refs:**

- `juniper-ml/notes/code-review/METRICS_MONITORING_R2.1_SHARED_OBSERVABILITY_DESIGN_2026-04-28.md`
  *(in the `juniper-ml` repo, not this one)*
- `juniper-data` SEC-16 commit / changelog entry that introduced
  `MetricsAuthMiddleware`
- `juniper-deploy` `prometheus/prometheus.yml` (docker scrape) and
  `k8s/helm/juniper/templates/{data,cascor,canopy}-servicemonitor.yaml`
  (k8s scrape) — both updated in the R5.2 PR that ships alongside this doc

---

## 1. Context

`juniper-data` ships `MetricsAuthMiddleware`, an IP-allowlist guard added
under SEC-16. The middleware checks the request peer IP against the
`JUNIPER_DATA_METRICS_ALLOW_IPS` env var on every `GET /metrics` and
returns `403 Forbidden` if the peer is not on the list. When the env var
is empty, the middleware allows all IPs (preserving local-dev ergonomics).

The other two services that expose `/metrics` — `juniper-cascor` (port
8200 in container, 8201 on host) and `juniper-canopy` (port 8050) — do
not currently ship any equivalent middleware. Their `/metrics` endpoints
respond `200 OK` to any caller that can reach them at the network layer.

Three Juniper services therefore have three different `/metrics`
postures, and the question for the broader observability work is:

> Should `MetricsAuthMiddleware` be lifted out of `juniper-data` and
> into the shared `juniper-observability` library, so all three services
> (and any future services) get the same IP-allowlist behaviour by
> default?

This was first raised as **Q3 in the R2.1 shared-observability design
doc** (2026-04-28) and re-surfaced as **Q5 in the R5 entry plan**
(2026-05-01). The R5 entry plan tentatively resolved the question to
**"keep per-service, document rationale"**, with the documentation
itself deferred to this R5.2 sub-track.

This doc closes that documentation deferral.

---

## 2. Decision

**Keep `MetricsAuthMiddleware` per-service in `juniper-data`. Do not
move it to `juniper-observability` at this time.**

`juniper-cascor` and `juniper-canopy` continue to expose `/metrics`
without an in-process IP allowlist. Their scrape protection is provided
at the network layer (NetworkPolicy in k8s, bridge-network isolation in
docker-compose).

The decision is reversible — see §5 for the triggers that would
re-open it.

---

## 3. Reasoning

The decision is driven by four factors that, taken together, point
toward keeping the middleware narrowly scoped:

### 3a. Different exposure topologies

`juniper-cascor` and `juniper-canopy` `/metrics` endpoints are not
exposed beyond the cluster boundary in any documented deployment
topology:

- The k8s helm chart installs them as `ClusterIP` services
  (see `k8s/helm/juniper/templates/{cascor,canopy}-service.yaml`).
- The canopy ingress (`k8s/helm/juniper/templates/ingress.yaml`) routes
  `/` and dashboard paths only — it does not route `/metrics`.
- The docker-compose stack maps the cascor container's host port for
  developer convenience (8201->8200), but there is no equivalent
  `/metrics`-only exposure on a public interface.

`juniper-data` has historically been treated differently. CI runners,
public test clients, and ad-hoc dataset-fetch scripts have all needed
access to it from outside the deployment perimeter. SEC-16 was opened
specifically because `juniper-data` `/metrics` had been observed
reachable from contexts the other two services never see. The
asymmetry in middleware coverage reflects an asymmetry in real-world
exposure.

### 3b. Network-layer enforcement is sufficient (and already present) for cascor / canopy

In production k8s the `networkpolicy-cascor.yaml` and the deny-all
default policy (`networkpolicy-deny-all.yaml`) restrict ingress to the
cascor and canopy pods to known peers (canopy, prometheus). Adding an
in-process IP allowlist on top of NetworkPolicy is defence-in-depth that
this track does not currently judge to be worth the configuration cost,
because:

- The middleware adds a `JUNIPER_<SVC>_METRICS_ALLOW_IPS` env var to the
  service config surface. That surface has to be threaded through three
  different deployment artifacts (helm values, docker-compose env,
  systemd unit) per service.
- Operators who deploy with the kube-prometheus-stack subchart would
  need to discover the Prometheus pod IP (which is non-deterministic
  across rescheduling) and add it to the allowlist. The most common
  workaround is to set the allowlist to `0.0.0.0/0`, which silently
  defeats the protection.
- Misconfiguration (empty allowlist treated as "allow all", or a
  too-broad allowlist) is the most likely failure mode and produces no
  alert.

### 3c. `juniper-data` exposure justifies the per-service cost

For `juniper-data`, the same trade-off comes out the other way: the
service is exposed beyond the cluster boundary in enough deployments
that a defence-in-depth IP allowlist is worth the configuration cost.
SEC-16 was opened against a real observed exposure, not a theoretical
one, and the middleware shipped with documented allowlist defaults that
work for the common cases (local dev, CI, deployed prometheus).

### 3d. Lifting to shared lib forces config surface on services that don't need it

If `MetricsAuthMiddleware` moved to `juniper-observability` as an
opt-out, every service would inherit the new env var and the
"empty == allow all" trap. If it moved as an opt-in, every service
would inherit the import but nothing would change in practice for
cascor / canopy — at which point the lift hasn't bought anything.

The shared-library boundary exists to deduplicate logic that is *the
same* across services. The auth posture is not the same across services
today, and §3a/3b explain why it shouldn't be forced to be.

---

## 4. What this means in practice

| Question                                        | Answer (today)                                                                                              |
| ----------------------------------------------- | ----------------------------------------------------------------------------------------------------------- |
| Does `juniper-cascor` `/metrics` need an IP allowlist? | No. NetworkPolicy + ClusterIP boundary is the enforcement layer.                                            |
| Does `juniper-canopy` `/metrics` need an IP allowlist? | No. Same reasoning. The canopy ingress does not route `/metrics`.                                           |
| Does `juniper-data` keep `MetricsAuthMiddleware`?      | Yes. SEC-16 stays as-shipped.                                                                                |
| Does `juniper-observability` get the middleware?       | No. The library stays focused on metric registries / instrumentation helpers, not auth.                      |
| Where are scrape sources documented?                   | `prometheus/prometheus.yml` (docker), `k8s/helm/juniper/templates/*-servicemonitor.yaml` (k8s).              |

---

## 5. Future-revisit triggers

This decision SHOULD be re-opened if any of the following becomes true:

1. **Cascor or canopy `/metrics` gets exposed beyond the cluster
   boundary.** For example: a new ingress rule that routes `/metrics`,
   a debug NodePort that includes the metrics port, or a deployment
   topology that places the service on the public side of a load
   balancer. If the exposure asymmetry §3a relies on goes away, the
   case for keeping the middleware narrowly scoped weakens.

2. **A third Juniper service grows IP-allowlist requirements.** Two
   services with `MetricsAuthMiddleware` is per-service. Three or more
   is a pattern, and at three the deduplication value of a shared
   implementation starts to outweigh the §3d cost.

3. **An audit or compliance requirement mandates uniform metrics-auth
   posture across all services.** The most likely vector is a SOC2 /
   ISO 27001 control that asks for "all observability endpoints
   gated by an authentication mechanism."

4. **NetworkPolicy / ClusterIP isolation breaks down.** For example,
   a multi-tenant cluster where pods from other namespaces can reach
   Juniper service pods. At that point §3b stops holding.

When any of these triggers fires, re-open Q3 of R2.1 and update this
doc.

---

## 6. Implementation pointers

If a future PR does lift the middleware to `juniper-observability`, the
shape worth aiming for is:

- Module: `juniper_observability.metrics_auth.MetricsAuthMiddleware`
- Same constructor signature as the current `juniper-data` impl
- Per-service env var (`JUNIPER_<SVC>_METRICS_ALLOW_IPS`) so services
  keep independent allowlists
- An explicit "empty allowlist" semantic decision (`deny all` vs.
  `allow all`) — the current `juniper-data` behaviour of "empty = allow
  all" is permissive-by-default and should probably flip if/when the
  middleware lands in a shared lib

For now, none of that is implemented. This file documents the
deliberate decision not to.
