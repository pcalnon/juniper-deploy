"""Q-9 (CLI experimentation plan §15 / Wave 7.4) — experiment targets must not page.

Every RAW scrape-series selector in the alert and recording rules must exclude
``environment="host-experiment"`` — the label the per-run experiment launcher's
file_sd targets carry. Without the matcher, a deliberate stress benchmark pages
the on-call (alerts) or pollutes the SLO burn-rate inputs (recording rules).

References to RECORDED series (names containing ``:``) are exempt: their inputs
get the matcher here, and ``by()`` aggregation drops the environment label
before they exist.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

RULES_DIR = Path(__file__).resolve().parent.parent / "prometheus"
RULE_FILES = ("alert_rules.yml", "recording_rules.yml")

# Raw scrape-series tokens: juniper_* app families, up, process_*. Recorded
# names (juniper:...) contain a colon and never match.
RAW_SELECTOR = re.compile(r"\b(?:juniper_[a-z0-9_]+|up|process_[a-z0-9_]+)(?P<labels>\{[^}]*\})?")
EXCLUSION = 'environment!="host-experiment"'


def _exprs():
    for fname in RULE_FILES:
        doc = yaml.safe_load((RULES_DIR / fname).read_text())
        for group in doc.get("groups", []):
            for rule in group.get("rules", []):
                name = rule.get("alert") or rule.get("record")
                yield fname, name, rule["expr"]


@pytest.mark.parametrize("fname,name,expr", list(_exprs()), ids=lambda v: v if isinstance(v, str) and not v.startswith(("groups", "sum", "rate", "histogram")) else None)
def test_every_raw_selector_excludes_host_experiment(fname: str, name: str, expr: str) -> None:
    unscoped = []
    for m in RAW_SELECTOR.finditer(expr):
        labels = m.group("labels") or ""
        if EXCLUSION not in labels:
            unscoped.append(m.group(0))
    assert not unscoped, f"{fname}:{name}: raw selectors missing {EXCLUSION!r}: {unscoped}"


def test_rule_files_present_and_nonempty() -> None:
    rows = list(_exprs())
    assert len(rows) >= 30, f"expected the full rule surface, found {len(rows)} rules"


def test_regex_detects_a_planted_unscoped_selector() -> None:
    """The gate must actually bite: a synthetic unscoped selector is caught."""
    expr = 'sum by (service) (rate(juniper_data_http_requests_total[5m]))'
    hits = [m.group(0) for m in RAW_SELECTOR.finditer(expr) if EXCLUSION not in (m.group("labels") or "")]
    assert hits == ["juniper_data_http_requests_total"]
