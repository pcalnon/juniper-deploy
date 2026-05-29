# Secret Mount Symmetry — Rationale + Change Log — 2026-05-28

**Author**: Paul Calnon
**Date**: 2026-05-28
**Companion PR**: juniper-deploy `fix/align-secret-mount-defaults-2026-05-28`
**Related**: juniper-cascor#311, juniper-deploy#87, #91/#92/#93

This note documents the docker-compose secret-default change introduced in the
companion PR — what regression class it closes, why the previous defaults were
problematic, and how the new design works.

---

## 1. Regression Class — Asymmetric `/run/secrets/X` Mounts

Docker-compose lets a single logical secret (e.g. `juniper_cascor_api_keys`) be
referenced by multiple services. The top-level `secrets:` block declares the
source-of-truth file path; each service that `mounts` that secret name binds
the same source onto its `/run/secrets/<name>`.

The source path is, however, **resolved per-`compose up` invocation**: if a
service is restarted independently with a different `--env-file` (or without
the env-file the rest of the stack started with), its `*_FILE` env var
substitution can resolve to a different path than its sibling services. Once
that happens, two containers mounting the *same logical secret name* end up
with **different content** in `/run/secrets/X`. The asymmetry persists until
the next stack-wide restart.

### Incident

On 2026-05-27 the juniper-deploy stack reached this state:

| Service | `/run/secrets/juniper_cascor_api_keys` source | Content |
|---|---|---|
| `juniper-canopy` | `./secrets.example/juniper_cascor_api_keys.txt` | 29 B `CHANGE_BEFORE_PRODUCTION_USE` |
| `juniper-cascor` | `./secrets/juniper_cascor_api_keys.txt` | 43 B real token |

Canopy was started without `--env-file .env.local`; cascor was restarted
~5 minutes later with `--env-file .env.local` (which only overrides
`JUNIPER_CASCOR_API_KEYS_FILE` and `JUNIPER_DATA_API_KEYS_FILE`, not the
singular `JUNIPER_CASCOR_API_KEY_FILE` or `CANOPY_API_KEY_FILE`). Result:

- Canopy sends `X-API-Key: CHANGE_BEFORE_PRODUCTION_USE` on every call to
  cascor.
- Cascor's `_parse_api_keys` (juniper-cascor#311) loads the real 43-byte
  token as its sole accepted key.
- Every canopy → cascor `/v1/*` HTTP call returns `401 Invalid API key`.

The cascade on the user-visible surface: the canopy dashboard's
training-status badge displays "error", the WebSocket supervisor (separate
bug, see notes/STACK_REGRESSION_ANALYSIS_2026-05-27.md) reconnect-loops, the
Dataset View Save / Generate / Launch buttons all fail.

---

## 2. What This PR Changes

The top-level `secrets:` block in `docker-compose.yml` previously defaulted
each of the five auth-path secrets to `./secrets.example/<name>.txt`:

```yaml
juniper_data_api_keys:
  file: "${JUNIPER_DATA_API_KEYS_FILE:-./secrets.example/juniper_data_api_keys.txt}"
juniper_cascor_api_key:
  file: "${JUNIPER_CASCOR_API_KEY_FILE:-./secrets.example/juniper_cascor_api_key.txt}"
juniper_cascor_api_keys:
  file: "${JUNIPER_CASCOR_API_KEYS_FILE:-./secrets.example/juniper_cascor_api_keys.txt}"
canopy_api_key:
  file: "${CANOPY_API_KEY_FILE:-./secrets.example/canopy_api_key.txt}"
cascor_auth_token:
  file: "${CASCOR_AUTH_TOKEN_FILE:-./secrets.example/cascor_auth_token.txt}"
```

This PR changes those five to `./secrets/<name>.txt`:

```yaml
juniper_data_api_keys:
  file: "${JUNIPER_DATA_API_KEYS_FILE:-./secrets/juniper_data_api_keys.txt}"
…and so on
```

`cascor_sentry_dsn`, `grafana_admin_password`, and `alertmanager_smtp_password`
retain their `./secrets.example/…` defaults because they are not part of the
canopy ↔ cascor auth path and have their own out-of-the-box-runnable
considerations.

---

## 3. Why This Is The Right Fix

### 3.1 Convergence with `prepare_secrets.bash`

