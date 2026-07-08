#!/usr/bin/env python
#####################################################################################################################################################################################################
# Project:       Juniper
# Application:   juniper-deploy
# File Name:     test_build_freshness_preflight.py
# Author:        Juniper Automation
#
# Date Created:  2026-07-07
#
# License:       MIT License
# Copyright:     Copyright (c) 2024-2026 Paul Calnon
#
# Description:
#    Offline behavioural + wiring gate for scripts/preflight_build_freshness.sh
#    (the `make build` freshness preflight). Mirrors the repo's other compose
#    gates (tests/test_compose_bind_posture_attestation.py): the script is
#    driven via its offline --config-json mode against SYNTHETIC git
#    repositories built in tmp_path — no Docker daemon, no network (the
#    "origin" remotes are local paths, so the script's default `git fetch`
#    path is exercised hermetically).
#
#    Incident of record (2026-07-07): `make build` silently built images from
#    juniper-cascor / juniper-canopy checkouts that were 3 / 5 commits behind
#    their already-merged sibling PRs (cascor#393 / canopy#432), shipping the
#    OLD single-flag SEC-F22 guard against deploy #148's NEW two-flag env —
#    juniper-cascor crash-looped on start. This gate pins the preflight that
#    makes that class impossible to hit silently:
#
#      (a) a fresh default-branch checkout PASSES ([FRESH], exit 0)
#      (b) a checkout BEHIND its origin default branch FAILS loudly
#          ([STALE], exit 1, names the repo + the `pull --ff-only` fix)
#      (c) the JUNIPER_BUILD_STALE_OK=1 / --allow-stale escape hatch
#          downgrades the refusal to a warning (exit 0)
#      (d) deliberate dev flows only WARN: non-default branch, ahead-only,
#          dirty working tree, non-git / missing contexts
#      (e) DIVERGED (ahead AND behind) also fails
#      (f) nested build contexts resolve to the ENCLOSING repo and are
#          checked once (the ../juniper-recurrence/juniper-recurrence shape)
#      (g) the shipped docker-compose.yml build contexts match the known
#          coverage domain (drift gate)
#      (h) the Makefile actually wires the preflight before both build
#          targets (unwiring it would resurrect the incident silently)
#
#####################################################################################################################################################################################################

from __future__ import annotations

import itertools
import json
import os
import subprocess
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
COMPOSE_PATH = REPO_ROOT / "docker-compose.yml"
MAKEFILE_PATH = REPO_ROOT / "Makefile"
PREFLIGHT_SCRIPT = REPO_ROOT / "scripts" / "preflight_build_freshness.sh"

# The build contexts the shipped compose declares (drift gate g). Extending the
# stack with a new built service is expected to update this set in the same PR.
EXPECTED_BUILD_CONTEXTS = {
    ".",
    "../juniper-canopy",
    "../juniper-cascor",
    "../juniper-cascor-worker",
    "../juniper-data",
    "../juniper-recurrence/juniper-recurrence",
}

_UNIQUE = itertools.count()


# ── Synthetic-repo helpers ──────────────────────────────────────────────────


def _git_env(tmp_path: Path) -> dict[str, str]:
    """Isolated git environment: no user/system config, no prompts, no color."""
    env = os.environ.copy()
    env.update(
        {
            "GIT_CONFIG_GLOBAL": "/dev/null",
            "GIT_CONFIG_SYSTEM": "/dev/null",
            "GIT_TERMINAL_PROMPT": "0",
            "HOME": str(tmp_path),
            "NO_COLOR": "1",
        }
    )
    env.pop("JUNIPER_BUILD_STALE_OK", None)
    return env


def _git(env: dict[str, str], cwd: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-c", "user.name=juniper-test", "-c", "user.email=test@juniper.local", *args],
        cwd=cwd,
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )


def _commit(env: dict[str, str], repo: Path, message: str = "change") -> None:
    (repo / "tracked.txt").write_text(f"{message}-{next(_UNIQUE)}\n", encoding="utf-8")
    _git(env, repo, "add", "-A")
    _git(env, repo, "commit", "-m", message)


def _mk_upstream_and_clone(tmp_path: Path, env: dict[str, str]) -> tuple[Path, Path]:
    """An 'origin' repo (a local path — fetchable offline) and a clone of it."""
    upstream = tmp_path / f"upstream-{next(_UNIQUE)}"
    upstream.mkdir()
    _git(env, upstream, "init", "-b", "main")
    _commit(env, upstream, "seed")
    clone = tmp_path / f"clone-{next(_UNIQUE)}"
    _git(env, tmp_path, "clone", str(upstream), str(clone))
    return upstream, clone


