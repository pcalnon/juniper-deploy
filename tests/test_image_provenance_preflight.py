#!/usr/bin/env python
#####################################################################################################################################################################################################
# Project:       Juniper
# Application:   juniper-deploy
# File Name:     test_image_provenance_preflight.py
# Author:        Juniper Automation
#
# Date Created:  2026-07-07
#
# License:       MIT License
# Copyright:     Copyright (c) 2024-2026 Paul Calnon
#
# Description:
#    Offline behavioural + wiring gate for scripts/preflight_image_provenance.sh
#    (the bring-up image-provenance preflight — the inverse of #150's
#    build-freshness preflight: it stops `make up`/`demo`/`dev`/`monitor`/
#    `obs-demo` from RUNNING images whose org.opencontainers.image.revision
#    label no longer matches the build-context checkout's HEAD, i.e. "checkout
#    updated but image not rebuilt").
#
#    Fully hermetic: the script is driven via --config-json (pre-rendered
#    compose config) + --image-provenance-map (image ref -> revision-label
#    value; a missing key = image not built), so no Docker daemon is touched,
#    and the git side runs against SYNTHETIC repos in tmp_path. Pins:
#
#      (a) matching revision PASSES ([MATCH], exit 0)
#      (b) a stale image on a default-branch checkout FAILS loudly
#          ([STALE], exit 1, behind-count + `make build` fix + escape hatch)
#      (c) JUNIPER_IMAGE_STALE_OK=1 / --allow-stale downgrade to a warning
#      (d) deliberate/unverifiable states only WARN: feature-branch mismatch,
#          unbuilt image, label-less image, match-but-dirty-checkout,
#          in-flight dirty image (base SHA == HEAD, tree still dirty)
#      (e) an ORPHANED dirty image (base SHA == HEAD but the tree is now
#          clean — the image holds code that exists in no commit) FAILS
#      (f) a revision absent from local history on the default branch FAILS
#      (g) services sharing one image are checked once; image-only services
#          (redis, prometheus, ...) and build-without-image services are
#          skipped
#      (h) 7- vs 8-char short SHAs prefix-match (doctor.sh convention)
#      (i) exit-2 usage contract (missing --config-json / map file)
#      (j) the Makefile wires $(IMAGE_PREFLIGHT) into every bring-up target
#          AFTER the bind preflight and BEFORE `docker compose ... up`
#
#####################################################################################################################################################################################################

from __future__ import annotations

import itertools
import json
import os
import re
import subprocess
from pathlib import Path
from tests.redacted_env import RedactedEnv

REPO_ROOT = Path(__file__).resolve().parents[1]
MAKEFILE_PATH = REPO_ROOT / "Makefile"
PREFLIGHT_SCRIPT = REPO_ROOT / "scripts" / "preflight_image_provenance.sh"

_UNIQUE = itertools.count()


# ── Synthetic-repo helpers (mirrors test_build_freshness_preflight.py) ──────


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
    env.pop("JUNIPER_IMAGE_STALE_OK", None)
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


def _commit(env: dict[str, str], repo: Path, message: str = "change") -> str:
    """Commit a change and return the new short HEAD SHA."""
    (repo / "tracked.txt").write_text(f"{message}-{next(_UNIQUE)}\n", encoding="utf-8")
    _git(env, repo, "add", "-A")
    _git(env, repo, "commit", "-m", message)
    return _git(env, repo, "rev-parse", "--short", "HEAD")


def _mk_repo(tmp_path: Path, env: dict[str, str]) -> tuple[Path, str]:
    """A default-branch (main) repo with an 'origin' remote, and its HEAD SHA.

    The preflight treats a checkout as default-branch by comparing the current
    branch against origin/HEAD (falling back to 'main'), so the synthetic repo
    is a clone — giving it a real origin — exactly like the sibling test suite.
    """
    upstream = tmp_path / f"upstream-{next(_UNIQUE)}"
    upstream.mkdir()
    _git(env, upstream, "init", "-b", "main")
    _commit(env, upstream, "seed")
    clone = tmp_path / f"clone-{next(_UNIQUE)}"
    _git(env, tmp_path, "clone", str(upstream), str(clone))
    return clone, _git(env, clone, "rev-parse", "--short", "HEAD")


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


