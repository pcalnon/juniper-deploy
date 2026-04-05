# SOPS Audit and Remediation Plan — Juniper Ecosystem

**Date**: 2026-03-03
**Author**: Paul Calnon
**Scope**: All 8 active Juniper repositories
**Status**: Phase 1-3 implemented, Phases 4-5 deferred

---

## Executive Summary

A full audit of SOPS (Secrets OPerationS) configuration across the Juniper ecosystem identified 15 issues ranging from critical to low severity. The ecosystem uses age (X25519) encryption with a single key shared across all 8 repositories. While the core encryption infrastructure works, there are significant gaps in documentation, tooling, key management, and developer experience.

This document details each finding, its impact, and the remediation plan.

---

## Current State

| Attribute | Value |
|-----------|-------|
| **SOPS version (installed)** | 3.12.1 |
| **SOPS version (encrypted files)** | 3.9.4 (version drift) |
| **Encryption backend** | age (X25519) |
| **Age public key** | `age1qmmfhude4xlpdx3wvqv994ahqayke04sgkt5r3ruclu9wmyt04xsdl2kkv` |
| **Age private key location** | `~/.config/sops/age/keys.txt` (permissions: 600, 189 bytes) |
| **`.sops.yaml` status** | Identical across all 8 repos |
| **Encrypted files** | `juniper-cascor/.env.enc`, `juniper-ml/.env.enc` |
| **Repos with pre-commit hooks** | juniper-cascor, juniper-data, juniper-canopy (3 of 8) |
| **Repos with `.gitleaks.toml`** | juniper-data only (1 of 8) |
| **Repos with `.gitattributes`** | None (0 of 8) |

### `.sops.yaml` (identical across all repos)

```yaml
creation_rules:
  - path_regex: \.env(\.secrets)?$
    age: "age1qmmfhude4xlpdx3wvqv994ahqayke04sgkt5r3ruclu9wmyt04xsdl2kkv"
```

### Pre-commit SOPS Hook (identical in all 3 repos that have it)

```yaml
- id: no-unencrypted-env
  name: Block unencrypted .env files
  entry: bash -c 'echo "ERROR: Unencrypted .env file detected. Use sops to encrypt." && exit 1'
  language: system
  files: ^\.env(\.secrets)?$
  types: [file]
```

---

## Findings

### SOPS-001: No Age Key Backup or Recovery Procedure

| Field | Value |
|-------|-------|
| **Severity** | Critical |
| **Impact** | Total data loss — if the age private key is lost, all encrypted secrets become permanently unrecoverable |
| **Current state** | Single copy at `~/.config/sops/age/keys.txt` (permissions 600, 189 bytes). No backup exists. |
| **Desired state** | Encrypted backup of age key with documented recovery procedure |
| **Remediation** | Create `util/sops-backup-key.sh` that produces an encrypted backup with verification. Document recovery in onboarding guide. |
| **Phase** | 1 (this session) |

### SOPS-002: Single Age Key for All Environments

| Field | Value |
|-------|-------|
| **Severity** | Critical |
| **Impact** | No environment separation — the same key decrypts dev, staging, and production secrets. A compromised dev machine exposes all environments. |
| **Current state** | One age key used across all repos and all environments |
| **Desired state** | Separate keys per environment (dev/staging/prod) with per-environment creation rules in `.sops.yaml` |
| **Remediation** | Generate environment-specific age keys. Update `.sops.yaml` with environment-specific `path_regex` rules. |
| **Phase** | 5 (future — separate task) |

### SOPS-003: No `.gitattributes` for SOPS Textconv Diff Driver

| Field | Value |
|-------|-------|
| **Severity** | High |
| **Impact** | `git diff` on encrypted files shows opaque base64 noise instead of readable plaintext diffs. Impossible to review secret changes in PRs or logs. |
| **Current state** | No `.gitattributes` in any of the 8 repos |
| **Desired state** | `.gitattributes` configuring SOPS textconv diff driver and binary merge strategy for encrypted files |
| **Remediation** | Create `.gitattributes` with `diff=sopsdiffer merge=binary` for `*.env.enc` and `*.env.secrets.enc`. |
| **Phase** | 2 (this session) |

### SOPS-004: Pre-commit Hook is Naive — Blocks `.env.example`

| Field | Value |
|-------|-------|
| **Severity** | High |
| **Impact** | False positive — the hook's regex `^\.env(\.secrets)?$` blocks `.env` and `.env.secrets`, which is correct. However, the regex pattern uses `files:` matching against the full filename, and `.env.example` does NOT match `^\.env(\.secrets)?$` because `.example` is extra. Actual issue: the hook unconditionally rejects any matched file with no ability to distinguish encrypted from unencrypted content. If the `.gitignore` ever fails to exclude `.env`, the hook gives no guidance beyond "use sops to encrypt." |
| **Current state** | Naive blocker in 3 repos (juniper-cascor, juniper-data, juniper-canopy). While the regex is technically correct for the base case, it provides no SOPS-awareness — it cannot verify whether a file IS encrypted. |
| **Desired state** | SOPS-aware hook that checks for SOPS metadata in committed `.env` files, allowing encrypted files through and blocking only unencrypted ones |
| **Remediation** | Replace with a script-based hook that inspects file content for SOPS metadata markers. |
| **Phase** | 2 (this session) |

