#!/usr/bin/env python
"""Render tests for juniper-data's HTTPS egress rule in the Helm chart.

Several juniper-data generators fetch their data at request time: equities / equities_seq from
Yahoo Finance and SEC EDGAR, mnist and arc_agi from the Hugging Face Hub. With
``networkPolicies.enabled`` (the default), the chart's deny-all and data policies allowed data only
DNS, so every such request failed while ``/v1/generators`` reported the generators available. The
owner ruled on 2026-09-24 that the stack gets that outbound route. The compose stack has it as the
``data-egress`` network (tests/test_compose_data_egress.py); this is the k8s half.

These tests are a STATIC MODEL of part of Kubernetes' NetworkPolicy semantics, not a cluster. They
model:
- a pod's allowed egress is the union of the egress rules of every NetworkPolicy that selects it
  and governs Egress, whatever that policy's own labels;
- a pod that no Egress policy selects is unrestricted;
- a policy selects pods in its own namespace only (an unset namespace is the release namespace);
- ``policyTypes`` defaults as Kubernetes does: when empty or absent, Ingress, plus Egress only when
  the policy has egress rules.

Constructs they do not model make the render FAIL rather than pass silently:
- ``podSelector.matchExpressions``;
- a ``*List`` wrapper;
- a non-core network-policy kind;
- ``hostNetwork`` on a Juniper pod (common CNIs do not apply NetworkPolicy to it).

Juniper pods are the chart's ``part-of: juniper`` pod templates in Deployments, StatefulSets,
DaemonSets, ReplicaSets, Jobs, CronJobs and bare Pods.

What must stay true:
- the data pod is governed, and its effective egress is EXACTLY DNS plus TCP 443 (one port, no
  ``endPort``) to ``0.0.0.0/0`` excluding RFC 1918, CGNAT and link-local;
- every other Juniper pod is governed, with no ``ipBlock`` peer and no peerless non-DNS rule.
  Beyond DNS, the public route is data's alone;
- the data pod mounts no service-account token, by automount or by a projected volume. The 443
  rule reaches a public API server where one exists, and juniper-data never calls the Kubernetes
  API;
- with ``networkPolicies.enabled=false`` no NetworkPolicy, of any policy type, selects a Juniper
  pod.

Accepted limits:
- The DNS rule has no peer, so ports 53 are open to any address.
- The Redis subchart's own policy allows its pods all egress.
- Only the default values are rendered.
- Enforcement by a real CNI is not tested.

History, each version refuted by an independent validation round:
- #232's version matched the rule's wording;
- #233's judged one labelled policy at a time;
- #235's mis-defaulted ``policyTypes``, ignored namespaces and ``hostNetwork``, and weakened the
  policies-off check to Egress policies only.

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
RELEASE_NAMESPACE = "default"  # what `helm template` uses when no --namespace is given
PUBLIC_V4 = "0.0.0.0/0"
EXCLUDED = {"10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16", "100.64.0.0/10", "169.254.0.0/16"}
DNS_PORTS = [{"protocol": "UDP", "port": 53}, {"protocol": "TCP", "port": 53}]
DNS_RULE = {"ports": DNS_PORTS}
HTTPS_RULE = {"to": [{"ipBlock": {"cidr": PUBLIC_V4, "except": sorted(EXCLUDED)}}], "ports": [{"protocol": "TCP", "port": 443}]}
TEMPLATE_KINDS = ("Deployment", "StatefulSet", "DaemonSet", "ReplicaSet", "Job")

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


def _namespace(doc: dict) -> str:
    return (doc.get("metadata") or {}).get("namespace") or RELEASE_NAMESPACE


def _pod_template(doc: dict) -> dict | None:
    """The pod template (metadata + spec) a workload runs, or the Pod itself."""
    kind = doc.get("kind")
    if kind in TEMPLATE_KINDS:
        return doc["spec"]["template"]
    if kind == "CronJob":
        return doc["spec"]["jobTemplate"]["spec"]["template"]
    if kind == "Pod":
        return doc
    return None


def _juniper_pods(docs: list[dict]) -> dict[str, dict]:
    """"<kind>/<name>" -> {namespace, labels, spec} for the chart's own (part-of: juniper) pods."""
    pods = {}
    for doc in docs:
        template = _pod_template(doc)
        if template is None:
            continue
        labels = (template.get("metadata") or {}).get("labels") or {}
        if labels.get("app.kubernetes.io/part-of") == "juniper":
            pods[f"{doc['kind']}/{doc['metadata']['name']}"] = {"namespace": _namespace(doc), "labels": labels, "spec": template.get("spec") or {}}
    return pods


