#!/usr/bin/env bash
# =============================================================================
# sops-pre-commit-hook.sh — SOPS-aware pre-commit hook
#
# Project: Juniper Ecosystem
# Author: Paul Calnon
# License: MIT
#
# Called by pre-commit for any staged .env* files. Allows safe files through
# and blocks unencrypted sensitive files.
#
# Allowed (pass-through):
#   - .env.example, .env.secrets.example (templates)
#   - .env.demo, .env.test (non-sensitive configs)
#   - .env.enc, .env.secrets.enc (SOPS-encrypted — verified by metadata check)
#
# Blocked:
#   - .env, .env.secrets (unencrypted sensitive files)
#   - .env.enc / .env.secrets.enc without valid SOPS metadata
# =============================================================================

set -euo pipefail

exit_code=0

for file in "$@"; do
    basename=$(basename "$file")

    # Allow template and non-sensitive files
    case "$basename" in
        .env.example|.env.secrets.example|.env.demo|.env.test)
            continue
            ;;
    esac

    # Allow encrypted files only if they have valid SOPS metadata
    case "$basename" in
        *.env.enc|*.env.secrets.enc)
            # Require multiple SOPS metadata fields (not just one prefix match)
            sops_fields_found=0
            grep -q "^sops_version=" "$file" 2>/dev/null && sops_fields_found=$((sops_fields_found + 1))
            grep -q "^sops_lastmodified=" "$file" 2>/dev/null && sops_fields_found=$((sops_fields_found + 1))
            grep -q "^sops_age__" "$file" 2>/dev/null && sops_fields_found=$((sops_fields_found + 1))

            if [[ $sops_fields_found -ge 3 ]]; then
                # Verify all non-metadata, non-comment lines contain ENC[AES256_GCM,...] values
                plaintext_lines=$(grep -v "^#" "$file" | grep -v "^sops_" | grep -v "^$" | grep -cv "ENC\[AES256_GCM," 2>/dev/null) || plaintext_lines=0
                if [[ "$plaintext_lines" -gt 0 ]]; then
                    echo "ERROR: ${file} contains ${plaintext_lines} non-encrypted value(s)."
                    echo "  All values in encrypted files must use SOPS encryption."
                    echo "  Re-encrypt with: sops -e -i ${file}"
                    exit_code=1
                else
                    continue
                fi
            else
                echo "ERROR: ${file} is named as encrypted but has insufficient SOPS metadata."
                echo "  Found ${sops_fields_found}/3 required metadata fields."
                echo "  Encrypt it with: bash util/sops-encrypt.sh <source> ${file}"
                exit_code=1
            fi
            ;;
    esac

    # Block unencrypted .env and .env.secrets files
    case "$basename" in
        .env|.env.secrets|.env.local|.env.development|.env.production|.env.staging)
            echo "ERROR: Unencrypted secrets file detected: ${file}"
            echo "  To fix, encrypt the file before committing:"
            echo "    bash util/sops-encrypt.sh ${file} ${file}.enc"
            echo "    git add ${file}.enc"
            echo "    git reset HEAD ${file}"
            exit_code=1
            ;;
    esac
done

exit $exit_code
