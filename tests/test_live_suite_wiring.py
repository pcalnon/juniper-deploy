#!/usr/bin/env python
#####################################################################################################################################################################################################
# Project:       Juniper
# Application:   juniper-deploy
# File Name:     test_live_suite_wiring.py
# Author:        Paul Calnon
#
# Date Created:  2026-10-08
#
# License:       MIT License
# Copyright:     Copyright (c) 2024-2026 Paul Calnon
#
# Description:
#    Offline wiring checks for the live-stack suite the test-runner image packages. No stack,
#    no network.
#
#    1. THREE LISTS NAME THE LIVE MODULES, and nothing tied them together until now:
#       - Dockerfile.test's CMD (what the image runs);
#       - publish-image.yml's LIVE_MODULES (what the publish job counts in the checkout);
#       - util/check_image_test_suite.py's MODULES (what it counts inside the image).
#       A module added to one list and not the others is either never run, or fails the
#       publish job with a count mismatch that names no module. The three must be equal, in
#       order.
#    2. THE W1.11 SMOKE'S KEYS. The compose test-runner passes canopy's and juniper-data's keys
#       to tests/test_canopy_recurrence_equities_smoke.py as Docker secrets, through *_FILE
#       variables. An env var that names a secret the service does not mount is a failure
#       class this stack has already shipped twice (cascor's accept-list, unmounted for about 16
#       days; cascor's outbound data key, PR #87): it reads as configured and authenticates
#       nothing.
#    3. tests/conftest.py's *_FILE indirection: the parse rules those secrets depend on.
#
#####################################################################################################################################################################################################

from __future__ import annotations

import ast
import importlib.util
import json
import re
from collections.abc import Callable
from pathlib import Path

import pytest
import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
DOCKERFILE_TEST = REPO_ROOT / "Dockerfile.test"
PUBLISH_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "publish-image.yml"
CHECK_SCRIPT = REPO_ROOT / "util" / "check_image_test_suite.py"
COMPOSE_PATH = REPO_ROOT / "docker-compose.yml"
CONFTEST_PATH = REPO_ROOT / "tests" / "conftest.py"

SMOKE_MODULE = "tests/test_canopy_recurrence_equities_smoke.py"
SECRETS_ROOT = "/run/secrets/"


def _dockerfile_cmd_modules() -> list[str]:
    """The `tests/...` arguments of Dockerfile.test's exec-form CMD, in order."""
    text = DOCKERFILE_TEST.read_text(encoding="utf-8").replace("\\\n", " ")
    match = re.search(r"^CMD\s+(\[.*\])\s*$", text, flags=re.MULTILINE)
    assert match, "Dockerfile.test has no exec-form (JSON array) CMD"
    return [arg for arg in json.loads(match.group(1)) if arg.startswith("tests/")]


def _workflow_live_modules() -> list[str]:
    workflow = yaml.safe_load(PUBLISH_WORKFLOW.read_text(encoding="utf-8"))
    return str(workflow["env"]["LIVE_MODULES"]).split()