def _data_pod(pods: dict[str, dict]) -> tuple[str, dict]:
    matches = [(name, pod) for name, pod in pods.items() if pod["labels"].get("app.kubernetes.io/component") == "data"]
    assert len(matches) == 1, f"expected exactly one data workload, got {[name for name, _ in matches]}"
    return matches[0]


def _selects(policy: dict, pod: dict) -> bool:
    if _namespace(policy) != pod["namespace"]:
        return False
    selector = policy["spec"].get("podSelector") or {}
    assert not selector.get("matchExpressions"), f"{policy['metadata']['name']}: podSelector.matchExpressions is not modelled by these tests; extend them before using it"
    return all(pod["labels"].get(key) == value for key, value in (selector.get("matchLabels") or {}).items())


def _governs_egress(policy: dict) -> bool:
    # Kubernetes' SetDefaults_NetworkPolicy: an EMPTY or absent policyTypes means Ingress, plus
    # Egress only when the policy has at least one egress rule. `[]` is not "no types".
    types = policy["spec"].get("policyTypes") or (["Ingress", "Egress"] if policy["spec"].get("egress") else ["Ingress"])
    return "Egress" in types


def _effective_egress(docs: list[dict], pod: dict) -> tuple[list[str], list[dict]]:
    """(names of the Egress policies selecting the pod, the union of their egress rules)."""
    names, rules = [], []
    for policy in docs:
        if policy.get("kind") == "NetworkPolicy" and _governs_egress(policy) and _selects(policy, pod):
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
    name, pod = _data_pod(_juniper_pods(docs))
    policies, rules = _effective_egress(docs, pod)
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
    for name, pod in sorted(pods.items()):
        if name == data_name:
            continue
        policies, rules = _effective_egress(docs, pod)
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
    _, pod = _data_pod(_juniper_pods(_render_chart()))
    spec = pod["spec"]
    assert spec.get("automountServiceAccountToken") is False, "the data pod must set automountServiceAccountToken: false; its 443 egress reaches a public API server where one exists"
    projected = [v["name"] for v in spec.get("volumes") or [] if any("serviceAccountToken" in source for source in (v.get("projected") or {}).get("sources") or [])]
    assert not projected, f"the data pod mounts a projected service-account token through volume(s) {projected}"


def test_policies_off_leaves_no_policy_selecting_a_juniper_pod() -> None:
    # Non-vacuity: with policies ON, the data pod is governed by at least the deny-all and data
    # policies, so an empty result below is a real result.
    docs = _render_chart()
    _, data_pod = _data_pod(_juniper_pods(docs))
    assert len(_effective_egress(docs, data_pod)[0]) >= 2, "with policies ON the data pod should be selected by the deny-all and data policies"
    # ANY policy type counts here: an ungated Ingress-only policy still denies ingress with policies
    # off. #235's version counted Egress policies only.
    docs_off = _render_chart(set_values=["networkPolicies.enabled=false"])
    selecting = {name: [p["metadata"]["name"] for p in docs_off if p.get("kind") == "NetworkPolicy" and _selects(p, pod)] for name, pod in _juniper_pods(docs_off).items()}
    assert not any(selecting.values()), f"networkPolicies.enabled=false must leave no NetworkPolicy selecting a Juniper pod, got {selecting}"


def test_no_other_network_policy_kinds_are_rendered() -> None:
    others = sorted({f"{d.get('apiVersion')}/{d.get('kind')}" for d in _render_chart() if str(d.get("kind", "")).endswith("NetworkPolicy") and d.get("apiVersion") != "networking.k8s.io/v1"})
    assert not others, f"these tests model networking.k8s.io/v1 NetworkPolicy only, and cannot see {others}; extend them first"


def test_render_has_no_unmodelled_constructs() -> None:
    docs = _render_chart()
    problems = [f"{d.get('kind')} {d['metadata'].get('name')}: a List wrapper, whose items Helm applies but these tests do not read" for d in docs if str(d.get("kind", "")).endswith("List")]
    problems += [f"{name}: hostNetwork, which common CNIs exempt from NetworkPolicy" for name, pod in _juniper_pods(docs).items() if pod["spec"].get("hostNetwork")]
    assert not problems, "the render uses constructs these tests do not model:\n" + "\n".join(problems)
