# Secrets Management Onboarding — Juniper Ecosystem

**Last Updated**: 2026-03-03

This guide covers how secrets are managed across the Juniper ecosystem using [SOPS](https://github.com/getsops/sops) with [age](https://age-encryption.org/) encryption.

---

## Overview

The Juniper ecosystem uses a two-file pattern for environment configuration:

| File | Purpose | Committed to git? | Encrypted? |
|------|---------|--------------------|------------|
| `.env.example` | Public configuration defaults (ports, log levels, URLs) | Yes | No |
| `.env.secrets.example` | Template showing which variables need encryption | Yes | No |
| `.env` | Active configuration (copy of `.env.example`) | No (gitignored) | No |
| `.env.secrets` | Active sensitive config (API keys, DSNs, tokens) | No (gitignored) | No |
| `.env.enc` | SOPS-encrypted secrets for version control | Yes | Yes |
| `.env.secrets.enc` | SOPS-encrypted secrets (alternative naming) | Yes | Yes |

**Flow**: Copy template -> fill in values -> encrypt with SOPS -> commit encrypted file.

---

## Prerequisites

### 1. Install SOPS

```bash
# Debian/Ubuntu
curl -LO https://github.com/getsops/sops/releases/download/v3.12.1/sops_3.12.1_amd64.deb
sudo dpkg -i sops_3.12.1_amd64.deb

# macOS
brew install sops

# Verify
sops --version
# Expected: sops 3.12.1 or later
```

### 2. Install age

```bash
# Debian/Ubuntu (via Go or package manager)
sudo apt install age

# macOS
brew install age

# Via conda (if available)
conda install -c conda-forge age

# Verify
age --version
```

### 3. Receive the Age Key

The age private key is required to decrypt secrets. Obtain it from the project lead through a secure channel (never via email, Slack, or any unencrypted medium).

```bash
# Create the SOPS age key directory
mkdir -p ~/.config/sops/age

# Place the key file (provided to you securely)
# The file should contain a line like:
#   AGE-SECRET-KEY-1XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX
chmod 600 ~/.config/sops/age/keys.txt

# Verify the key is readable by SOPS
ls -la ~/.config/sops/age/keys.txt
# Expected: -rw------- (permissions 600)
```

### 4. Verify Your Setup

Run the verification script from any Juniper repo that has it:

```bash
bash util/sops-verify-setup.sh
```

Or manually verify:

```bash
# Check SOPS is installed
sops --version

# Check age key exists with correct permissions
ls -la ~/.config/sops/age/keys.txt

# Check .sops.yaml exists in repo root
cat .sops.yaml

# Test decryption (if encrypted files exist)
sops -d .env.enc > /dev/null && echo "Decryption OK"
```

---

## Common Workflows

### Decrypting Secrets for Local Development

```bash
# Using the utility script
bash util/sops-decrypt.sh .env.enc .env

# Or manually
sops -d --input-type dotenv --output-type dotenv .env.enc > .env
chmod 600 .env
```

### Editing Encrypted Secrets In-Place

SOPS can open an encrypted file in your `$EDITOR`, decrypt it for editing, then re-encrypt on save:

```bash
# Opens .env.enc in $EDITOR with decrypted content
sops .env.enc

# When you save and quit, SOPS re-encrypts automatically
```

### Adding a New Secret

1. Add the variable name to `.env.secrets.example` (template):
   ```bash
   echo "NEW_API_KEY=" >> .env.secrets.example
   git add .env.secrets.example
   ```

2. Add the actual value to your local `.env.secrets`:
   ```bash
   echo "NEW_API_KEY=sk-live-abc123" >> .env.secrets
   ```

3. Encrypt and commit:
   ```bash
   bash util/sops-encrypt.sh .env.secrets .env.secrets.enc
   git add .env.secrets.enc
   git commit -m "chore: add NEW_API_KEY to encrypted secrets"
   ```

### Encrypting a New File

```bash
# Using the utility script (recommended)
bash util/sops-encrypt.sh .env.secrets .env.secrets.enc

# Or manually
sops -e --input-type dotenv --output-type dotenv .env.secrets > .env.secrets.enc

# Verify the encryption
bash util/sops-validate.sh .env.secrets.enc
```

### Verifying an Encrypted File

```bash
# Using the utility script
bash util/sops-validate.sh .env.enc

# Or manually — check for SOPS metadata
grep -q "^sops_" .env.enc && echo "Has SOPS metadata" || echo "NOT encrypted"

# Verify round-trip
sops -d --input-type dotenv --output-type dotenv .env.enc > /dev/null && echo "Decrypts OK"
```

---

## Pre-commit Hooks

Repos with pre-commit hooks (juniper-cascor, juniper-data, juniper-canopy, juniper-deploy) include a SOPS-aware hook that:

- **Allows**: `.env.example`, `.env.secrets.example`, `.env.demo`, `.env.test` (non-sensitive templates)
- **Allows**: `.env.enc`, `.env.secrets.enc` (SOPS-encrypted files — verified by checking for SOPS metadata)
- **Blocks**: Any `.env` or `.env.secrets` file that is NOT SOPS-encrypted

If the hook blocks your commit:

1. **You're trying to commit an unencrypted `.env` file** — encrypt it first:
   ```bash
   bash util/sops-encrypt.sh .env .env.enc
   git add .env.enc
   # Remove the unencrypted file from staging
   git reset HEAD .env
   ```

2. **You're committing a template file** — template files (`.env.example`, `.env.secrets.example`) should pass automatically.

---

## File Conventions

### `.env.example` (Public Defaults)

Contains all non-sensitive configuration with sensible defaults. Committed to git. Developers copy this to `.env` and customize.

```bash
# Example content
JUNIPER_DATA_HOST=0.0.0.0
JUNIPER_DATA_PORT=8100
JUNIPER_DATA_LOG_LEVEL=INFO
```

### `.env.secrets.example` (Sensitive Template)

Shows which variables contain secrets. Values are empty or placeholder. Committed to git. Developers copy this, fill in real values, then encrypt with SOPS.

```bash
# Example content — fill in values and encrypt with SOPS:
#   cp .env.secrets.example .env.secrets
#   # Edit .env.secrets with real values
#   sops -e --input-type dotenv --output-type dotenv .env.secrets > .env.secrets.enc
JUNIPER_DATA_API_KEYS=
JUNIPER_CASCOR_API_KEYS=
```

### `.env.enc` / `.env.secrets.enc` (Encrypted Secrets)

SOPS-encrypted files committed to git. With `encrypted_regex` configured, comments remain in plaintext while values are encrypted.

---

## Key Rotation

If the age key needs to be rotated (compromise, personnel change, scheduled rotation):

```bash
# Using the utility script (handles all repos)
bash util/sops-rotate-key.sh

# This will:
# 1. Generate a new age key pair
# 2. Re-encrypt all .env.enc files with the new key
# 3. Update .sops.yaml with the new public key
# 4. Output instructions for distributing the new key
```

See `util/sops-rotate-key.sh` for the full procedure.

---

## Key Backup

Back up the age private key to prevent permanent secret loss:

```bash
bash util/sops-backup-key.sh /path/to/secure/backup/location
```

Store the backup in a physically separate, secure location. See `util/sops-backup-key.sh` for details.

---

## Troubleshooting

### "could not decrypt data key"

**Cause**: Your age private key doesn't match the public key used for encryption.

```bash
# Check your key's public key
age-keygen -y ~/.config/sops/age/keys.txt
# Compare with the key in .sops.yaml
cat .sops.yaml
```

**Fix**: Obtain the correct age private key from the project lead.

### "no matching creation_rule"

**Cause**: The file path doesn't match any `path_regex` in `.sops.yaml`.

```bash
# Check the creation rules
cat .sops.yaml
```

**Fix**: Ensure your file is named `.env` or `.env.secrets` (matching the regex `\.env(\.secrets)?$`).

### "sops: command not found"

**Cause**: SOPS is not installed or not in PATH.

**Fix**: Install SOPS per the prerequisites section above.

### Encrypted file shows as binary diff in git

**Cause**: No `.gitattributes` configured for SOPS textconv diff driver.

**Fix**: Configure the SOPS diff driver:
```bash
# One-time setup (per clone/worktree)
git config diff.sopsdiffer.textconv "sops -d"
```

With `.gitattributes` in the repo, `git diff` will show decrypted plaintext diffs for encrypted files.

### Pre-commit hook blocks `.env.example`

**Cause**: Using the old naive hook that blocks all `.env` files.

**Fix**: Update to the SOPS-aware hook. See the `.pre-commit-config.yaml` in this repo for the correct configuration.

### SOPS version mismatch warning

**Cause**: Encrypted files were created with a different SOPS version than the one installed.

**Fix**: This is generally safe — SOPS maintains backward compatibility. To update the file's SOPS metadata, re-encrypt it:
```bash
sops -d --input-type dotenv --output-type dotenv .env.enc | \
  sops -e --input-type dotenv --output-type dotenv /dev/stdin > .env.enc.new
mv .env.enc.new .env.enc
```

---

## Security Rules

1. **Never commit unencrypted `.env` or `.env.secrets` files** — always encrypt first
2. **Never share the age private key via unencrypted channels** — use secure file transfer
3. **Verify encryption before pushing** — run `bash util/sops-validate.sh <file>` or check for SOPS metadata
4. **Keep age key permissions at 600** — `chmod 600 ~/.config/sops/age/keys.txt`
5. **Back up the age key** — loss means permanent loss of all encrypted secrets
6. **Rotate the key** if a team member leaves or if compromise is suspected

---

## Architecture Reference

### SOPS Configuration (`.sops.yaml`)

Each repo contains an identical `.sops.yaml` that tells SOPS which files to encrypt and which key to use:

```yaml
creation_rules:
  - path_regex: \.env(\.secrets)?$
    encrypted_regex: "^.+$"
    age: "age1qmmfhude4xlpdx3wvqv994ahqayke04sgkt5r3ruclu9wmyt04xsdl2kkv"
```

- `path_regex`: Matches `.env` and `.env.secrets` files
- `encrypted_regex`: Encrypts all key-value entries (comments are natively preserved as plaintext by SOPS dotenv format)
- `age`: The public key used for encryption

### File Locations

| File | Location | Purpose |
|------|----------|---------|
| Age private key | `~/.config/sops/age/keys.txt` | Decryption key (never committed) |
| `.sops.yaml` | Each repo root | SOPS configuration |
| `.gitattributes` | Each repo root | Git diff/merge settings for encrypted files |
| `.gitleaks.toml` | Each repo root | Secret scanning configuration |
| `util/sops-*.sh` | `juniper-deploy/util/` | SOPS utility scripts |
