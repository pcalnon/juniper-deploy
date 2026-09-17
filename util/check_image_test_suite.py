#!/usr/bin/env python3
######################################################################################################################################################################################################
# Project:       Juniper
# Application:   juniper-deploy
# File Name:     check_image_test_suite.py
# Author:        Paul Calnon
#
# Date Created:  2026-09-16
#
# License:       MIT License
# Copyright:     Copyright (c) 2024-2026 Paul Calnon
#
# Description:
#    Publish-path contract for the juniper-deploy test-runner image. Runs INSIDE
#    the image (`docker run --entrypoint python IMG - < this`) and asserts that
#    the live-stack suite actually COLLECTS.
#
#    Why this specific check. The image's whole value is that it can run the
#    integration suite against a deployed stack; an image that builds, starts,
#    and then dies at conftest import is worthless and looks fine from outside.
#    That is not hypothetical -- it is what shipped: commit 65def44 (2026-03-13)
#    added tests/conftest.py's `from constants import ...` together with
#    `pythonpath = ["tests"]` in pyproject.toml, and Dockerfile.test never copied
#    pyproject.toml, so from then until 2026-09-16 the default CMD died with
#    `ModuleNotFoundError: No module named 'constants'` before running a single
#    test. Six months, unnoticed, because nothing asserted the suite was runnable.
#
#    A BARE "collection succeeded" IS NOT ENOUGH, which is why EXPECT_TESTS
#    exists. Collection of an empty set also "succeeds": pytest exits 0 having
#    found nothing, so a COPY that silently stopped matching would read as a
#    pass. The count is the discriminating half, exactly as the distribution
#    census (not the version string) is the discriminating half of the sibling
#    repos' CPU-only check.
#
# Usage:
#    docker run --rm -i -e EXPECT_TESTS=51 --entrypoint python IMAGE - < util/check_image_test_suite.py
#
# Exit status:
#    0  the expected number of tests collected, with no collection errors
#    1  wrong count, a collection error, or pytest unavailable
#
######################################################################################################################################################################################################

from __future__ import annotations

import os
import platform
import subprocess
import sys

MODULES = [
    "tests/test_health.py",
    "tests/test_availability.py",
    "tests/test_data_service.py",
    "tests/test_full_stack.py",
]


def main() -> int:
    expect_raw = os.environ.get("EXPECT_TESTS", "").strip()
    if not expect_raw:
        print("EXPECT_TESTS is unset -- refusing to check against an unstated expectation")
        return 1
    try:
        expect = int(expect_raw)
    except ValueError:
        print(f"EXPECT_TESTS={expect_raw!r} is not an integer")
        return 1
    if expect <= 0:
        print(f"EXPECT_TESTS={expect} -- a non-positive expectation would pass vacuously")
        return 1

    print(f"machine: {platform.machine()}  python: {platform.python_version()}")

    try:
        import pytest  # noqa: F401 - presence check only
    except ImportError:
        print("pytest is not installed in this image")
        return 1

    proc = subprocess.run(
        [sys.executable, "-m", "pytest", *MODULES, "--collect-only", "-q"],
        capture_output=True,
        text=True,
        timeout=300,
    )
    out = proc.stdout + proc.stderr

    # A collection ERROR aborts the run, so it must fail here even if some
    # modules collected -- a partially collectable suite is not a runnable one.
    if "error" in out.lower() and "errors" in out.lower():
        print("collection reported errors:")
        print(out[-2000:])
        return 1

    collected = None
    for line in out.splitlines():
        line = line.strip()
        if "test" in line and "collected" in line:
            for token in line.split():
                if token.isdigit():
                    collected = int(token)
                    break
            if collected is not None:
                break

    if collected is None:
        print("could not parse a collected-test count from pytest output:")
        print(out[-2000:])
        return 1

    print(f"collected: {collected}  expected: {expect}")
    if collected != expect:
        print(
            f"FAIL: the live-stack suite collected {collected} tests, expected {expect}. "
            "Either a module stopped being packaged (check Dockerfile.test's COPY set) "
            "or tests were added/removed and EXPECT_TESTS needs updating in the same PR."
        )
        return 1

    print(f"OK: live-stack suite collects {collected} tests, no collection errors")
    return 0


if __name__ == "__main__":
    sys.exit(main())
