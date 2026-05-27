#!/usr/bin/env python
"""Regression test pinning the `make monitor` observability entry point.

Discovered in notes/poc/POC_ISSUES_DISCOVERED.md (Issue 1): `make monitor`
brought up Prometheus + Grafana via the observability profile but did NOT
load `.env.observability`, so the JUNIPER_*_METRICS_ENABLED flags stayed at
their default `false` and every Juniper scrape target reported `down`.

This test pins the canonical wiring so the regression cannot re-land
silently.
"""

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
MAKEFILE = REPO_ROOT / "Makefile"


def _read_makefile() -> str:
    return MAKEFILE.read_text(encoding="utf-8")


def _monitor_recipe(makefile_text: str) -> str:
    """Return the recipe body of the `monitor:` target as a single string."""
    lines = makefile_text.splitlines()
    in_recipe = False
    body: list[str] = []
    for line in lines:
        if line.startswith("monitor:"):
            in_recipe = True
            continue
        if in_recipe:
            if line.startswith("\t") or line.strip() == "" or line.startswith("\\"):
                body.append(line)
                continue
            # First non-tab, non-blank line ends the recipe.
            break
    assert body, "monitor: target body not found in Makefile"
    return "\n".join(body)


def test_monitor_target_loads_env_observability() -> None:
    """`make monitor` must pass `--env-file .env.observability` to compose."""
    recipe = _monitor_recipe(_read_makefile())
    assert "--env-file .env.observability" in recipe, (
        "Issue 1: `monitor` target dropped `--env-file .env.observability`; "
        "without it JUNIPER_*_METRICS_ENABLED falls back to false and every "
        "Juniper scrape target reports down. See "
        "notes/poc/POC_ISSUES_DISCOVERED.md Issue 1."
    )


def test_monitor_target_uses_observability_profile() -> None:
    """`make monitor` must keep the observability + full profiles."""
    recipe = _monitor_recipe(_read_makefile())
    assert "--profile observability" in recipe
    assert "--profile full" in recipe


def test_monitor_chains_prepare_secrets() -> None:
    """`make monitor` must depend on `prepare-secrets` like every other lifecycle target."""
    text = _read_makefile()
    # Look for the dependency on the target line itself.
    for line in text.splitlines():
        if line.startswith("monitor:"):
            assert "prepare-secrets" in line, (
                "monitor: must declare `prepare-secrets` as a prereq so the "
                "grafana admin secret + cascor auth token exist before the "
                "containers start. Mirrors `up:`, `demo:`, `dev:`."
            )
            return
    raise AssertionError("monitor: target not found in Makefile")


def test_obs_alias_exists() -> None:
    """`make obs` aliases `make monitor` per the .env.observability header."""
    text = _read_makefile()
    found = False
    for line in text.splitlines():
        if line.startswith("obs:") and "monitor" in line:
            found = True
            break
    assert found, "obs: alias target referencing monitor must be defined"


def test_env_observability_does_not_advertise_nonexistent_targets() -> None:
    """Every `make <target>` advertised in the shortcut block must exist.

    The .env.observability header used to advertise `make obs` and `make
    obs-demo` neither of which existed — the source of Issue 1's "stale
    Makefile shortcut list" complaint. This test catches the same
    regression class without false-positive-ing on explanatory mentions
    (e.g. "make obs-demo is intentionally NOT provided").
    """
    import re

    env_path = REPO_ROOT / ".env.observability"
    text = env_path.read_text(encoding="utf-8")
    makefile_text = _read_makefile()

    # Match shortcut-list lines: a leading "#", whitespace, "make <target>",
    # then more whitespace, then either "#" (comment-style annotation) or
    # nothing. This matches `#   make monitor    # full + observability`
    # but NOT prose like `Note: \`make obs-demo\` is not provided`.
    shortcut_re = re.compile(r"^#\s+make\s+(\S+)\s*(#.*)?$")

    advertised = []
    for line in text.splitlines():
        match = shortcut_re.match(line)
        if match:
            advertised.append(match.group(1))

    missing = [t for t in advertised if f"{t}:" not in makefile_text]
    assert not missing, (
        f".env.observability advertises Make targets that don't exist: "
        f"{missing}. Either implement them or drop the reference."
    )
