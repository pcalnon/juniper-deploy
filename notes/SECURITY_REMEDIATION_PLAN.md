# juniper-deploy PR #14 Security Remediation Plan

**Date**: 2026-04-04
**PR**: [pcalnon/juniper-deploy#14](https://github.com/pcalnon/juniper-deploy/pull/14) — "Chore/phase3 cleanup"
**Branch**: `chore/phase3-cleanup`
**Blocking Issues**: [#17](https://github.com/pcalnon/juniper-deploy/issues/17) (secret-leak bypass), [#18](https://github.com/pcalnon/juniper-deploy/issues/18) (high-risk assessment)
**Author**: Paul Calnon

---

## Executive Summary

PR #14 introduces a comprehensive developer experience upgrade to juniper-deploy, including Docker Compose profiles for integration testing and observability, SOPS-based secrets management tooling, pre-commit hooks, and Gitleaks configuration. An automated security review (Cursor Automation) identified two high-severity security concerns that block the PR:

1. **Secret-leak detection bypass via `.env.enc` path allowlisting** (Issue #17) — The Gitleaks configuration blanket-allows files matching `*.env.enc`, and the SOPS pre-commit hook is skipped in CI contexts, creating a path for plaintext secrets to be committed undetected.
2. **Shell injection via environment variable interpolation** (Issue #17, uncertain concern) — `scripts/wait_for_services.sh` interpolates environment-derived URLs directly into inline Python code, enabling code injection if an attacker controls PORT environment variables.
3. **Broad infrastructure risk surface** (Issue #18) — The PR touches security-sensitive secrets wiring, Docker networks, volumes, and operational scripts across core services, warranting careful review.

This plan provides a root-cause analysis of each vulnerability, concrete remediation steps with code-level specifics, and a verification strategy.

---

## Issue #17 — Vulnerability 1: Secret-Leak Detection Bypass

### Root Cause Analysis

The vulnerability stems from three independent gaps that compound to create a bypass path:

#### Gap 1: Gitleaks Path-Based Allowlisting (`.gitleaks.toml`)

```toml
[allowlist]
  paths = [
    '''\.env\.enc$''',
    '''\.env\.secrets\.enc$''',
  ]
```

**Problem**: Gitleaks `[allowlist].paths` exempts matching files from **all** detection rules. Any file whose path ends in `.env.enc` or `.env.secrets.enc` is entirely invisible to Gitleaks — regardless of whether the file contains actual SOPS-encrypted ciphertext or plaintext secrets. This is confirmed by the [gitleaks source code](https://github.com/gitleaks/gitleaks/blob/master/detect/detect.go), where `checkCommitOrPathAllowed()` returns early before any rule evaluation, and by [gitleaks/gitleaks#1790](https://github.com/gitleaks/gitleaks/issues/1790).

**Attack scenario**: A developer (or attacker with repo write access) creates a file named `.env.enc` containing plaintext secrets like `DATABASE_PASSWORD=hunter2`. Gitleaks will never flag it because the path matches the allowlist.

#### Gap 2: Pre-commit Hook Skipped in CI (`.pre-commit-config.yaml`)

```yaml
ci:
  skip: [no-unencrypted-env]
```

**Problem**: The `ci:` section configures behavior for the [pre-commit.ci](https://pre-commit.ci) hosted service. If the project uses pre-commit.ci (now or in the future), the `no-unencrypted-env` hook — the only defense that validates SOPS metadata on `.env.enc` files — will be skipped entirely.

**Mitigating factor**: The current GitHub Actions CI workflow (`ci.yml`) runs `pre-commit run --all-files` directly, which does NOT respect the `ci:` section. The `SKIP` env var in CI is set to `docker-compose-check` only — `no-unencrypted-env` is NOT skipped. So today, the pre-commit hook runs in GitHub Actions CI. However, the `ci: skip` entry creates a latent vulnerability if the project ever adopts pre-commit.ci or if a developer misinterprets this configuration.

#### Gap 3: Weak SOPS Metadata Validation (`util/sops-pre-commit-hook.sh`)

```bash
case "$basename" in
    *.env.enc|*.env.secrets.enc)
        if grep -q "^sops_" "$file" 2>/dev/null; then
            continue  # Passes validation
        else
            exit_code=1
        fi
        ;;
esac
```

**Problem**: The SOPS metadata check uses a simple `grep -q "^sops_"` — it only verifies that *any* line starting with `sops_` exists in the file. An attacker can trivially spoof this:

```dotenv
sops_version=fake
DATABASE_PASSWORD=hunter2
AWS_SECRET_KEY=AKIAIOSFODNN7EXAMPLE
```

This file would pass the pre-commit hook because `grep -q "^sops_"` matches `sops_version=fake`, despite all remaining lines being plaintext secrets.

#### Combined Attack Path

```
Attacker creates .env.enc with spoofed sops_ prefix + plaintext secrets
  ├── Gitleaks:        SKIPPED (path allowlist)
  ├── Pre-commit hook: PASSED  (grep "^sops_" matches spoofed line)
  └── Result:          Plaintext secrets committed to repository
```

### Remediation Steps

#### R1.1: Replace Gitleaks Path Allowlisting with Content-Based Allowlisting

**File**: `.gitleaks.toml`

**Change**: Remove the blanket path allowlist. Instead, use `regexTarget = "match"` rules that suppress only lines matching SOPS ciphertext patterns — not entire files.

**Proposed replacement**:

```toml
title = "Juniper Gitleaks Configuration"

# Do NOT use [allowlist].paths to exempt .env.enc files — this would
# skip ALL rules for those files, including plaintext secret detection.

[allowlist]
  description = "Allowlisted patterns"

  # age public keys are not secrets (only the private key is sensitive)
  # SOPS-encrypted ciphertext values (ENC[AES256_GCM,...]) are safe to commit
  regexes = [
    '''age1[a-z0-9]{58}''',
    '''ENC\[AES256_GCM,data:[A-Za-z0-9+/=]+,''',
  ]
```

**Why not use `[[rules]]` with per-rule allowlists?** A `[[rules]]` block defines a *detection rule* — it tells Gitleaks to find a pattern and report it as a finding. Adding a per-rule `[rules.allowlist]` to suppress its own findings creates a no-op rule. Critically, per-rule allowlists do not affect findings from *other* rules (the built-in defaults). The actual goal is to suppress false positives when SOPS ciphertext triggers default rules like `generic-api-key`. The global `[allowlist].regexes` achieves this: when any finding's matched text contains the SOPS ciphertext pattern, it is suppressed across all rules.

**Rationale**: SOPS-encrypted dotenv files store values in `ENC[AES256_GCM,data:...,iv:...,tag:...,type:...]` format. With the path allowlist removed, Gitleaks will now scan `.env.enc` files. The global regex allowlist suppresses only findings whose matched text looks like SOPS ciphertext, so any plaintext secret in the file will still be detected by Gitleaks default rules.

#### R1.2: Remove CI Skip for SOPS Hook

**File**: `.pre-commit-config.yaml`

**Change**: Remove the `ci:` section entirely, or remove `no-unencrypted-env` from the skip list.

**Before**:
```yaml
ci:
  skip: [no-unencrypted-env]
```

**After**:
```yaml
# ci:
#   No hooks are skipped — SOPS validation runs everywhere.
```

**Rationale**: The SOPS validation hook must run in all contexts. If pre-commit.ci cannot execute it (e.g., because `sops` is not installed), the proper fix is to configure pre-commit.ci with a system dependency or switch to a portable validation approach (see R1.3).

#### R1.3: Strengthen SOPS Metadata Validation in Pre-commit Hook

**File**: `util/sops-pre-commit-hook.sh`

**Change**: Replace the weak `grep -q "^sops_"` check with multi-field validation that verifies the presence of critical SOPS metadata keys that are hard to spoof without actual SOPS encryption.

**Proposed replacement for the `.env.enc` case block**:

```bash
# Allow encrypted files only if they have valid SOPS metadata
case "$basename" in
    *.env.enc|*.env.secrets.enc)
        # Require multiple SOPS metadata fields (not just one prefix match)
        sops_fields_found=0
        grep -q "^sops_version=" "$file" 2>/dev/null && sops_fields_found=$((sops_fields_found + 1))
        grep -q "^sops_lastmodified=" "$file" 2>/dev/null && sops_fields_found=$((sops_fields_found + 1))
        grep -q "^sops_age__" "$file" 2>/dev/null && sops_fields_found=$((sops_fields_found + 1))

        if [[ $sops_fields_found -ge 3 ]]; then
            # Verify all non-metadata, non-comment lines contain ENC[AES256_GCM,...] values
            plaintext_lines=$(grep -v "^#" "$file" | grep -v "^sops_" | grep -v "^$" | grep -cv "ENC\[AES256_GCM," 2>/dev/null || echo "0")
            if [[ "$plaintext_lines" -gt 0 ]]; then
                echo "ERROR: ${file} contains ${plaintext_lines} non-encrypted value(s)."
                echo "  All values in encrypted files must use SOPS encryption."
                echo "  Re-encrypt with: sops -e -i ${file}"
                exit_code=1
            else
                continue
            fi
        else
            echo "ERROR: ${file} is named as encrypted but has insufficient SOPS metadata."
            echo "  Found ${sops_fields_found}/3 required metadata fields."
            echo "  Encrypt it with: bash util/sops-encrypt.sh <source> ${file}"
            exit_code=1
        fi
        ;;
esac
```

**Rationale**: This validates three independent SOPS metadata fields AND verifies that all non-metadata value lines contain `ENC[AES256_GCM,...]` ciphertext. A spoofed file would need to fabricate all three metadata fields AND wrap every value in valid-looking ciphertext format, making the bypass impractical.

#### R1.4: Add CI Pipeline SOPS Validation Job

**File**: `.github/workflows/ci.yml`

**Change**: Add a dedicated CI job that runs structural validation on all `*.env.enc` and `*.env.secrets.enc` files. This provides server-side defense-in-depth — even if pre-commit hooks are bypassed locally.

**Placement**: Insert after the `pre-commit` job, before `validate-compose`. Add `sops-validation` to the `needs:` list in the `required-checks` quality gate job so it becomes a required check.

**Proposed new job**:

```yaml
  # ═══════════════════════════════════════════════════════════════════════════
  # SOPS Encryption Validation
  # ═══════════════════════════════════════════════════════════════════════════
  sops-validation:
    name: SOPS Validation
    runs-on: ubuntu-latest
    steps:
      - name: Checkout Code
        uses: actions/checkout@de0fac2e4500dabe0009e67214ff5f5447ce83dd  # v6.0.2

      - name: Check for encrypted files
        id: check-enc
        run: |
          ENC_FILES=$(find . -name '*.env.enc' -o -name '*.env.secrets.enc' 2>/dev/null)
          if [ -z "$ENC_FILES" ]; then
            echo "No encrypted files found — skipping validation."
            echo "skip=true" >> "$GITHUB_OUTPUT"
          else
            echo "Found encrypted files:"
            echo "$ENC_FILES"
            echo "skip=false" >> "$GITHUB_OUTPUT"
          fi

      - name: Validate SOPS metadata structure
        if: steps.check-enc.outputs.skip != 'true'
        run: |
          exit_code=0
          for file in $(find . -name '*.env.enc' -o -name '*.env.secrets.enc'); do
            echo "Validating: $file"

            # Check for required SOPS metadata sections
            for key in sops_version sops_lastmodified; do
              if ! grep -q "^${key}=" "$file" 2>/dev/null; then
                echo "  FAIL: Missing SOPS metadata key: ${key}"
                exit_code=1
              fi
            done
            # Check for age recipient (prefix match — supports multiple recipients)
            if ! grep -q "^sops_age__" "$file" 2>/dev/null; then
              echo "  FAIL: Missing SOPS age recipient metadata"
              exit_code=1
            fi

            # Check that all value lines contain SOPS ciphertext
            plaintext=$(grep -v '^#' "$file" | grep -v '^sops_' | grep -v '^$' | grep -cv 'ENC\[AES256_GCM,' 2>/dev/null || echo "0")
            if [ "$plaintext" -gt 0 ]; then
              echo "  FAIL: $plaintext line(s) contain non-encrypted values"
              exit_code=1
            else
              echo "  PASS: All values are SOPS-encrypted"
            fi
          done
          exit $exit_code
```

**Rationale**: This is a server-side enforcement layer that cannot be bypassed by local configuration or env var manipulation. It structurally validates that encrypted files contain actual SOPS ciphertext without requiring the age private key (no decryption needed — just structural checks).

**Note**: Full decryption validation (as `sops-validate.sh` supports) would require the age private key in CI, which is a separate operational decision. The structural check above catches the bypass scenario without needing secrets in CI.

---

## Issue #17 — Vulnerability 2: Shell Injection in `wait_for_services.sh`

### Root Cause Analysis

**File**: `scripts/wait_for_services.sh`

The `check_service()` function constructs a Python one-liner using bash string interpolation:

```bash
check_service() {
    local name="$1"
    local url="$2"
    local result
    result=$(python3 -c "
import urllib.request, json, sys
try:
    resp = urllib.request.urlopen('${url}', timeout=3)
    ...
")
```

The `${url}` variable is interpolated by bash *before* Python parses the code. Since `url` is derived from environment variables:

```bash
DATA_URL="http://localhost:${JUNIPER_DATA_PORT:-8100}/v1/health/ready"
```

A malicious `JUNIPER_DATA_PORT` value can break out of the Python string literal and execute arbitrary code:

```bash
# Exploit payload:
export JUNIPER_DATA_PORT="8100/v1/health/ready', timeout=3); import os; os.system('id'); #"
```

This would produce the Python code:
```python
resp = urllib.request.urlopen('http://localhost:8100/v1/health/ready', timeout=3); import os; os.system('id'); #/v1/health/ready', timeout=3)
```

The `'` closes the Python string, the `;` starts a new statement, and `#` comments out the remainder — achieving arbitrary code execution.

### Attack Surface Assessment

| Context | PORT Var Source | Exploitability |
|---------|----------------|----------------|
| Local dev | `.env` file, shell env | **Medium** — A compromised `.env` file or malicious shell env could trigger this |
| CI (GitHub Actions) | Hardcoded in workflow | **Low** — PORT vars use defaults, not user-controlled |
| Docker Compose | `.env` or compose env | **Low** — Compose runs in container context |

**Severity**: Medium (CWE-78: OS Command Injection). While the attack surface is narrow (requires control of environment variables in the execution context), this is a well-known anti-pattern and was confirmed exploitable via live proof-of-concept by the validation agent.

### Full Inventory of Affected Files

The validation agent identified the same vulnerable pattern in additional scripts beyond `wait_for_services.sh`:

| File | Line(s) | Pattern | Exploitable? |
|------|---------|---------|--------------|
| `scripts/wait_for_services.sh` | 35 | `python3 -c` with `${url}` interpolation | **Yes** |
| `scripts/health_check.sh` | 59-79 | Multiline `python3 -c` with `${url}` inside try/except | **Yes** (confirmed with live PoC) |
| `scripts/test_health_enhanced.sh` | 66 | `python3 -c` with `${port}` interpolation | **Yes** |
| `scripts/test_health_enhanced.sh` | 107 | `curl` with `${CASCOR_HOST_PORT}` in URL | URL injection into curl (different class) |
| `.github/workflows/ci.yml` | 173-206 | Hardcoded URLs in inline Python | **Not vulnerable** |
| `docker-compose.yml` healthchecks | various | Hardcoded URLs in healthcheck commands | **Not vulnerable** |

### CI Workflow Assessment

The CI workflow (`ci.yml`) contains similar inline Python in its health check steps, but uses hardcoded ports (`8100`, `8201`, `8050`) rather than environment variables — so those instances are **not injectable**. However, `wait_for_services.sh` IS called from CI with `bash scripts/wait_for_services.sh 120`, where PORT defaults apply.

### Remediation Steps

#### R2.1: Pass URLs as Arguments Instead of String Interpolation

**Files**: `scripts/wait_for_services.sh`, `scripts/health_check.sh`, `scripts/test_health_enhanced.sh`

**Change**: In all three scripts, pass URLs/ports to Python via `sys.argv` instead of interpolating them into the code string.

**Proposed replacement for `check_service()`**:

```bash
check_service() {
    local name="$1"
    local url="$2"
    local result
    result=$(python3 -c "
import urllib.request, json, sys
url = sys.argv[1]
try:
    resp = urllib.request.urlopen(url, timeout=3)
    data = json.loads(resp.read().decode())
    status = data.get('status', 'unknown')
    version = data.get('version', 'n/a')
    service = data.get('service', 'unknown')
    if status in ('healthy', 'ok', 'ready'):
        print(f'ok|{status}|{version}')
    else:
        print(f'degraded|{status}|{version}')
except Exception:
    print('error|unreachable|n/a')
" "$url" 2>/dev/null)

    IFS='|' read -r ok status version <<< "$result"

    if [[ "$ok" == "ok" ]]; then
        echo "  ✓ ${name} is ready (status=${status}, version=${version})"
        return 0
    elif [[ "$ok" == "degraded" ]]; then
        echo "  ⚠ ${name} responded but status=${status}"
        return 1
    fi
    return 1
}
```

**Key change**: `url = sys.argv[1]` + `"$url"` as a positional argument after the `-c` script. Python receives the URL as a data argument, never as code. The shell variable `$url` is now a Python string argument, not interpolated into Python source.

#### R2.2: Add PORT Variable Validation

**File**: `scripts/wait_for_services.sh`

**Change**: Add input validation after the PORT defaults are resolved to reject non-numeric values.

**Proposed addition** (after the URL variable assignments):

```bash
# Validate port values are numeric (defense against env injection)
for port_var in JUNIPER_DATA_PORT CASCOR_PORT CANOPY_PORT; do
    port_val="${!port_var:-}"
    if [[ -n "$port_val" && ! "$port_val" =~ ^[0-9]+$ ]]; then
        echo "ERROR: ${port_var}='${port_val}' is not a valid port number"
        exit 1
    fi
done
```

**Rationale**: Defense-in-depth. Even with the `sys.argv` fix, validating that PORT values are numeric prevents any future misuse of these variables. The same validation pattern should be added to `health_check.sh` and `test_health_enhanced.sh`, adapting variable names as needed (e.g., `CASCOR_HOST_PORT` in those scripts).

#### R2.3: Remediate `curl` URL Injection in `test_health_enhanced.sh`

**File**: `scripts/test_health_enhanced.sh` (line 107)

**Problem**: This script passes `${CASCOR_HOST_PORT}` directly into a `curl` URL argument. While this is not a Python code injection, a malicious value containing spaces or shell metacharacters could inject additional `curl` arguments (e.g., `-o /tmp/pwned` for SSRF-like file writes).

**Change**: Apply the same PORT numeric validation (R2.2) before `curl` is called. Additionally, quote the URL argument to prevent word splitting:

```bash
curl -sf "http://localhost:${CASCOR_HOST_PORT}/v1/health"
```

**Rationale**: The PORT validation from R2.2 is the primary defense. Proper quoting of the curl URL provides secondary protection against word-splitting attacks.

---

## Issue #18 — High-Risk PR Assessment

### Analysis

Issue #18 is an automated risk assessment (Cursor Automation: "Assign PR reviewers") that flagged the PR as **High risk** due to:

1. Broad infrastructure changes across core services in `docker-compose.yml`
2. Security-sensitive secret management changes across multiple files
3. Operational/test behavior changes in shared scripts

This issue is not a specific vulnerability but a risk classification. It does not require code remediation — it requires thorough review, which the fixes in this plan address.

### Recommendation

Once the remediation for Issue #17 vulnerabilities is implemented and validated:

1. The specific vulnerabilities (Gitleaks bypass, shell injection) will be resolved
2. The remaining changes (Docker networks, volumes, profiles, observability) are standard infrastructure improvements that do not introduce security vulnerabilities
3. Issue #18 can be closed with a reference to this remediation plan and the PR that implements the fixes

---

## Implementation Plan

### Phase 1: Critical Security Fixes (Blocks PR Merge)

| Step | File(s) | Change | Issue |
|------|---------|--------|-------|
| 1a | `.gitleaks.toml` | Replace path allowlist with content-based ciphertext rule (R1.1) | #17 |
| 1b | `.pre-commit-config.yaml` | Remove `ci: skip: [no-unencrypted-env]` (R1.2) | #17 |
| 1c | `util/sops-pre-commit-hook.sh` | Multi-field metadata + ciphertext validation (R1.3) | #17 |
| 1d | `scripts/wait_for_services.sh`, `scripts/health_check.sh`, `scripts/test_health_enhanced.sh` | Replace string interpolation with `sys.argv` (R2.1) | #17 |
| 1e | `scripts/wait_for_services.sh`, `scripts/health_check.sh`, `scripts/test_health_enhanced.sh` | Add PORT variable numeric validation (R2.2) | #17 |
| 1f | `scripts/test_health_enhanced.sh` | Fix `curl` URL quoting and injection (R2.3) | #17 |

### Phase 2: Defense-in-Depth (Recommended, Not Blocking)

| Step | File(s) | Change | Issue |
|------|---------|--------|-------|
| 2a | `.github/workflows/ci.yml` | Add SOPS structural validation CI job (R1.4) | #17 |
| 2b | `.github/workflows/ci.yml` | Add `test` and `observability` profile validation to `validate-compose` job | #18 |

### Phase 3: Issue Resolution

| Step | Action |
|------|--------|
| 3a | Implement Phase 1 fixes on `chore/phase3-cleanup` branch |
| 3b | Run pre-commit hooks locally to verify fixes pass |
| 3c | Push to PR and verify CI passes |
| 3d | Close Issue #17 with reference to fix commit |
| 3e | Close Issue #18 with reference to this plan and completed review |
| 3f | Merge PR #14 |

---

## Verification Checklist

### For Vulnerability 1 (Secret-Leak Bypass)

- [ ] Create a test `.env.enc` file with spoofed `sops_version=fake` + plaintext secret
- [ ] Verify Gitleaks detects the plaintext secret (no longer path-allowlisted)
- [ ] Verify pre-commit hook rejects the file (insufficient metadata / non-encrypted values)
- [ ] Verify the hook passes for a legitimately SOPS-encrypted `.env.enc` file
- [ ] Verify CI pipeline catches the spoofed file (if Phase 2 SOPS validation job is added)

### For Vulnerability 2 (Shell Injection)

- [ ] Set `JUNIPER_DATA_PORT` to an injection payload and verify it is rejected by validation
- [ ] Verify `check_service()` works correctly with valid PORT values after the `sys.argv` change
- [ ] Verify the script still functions correctly in CI context

### Regression

- [ ] `pre-commit run --all-files` passes on the branch
- [ ] CI pipeline passes (all existing jobs)
- [ ] `make test` still functions (if Docker environment is available)
- [ ] Existing legitimately encrypted files (`.env.enc`) are not falsely rejected

---

## Appendix: Files Modified by PR #14

| File | Type | Security Relevance |
|------|------|-------------------|
| `.gitleaks.toml` | **New** | **HIGH** — Secret detection bypass via path allowlist |
| `.pre-commit-config.yaml` | **New** | **HIGH** — SOPS hook skipped in CI |
| `util/sops-pre-commit-hook.sh` | **New** | **HIGH** — Weak SOPS metadata validation |
| `scripts/wait_for_services.sh` | Modified | **MEDIUM** — Shell injection via env var interpolation |
| `scripts/health_check.sh` | Modified | **MEDIUM** — Same shell injection pattern (confirmed with live PoC) |
| `scripts/test_health_enhanced.sh` | Modified | **MEDIUM** — Same shell injection pattern |
| `.sops.yaml` | Modified | Low — Adds `encrypted_regex` (correct behavior) |
| `.gitattributes` | New | Low — Diff driver config for SOPS files |
| `docker-compose.yml` | Modified | Low — Networks, volumes, profiles (standard infra) |
| `Dockerfile.test` | New | Low — Test runner container |
| `Makefile` | Modified | Low — New make targets |
| `README.md` | Modified | None — Documentation |
| `docker-compose.override.yml.example` | New | None — Template |
| `.env.demo` | Modified | None — Non-sensitive demo config |
| `docs/SECRETS_ONBOARDING.md` | New | None — Documentation |
| `secrets.example/*.txt` | New | None — Template files |
| `util/sops-*.sh` | New | Low — Utility scripts |
| `notes/SOPS_AUDIT_AND_REMEDIATION_PLAN.md` | New | None — Documentation |
| `notes/PHASE2_SYSTEMD_IMPLEMENTATION_PLAN.md` | New | None — Documentation |
| `pytest.ini` | New | None — Test config |
| `scripts/test_demo_profile.sh` | Modified | None — Test script |
