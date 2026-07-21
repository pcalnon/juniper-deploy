"""Lint + behaviour gate for the env-repr secret-leak class (tests/redacted_env.py).

The class: a test builds ``env = os.environ.copy()`` (or ``dict(os.environ)`` /
``{**os.environ}``) for ``subprocess.run``; on a failure, pytest ``--showlocals`` /
rich-traceback runs render that frame-local through ``saferepr`` (alphabetically
sorted + truncated), putting real secrets at the visible head of the paste. The fix
is building the mapping as ``tests.redacted_env.RedactedEnv``, whose repr is masked.

The LINT half forbids raw ``os.environ``-derived mapping construction anywhere under
``tests/``; the BEHAVIOUR half proves the wrapper masks its repr, keeps dict
semantics, and drives a real subprocess. ``patch.dict(os.environ, ...)`` (in-process
env patching, not a subprocess mapping) is deliberately NOT flagged. Mirrors the
juniper-ml gate of the same name.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

from tests.redacted_env import RedactedEnv

_TESTS_DIR = Path(__file__).resolve().parent

# ``**os.environ`` (rather than ``{**os.environ``) also catches the multi-line
# spread form; the negative lookbehind exempts ``[mock.]patch.dict(os.environ, ...)``.
_RAW_ENV_PATTERN = re.compile(r"os\.environ\.copy\(\)|(?<!patch\.)\bdict\(os\.environ|\*\*os\.environ")

_ALLOWED_FILES = {"redacted_env.py", "test_env_repr_safety.py"}


def test_no_raw_environ_derived_mappings_in_tests():
    offenders = []
    for path in sorted(_TESTS_DIR.glob("*.py")):
        if path.name in _ALLOWED_FILES:
            continue
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            if _RAW_ENV_PATTERN.search(line):
                offenders.append(f"{path.name}:{lineno}: {line.strip()}")
    assert offenders == [], "Raw os.environ-derived mappings leak secrets via frame-local reprs; build them with tests.redacted_env.RedactedEnv instead: " + "; ".join(offenders)


def test_scanner_bites_on_synthetic_violations():
    # The negative case proving the lint is live.
    assert _RAW_ENV_PATTERN.search("env = os.environ.copy()")
    assert _RAW_ENV_PATTERN.search("env = dict(os.environ, FOO='bar')")
    assert _RAW_ENV_PATTERN.search("env = {**os.environ, 'FOO': 'bar'}")
    assert _RAW_ENV_PATTERN.search("    **os.environ,")


def test_scanner_ignores_in_process_env_patching():
    assert _RAW_ENV_PATTERN.search("with patch.dict(os.environ, {'FOO': 'bar'}):") is None
    assert _RAW_ENV_PATTERN.search("with mock.patch.dict(os.environ, {'FOO': 'bar'}):") is None


def test_repr_and_str_render_no_keys_or_values():
    env = RedactedEnv({"HOME": "/nowhere"}, SECRET_TOKEN="hunter2")  # nosec B106 — deliberately secret-shaped test value; the assertions prove it never renders
    for rendered in (repr(env), str(env), f"{env}"):
        assert "hunter2" not in rendered
        assert "SECRET_TOKEN" not in rendered
        assert "/nowhere" not in rendered
        assert "RedactedEnv" in rendered


def test_dict_semantics_and_copy_preserve_redaction():
    env = RedactedEnv({"A": "1"}, B="2")
    env["PATH"] = "/usr/bin"
    assert env["A"] == "1"
    assert env.get("B") == "2"
    clone = env.copy()
    assert isinstance(clone, RedactedEnv)
    assert dict(clone) == dict(env)
    assert "/usr/bin" not in repr(clone)


def test_subprocess_child_sees_injected_vars():
    env = RedactedEnv(os.environ, ENV_REPR_SAFETY_PROBE="ok")
    proc = subprocess.run([sys.executable, "-c", "import os; print(os.environ['ENV_REPR_SAFETY_PROBE'])"], env=env, capture_output=True, text=True, timeout=60, check=False)
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout.strip() == "ok"
