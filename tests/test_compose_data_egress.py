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
#    (juniper-deploy#231; hardened after independent validation found four gaps in the first
#    version's guards.)
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
#    The same isolation broke mnist and arc_agi, which fetch from the Hugging Face Hub: with no
#    network they answer `500` after about 23 s (measured the same way, 2026-09-24).
#
#    What must stay true, each pinned below:
#      - the network is NOT internal and does not disable IP masquerade, as LITERAL values:
#        a quoted or interpolated value can resolve to internal at `up` time (either would be
#        exactly the failure it exists to fix);
#      - ONLY juniper-data attaches (so it is juniper-data's route out, not a shared network, and
#        not a scrape path for Prometheus);
#      - every service attaches to declared networks by name. A `network_mode: service:` sidecar
#        would share juniper-data's egress without naming it, and a service with no `networks:`
#        lands on an undeclared network with dynamic addressing;
#      - juniper-data is on exactly `backend`, `data` and `data-egress`, and the first two stay
#        internal: the egress is additive, and another non-internal network would be a new
#        exposure;
#      - juniper-data publishes NO port. While every network it was on was internal, a `ports:`
#        mapping could not bind. On a non-internal network it would, so the guarantee that the
#        network used to give is now asserted instead. (Publishing is not the only way in:
#        see the network's definition in docker-compose.yml for direct routing on Docker < 28.)
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
# The whole definition, pinned. Any other key can undo the route: `internal`, masquerade or
# `gateway_mode_ipv4` driver options, `inhibit_ipv4`, a different driver, or an interpolation of
# any of them. So this does not list the bad keys; it pins the only good definition.
EGRESS_DEFINITION = {"driver": "bridge", "ipam": {"config": [{"subnet": "172.27.0.0/16"}]}}


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
    # Pinned EXACTLY (EGRESS_DEFINITION). #234 checked `internal` and masquerade as literal values,
    # and validation then passed `gateway_mode_ipv4: routed` (no NAT), `inhibit_ipv4`, the
    # `nat-unprotected` mode (it reopens direct routing to unpublished ports) and interpolated
    # variants of each. A pin catches all of them, and any future one.
    networks = _load_compose().get("networks") or {}
    assert EGRESS in networks, f"`{EGRESS}` is not declared: juniper-data has no outbound route, and every equities request fails at DNS"
    assert networks[EGRESS] == EGRESS_DEFINITION, f"`{EGRESS}` must be exactly {EGRESS_DEFINITION}, got {networks[EGRESS]!r}. Any other key can block the Yahoo Finance / SEC EDGAR / Hugging Face fetches or reopen direct routing; change the pin only as a deliberate decision"


def test_only_juniper_data_attaches_to_data_egress() -> None:
    services = _load_compose()["services"]
    attached = {name for name, spec in services.items() if EGRESS in _service_networks(spec or {})}
    assert attached == {DATA}, f"`{EGRESS}` is juniper-data's outbound route alone; attached: {sorted(attached)}"


def test_every_service_declares_its_networks() -> None:
    # A `network_mode: service:juniper-data` sidecar shares juniper-data's namespace, and with it
    # the egress route, without naming `data-egress`. A service with no `networks:` key, or with
    # `network_mode: bridge|host`, lands on a network the compose file does not declare, with
    # dynamic addressing: the drift the static subnets (D5) exist to stop.
    # A network NAMED but not declared (e.g. `default`) is the same drift, so each name must be one
    # of the compose file's own networks.
    compose = _load_compose()
    declared = set((compose.get("networks") or {}).keys())
    problems = []
    for name, spec in sorted(compose["services"].items()):
        spec = spec or {}
        if "network_mode" in spec:
            problems.append(f"{name}: network_mode {spec['network_mode']!r}")
        nets = _service_networks(spec)
        if not nets:
            problems.append(f"{name}: no `networks:`")
        if nets - declared:
            problems.append(f"{name}: undeclared network(s) {sorted(nets - declared)}")
    assert not problems, "every service must attach to declared networks by name:\n" + "\n".join(problems)


def test_no_service_uses_extends() -> None:
    # `extends` merges the base service's `networks`, so `extends: {service: juniper-data}` would
    # put a second service on `data-egress` while its own definition names only `backend`. The
    # attachment checks read each service's own keys, so they cannot see an inherited network. No
    # service uses `extends` today; forbidding it keeps every attachment visible.
    users = sorted(name for name, spec in _load_compose()["services"].items() if "extends" in (spec or {}))
    assert not users, f"services using `extends` hide inherited networks from these checks: {users}"


def test_juniper_data_keeps_its_internal_networks() -> None:
    compose = _load_compose()
    networks = compose.get("networks") or {}
    data_nets = _service_networks(compose["services"][DATA])
    # EXACT set: joining `frontend` too would give juniper-data a second non-internal network,
    # reachable by everything on it, which is a different decision from an outbound route.
    assert data_nets == {"backend", "data", EGRESS}, f"{DATA} networks {sorted(data_nets)}: expected exactly backend, data and {EGRESS}. The egress route is additive, `backend` / `data` are how the stack reaches it, and any other network is a new exposure"
    for name in ("backend", "data"):
        assert (networks[name] or {}).get("internal") is True, f"`{name}` must stay internal (the literal true): the egress route is juniper-data's alone, not a relaxation of the shared networks"


def test_juniper_data_publishes_no_port() -> None:
    spec = _load_compose()["services"][DATA]
    assert "ports" not in spec, f"{DATA} must publish no port: on `{EGRESS}` (not internal) a `ports:` mapping would bind, so this is now the only thing keeping it unexposed"
