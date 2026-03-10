#!/usr/bin/env bash
# =============================================================================
# sops-validate.sh — Validate a SOPS-encrypted file
#
# Project: Juniper Ecosystem
# Author: Paul Calnon
# License: MIT
#
# Usage: bash util/sops-validate.sh <encrypted-file> [encrypted-file2 ...]
#
# Checks:
#   1. File exists and is non-empty
#   2. File contains SOPS metadata (sops_ prefix keys)
#   3. File can be successfully decrypted
#   4. Reports encryption metadata (age recipient, SOPS version)
# =============================================================================

set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
BLUE='\033[0;34m'
NC='\033[0m'

if [[ $# -lt 1 ]]; then
    echo "Usage: bash util/sops-validate.sh <encrypted-file> [encrypted-file2 ...]"
    echo ""
    echo "Examples:"
    echo "  bash util/sops-validate.sh .env.enc"
    echo "  bash util/sops-validate.sh .env.enc .env.secrets.enc"
    exit 1
fi

if ! command -v sops &>/dev/null; then
    echo -e "${RED}ERROR${NC}: sops is not installed"
    exit 1
fi

exit_code=0

for file in "$@"; do
    echo "Validating: ${file}"

    # Check existence
    if [[ ! -f "$file" ]]; then
        echo -e "  ${RED}FAIL${NC}  File not found"
        exit_code=1
        echo ""
        continue
    fi

    # Check non-empty
    if [[ ! -s "$file" ]]; then
        echo -e "  ${RED}FAIL${NC}  File is empty"
        exit_code=1
        echo ""
        continue
    fi

    # Check SOPS metadata
    if grep -q "^sops_" "$file" 2>/dev/null; then
        echo -e "  ${GREEN}PASS${NC}  Has SOPS metadata"
    else
        echo -e "  ${RED}FAIL${NC}  Missing SOPS metadata (sops_ prefix keys not found)"
        exit_code=1
        echo ""
        continue
    fi

    # Extract metadata
    sops_version=$(grep "^sops_version=" "$file" 2>/dev/null | cut -d'=' -f2 || echo "unknown")
    sops_age_recipient=$(grep "^sops_age__list_0__map_recipient=" "$file" 2>/dev/null | cut -d'=' -f2 || echo "unknown")
    sops_lastmodified=$(grep "^sops_lastmodified=" "$file" 2>/dev/null | cut -d'=' -f2 || echo "unknown")

    echo -e "  ${BLUE}INFO${NC}  SOPS version: ${sops_version}"
    echo -e "  ${BLUE}INFO${NC}  Age recipient: ${sops_age_recipient}"
    echo -e "  ${BLUE}INFO${NC}  Last modified: ${sops_lastmodified}"

    # Try decrypting
    if sops -d --input-type dotenv --output-type dotenv "$file" >/dev/null 2>&1; then
        echo -e "  ${GREEN}PASS${NC}  Decryption successful"

        # Count encrypted vs plaintext lines
        total_lines=$(wc -l < "$file")
        metadata_lines=$(grep -c "^sops_" "$file" 2>/dev/null || echo "0")
        echo -e "  ${BLUE}INFO${NC}  Total lines: ${total_lines}, Metadata lines: ${metadata_lines}"
    else
        echo -e "  ${RED}FAIL${NC}  Decryption failed — check age key"
        exit_code=1
    fi

    echo ""
done

if [[ $exit_code -eq 0 ]]; then
    echo -e "${GREEN}All files validated successfully.${NC}"
else
    echo -e "${RED}Some files failed validation.${NC}"
fi

exit $exit_code
