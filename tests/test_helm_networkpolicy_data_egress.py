#!/usr/bin/env python
"""Render tests for juniper-data's HTTPS egress rule in the Helm chart.

Several juniper-data generators fetch their data at request time: equities / equities_seq from
Yahoo Finance and SEC EDGAR, mnist and arc_agi from the Hugging Face Hub. With
``networkPolicies.enabled`` (the default), the chart's deny-all and data policies allowed data only
DNS, so every such request failed while ``/v1/generators`` reported the generators available. The
owner ruled on 2026-09-24 that the stack gets that outbound route. The compose stack has it as the
``data-egress`` network (tests/test_compose_data_egress.py); this is the k8s half.

These tests evaluate policies the way Kubernetes does. A pod's allowed egress is the UNION of the
egress rules of EVERY NetworkPolicy that selects it and governs Egress, whatever labels the policy
itself carries. A pod that no Egress policy selects has unrestricted egress. So each test computes
a pod's effective egress from ALL rendered NetworkPolicies, not from one policy at a time.

What must stay true:
- the data pod is governed, and its effective egress is EXACTLY DNS plus TCP 443 (one port, no
  ``endPort``) to ``0.0.0.0/0`` excluding RFC 1918, CGNAT and link-local;
- every other Juniper pod is governed, and its effective egress has no ``ipBlock`` peer and no
  peerless rule other than DNS. Beyond DNS, the public route is data's alone;
- the data pod mounts no service-account token, by automount or by a projected volume. The 443
  rule reaches a public API server where one exists, and juniper-data never calls the Kubernetes
  API;
- with ``networkPolicies.enabled=false`` no NetworkPolicy selects a Juniper pod;
- no other network-policy kind (e.g. a CiliumNetworkPolicy) is rendered, because these tests
  cannot evaluate one.

Accepted limits:
- The DNS rule has no peer, so ports 53 are open to any address.
- The Redis subchart's own policy allows its pods all egress.
- Only the default values are rendered; a values override such as ``nameOverride`` is not covered.

History:
- #232 shipped tests that matched the rule's wording.
- #233's tests looked at one policy at a time, labels included. Validation passed policies that
  Kubernetes would union onto the data pod (a widened deny-all, a second or unlabelled policy, a
  widened selector) and policies that no longer apply (an empty selector, ``policyTypes:
  [Ingress]``).

Skips when the ``helm`` binary is not available, like tests/test_helm_chart_probes.py.
"""

import json
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
DNS_RULE = {"ports": DNS_PORTS}
HTTPS_RULE = {"to": [{"ipBlock": {"cidr": PUBLIC_V4, "except": sorted(EXCLUDED)}}], "ports": [{"protocol": "TCP", "port": 443}]}
WORKLOAD_KINDS = ("Deployment", "StatefulSet", "DaemonSet")

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


def _juniper_pods(docs: list[dict]) -> dict[str, dict]:
    """Workload name -> its pod template's labels, for the chart's own (part-of: juniper) pods."""
    pods = {}
    for doc in docs:
        if doc.get("kind") in WORKLOAD_KINDS:
            labels = doc["spec"]["template"]["metadata"].get("labels") or {}
            if labels.get("app.kubernetes.io/part-of") == "juniper":
                pods[doc["metadata"]["name"]] = labels
    return pods


def _data_pod(pods: dict[str, dict]) -> tuple[str, dict]:
    matches = [(name, labels) for name, labels in pods.items() if labels.get("app.kubernetes.io/component") == "data"]
    assert len(matches) == 1, f"expected exactly one data workload, got {[name for name, _ in matches]}"
    return matches[0]


def _selects(policy: dict, labels: dict) -> bool:
    selector = policy["spec"].get("podSelector") or {}
    assert not selector.get("matchExpressions"), f"{policy['metadata']['name']}: podSelector.matchExpressions is not evaluated by these tests; extend them before using it"
    return all(labels.get(key) == value for key, value in (selector.get("matchLabels") or {}).items())


def _governs_egress(policy: dict) -> bool:
    types = policy["spec"].get("policyTypes")
    if types is None:  # Kubernetes' default: Egress only when an egress section is present
        return "egress" in policy["spec"]
    return "Egress" in types


def _effective_egress(docs: list[dict], labels: dict) -> tuple[list[str], list[dict]]:
    """(names of the Egress policies selecting the pod, the union of their egress rules)."""
    names, rules = [], []
    for policy in docs:
        if policy.get("kind") == "NetworkPolicy" and _governs_egress(policy) and _selects(policy, labels):
            names.append(policy["metadata"]["name"])
            rules.extend(policy["spec"].get("egress") or [])
    return names, rules