def _check_script_modules() -> list[str]:
    tree = ast.parse(CHECK_SCRIPT.read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(isinstance(target, ast.Name) and target.id == "MODULES" for target in node.targets):
            return list(ast.literal_eval(node.value))
    raise AssertionError("util/check_image_test_suite.py defines no top-level MODULES list")


class TestLiveModuleLists:
    def test_the_three_lists_are_identical(self) -> None:
        image_runs = _dockerfile_cmd_modules()
        publish_counts = _workflow_live_modules()
        image_counts = _check_script_modules()
        # Anti-vacuous: three empty lists are equal too.
        assert image_runs, "Dockerfile.test's CMD names no tests/ module"
        assert image_runs == publish_counts == image_counts, (
            "the live-module lists drifted apart:\n"
            f"  Dockerfile.test CMD:                     {image_runs}\n"
            f"  publish-image.yml LIVE_MODULES:          {publish_counts}\n"
            f"  util/check_image_test_suite.py MODULES:  {image_counts}"
        )

    def test_every_listed_module_exists_and_the_w1_11_smoke_is_one(self) -> None:
        modules = _dockerfile_cmd_modules()
        missing = [module for module in modules if not (REPO_ROOT / module).is_file()]
        assert not missing, f"Dockerfile.test's CMD runs modules that do not exist: {missing}"
        assert SMOKE_MODULE in modules, f"{SMOKE_MODULE} is not in the test-runner image's CMD"


@pytest.fixture(scope="module")
def compose() -> dict:
    return yaml.safe_load(COMPOSE_PATH.read_text(encoding="utf-8"))


def _mounted_secret_names(service: dict) -> set[str]:
    names = set()
    for entry in service.get("secrets") or []:
        # Short syntax is the secret's name; long syntax names it under `source`.
        names.add(entry if isinstance(entry, str) else entry.get("source"))
    return names


class TestTestRunnerSmokeWiring:
    def test_each_key_file_names_a_secret_the_runner_mounts(self, compose: dict) -> None:
        runner = compose["services"]["test-runner"]
        env = runner.get("environment") or {}
        key_files = {name: str(value) for name, value in env.items() if name.startswith("JUNIPER_TEST_") and name.endswith("_API_KEY_FILE")}
        assert {"JUNIPER_TEST_CANOPY_API_KEY_FILE", "JUNIPER_TEST_DATA_API_KEY_FILE"} <= set(key_files), f"the test-runner must hand the smoke canopy's and juniper-data's keys; it sets {sorted(key_files)}"
        mounted = _mounted_secret_names(runner)
        declared = set(compose.get("secrets") or {})
        for name, path in sorted(key_files.items()):
            assert path.startswith(SECRETS_ROOT), f"{name}={path} is not a Docker secret path"
            secret = path[len(SECRETS_ROOT):]
            assert secret in mounted, f"{name} reads {path}, but the test-runner does not mount secret {secret!r} (mounted: {sorted(mounted)})"
            assert secret in declared, f"{name} reads secret {secret!r}, which the top-level `secrets:` block does not declare"

    def test_the_keys_are_the_ones_canopy_and_juniper_data_validate(self, compose: dict) -> None:
        """Symmetric mount: the runner sends exactly the secret each service checks against."""
        services = compose["services"]
        runner_env = services["test-runner"]["environment"]
        assert runner_env["JUNIPER_TEST_CANOPY_API_KEY_FILE"] == services["juniper-canopy"]["environment"]["CANOPY_API_KEY_FILE"]
        assert runner_env["JUNIPER_TEST_DATA_API_KEY_FILE"] == services["juniper-data"]["environment"]["JUNIPER_DATA_API_KEYS_FILE"]

    def test_the_runner_environment_carries_no_key_value(self, compose: dict) -> None:
        env = compose["services"]["test-runner"].get("environment") or {}
        plain = sorted(name for name in env if name.startswith("JUNIPER_TEST_") and name.endswith("_API_KEY"))
        assert not plain, f"the test-runner sets key VALUES in its environment ({plain}); `docker inspect` shows them. Use the *_FILE form."

    def test_the_runner_waits_for_juniper_recurrence(self, compose: dict) -> None:
        """canopy connects to juniper-recurrence lazily, so nothing else orders the two."""
        depends_on = compose["services"]["test-runner"].get("depends_on") or {}
        assert (depends_on.get("juniper-recurrence") or {}).get("condition") == "service_healthy", f"test-runner depends_on: {depends_on}"


@pytest.fixture()
def api_key() -> Callable[[str, str], str]:
    """conftest.py's `_api_key`, from a private copy of the module (conftest is pytest-special)."""
    spec = importlib.util.spec_from_file_location("conftest_api_key_under_test", CONFTEST_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module._api_key


PLAIN = "JUNIPER_TEST_WIRING_PROBE_API_KEY"
FROM_FILE = "JUNIPER_TEST_WIRING_PROBE_API_KEY_FILE"


class TestApiKeyFileIndirection:
    def test_the_plain_variable_wins(self, api_key, monkeypatch, tmp_path: Path) -> None:
        key_file = tmp_path / "key.txt"
        key_file.write_text("value-from-file\n", encoding="utf-8")
        monkeypatch.setenv(PLAIN, "value-from-env")
        monkeypatch.setenv(FROM_FILE, str(key_file))
        assert api_key(PLAIN, FROM_FILE) == "value-from-env"

    def test_the_file_gives_its_first_entry(self, api_key, monkeypatch, tmp_path: Path) -> None:
        """An accept-list file: comments and blank lines skipped, first comma-separated entry."""
        key_file = tmp_path / "keys.txt"
        key_file.write_text("# accept-list\n\n   first-key , second-key\nthird-key\n", encoding="utf-8")
        monkeypatch.delenv(PLAIN, raising=False)
        monkeypatch.setenv(FROM_FILE, str(key_file))
        assert api_key(PLAIN, FROM_FILE) == "first-key"

    def test_unset_empty_and_unreadable_resolve_to_no_key(self, api_key, monkeypatch, tmp_path: Path) -> None:
        monkeypatch.delenv(PLAIN, raising=False)
        monkeypatch.delenv(FROM_FILE, raising=False)
        assert api_key(PLAIN, FROM_FILE) == ""
        empty = tmp_path / "empty.txt"
        empty.write_text("# nothing but a comment\n", encoding="utf-8")
        monkeypatch.setenv(FROM_FILE, str(empty))
        assert api_key(PLAIN, FROM_FILE) == ""
        monkeypatch.setenv(FROM_FILE, str(tmp_path / "absent.txt"))
        assert api_key(PLAIN, FROM_FILE) == ""
