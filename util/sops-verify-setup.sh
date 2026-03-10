#!/usr/bin/env bash
# =============================================================================
# sops-verify-setup.sh — Validate SOPS installation and configuration
#
# Project: Juniper Ecosystem
# Author: Paul Calnon
# License: MIT
#
# Usage: bash util/sops-verify-setup.sh [--verbose]
#
# Checks:
#   1. SOPS is installed and meets minimum version
#   2. age is installed
#   3. Age private key exists with correct permissions
#   4. .sops.yaml exists and is valid
#   5. Age public key in .sops.yaml matches private key
#   6. Encrypted files (if any) can be decrypted
# =============================================================================

set -euo pipefail

# --- Configuration ---
MIN_SOPS_VERSION="3.9.0"
AGE_KEY_PATH="${SOPS_AGE_KEY_FILE:-${HOME}/.config/sops/age/keys.txt}"
SOPS_YAML=".sops.yaml"
VERBOSE="${1:-}"

# --- Colors ---
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

pass_count=0
fail_count=0
warn_count=0

pass() {
    echo -e "  ${GREEN}PASS${NC}  $1"
    pass_count=$((pass_count + 1))
}

fail() {
    echo -e "  ${RED}FAIL${NC}  $1"
    fail_count=$((fail_count + 1))
}

warn() {
    echo -e "  ${YELLOW}WARN${NC}  $1"
    warn_count=$((warn_count + 1))
}

info() {
    if [[ "$VERBOSE" == "--verbose" ]]; then
        echo -e "  ${BLUE}INFO${NC}  $1"
    fi
}

