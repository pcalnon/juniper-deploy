#!/usr/bin/env python
"""Regression tests pinning the `make doctor` build-provenance drift checker.

`make doctor` (juniper-ml notes/BUILD_PROVENANCE_DESIGN_2026-06-14.md, Part 7)
detects images running behind their source: it reads each image's
``org.opencontainers.image.revision`` OCI label via ``docker inspect`` and
compares it to the sibling source repo's HEAD, reporting FRESH / STALE /
UNKNOWN. These tests pin the target -> script wiring and the script's core
mechanism so the drift checker cannot silently regress, and confirm the
companion ``health_check.sh`` git_sha/drift column stays wired.
"""

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
MAKEFILE = REPO_ROOT / "Makefile"
DOCTOR = REPO_ROOT / "scripts" / "doctor.sh"
HEALTH_CHECK = REPO_ROOT / "scripts" / "health_check.sh"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _doctor_recipe(makefile_text: str) -> str:
    """Return the recipe body of the `doctor:` target as a single string."""
    in_recipe = False
    body: list[str] = []
    for line in makefile_text.splitlines():
        if line.startswith("doctor:"):
            in_recipe = True
            continue
        if in_recipe:
            if line.startswith("\t") or line.strip() == "" or line.startswith("\\"):
                body.append(line)
                continue
            # First non-tab, non-blank line ends the recipe.
            break
    assert body, "doctor: target body not found in Makefile"
    return "\n".join(body)


def _phony_targets(makefile_text: str) -> list[str]:
    """Return the target names declared across the (possibly continued) .PHONY line."""
    collected: list[str] = []
    capturing = False
    for line in makefile_text.splitlines():
        if line.startswith(".PHONY:"):
            capturing = True
            collected.append(line[len(".PHONY:") :])
        elif capturing:
            collected.append(line)
        if capturing and not line.rstrip().endswith("\\"):
            break
    return " ".join(seg.rstrip("\\").strip() for seg in collected).split()


def test_doctor_target_exists() -> None:
    """The Makefile defines a `doctor:` target."""
    assert any(line.startswith("doctor:") for line in _read(MAKEFILE).splitlines()), "Makefile must define a `doctor:` target (build-provenance drift checker)."


def test_doctor_target_is_phony() -> None:
    """`doctor` produces no file, so it must be declared .PHONY."""
    assert "doctor" in _phony_targets(_read(MAKEFILE)), "doctor must be listed in .PHONY alongside the other diagnostic targets."


def test_doctor_target_invokes_script() -> None:
    """`make doctor` delegates to scripts/doctor.sh (mirrors `health` -> health_check.sh)."""
    assert "scripts/doctor.sh" in _doctor_recipe(_read(MAKEFILE)), "doctor: must run scripts/doctor.sh."


def test_doctor_script_exists() -> None:
    assert DOCTOR.is_file(), "scripts/doctor.sh must exist."


def test_doctor_script_reads_oci_revision_label() -> None:
    """The drift check keys off the OCI revision label via docker inspect (not /v1/health,
    so it works even for services whose port is not host-published, e.g. juniper-data)."""
    text = _read(DOCTOR)
    assert "org.opencontainers.image.revision" in text
    assert "docker inspect" in text


def test_doctor_script_compares_source_head() -> None:
    """Drift is image-revision vs the sibling source repo's HEAD."""
    assert "rev-parse" in _read(DOCTOR), "doctor.sh must compare against `git rev-parse` HEAD of the source repo."


def test_doctor_script_classifies_fresh_stale_unknown() -> None:
    text = _read(DOCTOR)
    for verdict in ("FRESH", "STALE", "UNKNOWN"):
        assert verdict in text, f"doctor.sh must be able to report {verdict}."


def test_doctor_covers_all_built_services() -> None:
    """Every locally-built Juniper image must be checked for drift."""
    text = _read(DOCTOR)
    for image in ("juniper-data", "juniper-cascor", "juniper-canopy", "juniper-cascor-worker"):
        assert image in text, f"doctor.sh must check the {image} image for drift."


def test_health_check_surfaces_git_sha_and_drift() -> None:
    """`health_check.sh` gained a git_sha + drift column off the provenance fields."""
    text = _read(HEALTH_CHECK)
    assert "git_sha" in text, "health_check.sh must read git_sha from /v1/health."
    assert "GIT_SHA" in text and "DRIFT" in text, "health_check.sh must show GIT_SHA + DRIFT columns."


def test_doctor_flags_dirty_images() -> None:
    """OQ-2: an image whose revision ends in `-dirty` (built from uncommitted tracked
    changes) must be reported DIRTY, not FRESH — checked before the FRESH prefix compare."""
    text = _read(DOCTOR)
    assert "*-dirty" in text, "doctor.sh must detect the -dirty provenance marker."
    assert "DIRTY" in text, "doctor.sh must report a DIRTY status."


def test_makefile_stamps_dirty_via_helper() -> None:
    """PROVENANCE_ENV must stamp SHAs through provenance_sha.sh (which appends `-dirty`)
    rather than a bare rev-parse, so an image built from uncommitted code is detectable."""
    assert "provenance_sha.sh" in _read(MAKEFILE), "Makefile PROVENANCE_ENV must use scripts/provenance_sha.sh for -dirty-aware SHA stamping."


def test_health_check_flags_dirty() -> None:
    """health_check.sh's DRIFT column must surface DIRTY for a `-dirty` image revision."""
    text = _read(HEALTH_CHECK)
    assert "DIRTY" in text and "-dirty" in text, "health_check.sh must flag -dirty images as DIRTY."
