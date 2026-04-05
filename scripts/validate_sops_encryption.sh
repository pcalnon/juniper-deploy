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

    # SOPS-encrypted files must contain the "sops" metadata key.
    # Supported formats:
    #   - YAML/JSON: top-level "sops" key (e.g., "sops:", '"sops":' or '"sops"={')
    #   - dotenv: SOPS appends metadata lines prefixed with "sops_" (e.g., sops_version, sops_mac)
    if grep -qE '^\s*"?sops"?\s*[:={]|^sops_' "$file"; then
        return 0
    fi

    echo "ERROR: $file does not contain valid SOPS metadata."
    echo "       Encrypt with: sops --encrypt --in-place $file"
    EXIT_CODE=1
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
