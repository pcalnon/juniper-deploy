# Juniper Deploy — Deployment Trust Contract (SEC-F19 / SEC-F22 posture)

**Project**: Juniper — Cascade Correlation Neural Network Research Platform
**Application**: juniper-deploy (containerized stack)
**Author**: Paul Calnon
**Status**: Adopted posture (Phase 0 / D8) + the two-flag bind attestation & verifiable preflight
(D2, deploy side). The compose now carries the explicit loopback-publish attestation and a bring-up
preflight verifies it; the app-layer bind-guard lands in the sibling canopy / cascor PRs (this trio
must merge together).
**License**: MIT License
**Last Updated**: 2026-07-06

---

## 1. Purpose

This is the **deployment contract** for the containerized Juniper stack: a short, load-bearing
statement of what the stack trusts and why. It exists because the stack's real security perimeter is
an *implicit default* today, and two live-confirmed audit findings (SEC-F19, SEC-F22) turn on operators
understanding — and not silently defeating — that perimeter.

It is the **D8 / Phase 0** deliverable of the remediation design of record:
`juniper-ml/notes/JUNIPER_2026-07-03_JUNIPER-CANOPY_CONTROL-SURFACE-AUTH-AND-NAT-DESIGN.md`
(§3 shared root cause, §4 Option A, §5 Option C, §7 sequencing, §8 D1/D5/D6/D7/D8). The findings were
surfaced by `juniper-ml/notes/JUNIPER_2026-07-02_JUNIPER-ECOSYSTEM_STACK-SECURITY-AUDIT-PLAN.md` (§5.2, HO-3 / HO-6).

This document changes no runtime behavior. The one runtime change shipped alongside it is **D5**
(deterministic metrics subnets — §4 below).

---

## 2. The contract, in one sentence

> **Network position IS the trust boundary.** For the stack in its current single-user / trusted-LAN
> research mode, the security perimeter is the *coarse* boundary — the loopback host bind and the
> `internal: true` networks — **not** any of the fine-grained per-IP mechanisms inside the bridge, which
> Docker NAT defeats (every client presents as the bridge gateway IP).

Everything below is a corollary.

| Invariant | Statement | Enforced by (today) | Deferred complement |
| --- | --- | --- | --- |
| **I1 — loopback default** | Every published host port binds `127.0.0.1` by default. | compose `${BIND_HOST:-127.0.0.1}:…` publishes + regression test `tests/test_compose_security_config.py::test_published_ports_default_to_loopback_bind` (DEPLOY-08) + the **bind-posture preflight** (`scripts/preflight_bind_posture.sh`, run before every bring-up) verifies the loopback-publish attestation. | App-layer startup **bind-guard** (D2) — sibling canopy / cascor PRs; see §3. |
| **I2 — internal isolation** | `backend` / `data` carry no external route. | compose `networks: {backend,data}: internal: true`. | — |
| **I3 — `0.0.0.0` needs a proxy** | Exposing the control surface off-loopback is **only** supported behind a fronting authenticating proxy. | Documentation (this file) + the escape hatch shipped commented at loopback (`.env.example:11`) + the preflight **fails closed** on an un-attested non-loopback publish. | The proxy itself (**D7**) does not exist yet; `JUNIPER_<SVC>_AUTH_PROXY_ATTESTED` is the (attestation-only) opt-in; the app-layer bind-guard (**D2**) is the sibling PR. |
| **I4 — metrics = network scope** | The `/metrics` IP allowlist authorizes **which subnets** may scrape, not which hosts. | `MetricsAuthMiddleware` (fail-closed) + pinned `ipam` subnets + `internal:true` (**D5**, this PR). | XFF-from-trusted-proxy (**D6/A**), only once the proxy exists. |
| **I5 — per-IP caps ≠ auth** | The per-IP WS caps and HTTP rate buckets are **DoS-dampening**, not authentication. | Documented here; caps still run (best-effort). | Global + per-session caps (**D4**) restore per-user fairness under NAT. |

---

## 3. The control surface is loopback-bound by default

canopy's browser training-control routes (`POST /api/train/{start,pause,resume,stop,reset}`,
`GET /api/train/status`) are **key-exempt** and gated by an Origin-allowlist + anonymously-mintable
CSRF token (design §2.1). That gate is **forgeable by any in-network non-browser client** (SEC-F22,
confirmed live HO-6): a spoofed `Origin` header plus an anonymously-minted `/api/csrf` token drives the
full control surface with no real credential. A page-injected token (design Option B1) does **not** close
this — it merely relocates the anonymous mint from `/api/csrf` to the anonymously-served `/dashboard/`
(design §4, decision **D3**). The **browser holds no credential of any kind** today (there is no dashboard
login — design §2.1).

Therefore the **only effective control** for that surface today is that it is **not reachable off-host**:
the compose publish binds `127.0.0.1`. This is invariant **I1**. It is currently an *implicit default*.

