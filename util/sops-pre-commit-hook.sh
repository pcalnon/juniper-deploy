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

    # Allow encrypted files only if they have SOPS metadata
    case "$basename" in
        *.env.enc|*.env.secrets.enc)
            if grep -q "^sops_" "$file" 2>/dev/null; then
                continue
            else
                echo "ERROR: ${file} is named as encrypted but has no SOPS metadata."
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
