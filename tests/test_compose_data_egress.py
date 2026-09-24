#!/usr/bin/env python
#####################################################################################################################################################################################################
# Project:       Juniper
# Application:   juniper-deploy
# File Name:     test_compose_data_egress.py
# Author:        Juniper Automation
#
# Date Created:  2026-09-24
#
# License:       MIT License
# Copyright:     Copyright (c) 2024-2026 Paul Calnon
#
# Description:
#    Pins the `data-egress` network: juniper-data's outbound route, and nothing more.
#
#    Why the network exists. Since juniper-data 0.16.0 (juniper-data#421) the image carries the
#    `equities` / `equities_seq` dependencies. Those generators fetch from Yahoo Finance and SEC
#    EDGAR at request time. juniper-data's other networks, `backend` and `data`, are `internal:
#    true`. Measured on the published 0.16.0 image with one `equities_seq` request, fresh container
#    each time:
#      - with egress: `201`;
#      - on an internal network: `400 {"detail":"Invalid request parameters"}`, with
#        `Could not resolve host: query2.finance.yahoo.com` in the log.
#    So the stack advertised both generators as available and could build neither. The owner ruled
#    on 2026-09-24 for a dedicated egress network.
#
#    What must stay true, each pinned below:
#      - the network is NOT internal (internal is exactly the failure it exists to fix);
#      - ONLY juniper-data attaches (so it is juniper-data's route out, not a shared network, and
#        not a scrape path for Prometheus);
#      - juniper-data keeps `backend` and `data`, which stay internal: the egress is additive;
#      - juniper-data publishes NO port. While every network it was on was internal, a `ports:`
#        mapping could not bind. On a non-internal network it would, so the guarantee that the
#        network used to give is now asserted instead.
#
#    Pure YAML parse; no Docker daemon required.
#
#####################################################################################################################################################################################################

from __future__ import annotations

from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
COMPOSE_PATH = REPO_ROOT / "docker-compose.yml"

EGRESS = "data-egress"
DATA = "juniper-data"


def _load_compose() -> dict:
    return yaml.safe_load(COMPOSE_PATH.read_text(encoding="utf-8"))


def _service_networks(spec: dict) -> set[str]:
    """Return the set of network names a service attaches to (list or dict form)."""
    nets = spec.get("networks")
    if nets is None:
        return set()
    if isinstance(nets, dict):  # long form: `networks: {backend: {...}}`
        return set(nets.keys())
    return set(nets)  # short form: `networks: [backend, data]`


def test_data_egress_is_declared_and_not_internal() -> None:
    networks = _load_compose().get("networks") or {}
    assert EGRESS in networks, f"`{EGRESS}` is not declared: juniper-data has no outbound route, and every equities request fails at DNS"
    assert (networks[EGRESS] or {}).get("internal") is not True, f"`{EGRESS}` is internal: that blocks the Yahoo Finance / SEC EDGAR fetches this network exists to allow"


def test_only_juniper_data_attaches_to_data_egress() -> None:
    services = _load_compose()["services"]
    attached = {name for name, spec in services.items() if EGRESS in _service_networks(spec or {})}
    assert attached == {DATA}, f"`{EGRESS}` is juniper-data's outbound route alone; attached: {sorted(attached)}"


def test_juniper_data_keeps_its_internal_networks() -> None:
    compose = _load_compose()
    networks = compose.get("networks") or {}
    data_nets = _service_networks(compose["services"][DATA])
    assert {"backend", "data", EGRESS} <= data_nets, f"{DATA} networks {sorted(data_nets)}: the egress route is additive, and `backend` / `data` are how the stack reaches it"
    for name in ("backend", "data"):
        assert (networks[name] or {}).get("internal") is True, f"`{name}` must stay internal: the egress route is juniper-data's alone, not a relaxation of the shared networks"


def test_juniper_data_publishes_no_port() -> None:
    spec = _load_compose()["services"][DATA]
    assert "ports" not in spec, f"{DATA} must publish no port: on `{EGRESS}` (not internal) a `ports:` mapping would bind, so this is now the only thing keeping it unexposed"
