#!/usr/bin/env python
#####################################################################################################################################################################################################
# Project:       Juniper
# Application:   juniper-deploy
# File Name:     test_doctor_provenance_derivation.py
# Author:        Juniper Automation
#
# Date Created:  2026-07-08
#
# License:       MIT License
# Copyright:     Copyright (c) 2024-2026 Paul Calnon
#
# Description:
#    Behavioural gate for scripts/doctor.sh's render-derived service list.
#    doctor.sh previously hardcoded a 4-entry SERVICES array that drifted
#    (juniper-recurrence and the demo/dev service variants were never
#    checked); it now derives (service, image, build-context) rows from
#    `docker compose config --format json` — the same mechanism as the
#    preflight_build_freshness.sh / preflight_image_provenance.sh family.
#
#    Fully hermetic via the offline seams (--config-json pre-rendered config
#    + --image-provenance-map image->label JSON, which also disables the
#    running-container preference), against SYNTHETIC git repos in tmp_path —
#    no Docker daemon. Pins:
#
#      (a) EVERY built service gets its own row (services sharing one image
#          are NOT deduped — doctor is service-oriented), and nested build
#          contexts resolve to their enclosing repo
#      (b) classification parity with the old doctor: FRESH passes (incl.
#          7/8-char short-SHA prefix match); STALE exits 1 with the
#          `make build` note; `-dirty` revisions exit 1 as DIRTY; label-less
#          images and non-git contexts are UNKNOWN (non-fatal)
#      (c) image-only services (redis, prometheus, ...) and services without
#          an `image:` are skipped
#      (d) exit-2 usage contract for missing --config-json / map files
#      (e) the shipped docker-compose.yml's built-service set matches the
#          known coverage domain — the render-derived replacement for the old
#          4-image hardcoded-list lint (extending the stack updates this set
#          in the same PR)
#
#####################################################################################################################################################################################################

from __future__ import annotations

import itertools
import json
import os
import subprocess
from pathlib import Path

import yaml
from tests.redacted_env import RedactedEnv

REPO_ROOT = Path(__file__).resolve().parents[1]
COMPOSE_PATH = REPO_ROOT / "docker-compose.yml"
DOCTOR_SCRIPT = REPO_ROOT / "scripts" / "doctor.sh"

# The built services the shipped compose declares (drift gate e). The old
# hardcoded doctor list covered only 4 of these — recurrence and the
# demo/dev variants were silently unchecked.
EXPECTED_BUILT_SERVICES = {
    "juniper-canopy",
    "juniper-canopy-demo",
    "juniper-canopy-dev",
    "juniper-cascor",
    "juniper-cascor-demo",
    "juniper-cascor-worker",
    "juniper-data",
    "juniper-recurrence",
}

_UNIQUE = itertools.count()


# ── Synthetic-repo helpers (mirrors the preflight test suites) ──────────────


def _git_env(tmp_path: Path) -> dict[str, str]:
    env = RedactedEnv(os.environ)
    env.update(
        {
            "GIT_CONFIG_GLOBAL": "/dev/null",
            "GIT_CONFIG_SYSTEM": "/dev/null",
            "GIT_TERMINAL_PROMPT": "0",
            "HOME": str(tmp_path),
            "NO_COLOR": "1",
        }
    )
    return env


