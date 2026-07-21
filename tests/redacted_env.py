"""RedactedEnv -- an os.environ-derived mapping whose repr never shows values.

Subprocess-driving tests build child environments as ``env = os.environ.copy()``
(plus overrides) and pass them to ``subprocess.run``. That mapping then sits as a
frame-local in every assertion / ``check=True`` failure traceback, and pytest
``--showlocals`` / rich-traceback runs render frame locals through ``saferepr``
(alphabetically sorted + truncated) -- putting real secrets (``ANTHROPIC_API_KEY``,
``ALPHA_VANTAGE_TOKEN``, ...) at the visible head of failure pastes. Building the
mapping as ``RedactedEnv`` instead makes any such render harmless: it behaves as a
normal ``dict[str, str]`` (``subprocess.run(env=...)`` accepts it; ``env["PATH"] =
...`` works), only ``repr``/``str`` are masked.

Enforced by ``tests/test_env_repr_safety.py`` (the sole gate for this class; the
juniper-ml sibling carries the same pair).
"""

from __future__ import annotations

from collections.abc import Mapping


class RedactedEnv(dict):
    """``dict[str, str]`` whose ``repr``/``str`` never renders keys or values.

    ``RedactedEnv(os.environ)`` copies the current environment;
    ``RedactedEnv(os.environ, FOO="bar")`` layers keyword overrides on top.
    """

    def __init__(self, *bases: Mapping[str, str], **overrides: str) -> None:
        merged: dict[str, str] = {}
        for base in bases:
            merged.update(base)
        merged.update(overrides)
        super().__init__(merged)

    def __repr__(self) -> str:
        return f"<RedactedEnv: {len(self)} vars (values redacted)>"

    __str__ = __repr__

    def copy(self) -> "RedactedEnv":
        """Preserve redaction through ``.copy()``."""
        return RedactedEnv(self)