def _run_preflight(env: dict[str, str], config_path: Path, map_path: Path | None, *extra: str) -> subprocess.CompletedProcess:
    argv = ["bash", str(PREFLIGHT_SCRIPT), "--config-json", str(config_path)]
    if map_path is not None:
        argv += ["--image-provenance-map", str(map_path)]
    argv += list(extra)
    return subprocess.run(argv, cwd=REPO_ROOT, env=env, capture_output=True, text=True, check=False)


# ── (a) match passes ────────────────────────────────────────────────────────


def test_matching_revision_passes(tmp_path):
    env = _git_env(tmp_path)
    repo, head = _mk_repo(tmp_path, env)
    cfg = _config_json(tmp_path, {"svc": _built_service("svc:latest", repo)})
    result = _run_preflight(env, cfg, _map_json(tmp_path, {"svc:latest": head}))
    assert result.returncode == 0, result.stdout + result.stderr
    assert "[MATCH" in result.stdout
    assert "PASS" in result.stdout


def test_short_sha_prefix_lengths_still_match(tmp_path):
    env = _git_env(tmp_path)
    repo, _ = _mk_repo(tmp_path, env)
    eight = _git(env, repo, "rev-parse", "--short=8", "HEAD")
    cfg = _config_json(tmp_path, {"svc": _built_service("svc:latest", repo)})
    result = _run_preflight(env, cfg, _map_json(tmp_path, {"svc:latest": eight}))
    assert result.returncode == 0, result.stdout + result.stderr
    assert "[MATCH" in result.stdout


# ── (b) stale image on the default branch fails loudly ──────────────────────


def test_stale_image_on_default_branch_fails_with_fix_hint(tmp_path):
    env = _git_env(tmp_path)
    repo, old_head = _mk_repo(tmp_path, env)
    _commit(env, repo, "newer-source")  # image label now one commit behind HEAD
    cfg = _config_json(tmp_path, {"svc": _built_service("svc:latest", repo)})
    result = _run_preflight(env, cfg, _map_json(tmp_path, {"svc:latest": old_head}))
    assert result.returncode == 1, result.stdout + result.stderr
    assert "[STALE" in result.stdout
    assert "1 commit(s) behind" in result.stdout
    assert "svc:latest" in result.stdout
    assert "make build" in result.stdout, "the fix hint must be printed"
    assert "JUNIPER_IMAGE_STALE_OK" in result.stdout, "the escape hatch must be advertised"


# ── (c) escape hatch ────────────────────────────────────────────────────────


def test_image_stale_ok_env_downgrades_to_warning(tmp_path):
    env = _git_env(tmp_path)
    repo, old_head = _mk_repo(tmp_path, env)
    _commit(env, repo, "newer-source")
    cfg = _config_json(tmp_path, {"svc": _built_service("svc:latest", repo)})
    env["JUNIPER_IMAGE_STALE_OK"] = "1"
    result = _run_preflight(env, cfg, _map_json(tmp_path, {"svc:latest": old_head}))
    assert result.returncode == 0, result.stdout + result.stderr
    assert "[STALE-OK" in result.stdout


def test_allow_stale_flag_downgrades_to_warning(tmp_path):
    env = _git_env(tmp_path)
    repo, old_head = _mk_repo(tmp_path, env)
    _commit(env, repo, "newer-source")
    cfg = _config_json(tmp_path, {"svc": _built_service("svc:latest", repo)})
    result = _run_preflight(env, cfg, _map_json(tmp_path, {"svc:latest": old_head}), "--allow-stale")
    assert result.returncode == 0, result.stdout + result.stderr
    assert "[STALE-OK" in result.stdout


# ── (d) deliberate / unverifiable states warn, never fail ───────────────────


def test_feature_branch_mismatch_warns_not_fails(tmp_path):
    env = _git_env(tmp_path)
    repo, old_head = _mk_repo(tmp_path, env)
    _git(env, repo, "checkout", "-b", "feature/wip")
    _commit(env, repo, "feature-work")
    cfg = _config_json(tmp_path, {"svc": _built_service("svc:latest", repo)})
    result = _run_preflight(env, cfg, _map_json(tmp_path, {"svc:latest": old_head}))
    assert result.returncode == 0, result.stdout + result.stderr
    assert "[BRANCH" in result.stdout
    assert "feature/wip" in result.stdout


