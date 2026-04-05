#!/usr/bin/env bash
# =============================================================================
# sops-encrypt.sh — Encrypt a dotenv file with SOPS
#
# Project: Juniper Ecosystem
# Author: Paul Calnon
# License: MIT
#
# Usage: bash util/sops-encrypt.sh <input-file> [output-file]
#
# If output-file is omitted, defaults to <input-file>.enc
# (e.g., .env -> .env.enc, .env.secrets -> .env.secrets.enc)
#
# The script:
#   1. Validates the input file exists and is not already encrypted
#   2. Encrypts using SOPS with dotenv format
#   3. Validates the output has SOPS metadata
#   4. Verifies round-trip (decrypt and compare)
# =============================================================================

set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
NC='\033[0m'

# --- Arguments ---
if [[ $# -lt 1 ]]; then
    echo "Usage: bash util/sops-encrypt.sh <input-file> [output-file]"
    echo ""
    echo "Examples:"
    echo "  bash util/sops-encrypt.sh .env"
    echo "  bash util/sops-encrypt.sh .env .env.enc"
    echo "  bash util/sops-encrypt.sh .env.secrets .env.secrets.enc"
    exit 1
fi

INPUT_FILE="$1"
OUTPUT_FILE="${2:-${INPUT_FILE}.enc}"

# --- Validations ---
if [[ ! -f "$INPUT_FILE" ]]; then
    echo -e "${RED}ERROR${NC}: Input file not found: ${INPUT_FILE}"
    exit 1
fi

if [[ ! -s "$INPUT_FILE" ]]; then
    echo -e "${RED}ERROR${NC}: Input file is empty: ${INPUT_FILE}"
    exit 1
fi

# Check if input is already SOPS-encrypted
if grep -q "^sops_" "$INPUT_FILE" 2>/dev/null; then
    echo -e "${YELLOW}WARNING${NC}: Input file appears to already be SOPS-encrypted: ${INPUT_FILE}"
    echo "  Use 'sops ${INPUT_FILE}' to edit in-place, or decrypt first."
    exit 1
fi

if ! command -v sops &>/dev/null; then
    echo -e "${RED}ERROR${NC}: sops is not installed"
    exit 1
fi

if [[ ! -f ".sops.yaml" ]]; then
    echo -e "${RED}ERROR${NC}: .sops.yaml not found in current directory"
    exit 1
fi

# --- Encrypt ---
echo "Encrypting: ${INPUT_FILE} -> ${OUTPUT_FILE}"

if sops -e --input-type dotenv --output-type dotenv "$INPUT_FILE" > "${OUTPUT_FILE}.tmp"; then
    mv "${OUTPUT_FILE}.tmp" "$OUTPUT_FILE"
else
    rm -f "${OUTPUT_FILE}.tmp"
    echo -e "${RED}ERROR${NC}: SOPS encryption failed"
    exit 1
fi

# --- Validate output ---
if ! grep -q "^sops_" "$OUTPUT_FILE" 2>/dev/null; then
    echo -e "${RED}ERROR${NC}: Output file missing SOPS metadata — encryption may have failed"
    exit 1
fi

# --- Verify round-trip ---
TMPFILE=$(mktemp)
trap 'rm -f "$TMPFILE"' EXIT

if sops -d --input-type dotenv --output-type dotenv "$OUTPUT_FILE" > "$TMPFILE" 2>/dev/null; then
    if diff -q "$INPUT_FILE" "$TMPFILE" >/dev/null 2>&1; then
        echo -e "${GREEN}OK${NC}: Encryption verified — round-trip matches"
    else
        echo -e "${YELLOW}WARNING${NC}: Round-trip diff detected (may be due to encrypted_regex formatting)"
        echo "  This is expected if encrypted_regex strips/reformats comments."
    fi
else
    echo -e "${RED}ERROR${NC}: Failed to decrypt the newly encrypted file — check your age key"
    exit 1
fi

echo -e "${GREEN}Done${NC}: ${OUTPUT_FILE} ($(wc -c < "$OUTPUT_FILE") bytes)"
