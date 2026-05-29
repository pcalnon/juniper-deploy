#!/usr/bin/env python
"""Regression test enforcing stable, unique integer panel IDs on every dashboard.

Discovered in notes/poc/POC_ISSUES_DISCOVERED.md (Issue 5): the provisioned
dashboards in grafana/provisioning/dashboards/ lacked panel `id` fields,
so Grafana auto-assigned them at render time. `?viewPanel=N` deep links
and headless screenshot automation could not target specific panels from
JSON.

This test pins integer-ID + uniqueness without requiring monotonicity
(insertions in the middle should not cascade-renumber). Pattern lifted
from tests/test_alertmanager_config.py.
"""

import json
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
DASHBOARDS_DIR = REPO_ROOT / "grafana" / "provisioning" / "dashboards"
DASHBOARD_PATHS = sorted(DASHBOARDS_DIR.glob("*.json"))


def test_dashboards_exist() -> None:
    """Guard against an empty glob silently passing every parametrized test below."""
    assert DASHBOARD_PATHS, f"no dashboards found under {DASHBOARDS_DIR}"


@pytest.mark.parametrize("path", DASHBOARD_PATHS, ids=lambda p: p.name)
def test_panels_have_unique_integer_ids(path: Path) -> None:
    data = json.loads(path.read_text(encoding="utf-8"))
    panels = data.get("panels", [])
    assert panels, f"{path.name} has no panels[] — schema regression?"

    ids = [p.get("id") for p in panels]
    missing = [i for i, pid in enumerate(ids) if pid is None]
    non_int = [i for i, pid in enumerate(ids) if pid is not None and not isinstance(pid, int)]
    dupes = [pid for pid in ids if pid is not None and ids.count(pid) > 1]

    assert not missing, (
        f"{path.name}: panels at indices {missing} have no `id` field. "
        "All panels must carry a stable integer id so `?viewPanel=N` deep "
        "links and screenshot automation work. See "
        "notes/poc/POC_ISSUES_DISCOVERED.md Issue 5."
    )
    assert not non_int, (
        f"{path.name}: panels at indices {non_int} have non-integer ids: "
        f"{[ids[i] for i in non_int]}"
    )
    assert not dupes, f"{path.name}: duplicate panel ids found: {sorted(set(dupes))}"


@pytest.mark.parametrize("path", DASHBOARD_PATHS, ids=lambda p: p.name)
def test_top_level_dashboard_id_is_null(path: Path) -> None:
    """Grafana provisioning convention: top-level `id` is null (assigned at import)."""
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data.get("id") is None, (
        f"{path.name}: top-level `id` is {data.get('id')!r} but must be null "
        "for provisioned dashboards (Grafana assigns it on import)."
    )
