#!/usr/bin/env python
"""Render tests for juniper-data's HTTPS egress rule in the Helm chart.

The equities / equities_seq generators fetch from Yahoo Finance and SEC EDGAR at request time. With
``networkPolicies.enabled`` (the default), the chart's deny-all and data policies allowed data only
DNS, so every such request failed while ``/v1/generators`` reported both generators available. The
owner ruled on 2026-09-24 that the stack gets that outbound route. The compose stack has it as the
``data-egress`` network (tests/test_compose_data_egress.py); this is the k8s half.

What must stay true:
- the data policy allows TCP 443 to ``0.0.0.0/0``, excluding the ranges where cluster-internal
  services and cloud metadata live (RFC 1918, CGNAT, link-local);
- no OTHER Juniper policy gains that rule: the route belongs to data alone;
- with ``networkPolicies.enabled=false`` no policy renders at all (unchanged behaviour).

Skips when the ``helm`` binary is not available, like tests/test_helm_chart_probes.py.
"""

import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

CHART_DIR = Path(__file__).resolve().parent.parent / "k8s" / "helm" / "juniper"
RELEASE_NAME = "juniper-test"
PUBLIC_V4 = "0.0.0.0/0"
EXCLUDED = {"10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16", "100.64.0.0/10", "169.254.0.0/16"}

pytestmark = pytest.mark.skipif(
    shutil.which("helm") is None,
    reason="helm binary not available; skipping chart-render test",
)


def _render_chart(*, set_values: list[str] | None = None) -> list[dict]:
    cmd = ["helm", "template", RELEASE_NAME, str(CHART_DIR)]
    for kv in set_values or ():
        cmd += ["--set", kv]
    result = subprocess.run(cmd, capture_output=True, text=True, check=False)
    assert result.returncode == 0, f"helm template failed:\nstderr={result.stderr}\nstdout={result.stdout[:500]}"
    return [doc for doc in yaml.safe_load_all(result.stdout) if doc]


def _juniper_policies(docs: list[dict]) -> dict[str, dict]:
    """The chart's own NetworkPolicies, selected by label, not by name.

    Names depend on the release name: the fullname helper collapses a release name that already
    contains "juniper", so `juniper-test` renders `juniper-test-data`, not `juniper-test-juniper-data`.
    A name-prefix filter written the other way matched nothing and passed vacuously. The Redis
    subchart's own policy carries no `part-of` label and is not the chart's.
    """
    return {d["metadata"]["name"]: d for d in docs if d.get("kind") == "NetworkPolicy" and (d["metadata"].get("labels") or {}).get("app.kubernetes.io/part-of") == "juniper"}


def _data_policy(policies: dict[str, dict]) -> tuple[str, dict]:
    matches = [(name, pol) for name, pol in policies.items() if (pol["metadata"].get("labels") or {}).get("app.kubernetes.io/component") == "data"]
    assert len(matches) == 1, f"expected exactly one data NetworkPolicy, got {[name for name, _ in matches]} among {sorted(policies)}"
    return matches[0]


def _public_https_rules(policy: dict) -> list[dict]:
    """Egress rules that open TCP 443 to the public IPv4 range."""
    out = []
    for rule in policy["spec"].get("egress") or []:
        blocks = [peer.get("ipBlock") or {} for peer in rule.get("to") or []]
        ports = {(p.get("protocol", "TCP"), p.get("port")) for p in rule.get("ports") or []}
        if any(b.get("cidr") == PUBLIC_V4 for b in blocks) and ("TCP", 443) in ports:
            out.append(rule)
    return out


def test_data_policy_allows_https_to_public_addresses_only() -> None:
    name, policy = _data_policy(_juniper_policies(_render_chart()))
    rules = _public_https_rules(policy)
    assert len(rules) == 1, f"{name} must carry exactly one public-HTTPS egress rule (the equities fetches); found {len(rules)}"
    rule = rules[0]
    ports = {(p.get("protocol", "TCP"), p.get("port")) for p in rule.get("ports") or []}
    assert ports == {("TCP", 443)}, f"the public egress rule must open TCP 443 only, got {sorted(ports)}"
    (block,) = [peer["ipBlock"] for peer in rule["to"]]
    assert set(block.get("except") or []) == EXCLUDED, f"the public egress rule must exclude {sorted(EXCLUDED)} (cluster-internal and metadata ranges), got {sorted(block.get('except') or [])}"


def test_no_other_policy_gains_public_https() -> None:
    policies = _juniper_policies(_render_chart())
    data_name, _ = _data_policy(policies)
    others = {name for name, pol in policies.items() if name != data_name and _public_https_rules(pol)}
    assert not others, f"only {data_name} may open HTTPS to public addresses; also found in {sorted(others)}"


def test_policies_off_renders_no_policy() -> None:
    # Non-vacuity: the same selector must find the chart's policies when they are ON, or an empty
    # result below proves nothing.
    assert len(_juniper_policies(_render_chart())) >= 5, "the label selector found too few Juniper NetworkPolicies with policies ON"
    juniper = _juniper_policies(_render_chart(set_values=["networkPolicies.enabled=false"]))
    assert not juniper, f"networkPolicies.enabled=false must render no Juniper NetworkPolicy, got {sorted(juniper)}"
