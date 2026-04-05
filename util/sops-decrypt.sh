#!/usr/bin/env bash
# =============================================================================
# sops-decrypt.sh — Decrypt a SOPS-encrypted dotenv file
#
# Project: Juniper Ecosystem
# Author: Paul Calnon
# License: MIT
#
# Usage: bash util/sops-decrypt.sh <encrypted-file> [output-file]
#
# If output-file is omitted, strips the .enc suffix
# (e.g., .env.enc -> .env, .env.secrets.enc -> .env.secrets)
#
# The script:
#   1. Validates the encrypted file exists and has SOPS metadata
#   2. Decrypts using SOPS with dotenv format
#   3. Sets output file permissions to 600
# =============================================================================

set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
NC='\033[0m'

# --- Arguments ---
if [[ $# -lt 1 ]]; then
    echo "Usage: bash util/sops-decrypt.sh <encrypted-file> [output-file]"
    echo ""
    echo "Examples:"
    echo "  bash util/sops-decrypt.sh .env.enc"
    echo "  bash util/sops-decrypt.sh .env.enc .env"
    echo "  bash util/sops-decrypt.sh .env.secrets.enc .env.secrets"
    exit 1
fi

INPUT_FILE="$1"

# Derive output file by stripping .enc suffix
if [[ $# -ge 2 ]]; then
    OUTPUT_FILE="$2"
else
    OUTPUT_FILE="${INPUT_FILE%.enc}"
    if [[ "$OUTPUT_FILE" == "$INPUT_FILE" ]]; then
        echo -e "${RED}ERROR${NC}: Cannot derive output filename — input doesn't end in .enc"
        echo "  Specify output file explicitly: bash util/sops-decrypt.sh ${INPUT_FILE} <output-file>"
        exit 1
    fi
fi

# --- Validations ---
if [[ ! -f "$INPUT_FILE" ]]; then
    echo -e "${RED}ERROR${NC}: Encrypted file not found: ${INPUT_FILE}"
    exit 1
fi

if ! grep -q "^sops_" "$INPUT_FILE" 2>/dev/null; then
    echo -e "${RED}ERROR${NC}: File does not appear to be SOPS-encrypted (no sops_ metadata): ${INPUT_FILE}"
    exit 1
fi

if ! command -v sops &>/dev/null; then
    echo -e "${RED}ERROR${NC}: sops is not installed"
    exit 1
fi

# --- Safety check: don't overwrite without confirmation ---
if [[ -f "$OUTPUT_FILE" ]]; then
    echo -e "${YELLOW}WARNING${NC}: Output file already exists: ${OUTPUT_FILE}"
    read -r -p "Overwrite? [y/N] " response
    if [[ ! "$response" =~ ^[Yy]$ ]]; then
        echo "Aborted."
        exit 0
    fi
fi

# --- Decrypt ---
echo "Decrypting: ${INPUT_FILE} -> ${OUTPUT_FILE}"

if sops -d --input-type dotenv --output-type dotenv "$INPUT_FILE" > "${OUTPUT_FILE}.tmp"; then
    mv "${OUTPUT_FILE}.tmp" "$OUTPUT_FILE"
    chmod 600 "$OUTPUT_FILE"
else
    rm -f "${OUTPUT_FILE}.tmp"
    echo -e "${RED}ERROR${NC}: SOPS decryption failed"
    echo "  Check that your age key at ~/.config/sops/age/keys.txt matches the encryption key."
    exit 1
fi

echo -e "${GREEN}Done${NC}: ${OUTPUT_FILE} (permissions: 600, $(wc -l < "$OUTPUT_FILE") lines)"
