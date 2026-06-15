#!/usr/bin/env python
"""Tests for ``scripts/provenance_sha.sh`` — the ``-dirty``-aware provenance SHA stamper (OQ-2).

``provenance_sha.sh`` prints a repo's short HEAD SHA, suffixed with ``-dirty``
when the working tree has uncommitted *tracked* changes (untracked artifacts are
ignored). The deploy Makefile's ``PROVENANCE_ENV`` uses it to stamp image labels
so ``make doctor`` / ``make health`` flag an image built from uncommitted code as
DIRTY rather than FRESH. See juniper-ml ``notes/BUILD_PROVENANCE_DESIGN_2026-06-14.md``.
"""

import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "provenance_sha.sh"


def _git(cwd: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(cwd), *args], check=True, capture_output=True)


def _stamp(repo: Path) -> str:
    return subprocess.run(["bash", str(SCRIPT), str(repo)], capture_output=True, text=True, check=True).stdout


def _init_repo(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    _git(path, "init", "-q")
    _git(path, "config", "user.email", "test@juniper.local")
    _git(path, "config", "user.name", "Test")
    (path / "f.txt").write_text("v1\n")
    _git(path, "add", ".")
    _git(path, "commit", "-qm", "init")


def test_script_exists() -> None:
    assert SCRIPT.is_file(), "scripts/provenance_sha.sh must exist."


def test_clean_repo_returns_bare_sha(tmp_path) -> None:
    repo = tmp_path / "clean"
    _init_repo(repo)
    out = _stamp(repo)
    assert out and "-dirty" not in out, f"clean tree must yield a bare short SHA, got {out!r}"


def test_uncommitted_tracked_change_appends_dirty(tmp_path) -> None:
    repo = tmp_path / "dirty"
    _init_repo(repo)
    (repo / "f.txt").write_text("v2\n")  # modify a tracked file, do not commit
    assert _stamp(repo).endswith("-dirty"), "an uncommitted tracked edit must append -dirty"


def test_untracked_files_do_not_mark_dirty(tmp_path) -> None:
    """Untracked build artifacts (egg-info, pycache, .env) must NOT mark the build dirty."""
    repo = tmp_path / "untracked"
    _init_repo(repo)
    (repo / "artifact.egg-info").mkdir()
    (repo / "scratch.log").write_text("noise\n")
    assert "-dirty" not in _stamp(repo), "untracked files must not trigger -dirty"


def test_non_repo_returns_empty(tmp_path) -> None:
    assert _stamp(tmp_path / "does-not-exist") == "", "a non-repo path must yield an empty string"
