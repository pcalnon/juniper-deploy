#!/usr/bin/env python
#####################################################################################################################################################################################################
# Project:       Juniper
# Application:   juniper-deploy
# File Name:     test_gitleaks_config.py
# Author:        Paul Calnon
#
# Date Created:  2026-10-25
#
# License:       MIT License
# Copyright:     Copyright (c) 2024-2026 Paul Calnon
#
# Description:
#    Static and real-engine regression guard for ``.gitleaks.toml``: the ruleset
#    the ci.yml ``Gitleaks`` job loads must not be empty.
#
#    Until 2026-10-25 the file held an ``[allowlist]`` and no ``[extend]`` table,
#    and a gitleaks v8 config without ``[extend] useDefault = true`` loads ONLY
#    its own ``[[rules]]`` -- of which it had none. The Gitleaks job therefore
#    ran with zero rules and could not fail: a fabricated GitHub token passed it
#    while gitleaks' built-in config flags the same token (the defect
#    juniper-ml#2203 found and fixed there).
#
#    The real-engine tests run the gitleaks binary (``GITLEAKS_BIN``, else
#    ``gitleaks`` on PATH) on a token ASSEMBLED AT RUNTIME, so this file holds no
#    literal that gitleaks or GitHub push protection would flag. They skip
#    without a binary, except in the Gitleaks job, which runs this file with
#    ``GITLEAKS_PARITY_REQUIRED=1`` after gitleaks-action has put the binary on
#    PATH: a check that could not run is not a pass.
#
#####################################################################################################################################################################################################

import json
import os
import re
import shutil
import string
import subprocess  # nosec B404 -- runs the gitleaks binary with a fixed argv, never a shell
import tomllib
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
CONFIG = REPO_ROOT / ".gitleaks.toml"
IGNORE = REPO_ROOT / ".gitleaksignore"
WORKFLOW = REPO_ROOT / ".github" / "workflows" / "ci.yml"
THIS_FILE = "tests/test_gitleaks_config.py"
# The engine gitleaks-action v3.0.0 installs by default, pinned in ci.yml as GITLEAKS_VERSION.
ENGINE_VERSION = "8.24.3"
ENTRY = re.compile(r"[0-9a-f]{40}:[^:\s]+:[a-z0-9-]+:[0-9]+")


def _fabricated_github_pat():
    """A GitHub-PAT-SHAPED value from a fixed-step walk over the alphabet: deterministic, never a credential."""
    alphabet = string.ascii_letters + string.digits
    return "gh" + "p_" + "".join(alphabet[(11 + i * 29) % len(alphabet)] for i in range(36))


def test_config_extends_the_default_ruleset():
    # Without this table gitleaks loads only this file's [[rules]]: the zero-rule config that passed every scan.
    with open(CONFIG, "rb") as fh:
        cfg = tomllib.load(fh)
    assert cfg.get("extend", {}).get("useDefault") is True, "[extend] useDefault = true is missing: gitleaks would load no default rule"


def test_global_allowlist_has_no_paths():
    # The config's own comment: a global [allowlist].paths entry skips EVERY rule for those files.
    with open(CONFIG, "rb") as fh:
        cfg = tomllib.load(fh)
    assert "paths" not in cfg.get("allowlist", {}), "a global [allowlist].paths exempts whole files from every rule"


def _ignore_lines():
    return [line.strip() for line in IGNORE.read_text(encoding="utf-8").splitlines()]


def test_ignore_entries_are_commit_scoped_and_unique():
    entries = [line for line in _ignore_lines() if line and not line.startswith("#")]
    assert entries, ".gitleaksignore holds no entry"
    for line in entries:
        assert ENTRY.fullmatch(line), f"{line!r}: an entry must name its 40-hex commit; a file-scoped one would hide FUTURE secrets"
    assert len(entries) == len(set(entries)), "duplicate .gitleaksignore entries"


def test_every_ignore_entry_sits_under_a_class_comment():
    # Entries may be grouped, but the nearest line above a group must be a comment: a blank line orphans it.
    lines = _ignore_lines()
    for i, line in enumerate(lines):
        if not ENTRY.fullmatch(line):
            continue
        j = i - 1
        while j >= 0 and ENTRY.fullmatch(lines[j]):
            j -= 1
        assert j >= 0 and lines[j].startswith("#"), f".gitleaksignore line {i + 1}: every entry belongs to a group under a comment naming its class"


def test_ci_pins_the_engine_and_requires_the_real_engine_run():
    steps = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))["jobs"]["gitleaks"]["steps"]
    action = next(i for i, s in enumerate(steps) if str(s.get("uses", "")).startswith("gitleaks/gitleaks-action@"))
    assert str(steps[action].get("env", {}).get("GITLEAKS_VERSION")) == ENGINE_VERSION
    runs = [s for s in steps[action + 1 :] if THIS_FILE in str(s.get("run", ""))]
    assert runs, f"no Gitleaks-job step after the gitleaks action runs {THIS_FILE}"
    assert all(str(s.get("env", {}).get("GITLEAKS_PARITY_REQUIRED")) == "1" for s in runs), "the real-engine run must set GITLEAKS_PARITY_REQUIRED=1"


@pytest.fixture
def gitleaks_bin():
    found = os.environ.get("GITLEAKS_BIN") or shutil.which("gitleaks")
    if found is None:
        if os.environ.get("GITLEAKS_PARITY_REQUIRED") == "1":
            pytest.fail("GITLEAKS_PARITY_REQUIRED=1 but no gitleaks binary (GITLEAKS_BIN unset, none on PATH)")
        pytest.skip("no gitleaks binary (set GITLEAKS_BIN, or put gitleaks on PATH)")
    return found


@pytest.mark.parametrize("mode", ["auto-discovered", "explicit --config", "built-in default (control)"])
def test_real_engine_fires_on_a_fabricated_token(gitleaks_bin, tmp_path, mode):
    scan = tmp_path / "scan"
    scan.mkdir()
    (scan / "sample.txt").write_text("GITHUB_TOKEN=" + _fabricated_github_pat() + "\n", encoding="utf-8")
    report = tmp_path / "report.json"
    argv = [gitleaks_bin, "dir", "--redact", "--no-banner", "--no-color", "--exit-code=0", "--report-format=json", f"--report-path={report}"]
    if mode == "auto-discovered":
        # CI's path: gitleaks-action passes no --config, so the engine reads <source>/.gitleaks.toml.
        shutil.copyfile(CONFIG, scan / ".gitleaks.toml")
    elif mode == "explicit --config":
        argv += ["--config", str(CONFIG)]
    # A GITLEAKS_CONFIG* variable outranks <source>/.gitleaks.toml; scrub it so auto-discovery is what is tested.
    env = {k: v for k, v in os.environ.items() if k not in ("GITLEAKS_CONFIG", "GITLEAKS_CONFIG_TOML")}
    res = subprocess.run([*argv, str(scan)], capture_output=True, text=True, timeout=120, check=False, env=env)  # nosec B603
    assert res.returncode == 0, f"gitleaks exited {res.returncode}: {res.stderr[-400:]}"
    with open(report, encoding="utf-8") as fh:
        findings = json.load(fh)
    assert all(f.get("Secret") == "REDACTED" for f in findings), "the report was not redacted"
    fired = {f["RuleID"] for f in findings if Path(f["File"]).name == "sample.txt"}
    assert "github-pat" in fired, f"{mode}: the built-in github-pat rule did not fire -- the ruleset does not include the default rules"
