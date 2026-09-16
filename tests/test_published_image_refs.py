#!/usr/bin/env python
#####################################################################################################################################################################################################
# Project:       Juniper
# Application:   juniper-deploy
# File Name:     test_published_image_refs.py
# Author:        Paul Calnon
#
# Date Created:  2026-09-15
#
# License:       MIT License
# Copyright:     Copyright (c) 2024-2026 Paul Calnon
#
# Description:
#    Container-registry Wave 3 regression: every Juniper ``image:`` in
#    docker-compose.yml must stay a PUBLISHED, fully-qualified, X.Y.Z release
#    ref. Guards the failure class where a pin quietly reverts to a bare
#    ``<name>:latest`` -- which is not a version at all but a LOCAL build-output
#    tag, so the stack silently goes back to being un-runnable on any host that
#    has not just built it.
#
#    Offline and network-free by construction: it asserts the SHAPE of the refs
#    and the parser that finds them. Whether those refs actually resolve in GHCR
#    is the job of scripts/verify_published_images.py, which needs the network
#    and runs as its own CI job.
#
#    See juniper-ml notes/JUNIPER_2026-09-05_JUNIPER-ECOSYSTEM_CONTAINER-REGISTRY-
#    PUBLISHING-PLAN.md (§5 Wave 3, D-1, D-3, D-4).
#
#####################################################################################################################################################################################################

from pathlib import Path
import re
import subprocess
import sys

import pytest
import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
COMPOSE_PATH = REPO_ROOT / "docker-compose.yml"
VERIFY_SCRIPT = REPO_ROOT / "scripts" / "verify_published_images.py"

JUNIPER_NS = "ghcr.io/pcalnon/"

# ghcr.io/pcalnon/<name>:<X.Y.Z>. A bare name, a :latest or a floating :X.Y all
# fail: D-3 publishes X.Y.Z / X.Y / latest, but only X.Y.Z names one artifact
# forever, and a deployment file must name one artifact forever.
PINNED_RE = re.compile(r"^ghcr\.io/pcalnon/[a-z0-9][a-z0-9._-]*:\d+\.\d+\.\d+$")

# The nine sites censused 2026-09-15, service -> image. Spelled out rather than
# counted so a service that silently changes WHICH image it runs is caught too.
EXPECTED_SITES = {
    "juniper-data": "ghcr.io/pcalnon/juniper-data",
    "demo-seed": "ghcr.io/pcalnon/juniper-data",
    "juniper-cascor": "ghcr.io/pcalnon/juniper-cascor",
    "juniper-cascor-demo": "ghcr.io/pcalnon/juniper-cascor",
    "juniper-cascor-worker": "ghcr.io/pcalnon/juniper-cascor-worker",
    "juniper-recurrence": "ghcr.io/pcalnon/juniper-recurrence",
    "juniper-canopy": "ghcr.io/pcalnon/juniper-canopy",
    "juniper-canopy-demo": "ghcr.io/pcalnon/juniper-canopy",
    "juniper-canopy-dev": "ghcr.io/pcalnon/juniper-canopy",
}


@pytest.fixture(scope="module")
def services() -> dict:
    doc = yaml.safe_load(COMPOSE_PATH.read_text(encoding="utf-8"))
    return doc["services"]


def _juniper_images(services: dict) -> dict[str, str]:
    return {
        name: svc["image"]
        for name, svc in services.items()
        if isinstance(svc, dict)
        and isinstance(svc.get("image"), str)
        and svc["image"].startswith(JUNIPER_NS)
    }


def test_no_juniper_image_is_an_unqualified_local_tag(services: dict) -> None:
    """No service may name a Juniper image without a registry.

    This is the regression itself, stated directly: `juniper-canopy:latest` has
    no registry, so it names whatever the local daemon last built.
    """
    offenders = {
        name: svc["image"]
        for name, svc in services.items()
        if isinstance(svc, dict)
        and isinstance(svc.get("image"), str)
        and re.match(r"^juniper-[a-z-]+:", svc["image"])
    }
    assert not offenders, (
        "these services name a Juniper image with no registry, which is a LOCAL "
        f"build-output tag rather than a version: {offenders}"
    )


def test_every_juniper_image_site_is_present_and_pinned(services: dict) -> None:
    found = _juniper_images(services)

    # Anti-vacuous: an empty match must never read as success.
    assert found, (
        f"no service names an image under {JUNIPER_NS} — either the Wave 3 pin was "
        "reverted wholesale or this test's parser is broken"
    )

    assert set(found) == set(EXPECTED_SITES), (
        "the set of services carrying a Juniper image drifted from the Wave 3 census; "
        f"update EXPECTED_SITES in the same PR (got {sorted(found)})"
    )

    for service, ref in sorted(found.items()):
        repo = ref.rsplit(":", 1)[0]
        assert repo == EXPECTED_SITES[service], (
            f"{service} changed which image it runs: {repo} (expected "
            f"{EXPECTED_SITES[service]})"
        )
        assert PINNED_RE.match(ref), (
            f"{service} -> {ref!r} is not a fully-qualified X.Y.Z release pin"
        )


def test_shared_images_are_pinned_to_one_version(services: dict) -> None:
    """canopy x3, cascor x2 and data x2 must not drift apart from each other.

    demo-seed is the one that matters: it has no `build:` of its own and reuses
    the data image, so a bump that moves `juniper-data` and forgets demo-seed
    would seed a demo from a different build than the one serving it.
    """
    by_repo: dict[str, set[str]] = {}
    for ref in _juniper_images(services).values():
        repo, _, tag = ref.rpartition(":")
        by_repo.setdefault(repo, set()).add(tag)

    split = {repo: sorted(tags) for repo, tags in by_repo.items() if len(tags) > 1}
    assert not split, f"these images are pinned to more than one version: {split}"


def test_verify_script_lists_exactly_the_shipped_sites() -> None:
    """The network-free half of the CI gate agrees with this test's own parse."""
    proc = subprocess.run(
        [sys.executable, str(VERIFY_SCRIPT), "--list-only", "--expect-count", str(len(EXPECTED_SITES))],
        capture_output=True,
        text=True,
        timeout=60,
        cwd=REPO_ROOT,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    for service in EXPECTED_SITES:
        assert service in proc.stdout, f"{service} missing from --list-only output"


def test_verify_script_refuses_a_compose_with_no_juniper_images(tmp_path: Path) -> None:
    """The gate must exit non-zero on the reverted-pin shape, not report success."""
    fixture = tmp_path / "reverted.yml"
    fixture.write_text(
        "services:\n"
        "  juniper-data:\n"
        "    image: juniper-data:latest\n",
        encoding="utf-8",
    )
    proc = subprocess.run(
        [sys.executable, str(VERIFY_SCRIPT), "--compose", str(fixture), "--list-only"],
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert proc.returncode == 2, (
        "a compose file with every pin reverted must be refused, not passed; "
        f"got exit {proc.returncode}: {proc.stdout + proc.stderr}"
    )
    assert "ZERO images" in proc.stderr
