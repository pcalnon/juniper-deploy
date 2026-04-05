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


class _ReadyHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802 (BaseHTTPRequestHandler API)
        if self.path != "/v1/health/ready":
            self.send_response(404)
            self.end_headers()
            return

        body = json.dumps(self.server.payload).encode("utf-8")  # type: ignore[attr-defined]
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt: str, *args: object) -> None:  # noqa: A003
        # Keep test output deterministic and quiet.
        return


class _ReadyServer(ThreadingHTTPServer):
    allow_reuse_address = True

    def __init__(self, server_address: tuple[str, int], payload: dict[str, str]) -> None:
        super().__init__(server_address, _ReadyHandler)
        self.payload = payload


@contextmanager
def _health_server(payload: dict[str, str]) -> Iterator[int]:
    server = _ReadyServer(("localhost", 0), payload)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server.server_port
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def _run_wait_script(timeout: int, data_port: int, cascor_port: int, canopy_port: int) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env.update(
        {
            "JUNIPER_DATA_PORT": str(data_port),
            "CASCOR_PORT": str(cascor_port),
            "CANOPY_PORT": str(canopy_port),
        }
    )
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
    with ExitStack() as stack:
        data_port = stack.enter_context(_health_server({"status": "ready", "version": "1.0.0", "service": "data"}))
        cascor_port = stack.enter_context(_health_server({"status": "ok", "version": "1.1.0", "service": "cascor"}))
        canopy_port = stack.enter_context(_health_server({"status": "healthy", "version": "1.2.0", "service": "canopy"}))

        result = _run_wait_script(timeout=0, data_port=data_port, cascor_port=cascor_port, canopy_port=canopy_port)

    combined = f"{result.stdout}\n{result.stderr}"
    assert result.returncode == 0, combined
    assert "All services are ready. Ready to run integration tests." in combined
    assert "juniper-data" in combined
    assert "status=ready" in combined


def test_wait_for_services_fails_when_service_reports_non_ready_status() -> None:
    with ExitStack() as stack:
        data_port = stack.enter_context(_health_server({"status": "ready", "version": "1.0.0", "service": "data"}))
        cascor_port = stack.enter_context(_health_server({"status": "starting", "version": "1.1.0", "service": "cascor"}))
        canopy_port = stack.enter_context(_health_server({"status": "ready", "version": "1.2.0", "service": "canopy"}))

        result = _run_wait_script(timeout=0, data_port=data_port, cascor_port=cascor_port, canopy_port=canopy_port)

    combined = f"{result.stdout}\n{result.stderr}"
    assert result.returncode == 1, combined
    assert "responded but status=starting" in combined
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
    encrypted.write_text("sops_version=3.9.4\nKEY=ENC[AES256_GCM,data:abc]\n", encoding="utf-8")

    result = _run_pre_commit_hook(str(env_example), str(encrypted))
    assert result.returncode == 0, f"{result.stdout}\n{result.stderr}"


def test_sops_pre_commit_rejects_fake_encrypted_file_without_sops_metadata(tmp_path: Path) -> None:
    fake_encrypted = tmp_path / ".env.enc"
    fake_encrypted.write_text("KEY=plaintext\n", encoding="utf-8")

    result = _run_pre_commit_hook(str(fake_encrypted))
    combined = f"{result.stdout}\n{result.stderr}"
    assert result.returncode == 1, combined
    assert "has no SOPS metadata" in combined


def test_sops_pre_commit_rejects_unencrypted_sensitive_env_files(tmp_path: Path) -> None:
    plaintext = tmp_path / ".env"
    plaintext.write_text("SECRET=value\n", encoding="utf-8")

    result = _run_pre_commit_hook(str(plaintext))
    combined = f"{result.stdout}\n{result.stderr}"
    assert result.returncode == 1, combined
    assert "Unencrypted secrets file detected" in combined
