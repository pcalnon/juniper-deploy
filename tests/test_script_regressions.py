#!/usr/bin/env python
"""Regression tests for shell utility scripts added in recent changes."""

from __future__ import annotations

import json
import os
import subprocess
import threading
from contextlib import ExitStack, contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Iterator


REPO_ROOT = Path(__file__).resolve().parents[1]
WAIT_SCRIPT = REPO_ROOT / "scripts" / "wait_for_services.sh"
PRE_COMMIT_SCRIPT = REPO_ROOT / "util" / "sops-pre-commit-hook.sh"


class _LiveHandler(BaseHTTPRequestHandler):
    """Minimal handler: returns 200 on /v1/health/live if server.healthy is True."""

    def do_GET(self) -> None:  # noqa: N802 (BaseHTTPRequestHandler API)
        if self.path != "/v1/health/live":
            self.send_response(404)
            self.end_headers()
            return

        if self.server.healthy:  # type: ignore[attr-defined]
            self.send_response(200)
        else:
            self.send_response(503)
        self.end_headers()

    def log_message(self, fmt: str, *args: object) -> None:  # noqa: A003
        return


class _LiveServer(ThreadingHTTPServer):
    allow_reuse_address = True

    def __init__(self, server_address: tuple[str, int], healthy: bool = True) -> None:
        super().__init__(server_address, _LiveHandler)
        self.healthy = healthy


@contextmanager
def _health_server(port: int = 0, healthy: bool = True) -> Iterator[int]:
    """Start a server on ``port`` (use the default ``0`` to pick a free port)."""
    server = _LiveServer(("localhost", port), healthy)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server.server_port
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def _run_wait_script(
    timeout: int,
    *,
    data_port: int,
    cascor_port: int,
    canopy_port: int,
) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    # scripts/config.sh resolves these env vars (with fallbacks). Pass all
    # three so the test never collides with a real juniper stack running on
    # the default 8100/8201/8050.
    env["JUNIPER_DATA_PORT"] = str(data_port)
    env["CASCOR_HOST_PORT"] = str(cascor_port)
    env["CANOPY_PORT"] = str(canopy_port)
    return subprocess.run(
        ["bash", str(WAIT_SCRIPT), str(timeout)],
        cwd=REPO_ROOT,
        env=env,
        check=False,
        capture_output=True,
        text=True,
        timeout=15,
    )


def test_wait_for_services_succeeds_when_all_ready_statuses() -> None:
    """Script reports success when all three liveness endpoints return 200."""
    with ExitStack() as stack:
        # All three mock servers bind to ephemeral ports (port=0); the chosen
        # ports are piped to the script via env vars. Binding to the default
        # 8100/8201/8050 used to fail with EADDRINUSE whenever a real juniper
        # stack was running on the same host (the common dev case).
        data_port = stack.enter_context(_health_server(healthy=True))
        cascor_port = stack.enter_context(_health_server(healthy=True))
        canopy_port = stack.enter_context(_health_server(healthy=True))

        result = _run_wait_script(
            timeout=5,
            data_port=data_port,
            cascor_port=cascor_port,
            canopy_port=canopy_port,
        )

    combined = f"{result.stdout}\n{result.stderr}"
    assert result.returncode == 0, combined
    assert "All services are ready" in combined
    assert "juniper-data" in combined


def test_wait_for_services_fails_when_service_reports_non_ready_status() -> None:
    """Script times out when a service returns non-200 on liveness."""
    with ExitStack() as stack:
        data_port = stack.enter_context(_health_server(healthy=True))
        cascor_port = stack.enter_context(_health_server(healthy=False))
        canopy_port = stack.enter_context(_health_server(healthy=True))

        result = _run_wait_script(
            timeout=0,
            data_port=data_port,
            cascor_port=cascor_port,
            canopy_port=canopy_port,
        )

    combined = f"{result.stdout}\n{result.stderr}"
    assert result.returncode == 1, combined
    assert "Services did not become ready within 0s" in combined


def _run_pre_commit_hook(*files: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", str(PRE_COMMIT_SCRIPT), *files],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
        timeout=10,
    )


def test_sops_pre_commit_allows_templates_and_encrypted_files(tmp_path: Path) -> None:
    env_example = tmp_path / ".env.example"
    env_example.write_text("FOO=bar\n", encoding="utf-8")

    encrypted = tmp_path / ".env.enc"
    encrypted.write_text(
        "sops_version=3.9.4\n"
        "sops_lastmodified=2026-04-05T00:00:00Z\n"
        "sops_age__list_0__map_recipient=age1abc\n"
        "KEY=ENC[AES256_GCM,data:abc,iv:def,tag:ghi,type:str]\n",
        encoding="utf-8",
    )

    result = _run_pre_commit_hook(str(env_example), str(encrypted))
    assert result.returncode == 0, f"{result.stdout}\n{result.stderr}"


def test_sops_pre_commit_rejects_fake_encrypted_file_without_sops_metadata(tmp_path: Path) -> None:
    fake_encrypted = tmp_path / ".env.enc"
    fake_encrypted.write_text("KEY=plaintext\n", encoding="utf-8")

    result = _run_pre_commit_hook(str(fake_encrypted))
    combined = f"{result.stdout}\n{result.stderr}"
    assert result.returncode == 1, combined
    assert "insufficient SOPS metadata" in combined


def test_sops_pre_commit_rejects_unencrypted_sensitive_env_files(tmp_path: Path) -> None:
    plaintext = tmp_path / ".env"
    plaintext.write_text("SECRET=value\n", encoding="utf-8")

    result = _run_pre_commit_hook(str(plaintext))
    combined = f"{result.stdout}\n{result.stderr}"
    assert result.returncode == 1, combined
    assert "Unencrypted secrets file detected" in combined
