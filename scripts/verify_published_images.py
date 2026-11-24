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
#    CURRENCY (added 2026-09-22) is a SEPARATE question from existence, and this
#    script used to answer only the latter. A pin can resolve perfectly, carry
#    both arches, and still be a release behind. That is not hypothetical
#    either: docker-compose.yml pinned juniper-canopy:0.8.0 for three days after
#    0.8.1 shipped, and this check ran GREEN throughout, because every ref it
#    was asked about existed. juniper-deploy#225 fixed that one drift; nothing
#    detected it.
#
#    Staleness is ADVISORY by default, and deliberately so. Failing the build
#    the instant any upstream release lands would block every unrelated PR in
#    this repo until someone bumped a pin -- turning a visibility problem into
#    an availability one. The default emits a ``::warning::`` (visible on the
#    run and in the PR) and still exits 0; ``--fail-on-stale`` is for a
#    scheduled job that SHOULD page.
#
# Usage:
#    python3 scripts/verify_published_images.py                    # verify the shipped compose
#    python3 scripts/verify_published_images.py --list-only        # print refs, no network
#    python3 scripts/verify_published_images.py --compose FILE     # a different compose file
#    python3 scripts/verify_published_images.py --expect-count 9   # pin the site count
#    python3 scripts/verify_published_images.py --fail-on-stale    # currency is an ERROR
#    python3 scripts/verify_published_images.py --no-currency      # skip the tag-list query
#
# Exit status:
#    0  every Juniper image ref resolves and lists amd64 + arm64
#    1  at least one ref is missing, single-arch, or unreadable
#       (or, with --fail-on-stale, at least one pin is behind its latest release)
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


def _semver(tag: str) -> tuple[int, int, int] | None:
    """(major, minor, patch) for an X.Y.Z tag, else None.

    Compared as a TUPLE OF INTS, never as a string: `"0.10.0" < "0.9.0"` is true
    lexicographically and false in every sense that matters here.
    """
    parts = tag.split(".")
    if len(parts) != 3:
        return None
    try:
        return tuple(int(p) for p in parts)  # type: ignore[return-value]
    except ValueError:
        return None


def latest_published(repo: str) -> tuple[tuple[int, int, int] | None, str]:
    """Highest X.Y.Z tag published for ``repo``, from the registry's own tag list.

    The registry is the authority here, not the GitHub Releases API: a Release can
    exist whose image publish failed, and the question this answers is "what could
    this compose file pull today".
    """
    try:
        token = _get(
            f"https://ghcr.io/token?scope=repository:{repo}:pull&service=ghcr.io"
        )["token"]
        body = _get(f"https://ghcr.io/v2/{repo}/tags/list", token)
    except urllib.error.HTTPError as exc:
        return None, f"HTTP {exc.code} reading the tag list"
    except (urllib.error.URLError, KeyError, ValueError) as exc:
        return None, f"could not read the tag list: {exc}"

    versions = [v for v in (_semver(tag) for tag in (body.get("tags") or [])) if v]
    if not versions:
        return None, "no X.Y.Z tags published"
    best = max(versions)
    return best, ".".join(str(n) for n in best)


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
    ap.add_argument(
        "--fail-on-stale",
        action="store_true",
        help="exit 1 when a pin is behind its latest published release (default: warn only)",
    )
    ap.add_argument(
        "--no-currency",
        action="store_true",
        help="skip the currency check entirely (existence + arch only, the pre-2026-09-22 behaviour)",
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

    failed: list[str] = []
    stale: list[tuple[str, str]] = []
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
            continue

        if args.no_currency:
            continue

        repo, _, tag = ref[len("ghcr.io/") :].rpartition(":")
        pinned = _semver(tag)
        newest, newest_detail = latest_published(repo)
        if pinned is None or newest is None:
            print(f"          currency: not determined — {newest_detail}")
        elif newest > pinned:
            stale.append((ref, newest_detail))
            print(
                f"          ::warning::STALE PIN — {newest_detail} is published, "
                f"this pins {tag}"
            )
        else:
            print(f"          currency: current (latest published is {newest_detail})")

    print()
    if failed:
        print(f"  {len(failed)} of {len(unique)} refs failed: {failed}", file=sys.stderr)
        return 1

    print(f"  all {len(unique)} published refs resolve with {sorted(REQUIRED_ARCHES)}")

    if stale:
        print()
        print(f"  {len(stale)} of {len(unique)} pins are BEHIND their latest release:")
        for ref, newest_detail in stale:
            print(f"      {ref}  ->  {newest_detail} available")
        # Existence and currency are different questions with different blast radii.
        # A missing ref breaks `up` for everyone; a stale one ships an older but
        # working stack. Only the former should turn this red by default.
        if args.fail_on_stale:
            print("  --fail-on-stale given: treating staleness as an error", file=sys.stderr)
            return 1
        print("  (advisory — pass --fail-on-stale to make this an error)")

    return 0


if __name__ == "__main__":
    sys.exit(main())
