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


def test_trusted_ips_declared_on_juniper_cascor() -> None:
    """`docker-compose.yml`'s juniper-cascor env block must declare TRUSTED_IPS.

    POC remediation §3.1 added ``MetricsAuthMiddleware`` to juniper-cascor
    (PR juniper-cascor#313). Wave-3 (this PR) wires its env-var override into
    compose so ``make monitor`` can widen the allowlist to the Docker bridge
    subnets via ``.env.observability`` — same posture juniper-data has had
    since PR juniper-deploy#98.
    """
    compose = _load_compose()
    env_block = compose["services"]["juniper-cascor"]["environment"]
    assert "JUNIPER_CASCOR_METRICS_TRUSTED_IPS" in env_block, (
        "Wave-3 regression: `JUNIPER_CASCOR_METRICS_TRUSTED_IPS` is missing "
        "from services.juniper-cascor.environment in docker-compose.yml. "
        "Without the declaration, `--env-file` substitution silently no-ops "
        "and the cascor `/metrics` scrape returns HTTP 403 from "
        "MetricsAuthMiddleware even after the operator sets the env var. "
        "Mirrors the juniper-data wiring established in juniper-deploy#98."
    )


def test_cascor_trusted_ips_value_substitutes_env_var() -> None:
    """The cascor declared value must support `${JUNIPER_CASCOR_METRICS_TRUSTED_IPS:-...}` substitution."""
    compose = _load_compose()
    value = compose["services"]["juniper-cascor"]["environment"]["JUNIPER_CASCOR_METRICS_TRUSTED_IPS"]
    assert isinstance(value, str)
    assert "${JUNIPER_CASCOR_METRICS_TRUSTED_IPS" in value, (
        "TRUSTED_IPS value must reference the env var via "
        "`${JUNIPER_CASCOR_METRICS_TRUSTED_IPS:-...}` so operator overrides work."
    )
    assert "127.0.0.1" in value and "::1" in value, (
        "Default value must keep loopback-only behaviour: ['127.0.0.1', '::1']."
    )


def test_trusted_ips_declared_on_juniper_canopy() -> None:
    """`docker-compose.yml`'s juniper-canopy env block must declare TRUSTED_IPS.

    POC remediation §6 added ``MetricsAuthMiddleware`` to juniper-canopy
    (PR juniper-canopy#331), via the helper promoted to
    ``juniper-observability`` 0.3.0 (PR juniper-ml#335). This PR wires
    its env-var override into compose so ``make monitor`` can widen the
    allowlist to the Docker bridge subnets via ``.env.observability``.
    """
    compose = _load_compose()
    env_block = compose["services"]["juniper-canopy"]["environment"]
    assert "JUNIPER_CANOPY_METRICS_TRUSTED_IPS" in env_block, (
        "POC §6 regression: `JUNIPER_CANOPY_METRICS_TRUSTED_IPS` is "
        "missing from services.juniper-canopy.environment in "
        "docker-compose.yml. Without the declaration, `--env-file` "
        "substitution silently no-ops and the canopy `/metrics` scrape "
        "returns HTTP 403 from MetricsAuthMiddleware even after the "
        "operator sets the env var. Mirrors the juniper-data wiring "
        "(juniper-deploy#98) and juniper-cascor wiring "
        "(juniper-deploy#105 Wave-3)."
    )


def test_canopy_trusted_ips_value_substitutes_env_var() -> None:
    """The canopy declared value must support `${JUNIPER_CANOPY_METRICS_TRUSTED_IPS:-...}` substitution."""
    compose = _load_compose()
    value = compose["services"]["juniper-canopy"]["environment"]["JUNIPER_CANOPY_METRICS_TRUSTED_IPS"]
    assert isinstance(value, str)
    assert "${JUNIPER_CANOPY_METRICS_TRUSTED_IPS" in value, (
        "TRUSTED_IPS value must reference the env var via "
        "`${JUNIPER_CANOPY_METRICS_TRUSTED_IPS:-...}` so operator overrides work."
    )
    assert "127.0.0.1" in value and "::1" in value, (
        "Default value must keep loopback-only behaviour: ['127.0.0.1', '::1']."
    )


def test_env_observability_widens_all_scraped_services_to_bridge_cidrs() -> None:
    """`.env.observability` must pre-set TRUSTED_IPS for all scraped app services.

    Without this, ``make monitor`` (which loads `.env.observability`) brings
    up the observability profile with METRICS_ENABLED=true but app
    targets stay ``down: 403`` because the literal-default
    ``["127.0.0.1","::1"]`` does not match Prometheus's bridge-network IP.

    SEC-F19 / D5 pinned the four compose networks to static ipam subnets
    (172.28–172.31/16); the allowlists reference exactly the pinned subnets
    each target shares with Prometheus. The precise subnet<->allowlist
    agreement is enforced by tests/test_compose_metrics_subnet_alignment.py;
    this test keeps the coarse presence check.
    """
    env_obs = (REPO_ROOT / ".env.observability").read_text(encoding="utf-8")
    for service_var in (
        "JUNIPER_DATA_METRICS_ENABLED",
        "JUNIPER_CASCOR_METRICS_ENABLED",
        "JUNIPER_RECURRENCE_METRICS_ENABLED",
        "CANOPY_METRICS_ENABLED",
    ):
        assert f"{service_var}=true" in env_obs, f"`.env.observability` must enable `{service_var}`."
    for service_var in (
        "JUNIPER_DATA_METRICS_TRUSTED_IPS",
        "JUNIPER_CASCOR_METRICS_TRUSTED_IPS",
        "JUNIPER_RECURRENCE_METRICS_TRUSTED_IPS",
        "JUNIPER_CANOPY_METRICS_TRUSTED_IPS",
    ):
        assert f"{service_var}=" in env_obs, f"`.env.observability` must set `{service_var}` (POC remediation completeness)."
    # The pinned bridge subnets Prometheus shares with a scrape target
    # (backend/data/frontend) must each appear in the allowlist so the
    # prometheus container's source IP matches regardless of which shared
    # network the scrape is routed over. monitoring (172.31) hosts no scrape
    # target, so it is intentionally NOT in any allowlist.
    for cidr in ("172.28.0.0/16", "172.29.0.0/16", "172.30.0.0/16"):
        assert cidr in env_obs, f"`.env.observability` must include pinned subnet `{cidr}` in METRICS_TRUSTED_IPS."


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
