#!/usr/bin/env python
"""Regression tests for Alertmanager routing of Prometheus alert severities."""

from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
ALERTMANAGER_PATH = REPO_ROOT / "alertmanager" / "alertmanager.yml"
PROMETHEUS_RULES_PATH = REPO_ROOT / "prometheus" / "alert_rules.yml"

EXPECTED_MWMBR_ROUTES = {
    "page": {
        "receiver": "critical",
        "group_wait": "10s",
        "repeat_interval": "1h",
    },
    "ticket": {
        "receiver": "tickets",
        "group_wait": "1m",
        "group_interval": "10m",
        "repeat_interval": "12h",
    },
}


def _load_yaml(path: Path) -> dict:
    with path.open(encoding="utf-8") as file:
        data = yaml.safe_load(file)
    assert isinstance(data, dict), f"{path} did not parse as a YAML mapping"
    return data


def _alertmanager_routes_by_severity() -> dict[str, dict]:
    config = _load_yaml(ALERTMANAGER_PATH)
    nested_routes = config.get("route", {}).get("routes", [])
    assert isinstance(nested_routes, list), "alertmanager route.routes must be a list"

    routes = {}
    for route in nested_routes:
        match = route.get("match") or {}
        severity = match.get("severity")
        if severity:
            routes[severity] = route
    return routes


def _alertmanager_receiver_names() -> set[str]:
    config = _load_yaml(ALERTMANAGER_PATH)
    receivers = config.get("receivers", [])
    assert isinstance(receivers, list), "alertmanager receivers must be a list"
    return {receiver["name"] for receiver in receivers if "name" in receiver}


def _prometheus_alert_severities() -> set[str]:
    rules = _load_yaml(PROMETHEUS_RULES_PATH)
    severities = set()
    for group in rules.get("groups", []):
        for rule in group.get("rules", []):
            severity = rule.get("labels", {}).get("severity")
            if severity:
                severities.add(severity)
    return severities


def test_mwmbr_alert_severities_are_used_by_prometheus_rules():
    """Guard the contract introduced by R5.4 burn-rate alerts."""
    severities = _prometheus_alert_severities()

    assert {"page", "ticket"} <= severities


def test_mwmbr_alert_severities_have_explicit_alertmanager_routes():
    """Fast-burn pages and slow-burn tickets must not fall through to default."""
    routes = _alertmanager_routes_by_severity()
    receivers = _alertmanager_receiver_names()

    for severity, expected in EXPECTED_MWMBR_ROUTES.items():
        route = routes.get(severity)
        assert route is not None, f"severity={severity!r} has no explicit route"
        assert route["receiver"] == expected["receiver"]
        assert route["receiver"] in receivers
        assert route["group_wait"] == expected["group_wait"]
        assert route["repeat_interval"] == expected["repeat_interval"]
        if "group_interval" in expected:
            assert route["group_interval"] == expected["group_interval"]
