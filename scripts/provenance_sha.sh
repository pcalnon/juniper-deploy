#!/usr/bin/env bash
#####################################################################################################################################################################################################
# Project:       Juniper
# Application:   juniper-deploy
# File Name:     provenance_sha.sh
# Author:        Paul Calnon
#
# License:       MIT License
# Copyright:     Copyright (c) 2024-2026 Paul Calnon
#
# Description:
#    Print the short git SHA for the repo at $1, suffixed with ``-dirty`` when
#    its working tree has uncommitted *tracked* changes. Untracked files (build
#    artifacts, .env, data/, __pycache__) are deliberately ignored
#    (``--untracked-files=no``) so they don't spuriously mark every developer
#    build dirty — only uncommitted committed-file edits count. Prints an empty
#    string when $1 is not a git repo (→ the image is stamped with empty
#    provenance → ``make doctor`` reports UNKNOWN, "rebuild").
#
#    Used by the deploy Makefile's PROVENANCE_ENV to stamp build provenance so
#    ``make doctor`` / ``make health`` can flag an image built from uncommitted
#    code as DIRTY rather than FRESH (OQ-2; see juniper-ml
#    notes/BUILD_PROVENANCE_DESIGN_2026-06-14.md).
#
# Usage:
#    scripts/provenance_sha.sh <repo-dir>
#
#####################################################################################################################################################################################################

set -uo pipefail

dir="${1:?usage: provenance_sha.sh <repo-dir>}"

# Short HEAD SHA; empty (exit 0) when not a git repo so a missing sibling maps
# to empty provenance rather than aborting the whole `make build`.
sha="$(git -C "$dir" rev-parse --short HEAD 2>/dev/null)" || exit 0
[[ -z "$sha" ]] && exit 0

# Tracked-only dirty check: uncommitted edits to committed files mean the image
# would contain code that is in no commit. Untracked files are excluded.
if [[ -n "$(git -C "$dir" status --porcelain --untracked-files=no 2>/dev/null)" ]]; then
    sha="${sha}-dirty"
fi

printf '%s' "$sha"