# --- Version comparison ---
version_ge() {
    # Returns 0 if $1 >= $2 (semver comparison)
    local IFS=.
    local i ver1=($1) ver2=($2)
    for ((i = 0; i < ${#ver2[@]}; i++)); do
        if [[ -z "${ver1[i]:-}" ]]; then
            return 1
        fi
        if ((10#${ver1[i]} > 10#${ver2[i]})); then
            return 0
        fi
        if ((10#${ver1[i]} < 10#${ver2[i]})); then
            return 1
        fi
    done
    return 0
}

echo "============================================="
echo " SOPS Setup Verification — Juniper Ecosystem"
echo "============================================="
echo ""

# --- Check 1: SOPS installed ---
echo "1. SOPS Installation"
if command -v sops &>/dev/null; then
    sops_version=$(sops --version 2>&1 | grep -oP '\d+\.\d+\.\d+' | head -1)
    if [[ -n "$sops_version" ]]; then
        pass "SOPS installed: v${sops_version}"
        if version_ge "$sops_version" "$MIN_SOPS_VERSION"; then
            pass "SOPS version >= ${MIN_SOPS_VERSION}"
        else
            fail "SOPS version ${sops_version} < minimum ${MIN_SOPS_VERSION}"
        fi
    else
        warn "SOPS installed but could not determine version"
    fi
else
    fail "SOPS is not installed (install from https://github.com/getsops/sops/releases)"
fi
echo ""

# --- Check 2: age installed ---
echo "2. age Installation"
if command -v age &>/dev/null; then
    age_version=$(age --version 2>&1 | head -1)
    pass "age installed: ${age_version}"
else
    fail "age is not installed (install from https://age-encryption.org/)"
fi

if command -v age-keygen &>/dev/null; then
    pass "age-keygen available"
else
    fail "age-keygen is not available"
fi
echo ""

# --- Check 3: Age private key ---
echo "3. Age Private Key"
if [[ -f "$AGE_KEY_PATH" ]]; then
    pass "Key file exists: ${AGE_KEY_PATH}"

    # Check permissions
    perms=$(stat -c '%a' "$AGE_KEY_PATH" 2>/dev/null || stat -f '%A' "$AGE_KEY_PATH" 2>/dev/null)
    if [[ "$perms" == "600" ]]; then
        pass "Key file permissions: ${perms} (correct)"
    else
        warn "Key file permissions: ${perms} (should be 600). Fix with: chmod 600 ${AGE_KEY_PATH}"
    fi

    # Check key format
    if grep -q "^AGE-SECRET-KEY-" "$AGE_KEY_PATH"; then
        pass "Key file contains valid age secret key"
    else
        fail "Key file does not contain a valid age secret key (expected AGE-SECRET-KEY-... line)"
    fi

    # Derive public key
    if command -v age-keygen &>/dev/null; then
        derived_pubkey=$(age-keygen -y "$AGE_KEY_PATH" 2>/dev/null)
        if [[ -n "$derived_pubkey" ]]; then
            info "Derived public key: ${derived_pubkey}"
        fi
    fi
else
    fail "Key file not found: ${AGE_KEY_PATH}"
    echo "       Set SOPS_AGE_KEY_FILE or place the key at ~/.config/sops/age/keys.txt"
fi
echo ""

# --- Check 4: .sops.yaml ---
echo "4. SOPS Configuration (.sops.yaml)"
if [[ -f "$SOPS_YAML" ]]; then
    pass ".sops.yaml exists in repo root"

    # Check for creation_rules
    if grep -q "creation_rules" "$SOPS_YAML"; then
        pass ".sops.yaml contains creation_rules"
    else
        fail ".sops.yaml missing creation_rules"
    fi

    # Check for age key
    sops_pubkey=$(grep -oP 'age: "?\K[^"]+' "$SOPS_YAML" 2>/dev/null | head -1)
    if [[ -n "$sops_pubkey" ]]; then
        pass ".sops.yaml has age public key configured"
        info "Public key in .sops.yaml: ${sops_pubkey}"
    else
        fail ".sops.yaml missing age public key"
    fi

    # Check for encrypted_regex
    if grep -q "encrypted_regex" "$SOPS_YAML"; then
        pass ".sops.yaml has encrypted_regex configured"
    else
        warn ".sops.yaml missing encrypted_regex (comments will be encrypted)"
    fi

    # Cross-check: does the public key match our private key?
    if [[ -n "${derived_pubkey:-}" ]] && [[ -n "${sops_pubkey:-}" ]]; then
        if [[ "$derived_pubkey" == "$sops_pubkey" ]]; then
            pass "Age key pair matches: private key -> public key in .sops.yaml"
        else
            fail "Key mismatch: private key derives ${derived_pubkey} but .sops.yaml has ${sops_pubkey}"
        fi
    fi
else
    fail ".sops.yaml not found in repo root"
fi
echo ""

# --- Check 5: Encrypted files ---
echo "5. Encrypted Files"
enc_files=$(find . -maxdepth 2 -name "*.env.enc" -o -name "*.env.secrets.enc" 2>/dev/null | sort)
if [[ -n "$enc_files" ]]; then
    while IFS= read -r enc_file; do
        if grep -q "^sops_" "$enc_file" 2>/dev/null; then
            pass "${enc_file} has SOPS metadata"

            # Try decrypting
            if command -v sops &>/dev/null && [[ -f "$AGE_KEY_PATH" ]]; then
                if sops -d --input-type dotenv --output-type dotenv "$enc_file" >/dev/null 2>&1; then
                    pass "${enc_file} decrypts successfully"
                else
                    fail "${enc_file} failed to decrypt"
                fi
            fi
        else
            warn "${enc_file} exists but has no SOPS metadata — may not be properly encrypted"
        fi
    done <<< "$enc_files"
else
    info "No encrypted files found (*.env.enc, *.env.secrets.enc)"
fi
echo ""

# --- Check 6: .gitattributes ---
echo "6. Git Configuration"
if [[ -f ".gitattributes" ]]; then
    if grep -q "sopsdiffer" ".gitattributes"; then
        pass ".gitattributes has SOPS diff driver configured"
    else
        warn ".gitattributes exists but missing SOPS diff driver"
    fi
else
    warn "No .gitattributes — encrypted files will show binary diffs"
fi

# Check if sopsdiffer is configured in git
if git config diff.sopsdiffer.textconv &>/dev/null 2>&1; then
    pass "Git diff.sopsdiffer.textconv is configured"
else
    warn "Git diff.sopsdiffer.textconv not configured. Run: git config diff.sopsdiffer.textconv 'sops -d'"
fi
echo ""

# --- Summary ---
echo "============================================="
echo " Summary"
echo "============================================="
echo -e "  ${GREEN}Passed${NC}: ${pass_count}"
echo -e "  ${RED}Failed${NC}: ${fail_count}"
echo -e "  ${YELLOW}Warnings${NC}: ${warn_count}"
echo ""

if [[ $fail_count -gt 0 ]]; then
    echo -e "${RED}Setup has failures that must be resolved.${NC}"
    exit 1
elif [[ $warn_count -gt 0 ]]; then
    echo -e "${YELLOW}Setup is functional but has warnings to address.${NC}"
    exit 0
else
    echo -e "${GREEN}Setup is fully verified.${NC}"
    exit 0
fi