### SOPS-005: No `encrypted_regex` in `.sops.yaml`

| Field | Value |
|-------|-------|
| **Severity** | High |
| **Impact** | SOPS encrypts the entire file contents including comments and blank lines. This makes encrypted files completely opaque — you cannot see the structure, comments, or which keys exist without decrypting. |
| **Current state** | No `encrypted_regex` in `.sops.yaml` |
| **Desired state** | `encrypted_regex` that preserves comments (`#`) and blank lines in plaintext while encrypting all `KEY=VALUE` lines |
| **Remediation** | Add `encrypted_regex: "^.+$"` to `.sops.yaml` creation rules. SOPS dotenv format natively preserves comment lines as plaintext; `encrypted_regex` ensures only key-value entries are encrypted. Note: SOPS uses Go's RE2 regex engine which does not support lookaheads. |
| **Phase** | 2 (this session) |

### SOPS-006: No Key Rotation Procedure Documented

| Field | Value |
|-------|-------|
| **Severity** | High |
| **Impact** | If the age key is compromised or needs rotation, there is no documented procedure for generating a new key, re-encrypting all files, and updating all repos. |
| **Current state** | No documentation or tooling for key rotation |
| **Desired state** | Documented procedure and utility script for key rotation |
| **Remediation** | Create `util/sops-rotate-key.sh` and document the process in the onboarding guide. |
| **Phase** | 1 (this session) |

### SOPS-007: No Developer Onboarding Documentation for SOPS

| Field | Value |
|-------|-------|
| **Severity** | Medium |
| **Impact** | New developers have no guide for setting up SOPS, receiving the age key, or following the encrypt/decrypt workflow. |
| **Current state** | Brief comments in `.env.secrets.example` are the only documentation |
| **Desired state** | Comprehensive `docs/SECRETS_ONBOARDING.md` covering setup, workflow, troubleshooting |
| **Remediation** | Create the onboarding guide. |
| **Phase** | 1 (this session) |

### SOPS-008: SOPS Version Drift

| Field | Value |
|-------|-------|
| **Severity** | Medium |
| **Impact** | Encrypted files were created with SOPS 3.9.4, but the installed version is 3.12.1. While SOPS maintains backward compatibility for decryption, version drift can cause subtle issues with encryption format or metadata. |
| **Current state** | SOPS metadata in `.env.enc` files shows `version: 3.9.4` |
| **Desired state** | All encrypted files re-encrypted with current SOPS version; minimum version documented |
| **Remediation** | Re-encrypt files during Phase 4 propagation. Add version check to `util/sops-verify-setup.sh`. |
| **Phase** | 4 (deferred) |

### SOPS-009: No `.gitleaks.toml` or Secret Scanning Tool

| Field | Value |
|-------|-------|
| **Severity** | Medium |
| **Impact** | No automated detection of accidentally committed secrets. A mistyped `.gitignore` or manual `git add` could leak secrets. |
| **Current state** | Only juniper-data has a `.gitleaks.toml` (with one historical false-positive allowlist entry) |
| **Desired state** | `.gitleaks.toml` in all repos with standard patterns and SOPS-encrypted file allowlisting |
| **Remediation** | Create `.gitleaks.toml` in juniper-deploy (template), propagate to all repos in Phase 4. |
| **Phase** | 2 (this session — juniper-deploy only) |

### SOPS-010: Two Competing Secret Template Patterns

| Field | Value |
|-------|-------|
| **Severity** | Medium |
| **Impact** | Inconsistent developer experience — most repos use `.env.example` for both public config and sensitive template values, while juniper-deploy separates into `.env.example` (public) and `.env.secrets.example` (sensitive). |
| **Current state** | Only juniper-deploy has `.env.secrets.example`. All 8 repos have `.env.example`. |
| **Desired state** | Documented convention: `.env.example` for public config defaults (committed); `.env.secrets.example` for sensitive variable templates that need encryption (committed). Repos that have secrets should have both. |
| **Remediation** | Document the convention in the onboarding guide. Propagation to individual repos is a Phase 4 task. |
| **Phase** | 3 (documentation this session), 4 (propagation deferred) |

### SOPS-011: No Validation Script to Verify SOPS Setup

| Field | Value |
|-------|-------|
| **Severity** | Medium |
| **Impact** | No automated way to verify a developer's SOPS setup is correct — checking tool installation, key presence, `.sops.yaml` validity, and encrypted file integrity. |
| **Current state** | Manual verification only |
| **Desired state** | `util/sops-verify-setup.sh` that validates the full SOPS stack |
| **Remediation** | Create the verification script. |
| **Phase** | 1 (this session) |

### SOPS-012: `.sops.yaml` Duplicated Across 8 Repos

