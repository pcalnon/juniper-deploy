# Alertmanager Notification Runbook — Juniper Deploy

**Project**: Juniper Deploy
**Sub-Track**: OBS-ROUTE-01
**Closes audit findings**: 3.2 (P1, juniper-ml#195) and B.1 (P3)
**State-analysis source**: [`A9_AND_3_2_STATE_ANALYSIS_2026-05-03.md`](https://github.com/pcalnon/juniper-ml/blob/main/notes/observability/JUNIPER_2026-05-03_JUNIPER-ECOSYSTEM_A9-AND-3-2-STATE-ANALYSIS.md) §4 Option B
**Author**: Paul Calnon
**Last Updated**: 2026-05-04
**Status**: ACTIVE — placeholder credentials shipped; rotate before production paging matters

---

## 1. What this runbook covers

This runbook documents how the Juniper alertmanager stack delivers notifications, how to rotate the SMTP credentials it depends on, and how to triage a "no email arrived" report. Pre-OBS-ROUTE-01 the three alertmanager receivers (`default`, `critical`, `tickets`) were name-only stubs and silently dropped every alert routed to them. This runbook describes the post-fix wiring.

---

## 2. Routing tree summary

The current `alertmanager/alertmanager.yml` matches alert labels to receivers as follows:

| `severity` label | Receiver | `repeat_interval` | Notes |
|------------------|----------|-------------------|-------|
| `critical`       | `critical` | 1h              | Pager-tier — `severity: critical` is the legacy R-series fast-fail tier. |
| `page`           | `critical` | 1h              | METRICS-MON R5.4 burn-rate fast-burn (Google SRE Workbook MWMBR). |
| `ticket`         | `tickets`  | 12h             | METRICS-MON R5.4 burn-rate slow-burn. Non-paging by design. |
| `warning`        | `tickets`  | 24h             | **B.1 fold-in**. Pre-R5.4 R-series alerts (HighErrorRate, HighLatency, TrainingStalled, …). Pre-fix these fell through to `default` and were silently dropped. |
| `info`           | `tickets`  | 24h             | **B.1 fold-in**. Same root cause as warning. |
| anything else    | `default`  | 4h              | Safety-net. Now wired to email instead of dropping. |

`amtool config routes test` smoke output (re-run after any routing change):

```
severity=critical -> critical
severity=page     -> critical
severity=ticket   -> tickets
severity=warning  -> tickets
severity=info     -> tickets
severity=other    -> default
```

The B.1 fold-in deliberately co-locates `warning` / `info` in the same `tickets` mailbox as the R5.4 slow-burn `severity: ticket` stream. The email Subject carries the severity, so a downstream filter (Gmail label, Jira mailhook, sieve rule) can split them. If operations later wants a separate low-priority distribution list, see §3.

---

## 3. Splitting warning/info into a separate receiver (optional)

The OBS-ROUTE-01 PR routes `warning` and `info` to the existing `tickets` receiver to minimize new config knobs. If the volume on those two severities turns out to drown out the slow-burn `severity: ticket` stream, add a dedicated `low-priority` receiver:

1. In `alertmanager/alertmanager.yml`, append a new receiver block:

   ```yaml
   - name: "low-priority"
     email_configs:
       - to: "alerts-low-priority@example.com"
         send_resolved: true
         headers:
           Subject: "[Juniper {{ .CommonLabels.severity }}] {{ .CommonLabels.alertname }}"
   ```

2. Re-point the two existing `severity: warning` / `severity: info` routes from `receiver: "tickets"` to `receiver: "low-priority"`.

3. Re-validate (`amtool check-config`) and ship.

No SOPS / docker-compose changes are needed for that split — the SMTP global config is shared.

---

## 4. SMTP credential rotation

The alertmanager SMTP password lives in two places:

1. **Canonical encrypted source-of-record**: `.env.secrets.enc` (SOPS / age, key fingerprint `age1qmmfhude4xlpdx3wvqv994ahqayke04sgkt5r3ruclu9wmyt04xsdl2kkv`). Variable name: `ALERTMANAGER_SMTP_PASSWORD`.
2. **Runtime path (Docker secret)**: a plaintext file at `${ALERTMANAGER_SMTP_PASSWORD_FILE}` (default `./secrets.example/alertmanager_smtp_password.txt`, placeholder shipped in repo). Mounted into the alertmanager container at `/run/secrets/alertmanager_smtp_password` and referenced by `smtp_auth_password_file:` in `alertmanager.yml`.

Both must be in sync. Alertmanager does NOT natively substitute environment variables in YAML — only `_file:` indirection is honored — so the password cannot be passed via `env_file:` alone.

### 4.1 Rotation procedure

```bash
cd /path/to/juniper-deploy

# 1. Decrypt to a working copy
sops -d --input-type dotenv --output-type dotenv .env.secrets.enc > .env.secrets

# 2. Edit the password value (and any other rotated fields)
${EDITOR:-vim} .env.secrets   # update ALERTMANAGER_SMTP_PASSWORD

# 3. Re-encrypt and remove the plaintext copy
bash util/sops-encrypt.sh .env.secrets .env.secrets.enc
rm .env.secrets

# 4. Mirror the new password into the runtime Docker-secret file.
#    Production: point ALERTMANAGER_SMTP_PASSWORD_FILE at a path under
#    ./secrets/ (gitignored) instead of ./secrets.example/.
mkdir -p secrets
sops -d --input-type dotenv --output-type dotenv .env.secrets.enc \
  | grep ^ALERTMANAGER_SMTP_PASSWORD= \
  | cut -d= -f2- \
  > secrets/alertmanager_smtp_password.txt
chmod 600 secrets/alertmanager_smtp_password.txt
export ALERTMANAGER_SMTP_PASSWORD_FILE=./secrets/alertmanager_smtp_password.txt

# 5. Restart alertmanager so it picks up the new file
docker compose --profile observability up -d --force-recreate alertmanager
```

### 4.2 Variables shipped in `.env.secrets.enc`

| Variable | Purpose | Consumed by |
|----------|---------|-------------|
| `ALERTMANAGER_SMTP_USER` | Gmail (or other SMTP) user, also used as `smtp_auth_username` | Documentation; mirror into `alertmanager.yml` `global.smtp_auth_username` |
| `ALERTMANAGER_SMTP_PASSWORD` | SMTP app password | Mirror into `${ALERTMANAGER_SMTP_PASSWORD_FILE}` |
| `SMTP_FROM_DOMAIN` | Domain for `smtp_from` | Mirror into `alertmanager.yml` `global.smtp_from` |
| `TICKET_ALERT_RECIPIENT_EMAIL` | Recipient for `tickets` receiver | Mirror into `alertmanager.yml` `tickets.email_configs[0].to` |
| `CRITICAL_ALERT_RECIPIENT_EMAIL` | Recipient for `critical` receiver | Mirror into `alertmanager.yml` `critical.email_configs[0].to` |
| `DEFAULT_ALERT_RECIPIENT_EMAIL` | Recipient for `default` (safety-net) receiver | Mirror into `alertmanager.yml` `default.email_configs[0].to` |

Non-secret fields (`smarthost`, `from`, `to`, `auth_username`) are baked into `alertmanager.yml` as plain literals because alertmanager has no env-var interpolation. They are flagged `CHANGE_BEFORE_PRODUCTION_USE` in inline comments. Edit them directly; commit the change.

---

## 5. Triage — "no email arrived"

When an alert was expected to fire but no email landed in the inbox:

### 5.1 Check that the alert actually fired

```bash
# Is the alert in firing state in Prometheus?
curl -s http://localhost:9090/api/v1/alerts | jq '.data.alerts[] | select(.state=="firing")'

# Or hit the Prometheus UI
xdg-open http://localhost:9090/alerts
```

If the alert is not in `firing` state, the issue is upstream of alertmanager — check `prometheus/alert_rules.yml`, scrape configs, or the underlying metric.

### 5.2 Check that alertmanager received it

```bash
# Alerts currently held by alertmanager (firing or pending)
curl -s http://localhost:9093/api/v2/alerts | jq '.[] | {labels: .labels, status: .status}'

# Same view in the UI
xdg-open http://localhost:9093/#/alerts
```

If the alert is not present here, alertmanager scrape is misconfigured — check `prometheus/prometheus.yml` `alerting.alertmanagers` and the alertmanager container logs.

### 5.3 Confirm routing

```bash
docker run --rm -v "$(pwd)/alertmanager:/cfg:ro" \
  --entrypoint amtool prom/alertmanager:v0.27.0 \
  config routes test --config.file=/cfg/alertmanager.yml \
  severity=warning service=juniper-cascor
# expected: tickets
```

If the route resolves to the wrong receiver, edit `alertmanager.yml` and re-validate with `amtool check-config`.

### 5.4 Check the alertmanager container logs

```bash
docker compose logs alertmanager --tail=200 | grep -iE 'smtp|notify|error|email'
```

Common SMTP failure modes:

| Log pattern | Likely cause |
|-------------|--------------|
| `dial tcp ...: connection refused` | `smtp_smarthost` value wrong, or egress blocked |
| `unencrypted connection` / `535 5.7.0` | `smtp_require_tls` / `smtp_auth_password_file` mismatch with provider expectations |
| `open /run/secrets/alertmanager_smtp_password: no such file` | Docker secret not mounted; check `docker-compose.yml` `secrets:` block and `${ALERTMANAGER_SMTP_PASSWORD_FILE}` |
| `535 5.7.8 Authentication credentials invalid` | Password rotated upstream but `secrets/alertmanager_smtp_password.txt` not updated; re-run §4.1 step 4 |
| `554 ... message rejected` | Recipient or `from` domain rejected by the receiving MX; verify `to:` / `smtp_from` |

### 5.5 Force a synthetic alert end-to-end

```bash
# Send a synthetic alert directly to alertmanager
curl -s -X POST http://localhost:9093/api/v2/alerts -H 'Content-Type: application/json' -d '[
  {
    "labels": {"alertname": "RunbookTest", "severity": "warning", "service": "runbook"},
    "annotations": {"summary": "OBS-ROUTE-01 runbook synthetic test"},
    "startsAt": "'"$(date -u +%Y-%m-%dT%H:%M:%SZ)"'",
    "endsAt":   "'"$(date -u -d '+5 minutes' +%Y-%m-%dT%H:%M:%SZ)"'"
  }
]'
```

If the email arrives, the route + SMTP path is healthy. If not, re-walk §5.4.

---

## 6. References

- **Audit**: [`OBSERVABILITY_AUDIT_AND_OUTSTANDING_ISSUES_2026-05-03.md`](https://github.com/pcalnon/juniper-ml/blob/main/notes/code-review/JUNIPER_2026-05-03_JUNIPER-ECOSYSTEM_OBSERVABILITY-AUDIT-AND-OUTSTANDING-ISSUES.md) §3.2 (P1) and §B.1 (P3) — juniper-ml#195
- **State analysis**: [`A9_AND_3_2_STATE_ANALYSIS_2026-05-03.md`](https://github.com/pcalnon/juniper-ml/blob/main/notes/observability/JUNIPER_2026-05-03_JUNIPER-ECOSYSTEM_A9-AND-3-2-STATE-ANALYSIS.md) §4 Option B — juniper-ml#197
- **SOPS pattern**: [`SOPS_AUDIT_AND_REMEDIATION_PLAN.md`](./SOPS_AUDIT_AND_REMEDIATION_PLAN.md) for the age-key + pre-commit-hook arrangement used here
- **R5.4 burn-rate alerts**: `prometheus/alert_rules.yml` — search for `severity: page` / `severity: ticket`
- **Upstream alertmanager config reference**: <https://prometheus.io/docs/alerting/latest/configuration/#email_config>

---

## 7. Known limitations / follow-ups

- **Placeholder credentials shipped**. Every `to:` / `smtp_from` / `smtp_auth_username` value in `alertmanager/alertmanager.yml` and every value in `.env.secrets.enc` is a `CHANGE_BEFORE_PRODUCTION_USE` placeholder. Production paging will not work until these are rotated per §4.1.
- **`amtool` is snap-confined locally**. The validation path used in this repo is the container form: `docker run --rm -v $(pwd)/alertmanager:/cfg:ro --entrypoint amtool prom/alertmanager:v0.27.0 check-config /cfg/alertmanager.yml`. CI runs the same image.
- **No env-var substitution**. Alertmanager does not interpolate `$VAR` or `${VAR}` in its YAML. Anything that needs to vary by environment must either (a) be a `_file:` reference (only credentials are), or (b) be templated by a wrapper before the container starts. The simplest path is editing `alertmanager.yml` directly.
- **OBS-ROUTE-02 follow-up**: swap `critical` from email to PagerDuty once on-call rotation is established. Out of scope for this PR.
