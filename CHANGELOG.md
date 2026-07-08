# Changelog

All notable changes to `juniper-deploy` will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Added

- **Image-provenance preflight for the bring-up path** (`make up` / `demo` / `dev` / `monitor` / `obs-demo`) — the **inverse** of the build-freshness preflight below: that one stops `make build` from baking images out of stale checkouts; this one stops `docker compose up` from **running** images that no longer match the code on disk ("checkout updated but image not rebuilt"). Builds on the existing build-provenance stamps (`scripts/provenance_sha.sh` → `GIT_SHA` build arg → OCI `org.opencontainers.image.revision` label) and shares `scripts/doctor.sh`'s comparison conventions (prefix-compare for 7/8-char short SHAs, `-dirty` semantics) — doctor stays the interactive running-stack auditor; this is the enforcing bring-up gate:
  - **`scripts/preflight_image_provenance.sh`** (new): renders `docker compose config --format json` for the profiles about to come up, pairs every service's `image:` with its `build.context`'s **enclosing** git repo (nested contexts resolve; shared images — `juniper-cascor:latest` ×2, `juniper-canopy:latest` ×3 — are checked once), reads each **built** image's revision label (`docker image inspect`, not the running container — `up` recreates from the built tag), and classifies: `MATCH` (ok) / `STALE` or orphaned-`DIRTY` on a default-branch checkout (**fail, exit 1** — behind-count when the revision is in local history, `make build` fix hint) / in-flight `DIRTY`, non-default `BRANCH` mismatch, `NO-IMAGE` (compose builds it fresh), label-less or daemon-unreachable `UNVERIFIED` (warn only). Escape hatch: `JUNIPER_IMAGE_STALE_OK=1` env or `--allow-stale`; offline `--config-json` + `--image-provenance-map` modes drive the CI gate without a Docker daemon.
  - **`Makefile`**: runs after the bind-posture preflight and before `docker compose ... up` in all five bring-up targets, plus a standalone `make image-preflight`.
  - **`tests/test_image_provenance_preflight.py`** (new gate, 20 tests): hermetic (synthetic git repos + provenance map, no daemon): match passes (incl. 7/8-char prefix); default-branch stale and unknown-revision fail loudly; both escape hatches downgrade; feature-branch / unbuilt / label-less / match-but-dirty-checkout / in-flight-dirty warn; orphaned-dirty fails; shared-image dedupe; image-only and build-only services skipped; exit-2 usage contract; and a Makefile-wiring gate pinning bind-preflight → image-preflight → `up` order in every bring-up target.