def test_unbuilt_image_is_informational(tmp_path):
    env = _git_env(tmp_path)
    repo, _ = _mk_repo(tmp_path, env)
    cfg = _config_json(tmp_path, {"svc": _built_service("svc:latest", repo)})
    result = _run_preflight(env, cfg, _map_json(tmp_path, {}))  # image absent
    assert result.returncode == 0, result.stdout + result.stderr
    assert "[NO-IMAGE" in result.stdout


def test_labelless_image_is_unverified(tmp_path):
    env = _git_env(tmp_path)
    repo, _ = _mk_repo(tmp_path, env)
    cfg = _config_json(tmp_path, {"svc": _built_service("svc:latest", repo)})
    result = _run_preflight(env, cfg, _map_json(tmp_path, {"svc:latest": ""}))
    assert result.returncode == 0, result.stdout + result.stderr
    assert "[UNVERIFIED" in result.stdout
    assert "make build" in result.stdout


def test_match_with_dirty_checkout_notes_the_uncommitted_edits(tmp_path):
    env = _git_env(tmp_path)
    repo, head = _mk_repo(tmp_path, env)
    (repo / "tracked.txt").write_text("uncommitted edit\n", encoding="utf-8")
    cfg = _config_json(tmp_path, {"svc": _built_service("svc:latest", repo)})
    result = _run_preflight(env, cfg, _map_json(tmp_path, {"svc:latest": head}))
    assert result.returncode == 0, result.stdout + result.stderr
    assert "[MATCH" in result.stdout
    assert "uncommitted" in result.stdout


def test_inflight_dirty_image_with_dirty_tree_warns(tmp_path):
    env = _git_env(tmp_path)
    repo, head = _mk_repo(tmp_path, env)
    (repo / "tracked.txt").write_text("still iterating\n", encoding="utf-8")
    cfg = _config_json(tmp_path, {"svc": _built_service("svc:latest", repo)})
    result = _run_preflight(env, cfg, _map_json(tmp_path, {"svc:latest": f"{head}-dirty"}))
    assert result.returncode == 0, result.stdout + result.stderr
    assert "[DIRTY" in result.stdout
    assert "in-flight" in result.stdout


# ── (e) orphaned dirty image fails ──────────────────────────────────────────


def test_orphaned_dirty_image_with_clean_tree_fails(tmp_path):
    env = _git_env(tmp_path)
    repo, head = _mk_repo(tmp_path, env)  # tree is clean
    cfg = _config_json(tmp_path, {"svc": _built_service("svc:latest", repo)})
    result = _run_preflight(env, cfg, _map_json(tmp_path, {"svc:latest": f"{head}-dirty"}))
    assert result.returncode == 1, result.stdout + result.stderr
    assert "[DIRTY" in result.stdout
    assert "no longer exists" in result.stdout


def test_orphaned_dirty_image_respects_escape_hatch(tmp_path):
    env = _git_env(tmp_path)
    repo, head = _mk_repo(tmp_path, env)
    cfg = _config_json(tmp_path, {"svc": _built_service("svc:latest", repo)})
    env["JUNIPER_IMAGE_STALE_OK"] = "1"
    result = _run_preflight(env, cfg, _map_json(tmp_path, {"svc:latest": f"{head}-dirty"}))
    assert result.returncode == 0, result.stdout + result.stderr
    assert "[DIRTY-OK" in result.stdout


# ── (f) revision missing from local history ─────────────────────────────────


def test_unknown_revision_on_default_branch_fails(tmp_path):
    env = _git_env(tmp_path)
    repo, _ = _mk_repo(tmp_path, env)
    cfg = _config_json(tmp_path, {"svc": _built_service("svc:latest", repo)})
    result = _run_preflight(env, cfg, _map_json(tmp_path, {"svc:latest": "0000000"}))
    assert result.returncode == 1, result.stdout + result.stderr
    assert "not in" in result.stdout and "local history" in result.stdout