`scripts/prepare_secrets.bash` (chained by `make up`, `make demo`,
`make dev`) populates `./secrets/<name>.txt` for every name in its
`MAPPINGS` array — either the real value from `.env.secrets.enc` (when SOPS
is available) or a 0-byte placeholder. Both states are handled gracefully
downstream:

- **0-byte placeholder**: cascor's `_parse_api_keys` validator
  (juniper-cascor#311) returns `None` → auth disabled. Canopy's
  `get_secret()` helper returns `""` → `SecurityMiddleware` deactivates.
  The stack comes up auth-off across the board, symmetrically.
- **Populated real token**: cascor loads `api_keys = ['<token>']`. Canopy
  reads the same token from its mount of the same secret name and sends
  it as `X-API-Key`. Match → 200.

With the previous default (`./secrets.example/…`), `prepare_secrets.bash`
was an out-of-band action — running it populated `./secrets/…` but compose
still bound `./secrets.example/…` unless the operator remembered to set
`*_FILE` env vars. The new default makes `prepare-secrets` the canonical
source of truth.

### 3.2 Eliminates the `--env-file .env.local` band-aid

The `.env.local` template (referenced in memory
`reference_juniper_deploy_local_secrets_env_2026-05-10`) was created to
work around the previous defaults' auth-on-by-placeholder behaviour. Its
incomplete override is precisely what caused the 2026-05-27 incident.
After this PR, the canonical local-stack invocation is the simpler:

```bash
bash scripts/prepare_secrets.bash    # or `make prepare-secrets`
docker compose --profile full up -d
```

with no env-file required.

### 3.3 Fresh-clone behaviour

A fresh `git clone` does not include `./secrets/<name>.txt` (gitignored).
Operators must either:

1. Run `make up` (or `make demo` / `make dev` / `make monitor`) — chains
   `prepare-secrets` which creates the `secrets/` directory and 0-byte
   placeholder files before `docker compose up`. Stack comes up auth-off.
2. Run `bash scripts/prepare_secrets.bash` then `docker compose up`.
3. Set `JUNIPER_*_FILE` env vars to point elsewhere (e.g., back at
   `./secrets.example/…` for the legacy behaviour).

`docker compose up` without one of these will fail at bind-mount time
because the source file does not exist. This is intentional — the failure
is loud and immediate rather than the previous silent asymmetric-mount
trap.

---

## 4. What Operators Should Do

After this PR merges:

- If you already have `./secrets/<name>.txt` populated (e.g., via SOPS):
  no change needed. Both canopy and cascor will now mount the same
  populated content by default.
- If you were relying on `--env-file .env.local` for the auth-off PoC
  state: remove the override and run `make prepare-secrets` first; the
  empty placeholders give the same auth-off behaviour symmetrically.
- If you run `docker compose up` directly (no `make`): you must now run
  `bash scripts/prepare_secrets.bash` first.

---

## 5. Test Additions

This PR adds `tests/test_compose_secret_mount_symmetry.py`, which asserts:

1. Every secret default in the top-level `secrets:` block points at a path
   under `./secrets/` for the five auth-relevant secrets listed above.
2. Every such default has a matching entry in `scripts/prepare_secrets.bash`
   `MAPPINGS` (so `prepare-secrets` is guaranteed to produce a file at
   that path).
3. The comment block documents the symmetry design.

A runtime integration test that asserts mount-byte-symmetry across canopy
+ cascor `/run/secrets/<name>` is deferred to a follow-up PR (it requires
a running stack and adds CI complexity); the static guards in (1)/(2)
catch the regression class at PR-merge time.

---

## 6. Related Follow-Ups

- juniper-canopy: fix the eight `/v1/v1/...` callsites in
  `cascor_service_adapter.py` (separate PR — see
  notes/STACK_REGRESSION_REMEDIATION_PLAN_2026-05-27.md E.1 in juniper-ml).
- juniper-cascor-client + juniper-canopy + juniper-cascor + juniper-deploy:
  WS Origin support for `/ws/control` (separate PR cluster — E.2).
- juniper-ml: bump `juniper-cascor-client>=0.5.0` in `[clients]` extra (E.3).
- juniper-deploy: deprecate / update `.env.local` template since the auth
  override is no longer needed for symmetry (low priority).
