#!/usr/bin/env python
"""Decision tests for scripts/verify_published_images.py.

tests/test_published_image_refs.py pins the compose SHAPE and that ``_semver``
orders tuples of ints. It never runs the gate. Two decisions therefore had no
test, and both have already failed in production:

- Existence (#217). A tag that 404s, or a multi-arch tag that is missing
  linux's amd64 or arm64, must exit 1. A 404 is an answer and must not be
  retried; a 5xx is not an answer and must be retried. The 2026-09-15 incident
  this encodes: an anonymous token request timed out once in five, and a
  hard-failing gate that flakes is a gate people re-run instead of read.
- Currency (#226). A pin can resolve and carry both arches and still be a
  release behind. That is how juniper-canopy:0.8.0 stayed pinned for three days
  after 0.8.1 shipped, with this gate green the whole time. Staleness is
  advisory by default and an error only under ``--fail-on-stale``. A tag-list
  outage must not turn the existence gate red.

Offline: ``_get`` is replaced, or ``urlopen`` is. Nothing here contacts ghcr.io.
"""

from __future__ import annotations

import importlib.util
import json
import sys
import urllib.error
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
VERIFY_SCRIPT = REPO_ROOT / "scripts" / "verify_published_images.py"

CANOPY = "ghcr.io/pcalnon/juniper-canopy:0.8.0"
DATA = "ghcr.io/pcalnon/juniper-data:0.16.0"

BOTH_ARCHES = {
    "manifests": [
        {"platform": {"architecture": "amd64", "os": "linux"}},
        {"platform": {"architecture": "arm64", "os": "linux"}},
    ]
}