def _config_json(tmp_path: Path, *contexts: Path | str) -> Path:
    services: dict[str, dict] = {"plain-image-service": {"image": "busybox"}}
    for index, context in enumerate(contexts):
        services[f"built-service-{index}"] = {"build": {"context": str(context)}}
    config_path = tmp_path / f"render-{next(_UNIQUE)}.json"
    config_path.write_text(json.dumps({"services": services}), encoding="utf-8")
    return config_path


def _run_preflight(env: dict[str, str], config_path: Path, *extra: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["bash", str(PREFLIGHT_SCRIPT), "--config-json", str(config_path), *extra],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


# ── (a) fresh checkout passes ───────────────────────────────────────────────


def test_fresh_default_branch_checkout_passes(tmp_path):
    env = _git_env(tmp_path)
    _, clone = _mk_upstream_and_clone(tmp_path, env)
    result = _run_preflight(env, _config_json(tmp_path, clone))
    assert result.returncode == 0, result.stdout + result.stderr
    assert "[FRESH" in result.stdout
    assert "PASS" in result.stdout


# ── (b) behind-origin default branch fails loudly ───────────────────────────


def test_stale_default_branch_checkout_fails_and_names_the_fix(tmp_path):
    env = _git_env(tmp_path)
    upstream, clone = _mk_upstream_and_clone(tmp_path, env)
    _commit(env, upstream, "landed-after-clone")  # clone is now 1 behind
    result = _run_preflight(env, _config_json(tmp_path, clone))
    assert result.returncode == 1, result.stdout + result.stderr
    assert "[STALE" in result.stdout
    assert "BEHIND" in result.stdout
    assert str(clone) in result.stdout, "the failing repo must be named"
    assert "pull --ff-only" in result.stdout, "the fix hint must be printed"
    assert "JUNIPER_BUILD_STALE_OK" in result.stdout, "the escape hatch must be advertised"


def test_stale_detection_relies_on_the_default_fetch(tmp_path):
    """--no-fetch compares against last-fetched refs, so a fresh-cloned repo
    whose upstream has since advanced still LOOKS fresh — pinning why fetch is
    the default (and that --no-fetch is honoured)."""
    env = _git_env(tmp_path)
    upstream, clone = _mk_upstream_and_clone(tmp_path, env)
    _commit(env, upstream, "landed-after-clone")
    result = _run_preflight(env, _config_json(tmp_path, clone), "--no-fetch")
    assert result.returncode == 0, result.stdout + result.stderr
    assert "--no-fetch" in result.stdout


# ── (c) escape hatch ────────────────────────────────────────────────────────


def test_stale_ok_env_downgrades_to_warning(tmp_path):
    env = _git_env(tmp_path)
    upstream, clone = _mk_upstream_and_clone(tmp_path, env)
    _commit(env, upstream, "landed-after-clone")
    env["JUNIPER_BUILD_STALE_OK"] = "1"
    result = _run_preflight(env, _config_json(tmp_path, clone))
    assert result.returncode == 0, result.stdout + result.stderr
    assert "[STALE-OK" in result.stdout


def test_allow_stale_flag_downgrades_to_warning(tmp_path):
    env = _git_env(tmp_path)
    upstream, clone = _mk_upstream_and_clone(tmp_path, env)
    _commit(env, upstream, "landed-after-clone")
    result = _run_preflight(env, _config_json(tmp_path, clone), "--allow-stale")
    assert result.returncode == 0, result.stdout + result.stderr
    assert "[STALE-OK" in result.stdout


# ── (d) deliberate dev flows warn, never fail ───────────────────────────────


def test_non_default_branch_warns_not_fails(tmp_path):
    env = _git_env(tmp_path)
    upstream, clone = _mk_upstream_and_clone(tmp_path, env)
    _git(env, clone, "checkout", "-b", "feature/wip")
    _commit(env, upstream, "landed-after-clone")  # would be STALE if compared
    result = _run_preflight(env, _config_json(tmp_path, clone))
    assert result.returncode == 0, result.stdout + result.stderr
    assert "[BRANCH" in result.stdout
    assert "feature/wip" in result.stdout


def test_ahead_only_warns_not_fails(tmp_path):
    env = _git_env(tmp_path)
    _, clone = _mk_upstream_and_clone(tmp_path, env)
    _commit(env, clone, "unpushed-local-work")
    result = _run_preflight(env, _config_json(tmp_path, clone))
    assert result.returncode == 0, result.stdout + result.stderr
    assert "[AHEAD" in result.stdout


def test_dirty_working_tree_is_noted_but_passes(tmp_path):
    env = _git_env(tmp_path)
    _, clone = _mk_upstream_and_clone(tmp_path, env)
    (clone / "tracked.txt").write_text("uncommitted edit\n", encoding="utf-8")
    result = _run_preflight(env, _config_json(tmp_path, clone))
    assert result.returncode == 0, result.stdout + result.stderr
    assert "DIRTY" in result.stdout


def test_non_git_context_is_unverified_not_fatal(tmp_path):
    env = _git_env(tmp_path)
    plain_dir = tmp_path / "not-a-repo"
    plain_dir.mkdir()
    result = _run_preflight(env, _config_json(tmp_path, plain_dir))
    assert result.returncode == 0, result.stdout + result.stderr
    assert "[UNVERIFIED" in result.stdout


def test_missing_context_directory_warns_not_fails(tmp_path):
    env = _git_env(tmp_path)
    result = _run_preflight(env, _config_json(tmp_path, tmp_path / "does-not-exist"))
    assert result.returncode == 0, result.stdout + result.stderr
    assert "[MISSING" in result.stdout


# ── (e) diverged fails ──────────────────────────────────────────────────────


def test_diverged_default_branch_fails(tmp_path):
    env = _git_env(tmp_path)
    upstream, clone = _mk_upstream_and_clone(tmp_path, env)
    _commit(env, clone, "local-only")
    _commit(env, upstream, "origin-only")
    result = _run_preflight(env, _config_json(tmp_path, clone))
    assert result.returncode == 1, result.stdout + result.stderr
    assert "[DIVERGED" in result.stdout


# ── (f) nested contexts resolve to the enclosing repo, checked once ─────────


def test_nested_contexts_dedupe_to_one_enclosing_repo_check(tmp_path):
    env = _git_env(tmp_path)
    _, clone = _mk_upstream_and_clone(tmp_path, env)
    nested = clone / "app-subdir"
    nested.mkdir()
    result = _run_preflight(env, _config_json(tmp_path, clone, nested))
    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stdout.count("[FRESH") == 1, "one repo, two contexts -> exactly one check"


# ── usage-error contract ────────────────────────────────────────────────────


def test_missing_config_json_file_exits_2(tmp_path):
    env = _git_env(tmp_path)
    result = _run_preflight(env, tmp_path / "no-such-render.json")
    assert result.returncode == 2, result.stdout + result.stderr


def test_config_with_no_build_contexts_is_a_noop_pass(tmp_path):
    env = _git_env(tmp_path)
    result = _run_preflight(env, _config_json(tmp_path))
    assert result.returncode == 0, result.stdout + result.stderr
    assert "no-op" in result.stdout


# ── (g) shipped-compose coverage-domain drift gate ──────────────────────────


def test_shipped_compose_build_contexts_match_expected_domain():
    compose = yaml.safe_load(COMPOSE_PATH.read_text(encoding="utf-8"))
    contexts = set()
    for service in (compose.get("services") or {}).values():
        build = (service or {}).get("build")
        if isinstance(build, str):
            contexts.add(build)
        elif isinstance(build, dict) and build.get("context"):
            contexts.add(str(build["context"]))
    assert contexts == EXPECTED_BUILD_CONTEXTS, (
        "docker-compose.yml build contexts drifted from the preflight's known coverage domain "
        f"(got {sorted(contexts)}); update EXPECTED_BUILD_CONTEXTS in the same PR."
    )


# ── (h) Makefile wiring gate ────────────────────────────────────────────────


def test_makefile_wires_build_preflight_before_both_build_targets():
    makefile = MAKEFILE_PATH.read_text(encoding="utf-8")
    assert "BUILD_PREFLIGHT := bash scripts/preflight_build_freshness.sh" in makefile
    assert "build-preflight:" in makefile, "standalone `make build-preflight` target must exist"
    for target in ("\nbuild:", "\nbuild-no-cache:"):
        _, _, recipe_onward = makefile.partition(target)
        assert recipe_onward, f"Makefile target {target.strip()} not found"
        recipe_lines = [line for line in recipe_onward.splitlines()[1:] if line.startswith("\t")]
        assert recipe_lines and "$(BUILD_PREFLIGHT)" in recipe_lines[0], (
            f"the first recipe line of `make {target.strip().rstrip(':')}` must run $(BUILD_PREFLIGHT) "
            "so images cannot be built from silently-stale checkouts"
        )


def test_preflight_script_exists_and_is_executable():
    assert PREFLIGHT_SCRIPT.is_file()
    assert os.access(PREFLIGHT_SCRIPT, os.X_OK), "scripts/preflight_build_freshness.sh must be executable"