def _git(env: dict[str, str], cwd: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-c", "user.name=juniper-test", "-c", "user.email=test@juniper.local", *args],
        cwd=cwd,
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def _mk_repo(tmp_path: Path, env: dict[str, str]) -> tuple[Path, str]:
    """A committed repo and its short HEAD SHA."""
    repo = tmp_path / f"repo-{next(_UNIQUE)}"
    repo.mkdir()
    _git(env, repo, "init", "-b", "main")
    (repo / "tracked.txt").write_text(f"seed-{next(_UNIQUE)}\n", encoding="utf-8")
    _git(env, repo, "add", "-A")
    _git(env, repo, "commit", "-m", "seed")
    return repo, _git(env, repo, "rev-parse", "--short", "HEAD")


def _config_json(tmp_path: Path, services: dict[str, dict]) -> Path:
    config_path = tmp_path / f"render-{next(_UNIQUE)}.json"
    config_path.write_text(json.dumps({"services": services}), encoding="utf-8")
    return config_path


def _map_json(tmp_path: Path, mapping: dict[str, str]) -> Path:
    map_path = tmp_path / f"shas-{next(_UNIQUE)}.json"
    map_path.write_text(json.dumps(mapping), encoding="utf-8")
    return map_path


def _built_service(image: str, context: Path | str) -> dict:
    return {"image": image, "build": {"context": str(context)}}


def _run_doctor(env: dict[str, str], config_path: Path, map_path: Path | None) -> subprocess.CompletedProcess:
    argv = ["bash", str(DOCTOR_SCRIPT), "--config-json", str(config_path)]
    if map_path is not None:
        argv += ["--image-provenance-map", str(map_path)]
    return subprocess.run(argv, cwd=REPO_ROOT, env=env, capture_output=True, text=True, check=False)


# ── (a) every built service gets a row; nested contexts resolve ─────────────


def test_every_built_service_gets_its_own_row(tmp_path):
    env = _git_env(tmp_path)
    repo, head = _mk_repo(tmp_path, env)
    nested = repo / "app-subdir"
    nested.mkdir()
    cfg = _config_json(
        tmp_path,
        {
            "svc-main": _built_service("shared:latest", repo),
            "svc-demo": _built_service("shared:latest", repo),  # same image — still its own row
            "svc-nested": _built_service("nested:latest", nested),  # resolves to the enclosing repo
        },
    )
    result = _run_doctor(env, cfg, _map_json(tmp_path, {"shared:latest": head, "nested:latest": head}))
    assert result.returncode == 0, result.stdout + result.stderr
    for service in ("svc-main", "svc-demo", "svc-nested"):
        assert service in result.stdout, f"service {service} must get a doctor row"
    assert result.stdout.count("FRESH") == 3


# ── (b) classification parity ───────────────────────────────────────────────


def test_fresh_image_passes(tmp_path):
    env = _git_env(tmp_path)
    repo, head = _mk_repo(tmp_path, env)
    cfg = _config_json(tmp_path, {"svc": _built_service("svc:latest", repo)})
    result = _run_doctor(env, cfg, _map_json(tmp_path, {"svc:latest": head}))
    assert result.returncode == 0, result.stdout + result.stderr
    assert "FRESH" in result.stdout
    assert "No stale or dirty images detected" in result.stdout


def test_short_sha_prefix_lengths_still_match(tmp_path):
    env = _git_env(tmp_path)
    repo, _ = _mk_repo(tmp_path, env)
    eight = _git(env, repo, "rev-parse", "--short=8", "HEAD")
    cfg = _config_json(tmp_path, {"svc": _built_service("svc:latest", repo)})
    result = _run_doctor(env, cfg, _map_json(tmp_path, {"svc:latest": eight}))
    assert result.returncode == 0, result.stdout + result.stderr
    assert "FRESH" in result.stdout


def test_stale_image_exits_1_with_rebuild_note(tmp_path):
    env = _git_env(tmp_path)
    repo, old_head = _mk_repo(tmp_path, env)
    (repo / "tracked.txt").write_text("newer\n", encoding="utf-8")
    _git(env, repo, "add", "-A")
    _git(env, repo, "commit", "-m", "newer")
    cfg = _config_json(tmp_path, {"svc": _built_service("svc:latest", repo)})
    result = _run_doctor(env, cfg, _map_json(tmp_path, {"svc:latest": old_head}))
    assert result.returncode == 1, result.stdout + result.stderr
    assert "STALE" in result.stdout
    assert "make build" in result.stdout


def test_dirty_image_exits_1(tmp_path):
    env = _git_env(tmp_path)
    repo, head = _mk_repo(tmp_path, env)
    cfg = _config_json(tmp_path, {"svc": _built_service("svc:latest", repo)})
    result = _run_doctor(env, cfg, _map_json(tmp_path, {"svc:latest": f"{head}-dirty"}))
    assert result.returncode == 1, result.stdout + result.stderr
    assert "DIRTY" in result.stdout
    assert "uncommitted" in result.stdout


def test_labelless_image_is_unknown_and_nonfatal(tmp_path):
    env = _git_env(tmp_path)
    repo, _ = _mk_repo(tmp_path, env)
    cfg = _config_json(tmp_path, {"svc": _built_service("svc:latest", repo)})
    result = _run_doctor(env, cfg, _map_json(tmp_path, {"svc:latest": ""}))
    assert result.returncode == 0, result.stdout + result.stderr
    assert "UNKNOWN" in result.stdout
    assert "no revision label" in result.stdout


def test_unbuilt_image_is_unknown_and_nonfatal(tmp_path):
    env = _git_env(tmp_path)
    repo, _ = _mk_repo(tmp_path, env)
    cfg = _config_json(tmp_path, {"svc": _built_service("svc:latest", repo)})
    result = _run_doctor(env, cfg, _map_json(tmp_path, {}))  # missing key = not built
    assert result.returncode == 0, result.stdout + result.stderr
    assert "UNKNOWN" in result.stdout


def test_non_git_context_is_unknown_and_nonfatal(tmp_path):
    env = _git_env(tmp_path)
    plain_dir = tmp_path / "not-a-repo"
    plain_dir.mkdir()
    cfg = _config_json(tmp_path, {"svc": _built_service("svc:latest", plain_dir)})
    result = _run_doctor(env, cfg, _map_json(tmp_path, {"svc:latest": "abc1234"}))
    assert result.returncode == 0, result.stdout + result.stderr
    assert "UNKNOWN" in result.stdout
    assert "source repo not found" in result.stdout


# ── (c) skip rules ──────────────────────────────────────────────────────────


def test_image_only_and_build_only_services_are_skipped(tmp_path):
    env = _git_env(tmp_path)
    repo, head = _mk_repo(tmp_path, env)
    cfg = _config_json(
        tmp_path,
        {
            "svc": _built_service("svc:latest", repo),
            "redis": {"image": "redis:7.4-alpine"},
            "anonymous-build": {"build": {"context": str(repo)}},
        },
    )
    result = _run_doctor(env, cfg, _map_json(tmp_path, {"svc:latest": head}))
    assert result.returncode == 0, result.stdout + result.stderr
    assert "redis" not in result.stdout
    assert "anonymous-build" not in result.stdout


def test_config_with_no_built_services_is_nonfatal(tmp_path):
    env = _git_env(tmp_path)
    cfg = _config_json(tmp_path, {"redis": {"image": "redis:7.4-alpine"}})
    result = _run_doctor(env, cfg, _map_json(tmp_path, {}))
    assert result.returncode == 0, result.stdout + result.stderr
    assert "Nothing to check" in result.stdout


# ── (d) usage-error contract ────────────────────────────────────────────────


def test_missing_config_json_file_exits_2(tmp_path):
    env = _git_env(tmp_path)
    result = _run_doctor(env, tmp_path / "no-such-render.json", None)
    assert result.returncode == 2, result.stdout + result.stderr


def test_missing_provenance_map_file_exits_2(tmp_path):
    env = _git_env(tmp_path)
    repo, _ = _mk_repo(tmp_path, env)
    cfg = _config_json(tmp_path, {"svc": _built_service("svc:latest", repo)})
    result = _run_doctor(env, cfg, tmp_path / "no-such-map.json")
    assert result.returncode == 2, result.stdout + result.stderr


# ── (e) shipped-compose coverage-domain drift gate ──────────────────────────


def test_shipped_compose_built_services_match_expected_domain():
    compose = yaml.safe_load(COMPOSE_PATH.read_text(encoding="utf-8"))
    built = set()
    for name, service in (compose.get("services") or {}).items():
        if isinstance(service, dict) and service.get("build") and service.get("image"):
            built.add(name)
    assert built == EXPECTED_BUILT_SERVICES, (
        "docker-compose.yml built services drifted from doctor's known coverage domain "
        f"(got {sorted(built)}); update EXPECTED_BUILT_SERVICES in the same PR."
    )