| Field | Value |
|-------|-------|
| **Severity** | Low |
| **Impact** | Configuration sync burden — any change to `.sops.yaml` (e.g., adding `encrypted_regex`, rotating keys) must be applied to all 8 repos manually. |
| **Current state** | Identical `.sops.yaml` in all repos |
| **Desired state** | Accepted as necessary for polyrepo architecture. Mitigated by utility scripts that can propagate changes. |
| **Remediation** | Document the sync requirement. Consider a propagation script in Phase 4. |
| **Phase** | 4 (deferred) |

### SOPS-013: No CI/CD Integration for SOPS

| Field | Value |
|-------|-------|
| **Severity** | Low |
| **Impact** | CI pipelines cannot decrypt secrets for integration testing. No automated validation of encrypted file integrity in CI. |
| **Current state** | No SOPS integration in GitHub Actions |
| **Desired state** | CI step that validates encrypted files can be decrypted (using `SOPS_AGE_KEY` secret). Optional: decrypt-at-test for integration tests. |
| **Remediation** | Add SOPS validation step to CI. Requires GitHub Actions secret for the age key. |
| **Phase** | 5 (future) |

### SOPS-014: Docker Compose Secrets and SOPS Are Parallel Systems

| Field | Value |
|-------|-------|
| **Severity** | Low |
| **Impact** | juniper-deploy has both a `secrets/` directory (Docker Compose secrets mechanism) and SOPS-encrypted `.env.enc` files. These are two parallel, unintegrated secrets management approaches. |
| **Current state** | Docker Compose `secrets/` uses plaintext files (gitignored). SOPS encrypts `.env` files. No integration between them. |
| **Desired state** | Documented relationship between the two systems. Optional: decrypt-at-deploy step that converts SOPS files to Docker Compose secrets format. |
| **Remediation** | Document in onboarding guide. Integration is a low-priority future enhancement. |
| **Phase** | 5 (future) |

### SOPS-015: No SOPS Merge Driver in `.gitattributes`

| Field | Value |
|-------|-------|
| **Severity** | Low |
| **Impact** | Git merge conflicts on encrypted files produce unusable results. Binary merge strategy (always take ours/theirs) is safer for encrypted files. |
| **Current state** | No `.gitattributes` in any repo |
| **Desired state** | `merge=binary` attribute on encrypted files to prevent merge conflicts |
| **Remediation** | Include in `.gitattributes` (same file as SOPS-003). |
| **Phase** | 2 (this session) |

---

## Remediation Summary by Phase

### Phase 1: Documentation and Utility Scripts (this session)

| Deliverable | Addresses |
|-------------|-----------|
| `docs/SECRETS_ONBOARDING.md` | SOPS-007 |
| `notes/SOPS_AUDIT_AND_REMEDIATION_PLAN.md` | Audit report |
| `util/sops-verify-setup.sh` | SOPS-011 |
| `util/sops-encrypt.sh` | SOPS-007 (tooling) |
| `util/sops-decrypt.sh` | SOPS-007 (tooling) |
| `util/sops-validate.sh` | SOPS-011 (tooling) |
| `util/sops-rotate-key.sh` | SOPS-006 |
| `util/sops-backup-key.sh` | SOPS-001 |

### Phase 2: Configuration Fixes (this session)

| Deliverable | Addresses |
|-------------|-----------|
| `.sops.yaml` update (add `encrypted_regex`) | SOPS-005 |
| `.gitattributes` | SOPS-003, SOPS-015 |
| `.gitleaks.toml` | SOPS-009 |
| `.pre-commit-config.yaml` with SOPS-aware hook | SOPS-004 |

### Phase 3: Template Consolidation (this session)

| Deliverable | Addresses |
|-------------|-----------|
| Documented `.env.example` / `.env.secrets.example` convention | SOPS-010 |

### Phase 4: Cross-Repo Propagation (deferred)

| Deliverable | Addresses |
|-------------|-----------|
| Propagate `.sops.yaml` update to all 8 repos | SOPS-005, SOPS-012 |
| Add `.gitattributes` to all repos | SOPS-003, SOPS-015 |
| Update pre-commit hooks in juniper-cascor, juniper-data, juniper-canopy | SOPS-004 |
| Add `.gitleaks.toml` to remaining 7 repos | SOPS-009 |
| Re-encrypt existing `.env.enc` files with updated config | SOPS-008 |

### Phase 5: Future Enhancements (separate tasks)

| Deliverable | Addresses |
|-------------|-----------|
| Multi-key management (dev/staging/prod) | SOPS-002 |
| CI/CD integration | SOPS-013 |
| Docker Compose secrets integration | SOPS-014 |

---

## Gaps and Future Considerations

1. **No automated CI integration** — CI pipelines need `SOPS_AGE_KEY` GitHub Actions secret for decryption
2. **Docker Compose secrets vs. SOPS** — parallel systems that could be integrated with a decrypt-at-deploy step
3. **Single-developer setup** — current architecture assumes one developer; multi-developer needs key distribution
4. **No encrypted file integrity verification in CI** — could add `sops -d --output /dev/null` as a CI validation step
5. **Gitleaks baseline scan** — existing repos may have historical secrets in git history that need triage
6. **SOPS version pinning** — no mechanism to enforce minimum SOPS version across developer machines