- **Build-freshness preflight for `make build` / `make build-no-cache`** (incident of record 2026-07-07: `make build` silently built images from juniper-cascor / juniper-canopy checkouts 3 / 5 commits behind their already-merged sibling PRs cascor#393 / canopy#432, shipping the old single-flag SEC-F22 bind-guard against #148's new two-flag env — juniper-cascor crash-looped on start and blocked canopy + both workers). The compose stack builds first-party images from **local sibling checkouts** (`build.context: ../juniper-cascor` etc.), so image freshness is bounded by local-checkout freshness, not GitHub main; this preflight makes that boundary visible and enforced:
  - **`scripts/preflight_build_freshness.sh`** (new): renders `docker compose config --format json`, resolves every unique `build.context` to its **enclosing** git repository (contexts may be nested subdirectories, e.g. `../juniper-recurrence/juniper-recurrence`, and are checked once per repo), fetches the origin default branch (local-path remotes work offline; a fetch failure degrades to a warning), and classifies each: `FRESH` (ok) / `STALE` / `DIVERGED` (**fail, exit 1** — names the repo and the `git -C <repo> pull --ff-only` fix) / `AHEAD`, non-default `BRANCH`, `DIRTY` tree, `UNVERIFIED`, `MISSING` (warn only — deliberate dev flows never block). Escape hatch: `JUNIPER_BUILD_STALE_OK=1` env or `--allow-stale`; offline `--config-json` + `--no-fetch` modes drive the CI gate. Mirrors `preflight_bind_posture.sh` (bash orchestration + stdlib-python JSON parse, no jq; exit 0/1/2 contract).
  - **`Makefile`**: the preflight runs as the first recipe line of `build` and `build-no-cache` (a failure aborts before `docker compose build`), plus a standalone `make build-preflight`.
  - **`tests/test_build_freshness_preflight.py`** (new gate): drives the script's offline mode against synthetic git repos (hermetic — the "origins" are local paths, so the default-fetch path is exercised without network): fresh passes; behind fails loudly with the fix hint; the escape hatch downgrades; branch/ahead/dirty/non-git/missing only warn; diverged fails; nested contexts dedupe to one enclosing-repo check; plus a shipped-compose coverage-domain drift gate and a Makefile-wiring gate (unwiring the preflight fails CI).

### Security

- **SEC-F22 / D2 — explicit two-flag bind attestation + verifiable preflight** (design of record: `juniper-ml/notes/JUNIPER_2026-07-03_JUNIPER-CANOPY_CONTROL-SURFACE-AUTH-AND-NAT-DESIGN.md` §4 Option A / §8 D2; trust contract `notes/DEPLOYMENT_TRUST_CONTRACT_2026-07-04.md` §3/§5). The canopy + cascor containers bind `0.0.0.0` inside their netns (`..._HOST=0.0.0.0`), so the app-layer startup bind-guard (sibling canopy/cascor PRs) would hard-fail unless the bind posture is attested. This PR ships the **deploy side** of that contract:
  - **`docker-compose.yml`**: every canopy/cascor service (`juniper-cascor`, `juniper-cascor-demo`, `juniper-canopy`, `juniper-canopy-demo`, `juniper-canopy-dev`) now sets `JUNIPER_<SVC>_LOOPBACK_PUBLISH_ATTESTED: "true"` — attesting the reachable surface is the loopback-only host publish (`${BIND_HOST:-127.0.0.1}:` in `ports:`). `JUNIPER_<SVC>_AUTH_PROXY_ATTESTED` (the Phase-4 / D7 attestation-only proxy flag) is deliberately set **nowhere** (no fronting proxy exists). The stale single-flag `FRONTING_AUTH_ATTESTED` sketch is removed from the trust contract.
  - **`scripts/preflight_bind_posture.sh`** (new — **verifiable**): renders `docker compose config --format json` and asserts every published host port of each `..._LOOPBACK_PUBLISH_ATTESTED=true` service binds a loopback IP (`127.0.0.0/8` / `::1`). A service that attests loopback-publish but publishes a non-loopback host IP without also setting `..._AUTH_PROXY_ATTESTED=true` fails loudly (exit 1) — catching the silent `BIND_HOST=0.0.0.0` footgun BEFORE bring-up. Parse-only (`docker compose config` never touches the running stack); an offline `--config-json` mode drives the CI gate.
  - **`Makefile`**: the preflight runs before `docker compose up` in `up` / `demo` / `dev` / `monitor` / `obs-demo` (a failure aborts the target), plus a standalone `make preflight` that checks every profile.
  - **`tests/test_compose_bind_posture_attestation.py`** (new gate, mirrors `test_compose_metrics_subnet_alignment.py`): the shipped compose is loopback-published for every attested service; canopy + cascor both carry the flag; `AUTH_PROXY_ATTESTED` is set nowhere; no stale `FRONTING_AUTH_ATTESTED`; and the preflight PASSES the shipped config while BITING (exit 1) on an injected non-loopback publish.
  - **Merge coupling**: this deploy PR **must merge together with** the sibling canopy + cascor bind-guard PRs (the compose attests the posture the apps enforce). **Deploy-gated** (owner-approved env/deploy change — not rolled out by merge).
- **SEC-F19 / D5 — deterministic metrics subnets** (design of record: `juniper-ml/notes/JUNIPER_2026-07-03_JUNIPER-CANOPY_CONTROL-SURFACE-AUTH-AND-NAT-DESIGN.md` §5 Option C1, §8 D5; audit `juniper-ml/notes/JUNIPER_2026-07-02_JUNIPER-ECOSYSTEM_STACK-SECURITY-AUDIT-PLAN.md` §5.2 HO-3). Pinned each of the four compose networks to a static `ipam.config.subnet` — `backend 172.28.0.0/16` + `data 172.29.0.0/16` (both `internal: true`), `frontend 172.30.0.0/16`, `monitoring 172.31.0.0/16` — and re-pinned `.env.observability`'s `*_METRICS_TRUSTED_IPS` to **exactly** the subnets each scrape target shares with Prometheus (`juniper-data` → 172.28/172.29; `juniper-cascor` / `juniper-canopy` → 172.28/172.29/172.30; each plus loopback). This removes the dynamic-IPAM drift that let the live bridge move to `172.23.0.0/16` — outside the old `172.18–21` allowlist — yielding either a 403 scrape failure (availability) or a whole-subnet-trust widening (authorization). Subnets are the **top four /16s of Docker's default address pool**, chosen to avoid Docker's bottom-up auto-assignment; collision-checked 2026-07-04 against the host daemon (`docker network inspect` — only `172.17.0.0/16` allocated). The allowlist is reframed (compose + `.env.observability` comments) as **network-scope authorization** (which subnets may scrape), backed by `internal: true` isolation + the fail-closed `MetricsAuthMiddleware` — **not** per-host authentication; the middleware is unchanged. New drift gate `tests/test_compose_metrics_subnet_alignment.py` asserts the pinned `ipam` subnets and the allowlist CIDRs agree so they cannot silently diverge; `tests/test_compose_metrics_trusted_ips_wired.py` updated to the pinned CIDRs. **Deploy-gated** (owner-approved env/deploy change — not rolled out by merge).
- **SEC-F22 / SEC-F19 / D8 — deployment trust contract (Phase 0).** New `notes/DEPLOYMENT_TRUST_CONTRACT_2026-07-04.md` records the stack's trust model: network position **is** the trust boundary; the control surface is loopback-bound by default (DEPLOY-08, `tests/test_compose_security_config.py`); `BIND_HOST=0.0.0.0` (`.env.example:11`) is supported **only** behind a fronting authenticating proxy (deferred, D7 — not present in this repo yet); the per-IP WS caps are DoS-dampening, not authentication; the metrics allowlist is network-scope authorization. The enforcing app-layer **bind-guard** (D2, canopy + cascor) is the deferred complement — **no merged PR as of 2026-07-04** (verified: cascor has it in-flight/uncommitted, canopy none).

### Changed

- **CFG-06** (follow-up #2 of 3 from the cascor-worker design doc §7 rollout plan): worker container-side env-var names migrated from legacy `CASCOR_*` / `CASCOR_WORKER_*` to canonical `JUNIPER_CASCOR_WORKER_*` across both deploy surfaces. Worker image >= 0.4.0 emits `DeprecationWarning` for any remaining legacy name; this change stops the warnings firing in default deploys.
  - **`docker-compose.yml`** (worker service block at lines 224-233): `CASCOR_SERVER_URL` → `JUNIPER_CASCOR_WORKER_SERVER_URL`; `CASCOR_HEARTBEAT_INTERVAL` → `JUNIPER_CASCOR_WORKER_HEARTBEAT_INTERVAL`. The host-side `${CASCOR_WORKER_*_URL}` / `${CASCOR_WORKER_*_HEARTBEAT_INTERVAL}` interpolations are intentionally left as-is (operator-facing rename is a separate concern). `CASCOR_AUTH_TOKEN_FILE` is **intentionally not renamed** in this PR — the secret-file handling path (`_FILE` suffix) needs separate verification before the canonical rename.
  - **`k8s/helm/juniper/values.yaml`** (`worker.env` map): `CASCOR_HEARTBEAT_INTERVAL` → `JUNIPER_CASCOR_WORKER_HEARTBEAT_INTERVAL`.
  - **`k8s/helm/juniper/templates/worker-deployment.yaml`** (worker container `env:`): `CASCOR_SERVER_URL` → `JUNIPER_CASCOR_WORKER_SERVER_URL`; `CASCOR_AUTH_TOKEN` → `JUNIPER_CASCOR_WORKER_AUTH_TOKEN` (plain env var via `secretKeyRef`, no `_FILE` complication); `CASCOR_WORKER_HEALTH_BIND` → `JUNIPER_CASCOR_WORKER_HEALTH_BIND`; `CASCOR_WORKER_HEALTH_PORT` → `JUNIPER_CASCOR_WORKER_HEALTH_PORT`.
  - **`tests/test_helm_chart_probes.py`**: positive + negative health-env-var assertions updated to the canonical names (lines 185-186, 195-196).
  - **`tests/test_compose_security_config.py`**: `forbidden_env_vars` invariant extended with `JUNIPER_CASCOR_WORKER_AUTH_TOKEN` so the new canonical name is also blocked from being set as a plain env var (DEPLOY-09 + DEPLOY-11 invariant — secret may only be `_FILE`-mounted).
  - Full deploy test suite: 60 passed, 27 skipped (docker-stack tests, unaffected), 0 failed. `docker compose --profile full config` renders cleanly.
  - **Out of scope**: operator-facing documentation (`AGENTS.md`, `README.md`, `docs/REFERENCE.md`) updates live in follow-up #3 (next PR) per the design doc §7 split.
- **CFG-06 docs sweep** (follow-up #3 — juniper-deploy half; cascor-worker half shipped via [cascor-worker #87](https://github.com/pcalnon/juniper-cascor-worker/pull/87)). `docs/REFERENCE.md` "Kubernetes Secret Keys" table updated: the `cascor_auth_token` row now references the canonical `JUNIPER_CASCOR_WORKER_AUTH_TOKEN` env var (was `CASCOR_AUTH_TOKEN`) matching the rename shipped in [#80](https://github.com/pcalnon/juniper-deploy/pull/80)'s `worker-deployment.yaml` edit. `AGENTS.md` + `README.md` "Docker Secret env-var mappings" tables describe compose-only `*_FILE` mounts and remain accurate (compose's `CASCOR_AUTH_TOKEN_FILE` was intentionally left unchanged in #80).

### Added

- **OQ-2: build-provenance `-dirty` detection — `make doctor` / `make health` now flag images built from uncommitted code.** New `scripts/provenance_sha.sh` prints a repo's short HEAD SHA suffixed with `-dirty` when its working tree has uncommitted *tracked* changes (untracked artifacts like `*.egg-info`, `__pycache__`, `.env` are ignored via `--untracked-files=no`, so they don't spuriously mark every developer build dirty). The Makefile's `PROVENANCE_ENV` stamps SHAs through it, so an image built from a dirty tree carries an `abc1234-dirty` revision label. `scripts/doctor.sh` recognizes the marker and reports **DIRTY** (exiting non-zero) — checked *before* the FRESH prefix-compare, which would otherwise pass `abc1234-dirty` as a match for `abc1234`; `scripts/health_check.sh`'s DRIFT column shows **DIRTY** likewise. Closes OQ-2 of the build-provenance design (ratified 2026-06-14 but previously unshipped). Tests: `tests/test_provenance_sha.py` (clean / dirty-tracked / untracked-only / non-repo) + extended `tests/test_makefile_doctor.py`.

- **Build-provenance drift checker — `make doctor`** (juniper-ml design [#412](https://github.com/pcalnon/juniper-ml/pull/412), Part 7). New `scripts/doctor.sh` reads each Juniper image's `org.opencontainers.image.revision` OCI label via `docker inspect` (the running container's image when up, else the built `:latest`) and compares it to the sibling source repo's `git rev-parse --short HEAD`, reporting **FRESH / STALE / UNKNOWN** per service and exiting non-zero when any image is STALE. `docker inspect` is used rather than `/v1/health` so the check works for services whose port is not host-published (e.g. juniper-data). `scripts/health_check.sh` gains companion **GIT_SHA + DRIFT** columns (sourced from the new `/v1/health` `git_sha` field). Follow-up to the build-args wiring in [#118](https://github.com/pcalnon/juniper-deploy/pull/118); fully populated once the service provenance PRs land and images are rebuilt. Regression test: `tests/test_makefile_doctor.py` (9 tests).

- **METRICS-MON R1.3 / seed-04 (Helm chart 1.0.0 → 1.1.0)**: opt-in HTTP probe wiring for the `juniper-cascor-worker` Deployment, gated by the new `worker.healthcheck.enabled` flag (default **`false`**). When flag is `false`, `worker-deployment.yaml` continues to render the legacy `exec: kill -0 1` probes — operators on older worker images are unaffected. When the flag is `true`, the chart:
  - exposes a named container port `health` on `worker.healthcheck.port` (default `8210`);
  - injects `CASCOR_WORKER_HEALTH_BIND=0.0.0.0` and `CASCOR_WORKER_HEALTH_PORT=<port>` into the worker pod env (the worker image at >= 0.4.0 binds localhost-only by default);
  - replaces the `exec` probes with `httpGet` probes against `/v1/health/live` and `/v1/health/ready` per the R1.2 contract.
  This flag remains `false` in chart 1.1.0; chart 1.2.0 will flip the default to `true` after staging burn-in (two-step rollout per the design doc, §8). New regression tests in `tests/test_helm_chart_probes.py` assert both flag states render correctly. See [`notes/code-review/METRICS_MONITORING_R1.3_WORKER_HEARTBEAT_DESIGN_2026-04-27.md`](https://github.com/pcalnon/juniper-ml/blob/main/notes/code-review/METRICS_MONITORING_R1.3_WORKER_HEARTBEAT_DESIGN_2026-04-27.md) in juniper-ml. Companion app PRs (merged 2026-04-27/28): pcalnon/juniper-cascor#150, pcalnon/juniper-cascor-worker#37.
- Track 5C — DEPLOY-07: Compose-level resource limits via three new YAML anchors (`x-resources-heavy`, `x-resources-light`, `x-resources-tiny`) in `docker-compose.yml`. Heavy tier (juniper-cascor, juniper-cascor-demo, juniper-cascor-worker) gets `${RESOURCES_HEAVY_CPUS:-4.0}` / `${RESOURCES_HEAVY_MEMORY:-8G}` limits; light tier (juniper-data, juniper-canopy variants, prometheus, grafana) gets `${RESOURCES_LIGHT_CPUS:-1.0}` / `${RESOURCES_LIGHT_MEMORY:-2G}`; tiny tier (alertmanager, redis) gets `${RESOURCES_TINY_CPUS:-0.5}` / `${RESOURCES_TINY_MEMORY:-256M}`. Override any value via the corresponding env var. One-shot containers (`demo-seed`, `test-runner`) intentionally skipped.
- Track 5C — DEPLOY-12: Host-side service ports added to `scripts/config.sh` as `JUNIPER_DATA_PORT`, `JUNIPER_CASCOR_PORT`, `JUNIPER_CANOPY_PORT` with `${VAR:-default}` substitution. `scripts/wait_for_services.sh` now uses these instead of the inline `8100` / `8050` literals it had before.
- Track 5C — DEPLOY-09 + DEPLOY-11: Regression test `test_secrets_only_no_plain_api_key_env_vars` in `tests/test_compose_security_config.py` ensures no compose service ever re-introduces a plain `*_API_KEY*` or `CASCOR_AUTH_TOKEN` env var.

### Changed

- Track 5C — DEPLOY-09: Removed the plain `CASCOR_AUTH_TOKEN: "${CASCOR_WORKER_AUTH_TOKEN:-}"` env var from the `juniper-cascor-worker` service in `docker-compose.yml`. The token is now read exclusively from the Docker secret file at `/run/secrets/cascor_auth_token` (mount + `CASCOR_AUTH_TOKEN_FILE` env var pointing at it remain). Closes the leak path through `docker inspect`, container env dumps, and accidentally-committed `.env` files.
- Track 5C — DEPLOY-11: Same hardening applied to API-key wiring across `juniper-data`, `juniper-cascor`, and `juniper-canopy` — the plain `JUNIPER_DATA_API_KEYS`, `JUNIPER_CASCOR_API_KEYS`, `JUNIPER_DATA_API_KEY`, and `JUNIPER_CASCOR_API_KEY` env vars were removed. Each service now reads from its `*_FILE` variant only. The `secrets.example/*` placeholder files keep the auth-on default working out of the box.
- Track 5C — DEPLOY-15: Pinned Helm chart image tags off `latest` in `k8s/helm/juniper/values.yaml`: `data.image.tag` `latest` → `0.6.0`; `cascor.image.tag` `latest` → `0.4.0`; `canopy.image.tag` `latest` → `0.4.0`; `worker.image.tag` `latest` → `0.3.0`. Bump these in lockstep with each app's release. Reproducible deployments are now the default.
- Track 5C — DEPLOY-06 + DEPLOY-16: Set a non-empty placeholder default for `kube-prometheus-stack.grafana.adminPassword` (`change-me-juniper-grafana`) and added the `admin.existingSecret` / `admin.userKey` / `admin.passwordKey` indirection so production deployments can point at a Kubernetes Secret. Empty default previously installed Grafana with a predictable credential.
- Track 5C — DEPLOY-10: Demo profile services (`juniper-cascor-demo`, `juniper-canopy-demo`, `juniper-canopy-dev`) now ship with `*_RATE_LIMIT_ENABLED=true` / `*_RATE_LIMIT_REQUESTS_PER_MINUTE=60` defaults, matching the full profile. Auth remains intentionally disabled in demo mode (open-by-design), but rate limiting prevents a single client from knocking the demo over.

### Changed (BREAKING — Helm chart major version bump 0.2.1 → 1.0.0)

- **METRICS-MON R1.2 / seed-02 / seed-03**: corrected `livenessProbe.httpGet.path` and `readinessProbe.httpGet.path` defaults in `k8s/helm/juniper/values.yaml` to point at the per-service R1.2 probe endpoints. Before this change three of the six probe paths pointed at `/v1/health` (the legacy combined no-op endpoint) instead of the new `/v1/health/live` (in-process liveness tick) and `/v1/health/ready` (503-on-not_ready) endpoints introduced in juniper-data v0.4.x, juniper-cascor v0.4.x, and juniper-canopy v0.4.x.
  - **juniper-data**: liveness `/v1/health` → `/v1/health/live`; readiness `/v1/health` → `/v1/health/ready`
  - **juniper-cascor**: liveness `/v1/health` → `/v1/health/live`; readiness already `/v1/health/ready`
  - **juniper-canopy**: liveness `/v1/health` → `/v1/health/live`; readiness `/v1/health` → `/v1/health/ready`
  - Helm chart `version` and `appVersion` bumped from `0.2.1` to `1.0.0` to signal the breaking probe-path default change. Operators with overridden `values-*.yaml` files are unaffected; operators relying on chart defaults must re-render.
  - New regression test `tests/test_helm_chart_probes.py` runs `helm template` and asserts each Juniper Deployment uses the R1.2 probe paths (skipped when `helm` binary is unavailable).
  - See [`notes/code-review/METRICS_MONITORING_R1.2_PROBE_DESIGN_2026-04-27.md`](https://github.com/pcalnon/juniper-ml/blob/main/notes/code-review/METRICS_MONITORING_R1.2_PROBE_DESIGN_2026-04-27.md) in juniper-ml for the cross-repo contract; companion app PRs merged 2026-04-27: pcalnon/juniper-data#51, pcalnon/juniper-cascor#147, pcalnon/juniper-canopy#183. `docker-compose.yml` healthchecks (which target `/v1/health` directly) are unchanged — Compose has no live/ready distinction.

### Added

- Track 5B/5C — CI-03: New `tests` job in `.github/workflows/ci.yml` that installs `requirements-test.txt` and runs `pytest tests/`. Wires the existing 1,427 lines of test code into CI for the first time; live-service tests skip cleanly via the `require_*` fixtures. Added to the `required-checks` quality gate alongside `pre-commit`, `sops-validation`, and `validate-compose`.
- Track 5B/5C — DEPLOY-08: Introduced a `BIND_HOST` environment variable (default `127.0.0.1`) that governs the host-side bind address of every published port in `docker-compose.yml` (`juniper-data`, `juniper-cascor`, `juniper-cascor-demo`, `juniper-canopy`, `juniper-canopy-demo`, `juniper-canopy-dev`). Cascor and canopy ports are now loopback-only out of the box; set `BIND_HOST=0.0.0.0` to publish externally.
- Regression tests `test_published_ports_default_to_loopback_bind` (DEPLOY-08) and `test_canopy_dev_can_reach_juniper_data` (DEPLOY-13) in `tests/test_compose_security_config.py`.
- Track 5A — DEPLOY-02: AlertManager service added to `docker-compose.yml` (image `prom/alertmanager:v0.27.0`, profile `observability`, host port `${ALERTMANAGER_PORT:-9093}`, healthcheck on `/-/healthy`). Closes the gap where `prometheus.yml` references `alertmanager:9093` but no container existed to serve it. Added `ALERTMANAGER_PORT` documentation to `.env.example`.
- Hardcoded-values refactor (Wave 1 + Wave 4): introduced YAML merge-key healthcheck anchors in `docker-compose.yml` (`x-healthcheck-defaults`, `x-healthcheck-cascor`, `x-healthcheck-canopy`, `x-healthcheck-worker`, `x-healthcheck-redis`) and rewired all 8 container healthchecks to consume them via `<<: *anchor`. New env vars `WORKER_REPLICAS` and `HEALTHCHECK_*` (interval/timeout/retries/start_period, plus per-service overrides) interpolate into the anchors for runtime tuning without editing the compose file.
- New `scripts/config.sh` (Wave 1) and expanded `tests/constants.py` (Wave 3) — sourced by shell scripts and used by integration tests to eliminate inline literals (service URLs, port numbers, retry tuning, healthcheck endpoints).
- Documentation headers added to `prometheus/prometheus.yml` and `grafana/provisioning/datasources/prometheus.yml` mapping the remaining inline literals to their corresponding env vars and explaining why each value cannot be interpolated by the upstream image.

### Changed

- Track 5A — DEPLOY-01: Renamed compose secret `juniper_data_api_key` (singular) to `juniper_data_api_keys` (plural) to match the application config (`JUNIPER_DATA_API_KEYS_FILE` already pointed at `/run/secrets/juniper_data_api_keys`). Updated the secret definition's default path to `secrets.example/juniper_data_api_keys.txt`, renamed the override env var to `JUNIPER_DATA_API_KEYS_FILE`, updated the `tests/test_compose_security_config.py` assertions, and updated the CI stub filename in `.github/workflows/ci.yml`.
- Track 5A — DEPLOY-03: Prometheus volume mount changed from a single-file bind (`./prometheus/prometheus.yml:/etc/prometheus/prometheus.yml:ro`) to a directory bind (`./prometheus:/etc/prometheus:ro`) so the `recording_rules.yml` and `alert_rules.yml` files referenced by `prometheus.yml`'s `rule_files:` block are reachable inside the container.
- Hardcoded-values refactor (Wave 3 + Wave 4): replaced inline service URLs, port numbers, retry counts, and healthcheck endpoints across `up.sh`, `down.sh`, `status.sh`, and `restart.sh` with values sourced from `scripts/config.sh`. `replicas: 2` for the worker service is now `replicas: ${WORKER_REPLICAS:-2}`.
- `tests/constants.py` expanded to centralize the per-service expected ports, healthcheck paths, and Docker network names referenced by integration tests.
- AGENTS.md "Environment Variables" section gained a new "Healthcheck Tuning" subsection documenting the merge-key anchors and the override variables.
- Aligned Helm chart version with app version: `k8s/helm/juniper/Chart.yaml` `version` bumped `0.1.0` -> `0.2.0` to match `appVersion`. Establishes the going-forward convention that chart `version` and `appVersion` track together.
- Track 5B/5C — DEPLOY-13: `juniper-canopy-dev` now attaches to the `backend`, `data`, and `frontend` networks (was `frontend` only) so the dev profile can reach `juniper-data` (which is on `backend`/`data`). Closes the broken-by-design isolation in the dev profile.
- Track 5B/5C — DEPLOY-05: Helm chart `k8s/helm/juniper/values.yaml` now sets `redis.auth.enabled: true` with a placeholder default password (`change-me-juniper-redis`); production deployments should override via `redis.auth.existingSecret`. The `juniper.redis.url` helper template injects the password into the rendered `REDIS_URL` when auth is enabled, so canopy connects with credentials end-to-end.

### Fixed

- `CHANGELOG.md` 0.2.0 section: corrected Redis image version reference from "Redis 7-alpine" to "Redis 7.4-alpine" to match the pinned `redis:7.4-alpine` in `docker-compose.yml`.

### Notes

- Wave 5 verified: `docker compose config` succeeds, `promtool check config` succeeds against `prometheus/prometheus.yml`, and override smoke tests pass for `WORKER_REPLICAS=5` and `HEALTHCHECK_INTERVAL=42s`.
- All 29 integration tests pass (42 skipped — they require running services); pre-commit (9 hooks: shellcheck, yamllint, helm-lint, sops-check) is clean.
- No service behavior changes — every healthcheck merges to the same final command/interval/timeout/retries/start_period as before the refactor.

## [0.2.0] - 2026-04-08

### Added

- Demo, dev, and full Docker Compose profiles for different operational modes
- Observability stack: Prometheus v3.10.0, AlertManager v0.28.1, Grafana 12.4.0 with `observability` profile
- Auto-provisioned Grafana dashboards for all Juniper services (overview, data, cascor, canopy)
- Grafana dashboard provider configuration and home dashboard (`juniper-overview.json`)
- Grafana datasource with stable UID (`prometheus`), `httpMethod: POST`, and `timeInterval: 10s`
- Prometheus alerting rules, recording rules, and AlertManager routing configuration
- Enhanced Prometheus scrape configuration with per-job intervals, service/environment labels, and self-monitoring
- Redis service for juniper-canopy session/cache store (full and test profiles)
- `juniper-cascor-worker` service for distributed training (Phase 3, full and test profiles)
- Kubernetes Helm chart for Juniper stack deployment (Phase 4)
- Docker secrets support for API keys and Grafana admin password (`secrets/` directory)
- SOPS encryption configuration for environment secret files
- `Makefile` developer interface with 23 targets wrapping Docker Compose commands
- `make monitor` target for full stack with observability (Prometheus + Grafana)
- `make prepare-secrets` target to create placeholder secret files
- `health_check.sh` script for formatted health report output
- `wait_for_services.sh` script for polling health endpoints until ready
- `test_demo_profile.sh` integration test script (7-step demo validation)
- `test_health_enhanced.sh` enhanced health check validation (8-step schema checks)
- `Dockerfile.test` for containerized integration test execution via `test` profile
- Integration test suite: `test_health.py`, `test_data_service.py`, `test_full_stack.py`, `test_availability.py`
- `test_compose_security_config.py` Docker security regression tests
- CI/CD pipeline (`.github/workflows/ci.yml`) with pre-commit, compose validation, and Docker integration jobs
- Dependabot configuration for pip and GitHub Actions dependency updates
- CODEOWNERS file for code review routing
- Comprehensive documentation suite: `QUICK_START.md`, `ENVIRONMENT_SETUP.md`, `USER_MANUAL.md`, `DEVELOPER_CHEATSHEET.md`, `OBSERVABILITY_GUIDE.md`, `REFERENCE.md`, `TESTING_QUICK_START.md`
- `AGENTS.md` with thread handoff and worktree procedures
- This CHANGELOG

### Changed

- Remapped juniper-cascor host port from 8200 to 8201 (`CASCOR_HOST_PORT` env var) to avoid conflicts
- Updated canopy environment variables to `JUNIPER_CANOPY_*` prefix
- Updated cascor environment variable prefixes: `CASCOR_HOST` -> `JUNIPER_CASCOR_HOST`, `CASCOR_PORT` -> `JUNIPER_CASCOR_PORT`, `CASCOR_LOG_LEVEL` -> `JUNIPER_CASCOR_LOG_LEVEL`
- Updated JuniperCanopy references to juniper-canopy (naming convention alignment)
- Updated health scripts for enhanced ReadinessResponse format
- Pinned all third-party Docker images to specific versions (Prometheus v3.10.0, Grafana 12.4.0, Redis 7.4-alpine)
- SHA-pinned all GitHub Actions (checkout@v6.0.2, setup-python@v6.2.0, cache@v5.0.4)

### Fixed

- Enforced network isolation on backend and data Docker networks (marked as `internal: true`)
- Defined `SECRETS_DIR` and `SECRETS_FILES` Makefile variables used by `prepare-secrets` target
- Removed non-existent `COPY conftest.py .` from `Dockerfile.test` (conftest.py is inside `tests/`)
- Corrected AGENTS.md profile table: removed Cassandra (not in compose), fixed Redis profile assignment
- Corrected AGENTS.md port binding documentation: Redis has no host port binding
- Corrected AGENTS.md Makefile target references: `make obs`/`make obs-demo` -> `make monitor`
- Removed predictable Grafana admin password fallback (now requires Docker secret)
- Prevented compose startup failures when secrets directory is missing
- Closed secret-leak bypass and shell injection vulnerabilities
- Strengthened SOPS validation for encrypted environment files
- Added missing redis service and secret definitions
- Resolved pre-commit failures (check-yaml, shellcheck, yamllint)
- Fixed per-service skip-gating in integration tests
- Aligned compose security tests with actual docker-compose configuration

### Security

- Docker network isolation: `frontend` (bridge), `backend` (internal), `data` (internal), `monitoring` (bridge)
- Restricted port bindings to `127.0.0.1` for internal services (juniper-data, Prometheus, AlertManager, Grafana)
- Container hardening: `no-new-privileges:true` and `cap_drop: ALL` for all Juniper application containers
- Redis accessible only within Docker network (no host port binding)
- Grafana admin password via Docker secret only (no environment variable fallback)
- Rate limiting enabled by default for juniper-cascor and juniper-canopy
- CORS origins defaults set to empty (restrictive) for all services
- API key headers added to Prometheus scrape configuration
- SOPS pre-commit hook blocks unencrypted `.env` files from commit
