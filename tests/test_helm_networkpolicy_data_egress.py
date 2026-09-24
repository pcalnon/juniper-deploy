#!/usr/bin/env python
"""Render tests for juniper-data's HTTPS egress rule in the Helm chart.

Several juniper-data generators fetch their data at request time: equities / equities_seq from
Yahoo Finance and SEC EDGAR, mnist and arc_agi from the Hugging Face Hub. With
``networkPolicies.enabled`` (the default), the chart's deny-all and data policies allowed data only
DNS, so every such request failed while ``/v1/generators`` reported the generators available. The
owner ruled on 2026-09-24 that the stack gets that outbound route. The compose stack has it as the
``data-egress`` network (tests/test_compose_data_egress.py); this is the k8s half.

What must stay true (each is pinned below):
- the data policy's egress is EXACTLY two rules: DNS, and TCP 443 (a single port, no ``endPort``)
  to ``0.0.0.0/0`` excluding RFC 1918, CGNAT and link-local. Pinning the whole set, not just
  "a 443 rule exists", is what stops a broader rule riding alongside it;
- no OTHER Juniper policy has an ``ipBlock`` egress peer, or a peerless egress rule other than DNS:
  the public route is data's alone, in any spelling (``::/0``, split ``/1`` blocks, a named port);
- the data pod mounts no service-account token. The 443 rule reaches a public API server, where one
  exists, and juniper-data never calls the Kubernetes API;
- with ``networkPolicies.enabled=false`` the chart renders none of its own policies. The Redis
  subchart still renders its own policy, which is not the chart's and is excluded by label.

Skips when the ``helm`` binary is not available, like tests/test_helm_chart_probes.py.

History: #232 shipped ``test_data_policy_allows_https_to_public_addresses_only``,
``test_no_other_policy_gains_public_https``, ``test_policies_off_renders_no_policy`` and a
``_public_https_rules`` helper. Validation showed eight strictly broader rules passing them, because
they matched the rule's wording (an ``endPort``, a peerless rule, ``::/0``, two ``/1`` halves, a named
port). The tests above replace them, and their names say what each one now pins.
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
DNS_PORTS = [{"protocol": "UDP", "port": 53}, {"protocol": "TCP", "port": 53}]
HTTPS_RULE = {"to": [{"ipBlock": {"cidr": PUBLIC_V4, "except": sorted(EXCLUDED)}}], "ports": [{"protocol": "TCP", "port": 443}]}

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


def _is_juniper(doc: dict) -> bool:
    return (doc["metadata"].get("labels") or {}).get("app.kubernetes.io/part-of") == "juniper"


def _juniper_policies(docs: list[dict]) -> dict[str, dict]:
    """The chart's own NetworkPolicies, selected by label, not by name.

    Names depend on the release name: the fullname helper collapses a release name that already
    contains "juniper", so `juniper-test` renders `juniper-test-data`, not `juniper-test-juniper-data`.
    A name-prefix filter written the other way matched nothing and passed vacuously. The Redis
    subchart's own policy carries no `part-of` label and is not the chart's.
    """
    return {d["metadata"]["name"]: d for d in docs if d.get("kind") == "NetworkPolicy" and _is_juniper(d)}


def _component(doc: dict) -> str | None:
    return (doc["metadata"].get("labels") or {}).get("app.kubernetes.io/component")


def _data_policy(policies: dict[str, dict]) -> tuple[str, dict]:
    matches = [(name, pol) for name, pol in policies.items() if _component(pol) == "data"]
    assert len(matches) == 1, f"expected exactly one data NetworkPolicy, got {[name for name, _ in matches]} among {sorted(policies)}"
    return matches[0]


def _normalised(rule: dict) -> dict:
    """A rule with its `except` list sorted, so an order change is not a difference."""
    out = {}
    for key, value in rule.items():
        if key == "to":
            peers = []
            for peer in value or []:
                block = peer.get("ipBlock")
                if block is not None and "except" in block:
                    peer = {**peer, "ipBlock": {**block, "except": sorted(block["except"])}}
                peers.append(peer)
            out[key] = peers
        else:
            out[key] = value
    return out


def test_data_policy_egress_is_exactly_dns_and_public_https() -> None:
    name, policy = _data_policy(_juniper_policies(_render_chart()))
    egress = [_normalised(rule) for rule in policy["spec"].get("egress") or []]
    expected = [{"ports": DNS_PORTS}, HTTPS_RULE]
    assert egress == expected, (
        f"{name}'s egress must be exactly DNS plus TCP 443 to {PUBLIC_V4} excluding {sorted(EXCLUDED)}, "
        f"with no endPort and no other rule; rendered:\n{yaml.safe_dump(egress, sort_keys=False)}"
    )


def test_no_other_policy_has_ip_block_or_peerless_non_dns_egress() -> None:
    policies = _juniper_policies(_render_chart())
    data_name, _ = _data_policy(policies)
    problems = []
    for name, policy in sorted(policies.items()):
        if name == data_name:
            continue
        for rule in policy["spec"].get("egress") or []:
            peers = rule.get("to") or []
            if any("ipBlock" in peer for peer in peers):
                problems.append(f"{name}: an ipBlock egress peer {peers}")
            if not peers and rule.get("ports") != DNS_PORTS:
                problems.append(f"{name}: a peerless egress rule that is not DNS-only {rule}")
    assert not problems, "only the data policy may open egress to addresses outside the cluster's pods:\n" + "\n".join(problems)


def test_data_pod_mounts_no_service_account_token() -> None:
    docs = _render_chart()
    deployments = [d for d in docs if d.get("kind") == "Deployment" and _is_juniper(d) and _component(d) == "data"]
    assert len(deployments) == 1, f"expected exactly one data Deployment, got {[d['metadata']['name'] for d in deployments]}"
    pod_spec = deployments[0]["spec"]["template"]["spec"]
    assert pod_spec.get("automountServiceAccountToken") is False, "the data pod must set automountServiceAccountToken: false; its 443 egress reaches a public API server where one exists"


def test_policies_off_renders_none_of_the_charts_policies() -> None:
    # Non-vacuity: the same selector must find the chart's policies when they are ON, or an empty
    # result below proves nothing.
    assert len(_juniper_policies(_render_chart())) >= 5, "the label selector found too few Juniper NetworkPolicies with policies ON"
    juniper = _juniper_policies(_render_chart(set_values=["networkPolicies.enabled=false"]))
    assert not juniper, f"networkPolicies.enabled=false must render none of the chart's NetworkPolicies, got {sorted(juniper)}"
