#!/usr/bin/env python3
"""
Compare what GHCR serves for a Juniper image tag NOW with what the local daemon holds under it.

Project: juniper-deploy
Sub-Project: ad-hoc tooling
Author: Paul Calnon
Created: 2026-10-08
Status: ad-hoc — investigation
Retire when: a permanent doctor/preflight compares local tags with the registry's digests
Related: W1.11 (juniper-ml notes/JUNIPER_2026-10-03_JUNIPER-RECURRENCE_EQUITIES-END-TO-END-AUDIT-AND-DEVELOPMENT-PLAN.md);
         scripts/test_canopy_recurrence_smoke.sh --published, which this finding motivated

For each ghcr.io/pcalnon/<repo>:<tag> given, prints the registry's index digest and the
linux/amd64 manifest digest it lists, next to the local tag's RepoDigests and its
org.opencontainers.image.revision label. A local tag whose digest is not the registry's is not
the published artifact, whatever its name says. Under Docker's containerd image store a LOCAL
BUILD also shows a RepoDigest, so the comparison has to be against the registry, not against
"has a digest". Anonymous and read-only: one token request and one manifest GET per tag.

Measured 2026-10-08 on the host this was written on: juniper-data:0.16.0, juniper-recurrence:0.5.0,
juniper-canopy:0.8.1 and juniper-cascor:0.11.0 were ALL local builds (revisions 29be6d3, be081fa,
1b2dd438, 95cdc56), and none matched GHCR.

Usage:
    python3 util/ad-hoc/2026-10-08_ghcr_tag_digest_probe.py ghcr.io/pcalnon/juniper-recurrence:0.5.0 [...]
"""

from __future__ import annotations

import json
import subprocess
import sys
import urllib.request

INDEX_TYPES = ", ".join(
    [
        "application/vnd.oci.image.index.v1+json",
        "application/vnd.docker.distribution.manifest.list.v2+json",
        "application/vnd.oci.image.manifest.v1+json",
        "application/vnd.docker.distribution.manifest.v2+json",
    ]
)


def _get(url: str, token: str | None = None, accept: str | None = None) -> tuple[dict, str]:
    headers = {}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if accept:
        headers["Accept"] = accept
    request = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(request, timeout=30) as response:  # nosec B310 - fixed https registry URL
        return json.loads(response.read()), response.headers.get("Docker-Content-Digest", "")


def probe(ref: str) -> None:
    name, tag = ref.rsplit(":", 1)
    repo = name.split("/", 1)[1]
    token = _get(f"https://ghcr.io/token?scope=repository:{repo}:pull")[0]["token"]
    index, index_digest = _get(f"https://ghcr.io/v2/{repo}/manifests/{tag}", token, INDEX_TYPES)
    amd64 = [m.get("digest") for m in index.get("manifests", []) if (m.get("platform") or {}).get("architecture") == "amd64" and (m.get("platform") or {}).get("os") == "linux"]
    local = subprocess.run(["docker", "image", "inspect", "--format", '{{json .RepoDigests}}|{{index .Config.Labels "org.opencontainers.image.revision"}}', ref], capture_output=True, text=True)
    local_digests, _, local_revision = local.stdout.strip().partition("|")
    print(ref)
    print(f"  registry index digest : {index_digest}")
    print(f"  registry amd64 digest : {amd64[0] if amd64 else '(no amd64 entry)'}")
    print(f"  local RepoDigests     : {local_digests or '(not present locally)'}")
    print(f"  local revision label  : {local_revision or '(none)'}")
    matches = bool(index_digest) and index_digest in local_digests
    print(f"  local tag IS the published index: {matches}")


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__ or "usage: probe REF [REF ...]")
        return 2
    for ref in sys.argv[1:]:
        probe(ref)
    return 0


if __name__ == "__main__":
    sys.exit(main())
