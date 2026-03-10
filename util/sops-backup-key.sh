#!/usr/bin/env bash
# =============================================================================
# sops-backup-key.sh — Create an encrypted backup of the age private key
#
# Project: Juniper Ecosystem
# Author: Paul Calnon
# License: MIT
#
# Usage: bash util/sops-backup-key.sh [backup-directory]
#
# If backup-directory is omitted, defaults to current directory.
#
# This script:
#   1. Reads the age private key from ~/.config/sops/age/keys.txt
#   2. Encrypts it with age using a passphrase (prompted interactively)
#   3. Saves the encrypted backup with a timestamped filename
#   4. Verifies the backup can be decrypted
#
# The backup file can be stored on a USB drive, in a password manager,
# or in any secure offline storage.
#
# To restore: age -d <backup-file> > ~/.config/sops/age/keys.txt
# =============================================================================

set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
BLUE='\033[0;34m'
NC='\033[0m'

AGE_KEY_PATH="${SOPS_AGE_KEY_FILE:-${HOME}/.config/sops/age/keys.txt}"
BACKUP_DIR="${1:-.}"
TIMESTAMP=$(date +%Y%m%d-%H%M%S)
BACKUP_FILE="${BACKUP_DIR}/age-key-backup-${TIMESTAMP}.age"

# --- Preflight ---
if ! command -v age &>/dev/null; then
    echo -e "${RED}ERROR${NC}: age is not installed"
    exit 1
fi

if [[ ! -f "$AGE_KEY_PATH" ]]; then
    echo -e "${RED}ERROR${NC}: Age key file not found: ${AGE_KEY_PATH}"
    exit 1
fi

if [[ ! -d "$BACKUP_DIR" ]]; then
    echo -e "${RED}ERROR${NC}: Backup directory does not exist: ${BACKUP_DIR}"
    exit 1
fi

echo "============================================="
echo " Age Key Backup — Juniper Ecosystem"
echo "============================================="
echo ""
echo -e "${BLUE}Source${NC}: ${AGE_KEY_PATH}"
echo -e "${BLUE}Destination${NC}: ${BACKUP_FILE}"
echo ""

# Show key info (public key only, never the secret)
if command -v age-keygen &>/dev/null; then
    pubkey=$(age-keygen -y "$AGE_KEY_PATH" 2>/dev/null || echo "unknown")
    echo -e "${BLUE}Public key${NC}: ${pubkey}"
    echo ""
fi

# --- Encrypt with passphrase ---
echo "You will be prompted to enter a passphrase to encrypt the backup."
echo "Choose a strong passphrase and store it separately from the backup file."
echo ""

if age -p -o "$BACKUP_FILE" "$AGE_KEY_PATH"; then
    chmod 600 "$BACKUP_FILE"
    echo ""
    echo -e "${GREEN}Backup created${NC}: ${BACKUP_FILE}"
    echo -e "${BLUE}Size${NC}: $(wc -c < "$BACKUP_FILE") bytes"
else
    echo -e "${RED}ERROR${NC}: Backup encryption failed"
    exit 1
fi

# --- Verify ---
echo ""
echo "Verifying backup (you will be prompted for the passphrase again)..."
TMPFILE=$(mktemp)
trap 'rm -f "$TMPFILE"' EXIT

if age -d -o "$TMPFILE" "$BACKUP_FILE"; then
    if diff -q "$AGE_KEY_PATH" "$TMPFILE" >/dev/null 2>&1; then
        echo -e "${GREEN}Verification passed${NC}: backup content matches original"
    else
        echo -e "${RED}ERROR${NC}: backup content does NOT match original"
        rm -f "$BACKUP_FILE"
        exit 1
    fi
else
    echo -e "${RED}ERROR${NC}: could not decrypt backup for verification"
    rm -f "$BACKUP_FILE"
    exit 1
fi

echo ""
echo "============================================="
echo " Backup Complete"
echo "============================================="
echo ""
echo "Store this file in a secure location separate from your workstation:"
echo "  ${BACKUP_FILE}"
echo ""
echo "To restore from backup:"
echo "  mkdir -p ~/.config/sops/age"
echo "  age -d ${BACKUP_FILE} > ~/.config/sops/age/keys.txt"
echo "  chmod 600 ~/.config/sops/age/keys.txt"
