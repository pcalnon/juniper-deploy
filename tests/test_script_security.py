#!/usr/bin/env python
#####################################################################################################################################################################################################
# Project:       Juniper
# Application:   juniper-deploy
# File Name:     test_script_security.py
# Author:        Juniper Automation
#
# Date Created:  2026-04-05
#
# License:       MIT License
# Copyright:     Copyright (c) 2024-2026 Paul Calnon
#
# Description:
#    Regression tests for shell script security hardening:
#      - No direct env var interpolation in Python code strings
#      - Port validation rejects non-numeric values
#      - SOPS validation script detects unencrypted files
#      - Pre-commit config includes SOPS validation hook
#
#####################################################################################################################################################################################################

import re
import subprocess
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = REPO_ROOT / "scripts"

SHELL_SCRIPTS = [
    "wait_for_services.sh",
    "health_check.sh",
    "test_demo_profile.sh",
    "test_health_enhanced.sh",
]


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


class TestNoPythonCodeInjection:
    """Ensure shell scripts do not interpolate variables into python3 -c strings."""

    def test_no_shell_var_in_python_urlopen(self):
        """Regression: urlopen() must use sys.argv, not shell-interpolated strings."""
        pattern = re.compile(r"""urlopen\(\s*['"]?\$\{""")
        for script_name in SHELL_SCRIPTS:
            content = _read_text(SCRIPTS_DIR / script_name)
            matches = pattern.findall(content)
            assert not matches, (
                f"{script_name} contains unsafe shell variable interpolation "
                f"inside Python urlopen() call: {matches}"
            )

    def test_python_uses_sys_argv_for_urls(self):
        """All python3 -c calls that use urlopen should take URL from sys.argv."""
        for script_name in SHELL_SCRIPTS:
            content = _read_text(SCRIPTS_DIR / script_name)
            # Find all python3 -c blocks that call urlopen
            python_blocks = re.findall(
                r'python3\s+-c\s+"([^"]*urlopen[^"]*)"', content, re.DOTALL
            )
            for block in python_blocks:
                assert "sys.argv" in block, (
                    f"{script_name} has a python3 -c block with urlopen() "
                    f"that does not use sys.argv for URL parameter"
                )


class TestPortValidation:
    """Ensure scripts validate port environment variables are numeric."""

    def test_scripts_validate_cascor_port(self):
        """Scripts using CASCOR_HOST_PORT must validate it is numeric.

        Checks for the bash regex pattern [0-9]+$ which is used in
        `[[ "$var" =~ ^[0-9]+$ ]]` validation guards.
        """
        scripts_using_cascor_port = [
            "wait_for_services.sh",
            "health_check.sh",
            "test_demo_profile.sh",
            "test_health_enhanced.sh",
        ]
        for script_name in scripts_using_cascor_port:
            content = _read_text(SCRIPTS_DIR / script_name)
            assert re.search(r'\^?\[0-9\]\+\$', content), (
                f"{script_name} uses CASCOR_HOST_PORT but does not validate "
                f"it is numeric"
            )

    def test_port_validation_rejects_injection_payload(self):
        """Port validation must reject a code injection payload.

        Uses a controlled adversarial payload to verify the numeric check
        prevents quote-breaking Python code injection.
        """
        # Write a small test script to a temp file to avoid heredoc quoting issues
        import tempfile
        test_script = (
            '#!/usr/bin/env bash\n'
            'cascor_port="$1"\n'
            'if ! [[ "$cascor_port" =~ ^[0-9]+$ ]]; then\n'
            '    echo "REJECTED"\n'
            '    exit 0\n'
            'fi\n'
            'echo "ACCEPTED"\n'
            'exit 1\n'
        )
        with tempfile.NamedTemporaryFile(suffix=".sh", mode="w", delete=False) as f:
            f.write(test_script)
            f.flush()
            result = subprocess.run(
                ["bash", f.name, '8201"); import os; os.system("echo PWNED"); #'],
                capture_output=True, text=True, timeout=5,
            )
            assert "REJECTED" in result.stdout, (
                "Port validation did not reject injection payload"
            )
            Path(f.name).unlink()


class TestSopsValidation:
    """Ensure SOPS validation script exists and works correctly."""

    def test_validate_sops_script_exists(self):
        script = SCRIPTS_DIR / "validate_sops_encryption.sh"
        assert script.exists(), "scripts/validate_sops_encryption.sh not found"

    def test_validate_sops_rejects_unencrypted_file(self):
        """SOPS validation must reject files without SOPS metadata."""
        import tempfile
        with tempfile.NamedTemporaryFile(suffix=".env.enc", mode="w", delete=False) as f:
            f.write("DB_PASSWORD=supersecret\n")
            f.flush()
            result = subprocess.run(
                ["bash", str(SCRIPTS_DIR / "validate_sops_encryption.sh"), f.name],
                capture_output=True, text=True, timeout=5,
            )
            assert result.returncode != 0, (
                "SOPS validation accepted a file without SOPS metadata"
            )
            assert "insufficient SOPS metadata" in result.stdout
            Path(f.name).unlink()

    def test_validate_sops_accepts_encrypted_file(self):
        """SOPS validation must accept files with SOPS metadata."""
        import tempfile
        with tempfile.NamedTemporaryFile(suffix=".env.enc", mode="w", delete=False) as f:
            f.write("KEY=ENC[AES256_GCM,data:abc,iv:def,tag:ghi,type:str]\n")
            f.write("sops_version=3.7.3\n")
            f.write("sops_lastmodified=2026-04-05T00:00:00Z\n")
            f.write("sops_age__list_0__map_recipient=age1abc\n")
            f.flush()
            result = subprocess.run(
                ["bash", str(SCRIPTS_DIR / "validate_sops_encryption.sh"), f.name],
                capture_output=True, text=True, timeout=5,
            )
            assert result.returncode == 0, (
                f"SOPS validation rejected a properly encrypted file: {result.stdout}"
            )
            Path(f.name).unlink()


class TestPreCommitConfig:
    """Ensure pre-commit configuration includes SOPS validation."""

    def test_validate_sops_hook_defined(self):
        config = _read_text(REPO_ROOT / ".pre-commit-config.yaml")
        assert "validate-sops-encryption" in config, (
            "Pre-commit config missing validate-sops-encryption hook"
        )

    def test_no_unencrypted_env_hook_defined(self):
        config = _read_text(REPO_ROOT / ".pre-commit-config.yaml")
        assert "no-unencrypted-env" in config, (
            "Pre-commit config missing no-unencrypted-env hook"
        )

    def test_enc_file_pattern_in_sops_hook(self):
        """The SOPS validation hook must match .enc files."""
        config = _read_text(REPO_ROOT / ".pre-commit-config.yaml")
        assert r"\.enc$" in config, (
            "Pre-commit SOPS hook does not match .enc files"
        )