def _canonical(rule: dict) -> str:
    """A rule as sorted JSON, with any `except` list sorted, so order is not a difference."""
    out = dict(rule)
    if "to" in out:
        peers = []
        for peer in out["to"] or []:
            block = peer.get("ipBlock")
            if block is not None and "except" in block:
                peer = {**peer, "ipBlock": {**block, "except": sorted(block["except"])}}
            peers.append(peer)
        out["to"] = peers
    return json.dumps(out, sort_keys=True)


def test_data_pod_effective_egress_is_exactly_dns_and_public_https() -> None:
    docs = _render_chart()
    name, labels = _data_pod(_juniper_pods(docs))
    policies, rules = _effective_egress(docs, labels)
    assert policies, f"no Egress NetworkPolicy selects {name}, so its egress is unrestricted"
    effective = {_canonical(rule) for rule in rules}
    expected = {_canonical(DNS_RULE), _canonical(HTTPS_RULE)}
    assert effective == expected, (
        f"{name}'s effective egress (the union over {policies}) must be exactly DNS plus TCP 443 to {PUBLIC_V4} "
        f"excluding {sorted(EXCLUDED)}; extra: {sorted(effective - expected)}; missing: {sorted(expected - effective)}"
    )


def test_other_juniper_pods_have_no_public_or_unscoped_egress() -> None:
    docs = _render_chart()
    pods = _juniper_pods(docs)
    data_name, _ = _data_pod(pods)
    problems = []
    for name, labels in sorted(pods.items()):
        if name == data_name:
            continue
        policies, rules = _effective_egress(docs, labels)
        if not policies:
            problems.append(f"{name}: no Egress NetworkPolicy selects it, so its egress is unrestricted")
        for rule in rules:
            peers = rule.get("to") or []
            if any("ipBlock" in peer for peer in peers):
                problems.append(f"{name}: an ipBlock egress peer {peers} (via {policies})")
            if not peers and rule.get("ports") != DNS_PORTS:
                problems.append(f"{name}: a peerless egress rule that is not DNS-only {rule} (via {policies})")
    assert not problems, "beyond DNS, only the data pod may reach addresses outside the cluster's pods:\n" + "\n".join(problems)


def test_data_pod_mounts_no_service_account_token() -> None:
    docs = _render_chart()
    deployments = [d for d in docs if d.get("kind") in WORKLOAD_KINDS and (d["spec"]["template"]["metadata"].get("labels") or {}).get("app.kubernetes.io/component") == "data"]
    assert len(deployments) == 1, f"expected exactly one data workload, got {[d['metadata']['name'] for d in deployments]}"
    pod_spec = deployments[0]["spec"]["template"]["spec"]
    assert pod_spec.get("automountServiceAccountToken") is False, "the data pod must set automountServiceAccountToken: false; its 443 egress reaches a public API server where one exists"
    projected = [v["name"] for v in pod_spec.get("volumes") or [] if any("serviceAccountToken" in source for source in (v.get("projected") or {}).get("sources") or [])]
    assert not projected, f"the data pod mounts a projected service-account token through volume(s) {projected}"


def test_policies_off_leaves_no_policy_selecting_a_juniper_pod() -> None:
    # Non-vacuity: with policies ON, the data pod is governed by at least the deny-all and data
    # policies, so an empty result below is a real result.
    docs = _render_chart()
    _, data_labels = _data_pod(_juniper_pods(docs))
    assert len(_effective_egress(docs, data_labels)[0]) >= 2, "with policies ON the data pod should be selected by the deny-all and data policies"
    docs_off = _render_chart(set_values=["networkPolicies.enabled=false"])
    selecting = {name: _effective_egress(docs_off, labels)[0] for name, labels in _juniper_pods(docs_off).items()}
    assert not any(selecting.values()), f"networkPolicies.enabled=false must leave no NetworkPolicy selecting a Juniper pod, got {selecting}"


def test_no_other_network_policy_kinds_are_rendered() -> None:
    others = sorted({f"{d.get('apiVersion')}/{d.get('kind')}" for d in _render_chart() if str(d.get("kind", "")).endswith("NetworkPolicy") and d.get("apiVersion") != "networking.k8s.io/v1"})
    assert not others, f"these tests evaluate networking.k8s.io/v1 NetworkPolicy only, and cannot see {others}; extend them first"
