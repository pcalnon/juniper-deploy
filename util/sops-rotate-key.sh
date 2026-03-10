#!/usr/bin/env bash
# =============================================================================
# sops-rotate-key.sh — Rotate the age encryption key
#
# Project: Juniper Ecosystem
# Author: Paul Calnon
# License: MIT
#
# Usage: bash util/sops-rotate-key.sh [--dry-run]
#
# This script:
#   1. Generates a new age key pair
#   2. Finds all .env.enc and .env.secrets.enc files in the repo
#   3. Re-encrypts each file with both old and new keys (transition period)
#   4. Updates .sops.yaml with the new public key
#   5. Outputs the new key for secure distribution
#
# IMPORTANT: After rotation, you must:
#   - Distribute the new age private key to all team members (securely)
#   - Update .sops.yaml in ALL 8 Juniper repos
#   - Re-encrypt files in other repos that have .env.enc files
#   - Back up the new key (see util/sops-backup-key.sh)
# =============================================================================

set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
BLUE='\033[0;34m'
NC='\033[0m'

DRY_RUN="${1:-}"
AGE_KEY_PATH="${SOPS_AGE_KEY_FILE:-${HOME}/.config/sops/age/keys.txt}"
SOPS_YAML=".sops.yaml"

# --- Preflight checks ---
if ! command -v sops &>/dev/null; then
    echo -e "${RED}ERROR${NC}: sops is not installed"
    exit 1
fi

if ! command -v age-keygen &>/dev/null; then
    echo -e "${RED}ERROR${NC}: age-keygen is not installed"
    exit 1
fi

if [[ ! -f "$AGE_KEY_PATH" ]]; then
    echo -e "${RED}ERROR${NC}: Current age key not found at ${AGE_KEY_PATH}"
    exit 1
fi

if [[ ! -f "$SOPS_YAML" ]]; then
    echo -e "${RED}ERROR${NC}: ${SOPS_YAML} not found in current directory"
    exit 1
fi

# --- Get current key info ---
current_pubkey=$(grep -oP 'age: "?\K[^"]+' "$SOPS_YAML" | head -1)
echo "============================================="
echo " SOPS Key Rotation — Juniper Ecosystem"
echo "============================================="
echo ""
echo -e "${BLUE}Current public key${NC}: ${current_pubkey}"
echo ""

# --- Generate new key ---
echo "Generating new age key pair..."
NEW_KEY_OUTPUT=$(age-keygen 2>&1)
new_pubkey=$(echo "$NEW_KEY_OUTPUT" | grep "^public key:" | awk '{print $3}')
new_secret=$(echo "$NEW_KEY_OUTPUT" | grep "^AGE-SECRET-KEY-")

if [[ -z "$new_pubkey" ]] || [[ -z "$new_secret" ]]; then
    echo -e "${RED}ERROR${NC}: Failed to generate new age key"
    exit 1
fi

echo -e "${GREEN}New public key${NC}: ${new_pubkey}"
echo ""

if [[ "$DRY_RUN" == "--dry-run" ]]; then
    echo -e "${YELLOW}DRY RUN${NC} — no changes will be made"
    echo ""
fi

# --- Find encrypted files ---
enc_files=$(find . -maxdepth 2 -name "*.env.enc" -o -name "*.env.secrets.enc" 2>/dev/null | sort)

if [[ -n "$enc_files" ]]; then
    echo "Encrypted files to re-encrypt:"
    echo "$enc_files" | while IFS= read -r f; do echo "  $f"; done
    echo ""
else
    echo "No encrypted files found in this repo."
    echo ""
fi

if [[ "$DRY_RUN" == "--dry-run" ]]; then
    echo "Would update:"
    echo "  1. ${SOPS_YAML} — replace age public key"
    echo "  2. ${AGE_KEY_PATH} — append new private key"
    if [[ -n "$enc_files" ]]; then
        echo "  3. Re-encrypt all files listed above with new key"
    fi
    echo ""
    echo -e "${YELLOW}Run without --dry-run to execute.${NC}"
    exit 0
fi

# --- Confirm ---
echo -e "${YELLOW}WARNING${NC}: This will:"
echo "  1. Update ${SOPS_YAML} with the new public key"
echo "  2. Append the new private key to ${AGE_KEY_PATH}"
echo "  3. Re-encrypt all encrypted files with the new key"
echo ""
read -r -p "Proceed with key rotation? [y/N] " response
if [[ ! "$response" =~ ^[Yy]$ ]]; then
    echo "Aborted."
    exit 0
fi

# --- Back up current key ---
backup_path="${AGE_KEY_PATH}.bak.$(date +%Y%m%d-%H%M%S)"
cp "$AGE_KEY_PATH" "$backup_path"
chmod 600 "$backup_path"
echo -e "${BLUE}Backed up current key to${NC}: ${backup_path}"

# --- Append new key to keyfile (keep old key for decrypting existing files) ---
echo "" >> "$AGE_KEY_PATH"
echo "# Rotated key — $(date -Iseconds)" >> "$AGE_KEY_PATH"
echo "$new_secret" >> "$AGE_KEY_PATH"
chmod 600 "$AGE_KEY_PATH"
echo -e "${GREEN}Appended new key to${NC}: ${AGE_KEY_PATH}"

# --- Update .sops.yaml ---
sed -i "s|${current_pubkey}|${new_pubkey}|g" "$SOPS_YAML"
echo -e "${GREEN}Updated${NC}: ${SOPS_YAML}"

# --- Re-encrypt files ---
if [[ -n "$enc_files" ]]; then
    echo ""
    echo "Re-encrypting files..."
    while IFS= read -r enc_file; do
        echo -n "  ${enc_file}... "
        # Decrypt with old key, re-encrypt with new key
        tmpfile=$(mktemp)
        if sops -d --input-type dotenv --output-type dotenv "$enc_file" > "$tmpfile" 2>/dev/null; then
            if sops -e --input-type dotenv --output-type dotenv "$tmpfile" > "${enc_file}.new" 2>/dev/null; then
                mv "${enc_file}.new" "$enc_file"
                echo -e "${GREEN}OK${NC}"
            else
                rm -f "${enc_file}.new"
                echo -e "${RED}FAILED to re-encrypt${NC}"
            fi
        else
            echo -e "${RED}FAILED to decrypt${NC}"
        fi
        rm -f "$tmpfile"
    done <<< "$enc_files"
fi

echo ""
echo "============================================="
echo " Rotation Complete"
echo "============================================="
echo ""
echo -e "${GREEN}New public key${NC}: ${new_pubkey}"
echo ""
echo -e "${YELLOW}Remaining steps${NC}:"
echo "  1. Distribute the new age private key to all team members (securely)"
echo "  2. Update .sops.yaml in ALL other Juniper repos with the new public key:"
echo "     sed -i 's|${current_pubkey}|${new_pubkey}|g' .sops.yaml"
echo "  3. Re-encrypt .env.enc files in other repos:"
echo "     sops -d --input-type dotenv --output-type dotenv .env.enc | \\"
echo "       sops -e --input-type dotenv --output-type dotenv /dev/stdin > .env.enc.new"
echo "     mv .env.enc.new .env.enc"
echo "  4. Back up the new key: bash util/sops-backup-key.sh"
echo "  5. Commit changes in all affected repos"