# ── (g) dedupe + skip rules ─────────────────────────────────────────────────


def test_services_sharing_an_image_are_checked_once(tmp_path):
    env = _git_env(tmp_path)
    repo, head = _mk_repo(tmp_path, env)
    cfg = _config_json(
        tmp_path,
        {
            "svc": _built_service("shared:latest", repo),
            "svc-demo": _built_service("shared:latest", repo),
        },
    )
    result = _run_preflight(env, cfg, _map_json(tmp_path, {"shared:latest": head}))
    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stdout.count("[MATCH") == 1, "one image, two services -> exactly one check"


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
    result = _run_preflight(env, cfg, _map_json(tmp_path, {"svc:latest": head}))
    assert result.returncode == 0, result.stdout + result.stderr
    assert "redis" not in result.stdout
    assert result.stdout.count("[MATCH") == 1


def test_config_with_no_built_services_is_a_noop_pass(tmp_path):
    env = _git_env(tmp_path)
    cfg = _config_json(tmp_path, {"redis": {"image": "redis:7.4-alpine"}})
    result = _run_preflight(env, cfg, _map_json(tmp_path, {}))
    assert result.returncode == 0, result.stdout + result.stderr
    assert "no-op" in result.stdout


# ── (i) usage-error contract ────────────────────────────────────────────────


def test_missing_config_json_file_exits_2(tmp_path):
    env = _git_env(tmp_path)
    result = _run_preflight(env, tmp_path / "no-such-render.json", None)
    assert result.returncode == 2, result.stdout + result.stderr


def test_missing_provenance_map_file_exits_2(tmp_path):
    env = _git_env(tmp_path)
    repo, _ = _mk_repo(tmp_path, env)
    cfg = _config_json(tmp_path, {"svc": _built_service("svc:latest", repo)})
    result = _run_preflight(env, cfg, tmp_path / "no-such-map.json")
    assert result.returncode == 2, result.stdout + result.stderr


# ── (j) Makefile wiring gate ────────────────────────────────────────────────

BRING_UP_TARGETS = ("up", "demo", "dev", "monitor", "obs-demo")


def _recipe_of(makefile: str, target: str) -> list[str]:
    match = re.search(rf"^{re.escape(target)}:.*$", makefile, flags=re.MULTILINE)
    assert match, f"Makefile target {target!r} not found"
    lines = []
    for line in makefile[match.end() :].splitlines()[1:]:
        if line.startswith("\t"):
            lines.append(line)
        elif line.strip() == "" or line.lstrip().startswith("#"):
            continue
        else:
            break
    return lines


def test_makefile_wires_image_preflight_into_every_bring_up_target():
    makefile = MAKEFILE_PATH.read_text(encoding="utf-8")
    assert "IMAGE_PREFLIGHT := bash scripts/preflight_image_provenance.sh" in makefile
    assert "image-preflight:" in makefile, "standalone `make image-preflight` target must exist"
    assert re.search(r"^\.PHONY:.*", makefile, flags=re.MULTILINE)
    assert "image-preflight" in " ".join(re.findall(r"^\.PHONY:[^\n]*(?:\n[ \t]+[^\n]*)*", makefile, flags=re.MULTILINE)[0].splitlines())
    for target in BRING_UP_TARGETS:
        recipe = _recipe_of(makefile, target)
        joined = "\n".join(recipe)
        assert "$(IMAGE_PREFLIGHT)" in joined, f"`make {target}` must run $(IMAGE_PREFLIGHT)"
        assert "$(PREFLIGHT)" in joined, f"`make {target}` must still run the bind preflight"
        bind_at = joined.index("$(PREFLIGHT)")
        image_at = joined.index("$(IMAGE_PREFLIGHT)")
        up_at = joined.index("up -d") if "up -d" in joined else len(joined)
        assert bind_at < image_at < up_at, (
            f"`make {target}` must run the bind preflight, then $(IMAGE_PREFLIGHT), then `docker compose ... up`"
        )


def test_preflight_script_exists_and_is_executable():
    assert PREFLIGHT_SCRIPT.is_file()
    assert os.access(PREFLIGHT_SCRIPT, os.X_OK), "scripts/preflight_image_provenance.sh must be executable"
