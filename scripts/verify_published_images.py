#!/usr/bin/env python3
#####################################################################################################################################################################################################
# Project:       Juniper
# Application:   juniper-deploy
# File Name:     verify_published_images.py
# Author:        Paul Calnon
#
# Date Created:  2026-09-15
#
# License:       MIT License
# Copyright:     Copyright (c) 2024-2026 Paul Calnon
#
# Description:
#    Container-registry plan D-1: juniper-deploy is the natural home for a check
#    that the images it PINS are actually published -- "a stronger check than
#    building from ../sibling paths".
#
#    Reads every Juniper ``image:`` ref out of docker-compose.yml and verifies,
#    against the registry itself, that each one exists and carries BOTH
#    architectures the plan's D-4 commits to (linux/amd64 + linux/arm64).
#
#    The failure this exists to catch: docker-compose.yml names a release ref
#    that was never published, or was published single-arch. Compose reports
#    that as a pull failure at `up` time, on the host that needed it, which is
#    the worst possible place to find out. A manifest query answers it in
#    milliseconds and needs no credentials -- all five packages are public.
#
#    A single-arch manifest is a REAL failure mode, not a hypothetical: both
#    arch jobs push by digest and only the merge job applies tags, so a lost
#    race would leave a single-arch image wearing a multi-arch tag -- which
#    fails only on the host that needs the missing arch (a Pi).
#
# Usage:
#    python3 scripts/verify_published_images.py                    # verify the shipped compose
#    python3 scripts/verify_published_images.py --list-only        # print refs, no network
#    python3 scripts/verify_published_images.py --compose FILE     # a different compose file
#    python3 scripts/verify_published_images.py --expect-count 9   # pin the site count
#
# Exit status:
#    0  every Juniper image ref resolves and lists amd64 + arm64
#    1  at least one ref is missing, single-arch, or unreadable
#    2  usage error, unreadable compose, or ZERO Juniper refs found
#
#####################################################################################################################################################################################################

from __future__ import annotations

import argparse
import json
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_COMPOSE = REPO_ROOT / "docker-compose.yml"

# Only refs under this namespace are ours to verify. Third-party pins in the same
# file (prom/prometheus, grafana/grafana, redis) are deliberately out of scope.
JUNIPER_NS = "ghcr.io/pcalnon/"

REQUIRED_ARCHES = {"amd64", "arm64"}

INDEX_TYPES = (
    "application/vnd.oci.image.index.v1+json",
    "application/vnd.docker.distribution.manifest.list.v2+json",
)

# ghcr.io/pcalnon/<name>:<X.Y.Z>  -- a bare name, a :latest, or a floating :X.Y
# is a REGRESSION of the Wave 3 pin, not merely a style question, so the shape is
# asserted rather than assumed.
PINNED_RE = re.compile(r"^ghcr\.io/pcalnon/[a-z0-9][a-z0-9._-]*:\d+\.\d+\.\d+$")