**Enforcing-code complement (D2, Phase 1) — two-flag attestation + a verifiable preflight.** The design
specifies a symmetric app-layer **startup bind-guard** in canopy and cascor: refuse to start when
configured to bind a non-loopback interface **unless** one of two explicit, per-service attestation flags
is set (design §4 Option A, §7 Phase 1, §8 D2). The attestation is split into a **verifiable** half and an
**attestation-only** half:

- `JUNIPER_<SVC>_LOOPBACK_PUBLISH_ATTESTED=true` — the service is reachable **only** via a loopback-only
  host publish. This is **verifiable**, and is verified: `scripts/preflight_bind_posture.sh` renders
  `docker compose config` and asserts every published host port of the service binds `127.0.0.0/8`
  before every bring-up (`make up/demo/dev/monitor/obs-demo`, and standalone `make preflight`). Because
  the containers bind `0.0.0.0` inside their netns (`..._HOST=0.0.0.0`), the compose sets this flag
  explicitly on all canopy/cascor services; the preflight makes the claim fail-closed rather than trusted.
- `JUNIPER_<SVC>_AUTH_PROXY_ATTESTED=true` — a fronting authenticating reverse proxy fronts the service
  (Phase-4 / D7). This is **attestation-only**: nothing here or in the app can verify a proxy exists, so
  it is a deliberate operator opt-in that suppresses the loopback-publish requirement. It is set
  **nowhere** in the shipped compose (no proxy exists yet — D7 is deferred).

Together this converts the prose assumption into a fail-closed invariant and closes the "silent
`BIND_HOST=0.0.0.0`" footgun. (This flag pair replaces the earlier single-flag sketch, which conflated
the verifiable loopback-publish claim with the unverifiable proxy claim.)

> Status of the enforcing code (updated 2026-07-06): the **deploy side** of D2 ships in this PR — the
> compose sets `JUNIPER_<SVC>_LOOPBACK_PUBLISH_ATTESTED=true` on every canopy/cascor service and the
> **bind-posture preflight** (`scripts/preflight_bind_posture.sh`, gate
> `tests/test_compose_bind_posture_attestation.py`) verifies it before bring-up. The **app-layer
> bind-guards** in canopy and cascor are the sibling PRs that read the same two flags; this deploy PR
> **must merge together with** them (the compose attests a posture the apps enforce). Until all three
> land, I1/I3 are enforced by the compose loopback publish (DEPLOY-08) + the preflight + this contract —
> treat off-loopback exposure as unsupported.

The canopy auth design already stated this precondition and is the origin of the requirement:
`juniper-canopy/notes/JUNIPER_CANOPY_TRAINING-CONTROL-AUTH_DESIGN_2026-06-30.md` §7.3 / §12 OQ-3 —
"The fix must not be shipped on a build that binds the control surface to a public interface without a
fronting auth layer."

---

## 4. The metrics allowlist is network-scope authorization (D5 — shipped in this PR)

The four compose networks are pinned to **static** `ipam.config.subnet` CIDRs, and
`.env.observability`'s `*_METRICS_TRUSTED_IPS` are pinned to **exactly** the subnets each scrape target
shares with Prometheus:

| Network | Pinned subnet | Role |
| --- | --- | --- |
| `backend` | `172.28.0.0/16` | `internal: true` |
| `data` | `172.29.0.0/16` | `internal: true` |
| `frontend` | `172.30.0.0/16` | bridge |
| `monitoring` | `172.31.0.0/16` | bridge (prometheus/grafana/alertmanager only — no scrape target) |

- `juniper-data` → `backend + data` → `172.28, 172.29` + loopback
- `juniper-cascor` / `juniper-canopy` → `backend + data + frontend` → `172.28, 172.29, 172.30` + loopback

Subnet choice (design §8 OQ-3 / §9 R3): the **top four /16s** of Docker's default address pool
(172.17–172.31). Docker holds `172.17.0.0/16` for the default bridge and auto-assigns user networks
bottom-up from `172.18`, so pinning the top avoids both auto-assignment and the audit's observed
`172.23.0.0/16` (HO-3). **Collision-checked 2026-07-04** against the host daemon
(`docker network inspect`): only `172.17.0.0/16` was allocated — `172.28`–`172.31` all free.

**Why this is authorization, not authentication (I4).** SEC-F19: Docker NAT collapses every client to the
bridge gateway, so a per-IP allowlist **cannot** distinguish individual hosts inside the bridge. The
allowlist is real only in **combination** with `internal: true` isolation on `backend`/`data` and the
**fail-closed** `MetricsAuthMiddleware` (loopback-only default; 403 on absent/unparseable client IP;
fail-loud on a bad CIDR; IPv4-mapped-IPv6 unwrap). Pinning removes the dynamic-IPAM drift that caused
either a 403 scrape failure (availability) or a whole-subnet-trust widening (authorization).

