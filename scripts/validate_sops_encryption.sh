#!/usr/bin/env bash
#####################################################################################################################################################################################################
# Project:       Juniper
# File Name:     validate_sops_encryption.sh
# Author:        Juniper Automation
#
# License:       MIT License
# Copyright:     Copyright (c) 2024-2026 Paul Calnon
#
# Description:
#    Validates that files with .enc extension contain valid SOPS metadata.
#    Used as a pre-commit hook and in CI to prevent committing unencrypted
#    files disguised with an .enc extension.
#
# Usage:
#    bash scripts/validate_sops_encryption.sh [file1] [file2] ...
#    # Without arguments, scans for *.env.enc and *.env.secrets.enc in repo root
#
#####################################################################################################################################################################################################

set -euo pipefail

EXIT_CODE=0

validate_sops_file() {
    local file="$1"

    if [[ ! -f "$file" ]]; then
        return 0
    fi

    # Require multiple SOPS metadata fields (not just one prefix match).
    # A single "sops_" prefix is trivially spoofed — require all three.
    local sops_fields_found=0
    grep -q "^sops_version=" "$file" 2>/dev/null && sops_fields_found=$((sops_fields_found + 1))
    grep -q "^sops_lastmodified=" "$file" 2>/dev/null && sops_fields_found=$((sops_fields_found + 1))
    grep -q "^sops_age__" "$file" 2>/dev/null && sops_fields_found=$((sops_fields_found + 1))

    if [[ $sops_fields_found -lt 3 ]]; then
        echo "ERROR: $file has insufficient SOPS metadata (${sops_fields_found}/3 required fields)."
        echo "       Encrypt with: sops --encrypt --in-place $file"
        EXIT_CODE=1
        return
    fi

    # Verify all non-metadata, non-comment lines contain ENC[AES256_GCM,...] values
    local plaintext_lines
    plaintext_lines=$(grep -v "^#" "$file" | grep -v "^sops_" | grep -v "^$" | grep -cv "ENC\[AES256_GCM," 2>/dev/null) || plaintext_lines=0
    if [[ "$plaintext_lines" -gt 0 ]]; then
        echo "ERROR: $file contains ${plaintext_lines} non-encrypted value(s)."
        echo "       All values must use SOPS encryption."
        echo "       Re-encrypt with: sops -e -i $file"
        EXIT_CODE=1
        return
    fi
}

if [[ $# -gt 0 ]]; then
    # Validate specific files passed as arguments
    for file in "$@"; do
        validate_sops_file "$file"
    done
else
    # Scan for encrypted env files in repo root
    REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
    for file in "$REPO_ROOT"/.env.enc "$REPO_ROOT"/.env.secrets.enc; do
        validate_sops_file "$file"
    done
fi

exit $EXIT_CODE
