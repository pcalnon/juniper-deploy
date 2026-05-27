#!/usr/bin/env python
"""Regression test pinning JUNIPER_DATA_METRICS_TRUSTED_IPS into compose.

Discovered in notes/poc/POC_ISSUES_DISCOVERED.md (Issue 3):
docker-compose.yml declared `JUNIPER_DATA_METRICS_ENABLED` but NOT
`JUNIPER_DATA_METRICS_TRUSTED_IPS`. Setting the variable via `--env-file`
silently no-opped because compose substitution only fills in `${VAR:-default}`
placeholders that exist in the YAML. This test pins the env-var declaration
and also catches the stale `_ALLOW_IPS` name across notes / prometheus.yml /
Helm chart.
"""

from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
COMPOSE_PATH = REPO_ROOT / "docker-compose.yml"


def _load_compose() -> dict:
    # Use safe_load_all in case the file ever gains a multi-doc structure.
    return yaml.safe_load(COMPOSE_PATH.read_text(encoding="utf-8"))


def test_trusted_ips_declared_on_juniper_data() -> None:
    """`docker-compose.yml`'s juniper-data env block must declare TRUSTED_IPS."""
    compose = _load_compose()
    env_block = compose["services"]["juniper-data"]["environment"]
    assert "JUNIPER_DATA_METRICS_TRUSTED_IPS" in env_block, (
        "Issue 3: `JUNIPER_DATA_METRICS_TRUSTED_IPS` is missing from "
        "services.juniper-data.environment in docker-compose.yml. "
        "Without the declaration, `--env-file` substitution silently no-ops "
        "and operators get HTTP 403 from MetricsAuthMiddleware with no clue "
        "why. See notes/METRICS_AUTH_RATIONALE.md."
    )


def test_trusted_ips_value_substitutes_env_var() -> None:
    """The declared value must support `${JUNIPER_DATA_METRICS_TRUSTED_IPS:-...}` substitution."""
    compose = _load_compose()
    value = compose["services"]["juniper-data"]["environment"]["JUNIPER_DATA_METRICS_TRUSTED_IPS"]
    assert isinstance(value, str)
    assert "${JUNIPER_DATA_METRICS_TRUSTED_IPS" in value, (
        "TRUSTED_IPS value must reference the env var via "
        "`${JUNIPER_DATA_METRICS_TRUSTED_IPS:-...}` so operator overrides work."
    )
    assert "127.0.0.1" in value and "::1" in value, (
        "Default value must keep loopback-only behaviour: ['127.0.0.1', '::1']."
    )


def test_no_stale_allow_ips_references_in_repo() -> None:
    """No file should reference the wrong env-var name `_ALLOW_IPS`."""
    # Files most likely to drift, per validator C findings (POC remediation
    # plan §1.2 + §7).
    paths = [
        REPO_ROOT / "prometheus" / "prometheus.yml",
        REPO_ROOT / "notes" / "METRICS_AUTH_RATIONALE.md",
        REPO_ROOT / "k8s" / "helm" / "juniper" / "templates" / "data-servicemonitor.yaml",
        REPO_ROOT / "k8s" / "helm" / "juniper" / "values.yaml",
        REPO_ROOT / "docker-compose.yml",
        REPO_ROOT / ".env.example",
    ]
    offenders = []
    for path in paths:
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8")
        # Match both the literal and the placeholder variants — the source-
        # of-truth env var lives in juniper-data settings as TRUSTED_IPS.
        if "_METRICS_ALLOW_IPS" in text:
            offenders.append(str(path.relative_to(REPO_ROOT)))
    assert not offenders, (
        f"The wrong env-var name `_METRICS_ALLOW_IPS` reappeared in: "
        f"{offenders}. The canonical name is `JUNIPER_DATA_METRICS_TRUSTED_IPS` "
        f"(see juniper-data/juniper_data/api/settings.py)."
    )