The pinned subnets and the allowlist CIDRs are **drift-checked** by
`tests/test_compose_metrics_subnet_alignment.py`, so they cannot silently diverge. Prior context on the
per-service (vs shared-lib) middleware decision: `notes/METRICS_AUTH_RATIONALE.md`.

---

## 5. The `BIND_HOST=0.0.0.0` escape hatch — only behind the proxy (I3)

`BIND_HOST` controls the host-side bind address for **every** published port; it ships commented at
loopback (`.env.example:11`, DEPLOY-08). Setting `BIND_HOST=0.0.0.0` exposes the control surface — and
with it the SEC-F22 forgeable gate — on all host interfaces, converting SEC-F22 from
"same-network-only" to "internet-reachable" with no credential in the path.

**Contract: `BIND_HOST=0.0.0.0` (or any non-loopback bind) is supported ONLY behind a fronting
authenticating reverse proxy that authenticates the dashboard user and is the single trusted source of
`X-Forwarded-For`.** That proxy is the convergence point of both findings (design §6, decision **D7**) and
**does not exist in this repo yet** (no traefik/nginx/caddy/haproxy in `docker-compose.yml`). Until it
exists, keep the default loopback bind. Setting `BIND_HOST=0.0.0.0` (or any non-loopback bind) now
**fails the bind-posture preflight** at bring-up: `scripts/preflight_bind_posture.sh` refuses to continue
unless the affected service also sets `JUNIPER_<SVC>_AUTH_PROXY_ATTESTED=true` (asserting the still-absent
fronting proxy). The app-layer bind-guard (§3, D2; sibling canopy/cascor PRs) makes the same requirement
fail-closed inside the services.

---

## 6. Per-IP caps are DoS-dampening, not authentication (I5)

The stack's per-IP WebSocket connection caps (canopy `max_connections_per_ip`, cascor
`ws_max_connections_per_ip`, the cascor handshake cooldown / worker limiter) and the HTTP rate limiters
all key on the raw socket peer, which under Docker NAT is the shared bridge gateway (SEC-F19, confirmed
live HO-3: six clients → `Per-IP limit reached for <gateway> (5/5)`). Consequences: one client's sockets
exhaust the shared cap for **everyone** (self-DoS), and the caps cannot identify a per-client actor.

**Read them as availability / fairness dampening — never as a per-client authenticator.** The design's
Phase-2 (**D4**) global + per-session caps restore per-user fairness without needing real client IP, and
the deferred XFF-from-trusted-proxy (**D6**) is the only mechanism that restores genuine per-client
identity — and only ever trusted from the configured proxy IP (never un-gated; XFF from any source is a
forge-your-identity footgun).

---

## 7. References

- **Design of record**: `juniper-ml/notes/JUNIPER_2026-07-03_JUNIPER-CANOPY_CONTROL-SURFACE-AUTH-AND-NAT-DESIGN.md`
  (§3 root cause, §4 SEC-F22 options, §5 SEC-F19 options, §6 proxy convergence, §7 sequencing, §8 D1–D8).
- **Audit**: `juniper-ml/notes/JUNIPER_2026-07-02_JUNIPER-ECOSYSTEM_STACK-SECURITY-AUDIT-PLAN.md` (§4.1, §4.7, §5.2; HO-3, HO-6).
- **canopy auth design (residual acknowledged)**:
  `juniper-canopy/notes/JUNIPER_CANOPY_TRAINING-CONTROL-AUTH_DESIGN_2026-06-30.md` §7.3, §12 OQ-3.
- **This repo**: `docker-compose.yml` (loopback publishes, `internal:true` networks, pinned `ipam` subnets,
  the `JUNIPER_<SVC>_LOOPBACK_PUBLISH_ATTESTED` two-flag attestation on canopy/cascor),
  `.env.observability` (pinned metrics allowlist), `.env.example:11` (`BIND_HOST` escape hatch),
  `scripts/preflight_bind_posture.sh` (the verifiable bind-posture preflight; `make preflight` + every
  bring-up target), `notes/METRICS_AUTH_RATIONALE.md` (per-service middleware decision),
  `tests/test_compose_security_config.py` (DEPLOY-08 loopback guard),
  `tests/test_compose_metrics_subnet_alignment.py` (D5 subnet↔allowlist drift check),
  `tests/test_compose_bind_posture_attestation.py` (the two-flag attestation + preflight gate).
- **Enforcing-code complement**: bind-guard **D2/D3** — the deploy-side two-flag attestation + verifiable
  preflight ship 2026-07-06 (this PR); the app-layer bind-guards (canopy + cascor, Phase 1) are the
  sibling PRs that read the same flags and must merge with it. Global + per-session caps **D4** (Phase 2);
  fronting proxy + XFF **D6/D7** (Phase 4) remain deferred.
</content>
</invoke>