def compose_image_refs(compose_path: Path) -> list[tuple[str, str]]:
    """Return [(service, image_ref), ...] for every Juniper-namespaced image."""
    try:
        doc = yaml.safe_load(compose_path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        print(f"verify-images: cannot read {compose_path}: {exc}", file=sys.stderr)
        raise SystemExit(2) from None

    found = []
    for name, svc in ((doc or {}).get("services") or {}).items():
        if not isinstance(svc, dict):
            continue
        image = svc.get("image")
        if isinstance(image, str) and image.startswith(JUNIPER_NS):
            found.append((name, image))
    return sorted(found)


def _get(url: str, token: str | None = None, accept: str | None = None, attempts: int = 3):
    """GET with a retry on TRANSIENT failures only.

    A 404 is a real answer -- the tag is not published -- and is re-raised
    immediately; retrying it would only slow the failure down. Timeouts, resets
    and 5xx are retried, because they say nothing about the tag. Observed
    2026-09-15: an anonymous ghcr.io token request timed out once in five, and a
    hard-failing gate that flakes one run in five is a gate people learn to
    re-run rather than read.
    """
    req = urllib.request.Request(url)
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    if accept:
        req.add_header("Accept", accept)

    last: Exception | None = None
    for attempt in range(attempts):
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:  # noqa: S310 - fixed https host
                return json.load(resp)
        except urllib.error.HTTPError as exc:
            if exc.code < 500:
                raise  # 404 and friends are answers, not failures to retry
            last = exc
        except (urllib.error.URLError, TimeoutError, ValueError) as exc:
            last = exc
        if attempt < attempts - 1:
            time.sleep(2 ** attempt)
    raise last if last else RuntimeError("unreachable")


def manifest_arches(ref: str) -> tuple[bool, str]:
    """(ok, detail) for one ghcr.io/<owner>/<name>:<tag> reference."""
    repo, _, tag = ref[len("ghcr.io/") :].rpartition(":")
    try:
        token = _get(
            f"https://ghcr.io/token?scope=repository:{repo}:pull&service=ghcr.io"
        )["token"]
    except (urllib.error.URLError, KeyError, ValueError) as exc:
        return False, f"could not obtain a pull token: {exc}"

    try:
        index = _get(
            f"https://ghcr.io/v2/{repo}/manifests/{tag}", token, ", ".join(INDEX_TYPES)
        )
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return False, "MANIFEST NOT FOUND — this tag was never published"
        return False, f"HTTP {exc.code} reading the manifest"
    except (urllib.error.URLError, ValueError) as exc:
        return False, f"could not read the manifest: {exc}"

    entries = index.get("manifests")
    if not entries:
        return False, "no manifest list — single-arch image wearing a multi-arch tag"

    arches = {
        m.get("platform", {}).get("architecture")
        for m in entries
        if m.get("platform", {}).get("architecture") not in (None, "unknown")
    }
    missing = REQUIRED_ARCHES - arches
    if missing:
        return False, f"missing {sorted(missing)} (has {sorted(arches)})"
    return True, f"arches={','.join(sorted(arches))}"


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Verify juniper-deploy's pinned image refs are published multi-arch."
    )
    ap.add_argument("--compose", type=Path, default=DEFAULT_COMPOSE)
    ap.add_argument(
        "--list-only",
        action="store_true",
        help="print the refs that would be checked and exit (no network)",
    )
    ap.add_argument(
        "--expect-count",
        type=int,
        default=None,
        help="fail unless exactly this many Juniper image sites are found",
    )
    args = ap.parse_args()

    sites = compose_image_refs(args.compose)

    # Anti-vacuous guard. A parser that silently matches nothing would otherwise
    # report success for a compose file with every pin reverted to :latest.
    if not sites:
        print(
            f"verify-images: ZERO images under {JUNIPER_NS} in {args.compose} — "
            "either the Wave 3 pin was reverted or this parser is broken. "
            "Refusing to report success.",
            file=sys.stderr,
        )
        return 2

    if args.expect_count is not None and len(sites) != args.expect_count:
        print(
            f"verify-images: expected {args.expect_count} Juniper image sites, found "
            f"{len(sites)}: {[s for s, _ in sites]}",
            file=sys.stderr,
        )
        return 2

    unique = sorted({ref for _, ref in sites})
    print(f"  {len(sites)} Juniper image sites, {len(unique)} unique refs\n")

    if args.list_only:
        for service, ref in sites:
            print(f"  {service:24} {ref}")
        return 0

    failed = []
    for ref in unique:
        used_by = [s for s, r in sites if r == ref]
        if not PINNED_RE.match(ref):
            print(f"  FAIL  {ref}\n          not an X.Y.Z release pin (used by {used_by})")
            failed.append(ref)
            continue
        ok, detail = manifest_arches(ref)
        print(f"  {'OK  ' if ok else 'FAIL'}  {ref}\n          {detail}  (used by {used_by})")
        if not ok:
            failed.append(ref)

    print()
    if failed:
        print(f"  {len(failed)} of {len(unique)} refs failed: {failed}", file=sys.stderr)
        return 1
    print(f"  all {len(unique)} published refs resolve with {sorted(REQUIRED_ARCHES)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