@pytest.fixture(scope="module")
def verify():
    """Import the script by path; it is not an installed module."""
    spec = importlib.util.spec_from_file_location("verify_published_images_policy", VERIFY_SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.modules["verify_published_images_policy"] = module
    spec.loader.exec_module(module)
    return module


def _http_error(url: str, code: int) -> urllib.error.HTTPError:
    """A synthetic HTTP error whose (empty) body is already closed.

    Python 3.14 emits ``ResourceWarning: Implicitly cleaning up <HTTPError ...>`` when an unclosed
    HTTPError is garbage-collected, and this repo's ``filterwarnings = ["error"]`` turns that into a
    failure in whichever test happens to be running at collection time. The code under test reads
    only ``.code``, so closing the body up front changes nothing it observes.
    """
    err = urllib.error.HTTPError(url, code, "synthetic", None, None)
    err.close()
    return err


def _write_compose(tmp_path: Path, services: dict[str, object]) -> Path:
    """Minimal compose. Values may be a string image or a non-string to be ignored."""
    lines = ["services:"]
    for name, image in services.items():
        lines.append(f"  {name}:")
        if isinstance(image, str):
            lines.append(f"    image: {image}")
        elif image is None:
            lines.append("    image:")
        else:
            # A mapping or list is not an image ref; the parser must skip it.
            lines.append(f"    image: {json.dumps(image)}")
    path = tmp_path / "compose.yml"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


class _Resp:
    def __init__(self, payload: bytes):
        self._payload = payload

    def read(self, _n: int = -1) -> bytes:
        return self._payload

    def __enter__(self):
        return self

    def __exit__(self, *_exc) -> bool:
        return False


def _install_registry(monkeypatch, verify, *, tags_by_repo: dict[str, list[str]] | Exception, manifest=None, on_manifest: Exception | None = None):
    """Replace ``_get``. Record every URL so a skipped query is visible."""
    seen: list[str] = []

    def _get(url: str, token: str | None = None, accept: str | None = None, attempts: int = 3):
        seen.append(url)
        if "/token?" in url:
            return {"token": "t"}
        if "/tags/list" in url:
            if isinstance(tags_by_repo, Exception):
                raise tags_by_repo
            repo = url.split("/v2/", 1)[1].split("/tags/list", 1)[0]
            return {"tags": tags_by_repo[repo]}
        if on_manifest is not None:
            raise on_manifest
        return BOTH_ARCHES if manifest is None else manifest

    monkeypatch.setattr(verify, "_get", _get)
    return seen


def _run(monkeypatch, verify, compose: Path, *extra: str) -> int:
    monkeypatch.setattr(sys, "argv", ["verify_published_images.py", "--compose", str(compose), *extra])
    return verify.main()


# ── registry GET: retry policy ──────────────────────────────────────────────


def test_client_error_is_not_retried(monkeypatch, verify) -> None:
    """A 404 is the answer 'not published'. Retrying it only slows the failure."""
    calls: list[str] = []
    sleeps: list[int] = []

    def urlopen(req, timeout=30):
        calls.append(req.full_url)
        raise _http_error(req.full_url, 404)

    monkeypatch.setattr(verify.urllib.request, "urlopen", urlopen)
    monkeypatch.setattr(verify.time, "sleep", lambda seconds: sleeps.append(seconds))

    with pytest.raises(urllib.error.HTTPError) as exc:
        verify._get("https://ghcr.io/v2/pcalnon/juniper-canopy/manifests/0.8.0")

    assert exc.value.code == 404
    assert calls == ["https://ghcr.io/v2/pcalnon/juniper-canopy/manifests/0.8.0"]
    assert sleeps == []


def test_server_error_is_retried_then_parsed(monkeypatch, verify) -> None:
    """A 5xx says nothing about the tag. The next attempt's body is the result."""
    calls = {"n": 0}
    sleeps: list[int] = []

    def urlopen(req, timeout=30):
        calls["n"] += 1
        assert req.get_header("Authorization") == "Bearer t"
        assert "oci.image.index" in (req.get_header("Accept") or "")
        if calls["n"] == 1:
            raise _http_error(req.full_url, 503)
        return _Resp(b'{"token": "t"}')

    monkeypatch.setattr(verify.urllib.request, "urlopen", urlopen)
    monkeypatch.setattr(verify.time, "sleep", lambda seconds: sleeps.append(seconds))

    assert verify._get("https://ghcr.io/v2/x", token="t", accept="application/vnd.oci.image.index.v1+json") == {"token": "t"}
    assert calls["n"] == 2
    assert sleeps == [1]  # 2**0, and no sleep after the success


def test_transport_errors_retry_then_raise_the_last(monkeypatch, verify) -> None:
    calls = {"n": 0}
    sleeps: list[int] = []

    def urlopen(req, timeout=30):
        calls["n"] += 1
        raise urllib.error.URLError("timed out")

    monkeypatch.setattr(verify.urllib.request, "urlopen", urlopen)
    monkeypatch.setattr(verify.time, "sleep", lambda seconds: sleeps.append(seconds))

    with pytest.raises(urllib.error.URLError, match="timed out"):
        verify._get("https://ghcr.io/token")

    assert calls["n"] == 3
    assert sleeps == [1, 2]  # not after the final attempt


def test_invalid_json_is_retried(monkeypatch, verify) -> None:
    """A truncated body is a ValueError, which is transient, not 'the tag is missing'."""
    bodies = [b"not-json", b'{"ok": 1}']

    def urlopen(req, timeout=30):
        return _Resp(bodies.pop(0))

    monkeypatch.setattr(verify.urllib.request, "urlopen", urlopen)
    monkeypatch.setattr(verify.time, "sleep", lambda _seconds: None)

    assert verify._get("https://ghcr.io/v2/x") == {"ok": 1}
    assert bodies == []


# ── manifest arches ─────────────────────────────────────────────────────────


def test_manifest_404_is_not_published(monkeypatch, verify) -> None:
    err = _http_error("https://ghcr.io/v2/pcalnon/juniper-canopy/manifests/0.8.0", 404)
    seen = _install_registry(monkeypatch, verify, tags_by_repo={}, on_manifest=err)

    ok, detail = verify.manifest_arches(CANOPY)

    assert ok is False
    assert detail == "MANIFEST NOT FOUND — this tag was never published"
    assert not any("/tags/list" in url for url in seen)


def test_manifest_http_status_is_named(monkeypatch, verify) -> None:
    err = _http_error("https://ghcr.io/v2/pcalnon/juniper-canopy/manifests/0.8.0", 401)
    _install_registry(monkeypatch, verify, tags_by_repo={}, on_manifest=err)

    ok, detail = verify.manifest_arches(CANOPY)

    assert ok is False
    assert detail == "HTTP 401 reading the manifest"


def test_token_failure_does_not_query_the_manifest(monkeypatch, verify) -> None:
    seen: list[str] = []

    def _get(url: str, token=None, accept=None, attempts=3):
        seen.append(url)
        raise urllib.error.URLError("timed out")

    monkeypatch.setattr(verify, "_get", _get)
    ok, detail = verify.manifest_arches(CANOPY)

    assert ok is False
    assert "could not obtain a pull token" in detail
    assert len(seen) == 1


def test_missing_token_field_is_a_token_failure(monkeypatch, verify) -> None:
    def _get(url: str, token=None, accept=None, attempts=3):
        return {}

    monkeypatch.setattr(verify, "_get", _get)
    ok, detail = verify.manifest_arches(CANOPY)
    assert ok is False
    assert "could not obtain a pull token" in detail


@pytest.mark.parametrize(
    "index",
    [{}, {"manifests": []}, {"manifests": None}],
)
def test_index_without_a_manifest_list_is_single_arch(monkeypatch, verify, index) -> None:
    _install_registry(monkeypatch, verify, tags_by_repo={}, manifest=index)
    ok, detail = verify.manifest_arches(CANOPY)
    assert ok is False
    assert "single-arch" in detail


def test_one_required_arch_is_named_as_missing(monkeypatch, verify) -> None:
    index = {
        "manifests": [
            {"platform": {"architecture": "amd64", "os": "linux"}},
            {"platform": {"architecture": "unknown", "os": "unknown"}},
            {"platform": {"architecture": "AMD64", "os": "linux"}},
        ]
    }
    _install_registry(monkeypatch, verify, tags_by_repo={}, manifest=index)

    ok, detail = verify.manifest_arches(CANOPY)

    assert ok is False
    # unknown is not an architecture, and the comparison is exact: AMD64 is not amd64.
    assert detail == "missing ['arm64'] (has ['AMD64', 'amd64'])"


def test_both_required_arches_pass_with_an_extra(monkeypatch, verify) -> None:
    index = {
        "manifests": [
            {"platform": {"architecture": "arm64", "os": "linux"}},
            {"platform": {"architecture": "amd64", "os": "linux"}},
            {"platform": {"architecture": "ppc64le", "os": "linux"}},
            {"platform": {}},
        ]
    }
    _install_registry(monkeypatch, verify, tags_by_repo={}, manifest=index)
    ok, detail = verify.manifest_arches(CANOPY)
    assert ok is True
    assert detail == "arches=amd64,arm64,ppc64le"


# ── latest published tag ────────────────────────────────────────────────────


def test_latest_published_orders_numerically_and_ignores_non_releases(monkeypatch, verify) -> None:
    """``max`` of the strings would pick v0.8.0 or 0.9.10 over 0.10.0.

    "0.10.0" < "0.9.0" lexicographically, and "0.10.0" < "0.9.10" as well.
    """
    tags = ["0.9.0", "0.10.0", "0.9.10", "latest", "0.9", "1.2.3-rc1", "v0.8.0", "", "dispatch-9890a23"]
    _install_registry(monkeypatch, verify, tags_by_repo={"pcalnon/juniper-canopy": tags})

    best, detail = verify.latest_published("pcalnon/juniper-canopy")

    assert best == (0, 10, 0)
    assert detail == "0.10.0"


@pytest.mark.parametrize(
    ("body_tags", "expected"),
    [
        ([], "no X.Y.Z tags published"),
        (None, "no X.Y.Z tags published"),
        (["latest", "main", "0.8"], "no X.Y.Z tags published"),
    ],
)
def test_no_release_tags_is_undetermined(monkeypatch, verify, body_tags, expected) -> None:
    def _get_body(url: str, token=None, accept=None, attempts=3):
        if "/token?" in url:
            return {"token": "t"}
        if body_tags is None:
            return {"tags": None}
        return {"tags": body_tags}

    monkeypatch.setattr(verify, "_get", _get_body)
    best, detail = verify.latest_published("pcalnon/juniper-canopy")
    assert best is None
    assert detail == expected


def test_tag_list_http_error_names_the_status(monkeypatch, verify) -> None:
    err = _http_error("https://ghcr.io/v2/pcalnon/juniper-canopy/tags/list", 404)
    _install_registry(monkeypatch, verify, tags_by_repo=err)

    best, detail = verify.latest_published("pcalnon/juniper-canopy")

    assert best is None
    assert detail == "HTTP 404 reading the tag list"


def test_tag_list_transport_error_is_undetermined(monkeypatch, verify) -> None:
    _install_registry(monkeypatch, verify, tags_by_repo=urllib.error.URLError("reset"))
    best, detail = verify.latest_published("pcalnon/juniper-canopy")
    assert best is None
    assert "could not read the tag list" in detail


# ── main(): the policy the shape tests do not execute ──────────────────────


def test_stale_pin_is_advisory_by_default(monkeypatch, verify, tmp_path, capsys) -> None:
    compose = _write_compose(tmp_path, {"juniper-canopy": CANOPY})
    seen = _install_registry(monkeypatch, verify, tags_by_repo={"pcalnon/juniper-canopy": ["0.8.0", "0.8.1", "latest"]})

    assert _run(monkeypatch, verify, compose) == 0
    out = capsys.readouterr()
    assert "::warning::STALE PIN — 0.8.1 is published, this pins 0.8.0" in out.out
    assert "1 of 1 pins are BEHIND" in out.out
    assert "advisory" in out.out
    assert "--fail-on-stale given" not in out.err
    assert any("/tags/list" in url for url in seen)


def test_fail_on_stale_exits_1_and_names_every_stale_ref(monkeypatch, verify, tmp_path, capsys) -> None:
    compose = _write_compose(
        tmp_path,
        {
            "juniper-canopy": CANOPY,
            "juniper-data": DATA,
        },
    )
    _install_registry(
        monkeypatch,
        verify,
        tags_by_repo={
            "pcalnon/juniper-canopy": ["0.8.1"],
            "pcalnon/juniper-data": ["0.16.1", "0.9.0"],
        },
    )

    assert _run(monkeypatch, verify, compose, "--fail-on-stale") == 1
    out = capsys.readouterr()
    assert "2 of 2 pins are BEHIND" in out.out
    assert f"{CANOPY}  ->  0.8.1 available" in out.out
    assert f"{DATA}  ->  0.16.1 available" in out.out
    assert "--fail-on-stale given: treating staleness as an error" in out.err


def test_no_currency_does_not_read_the_tag_list(monkeypatch, verify, tmp_path, capsys) -> None:
    compose = _write_compose(tmp_path, {"juniper-canopy": CANOPY})
    seen = _install_registry(monkeypatch, verify, tags_by_repo={"pcalnon/juniper-canopy": ["0.9.0"]})

    assert _run(monkeypatch, verify, compose, "--no-currency") == 0
    out = capsys.readouterr()
    assert "STALE" not in out.out
    assert not any("/tags/list" in url for url in seen)


def test_equal_version_is_current(monkeypatch, verify, tmp_path, capsys) -> None:
    """``newest >= pinned`` would call the current release stale."""
    compose = _write_compose(tmp_path, {"juniper-canopy": CANOPY})
    _install_registry(monkeypatch, verify, tags_by_repo={"pcalnon/juniper-canopy": ["0.8.0"]})

    assert _run(monkeypatch, verify, compose) == 0
    out = capsys.readouterr()
    assert "currency: current (latest published is 0.8.0)" in out.out
    assert "STALE" not in out.out
    assert "BEHIND" not in out.out


def test_pin_ahead_of_the_registry_is_not_stale(monkeypatch, verify, tmp_path, capsys) -> None:
    """Only ``newest > pinned`` is stale. A registry that lags the pin is current."""
    ahead = "ghcr.io/pcalnon/juniper-canopy:0.8.1"
    compose = _write_compose(tmp_path, {"juniper-canopy": ahead})
    _install_registry(monkeypatch, verify, tags_by_repo={"pcalnon/juniper-canopy": ["0.8.0"]})

    assert _run(monkeypatch, verify, compose) == 0
    assert "currency: current (latest published is 0.8.0)" in capsys.readouterr().out


def test_tag_list_outage_does_not_fail_an_existing_pin(monkeypatch, verify, tmp_path, capsys) -> None:
    compose = _write_compose(tmp_path, {"juniper-canopy": CANOPY})
    err = _http_error("https://ghcr.io/v2/pcalnon/juniper-canopy/tags/list", 503)
    _install_registry(monkeypatch, verify, tags_by_repo=err)

    assert _run(monkeypatch, verify, compose) == 0
    out = capsys.readouterr()
    assert "currency: not determined — HTTP 503 reading the tag list" in out.out
    assert "BEHIND" not in out.out
    assert out.err == ""


def test_missing_manifest_fails_and_skips_currency(monkeypatch, verify, tmp_path, capsys) -> None:
    compose = _write_compose(tmp_path, {"juniper-canopy": CANOPY, "juniper-data": DATA})
    seen = _install_registry(
        monkeypatch,
        verify,
        tags_by_repo={"pcalnon/juniper-data": ["0.16.0"]},
        on_manifest=_http_error("https://ghcr.io/manifests", 404),
    )

    assert _run(monkeypatch, verify, compose) == 1
    out = capsys.readouterr()
    assert "MANIFEST NOT FOUND" in out.out
    assert "2 of 2 refs failed" in out.err
    assert "BEHIND" not in out.out  # existence returns before the stale summary
    assert not any("/tags/list" in url for url in seen)


def test_floating_tag_fails_before_any_registry_call(monkeypatch, verify, tmp_path, capsys) -> None:
    compose = _write_compose(tmp_path, {"juniper-data": "ghcr.io/pcalnon/juniper-data:latest"})

    def _get(*_args, **_kwargs):
        raise AssertionError("a non-release pin must not be looked up")

    monkeypatch.setattr(verify, "_get", _get)
    assert _run(monkeypatch, verify, compose) == 1
    out = capsys.readouterr()
    assert "not an X.Y.Z release pin" in out.out
    assert "refs failed" in out.err


def test_one_stale_ref_does_not_indict_a_current_sibling(monkeypatch, verify, tmp_path, capsys) -> None:
    compose = _write_compose(tmp_path, {"juniper-canopy": CANOPY, "juniper-data": DATA})
    seen = _install_registry(
        monkeypatch,
        verify,
        tags_by_repo={
            "pcalnon/juniper-canopy": ["0.8.0", "0.8.1"],
            "pcalnon/juniper-data": ["0.16.0", "0.9.0"],
        },
    )

    assert _run(monkeypatch, verify, compose) == 0
    out = capsys.readouterr()
    assert "::warning::STALE PIN — 0.8.1 is published, this pins 0.8.0" in out.out
    assert "currency: current (latest published is 0.16.0)" in out.out
    assert "1 of 2 pins are BEHIND" in out.out
    assert f"{DATA}  ->" not in out.out
    assert sum("/tags/list" in url for url in seen) == 2


def test_duplicate_refs_are_queried_once(monkeypatch, verify, tmp_path, capsys) -> None:
    compose = _write_compose(
        tmp_path,
        {"juniper-canopy": CANOPY, "juniper-canopy-demo": CANOPY},
    )
    seen = _install_registry(monkeypatch, verify, tags_by_repo={"pcalnon/juniper-canopy": ["0.8.0"]})

    assert _run(monkeypatch, verify, compose) == 0
    out = capsys.readouterr()
    assert "2 Juniper image sites, 1 unique refs" in out.out
    assert sum("/manifests/" in url for url in seen) == 1
    assert sum("/tags/list" in url for url in seen) == 1


def test_list_only_does_not_touch_the_registry(monkeypatch, verify, tmp_path, capsys) -> None:
    compose = _write_compose(tmp_path, {"juniper-canopy": CANOPY})

    def _get(*_args, **_kwargs):
        raise AssertionError("--list-only must not query the registry")

    monkeypatch.setattr(verify, "_get", _get)
    assert _run(monkeypatch, verify, compose, "--list-only") == 0
    assert "juniper-canopy" in capsys.readouterr().out


def test_expect_count_mismatch_exits_2_before_network(monkeypatch, verify, tmp_path, capsys) -> None:
    compose = _write_compose(tmp_path, {"juniper-canopy": CANOPY})

    def _get(*_args, **_kwargs):
        raise AssertionError("a count mismatch must not query the registry")

    monkeypatch.setattr(verify, "_get", _get)
    assert _run(monkeypatch, verify, compose, "--expect-count", "2") == 2
    assert "expected 2 Juniper image sites, found 1" in capsys.readouterr().err


def test_zero_juniper_refs_exit_2(monkeypatch, verify, tmp_path, capsys) -> None:
    compose = _write_compose(tmp_path, {"redis": "redis:7", "prometheus": "prom/prometheus:v2.54.0"})
    assert _run(monkeypatch, verify, compose, "--list-only") == 2
    assert "ZERO images" in capsys.readouterr().err


def test_non_image_values_are_skipped(monkeypatch, verify, tmp_path, capsys) -> None:
    compose = tmp_path / "compose.yml"
    compose.write_text(
        "services:\n"
        "  broken: nope\n"
        "  listed:\n"
        "    image:\n"
        "      - ghcr.io/pcalnon/juniper-data:0.16.0\n"
        "  blank:\n"
        "    image:\n"
        "  juniper-data:\n"
        f"    image: {DATA}\n",
        encoding="utf-8",
    )
    _install_registry(monkeypatch, verify, tags_by_repo={"pcalnon/juniper-data": ["0.16.0"]})

    assert _run(monkeypatch, verify, compose) == 0
    out = capsys.readouterr().out
    assert "1 Juniper image sites, 1 unique refs" in out
    assert "juniper-data" in out
    assert "broken" not in out
    assert "listed" not in out


def test_unreadable_compose_exits_2(monkeypatch, verify, tmp_path, capsys) -> None:
    missing = tmp_path / "nope.yml"
    monkeypatch.setattr(sys, "argv", ["verify_published_images.py", "--compose", str(missing)])
    with pytest.raises(SystemExit) as exc:
        verify.main()
    assert exc.value.code == 2
    assert "cannot read" in capsys.readouterr().err


def test_invalid_yaml_exits_2(monkeypatch, verify, tmp_path, capsys) -> None:
    bad = tmp_path / "bad.yml"
    bad.write_text("services: [\n", encoding="utf-8")
    monkeypatch.setattr(sys, "argv", ["verify_published_images.py", "--compose", str(bad)])
    with pytest.raises(SystemExit) as exc:
        verify.main()
    assert exc.value.code == 2
    assert "cannot read" in capsys.readouterr().err
