#!/usr/bin/env python
"""Rehearsal of .github/workflows/pr-budget-alarm.yml's own shell.

The alarm (#218) is report-only. Nothing else in the repo executes it, so a
wrong comparison, a cursor/ prefix that matches too much, or a failed ``gh``
query that exits 1 (or that looks like a healthy empty queue) would ship
silently. This extracts the workflow's run steps and drives them with a stub
``gh`` and a stub ``curl``. It does not contact GitHub or Slack.

The two counts share one pair of thresholds, and the cursor count is a subset
of the total, so the level follows the total. The cursor count is still load-
bearing: it is what the summary and the Slack text report. A filter that
counts every ref, or none, is a different alarm.
"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest
import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = REPO_ROOT / ".github" / "workflows" / "pr-budget-alarm.yml"
COUNT_STEP = "Count open PRs and evaluate the budget"
SLACK_STEP = "Slack notification on breach (non-blocking, Q-CHANNEL)"

# A stand-in, not a credential. The stub never opens a connection.
WEBHOOK = "https://hooks.example.test/services/T00/B00/secret-token-value"


def _workflow() -> dict:
    doc = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    assert isinstance(doc, dict), "pr-budget-alarm.yml did not parse"
    return doc


def _step(name: str) -> dict:
    steps = _workflow()["jobs"]["budget-alarm"]["steps"]
    found = [step for step in steps if step.get("name") == name]
    assert len(found) == 1, f"{name!r} not found in pr-budget-alarm.yml"
    assert "run" in found[0]
    return found[0]


def _child_env(**overrides: str) -> dict[str, str]:
    """Minimal environment. The parent environment is not copied."""
    env = {
        "PATH": "/usr/bin:/bin",
        "HOME": os.environ.get("HOME", "/tmp"),  # git is unused; HOME stays unset-safe
        "LANG": "C",
    }
    env.update(overrides)
    return env


def _write_stub(path: Path, body: str) -> None:
    path.write_text(body, encoding="utf-8")
    path.chmod(0o755)


def _run_count(tmp_path: Path, refs: list[str], *, warn: str | None, alarm: str | None, gh_rc: int = 0) -> subprocess.CompletedProcess[str]:
    """Execute the count step's own shell. ``warn``/``alarm`` None means unset."""
    script = tmp_path / "count.sh"
    script.write_text(_step(COUNT_STEP)["run"], encoding="utf-8")
    prs = [{"number": i + 1, "headRefName": ref} for i, ref in enumerate(refs)]
    prs_path = tmp_path / "prs.json"
    prs_path.write_text(json.dumps(prs), encoding="utf-8")
    gh_out = tmp_path / "github_output"
    gh_out.write_text("", encoding="utf-8")
    summary = tmp_path / "step_summary"
    summary.write_text("", encoding="utf-8")

    stub_bin = tmp_path / "bin"
    stub_bin.mkdir()
    _write_stub(
        stub_bin / "gh",
        "#!/bin/bash\n"
        "set -euo pipefail\n"
        'printf "gh %s\\n" "$*" >> "$GH_LOG"\n'
        'if [[ "${GH_RC}" != "0" ]]; then\n'
        '  echo "temporary failure talking to the API" >&2\n'
        '  exit "${GH_RC}"\n'
        "fi\n"
        'cat "$PRS_JSON"\n',
    )
    gh_log = tmp_path / "gh.log"
    env = _child_env(
        PATH=str(stub_bin) + os.pathsep + "/usr/bin:/bin",
        GH_TOKEN="unused",
        GH_REPO="pcalnon/juniper-deploy",
        GH_RC=str(gh_rc),
        PRS_JSON=str(prs_path),
        GH_LOG=str(gh_log),
        GITHUB_OUTPUT=str(gh_out),
        GITHUB_STEP_SUMMARY=str(summary),
    )
    if warn is not None:
        env["PR_BUDGET_WARN"] = warn
    if alarm is not None:
        env["PR_BUDGET_ALARM"] = alarm

    proc = subprocess.run(
        ["bash", str(script)],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        env=env,
        check=False,
        timeout=30,
    )
    proc.gh_output = gh_out.read_text(encoding="utf-8")  # type: ignore[attr-defined]
    proc.summary = summary.read_text(encoding="utf-8")  # type: ignore[attr-defined]
    proc.gh_log = gh_log.read_text(encoding="utf-8") if gh_log.exists() else ""  # type: ignore[attr-defined]
    return proc


def _outputs(text: str) -> dict[str, str]:
    found: dict[str, str] = {}
    for line in text.splitlines():
        key, sep, value = line.partition("=")
        if sep:
            found[key] = value
    return found


@pytest.mark.parametrize(
    ("total", "warn", "alarm", "level"),
    [
        (0, None, None, "OK"),
        (14, "", "", "OK"),  # empty repo variables still mean the defaults 15 / 30
        (15, "", "", "WARN"),  # exactly the warn threshold, not one past it
        (29, None, None, "WARN"),
        (30, None, None, "ALARM"),  # exactly the alarm threshold
        (31, "10", "30", "ALARM"),
        (9, "10", "20", "OK"),
        (10, "10", "20", "WARN"),
        (19, "10", "20", "WARN"),
        (20, "10", "20", "ALARM"),
    ],
)
def test_level_follows_the_total_at_both_boundaries(tmp_path: Path, total: int, warn: str | None, alarm: str | None, level: str) -> None:
    proc = _run_count(tmp_path, ["feature/x"] * total, warn=warn, alarm=alarm)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    got = _outputs(proc.gh_output)
    assert got["level"] == level
    assert got["total"] == str(total)
    assert got["cursor"] == "0"
    assert f"| Status | **{level}** |" in proc.summary
    if level == "OK":
        assert "within range" in proc.summary
    elif level == "WARN":
        assert "approaching the alarm ceiling" in proc.summary
        assert "budget exceeded" not in proc.summary
    else:
        assert "budget exceeded" in proc.summary
        assert "within range" not in proc.summary


def test_empty_thresholds_fall_back_to_15_and_30(tmp_path: Path) -> None:
    """``${VAR:-default}`` treats an empty repo variable as unset. ``${VAR-default}`` would not."""
    proc = _run_count(tmp_path, ["feature/x"] * 15, warn="", alarm="")
    assert proc.returncode == 0, proc.stdout + proc.stderr
    got = _outputs(proc.gh_output)
    assert got["warn"] == "15"
    assert got["alarm"] == "30"
    assert got["level"] == "WARN"
    assert "| Warn threshold (`PR_BUDGET_WARN`) | 15 |" in proc.summary
    assert "| Alarm threshold (`PR_BUDGET_ALARM`) | 30 |" in proc.summary


def test_cursor_prefix_is_exact(tmp_path: Path) -> None:
    """Only a ref that starts with ``cursor/`` counts, and the count is reported."""
    refs = [
        "cursor/missing-test-coverage",
        "cursor/nested/name",
        "cursor/",
        "cursor",  # no slash
        "Cursor/Upper",  # the match is case-sensitive
        "cursor-bot/x",
        "feature/cursor/inside",
        "dependabot/github_actions/example",
    ]
    proc = _run_count(tmp_path, refs, warn="100", alarm="200")
    assert proc.returncode == 0, proc.stdout + proc.stderr
    got = _outputs(proc.gh_output)
    assert got["total"] == "8"
    assert got["cursor"] == "3"
    assert got["level"] == "OK"  # 8 is under a warn of 100; the cursor count must not inflate the level
    assert "| Open `cursor/` PRs | 3 |" in proc.summary
    assert "pr list" in proc.gh_log  # the numbers came from gh, not a hardcoded zero


def test_gh_failure_stays_green_and_is_not_an_empty_queue(tmp_path: Path) -> None:
    """A query failure must not page, and must not look like zero open PRs."""
    proc = _run_count(tmp_path, ["cursor/should-not-be-counted"], warn="1", alarm="1", gh_rc=1)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    got = _outputs(proc.gh_output)
    assert got == {"level": "OK"}
    assert "::warning title=pr-budget-alarm::" in proc.stdout
    assert "temporary failure" in proc.stdout
    assert "Could not query open PRs" in proc.summary
    assert "within range" not in proc.summary
    assert "should-not-be-counted" not in proc.summary
    assert "ALARM" not in proc.summary
    assert "WARN" not in proc.summary


def test_workflow_is_schedule_only_and_read_only() -> None:
    """The alarm must not run on pull requests, and its token must not be able to write."""
    doc = _workflow()
    # PyYAML 1.1 reads the bare key `on` as True.
    triggers = doc[True]
    assert set(triggers) == {"schedule", "workflow_dispatch"}
    assert doc["permissions"] == {"contents": "read", "pull-requests": "read"}
    text = WORKFLOW.read_text(encoding="utf-8")
    assert "pull_request" not in text
    assert "contents: write" not in text


def _run_slack(tmp_path: Path, *, webhook: str, curl_rc: int) -> subprocess.CompletedProcess[str]:
    script = tmp_path / "slack.sh"
    script.write_text(_step(SLACK_STEP)["run"], encoding="utf-8")
    stub_bin = tmp_path / "bin"
    stub_bin.mkdir()
    curl_log = tmp_path / "curl.log"
    _write_stub(
        stub_bin / "curl",
        "#!/bin/bash\n"
        "set -euo pipefail\n"
        ': > "$CURL_LOG"\n'
        'for arg in "$@"; do printf "%s\\0" "$arg" >> "$CURL_LOG"; done\n'
        'exit "$CURL_RC"\n',
    )
    env = _child_env(
        PATH=str(stub_bin) + os.pathsep + "/usr/bin:/bin",
        SLACK_WEBHOOK_URL=webhook,
        RUN_URL="https://github.com/pcalnon/juniper-deploy/actions/runs/1",
        LEVEL="WARN",
        TOTAL="12",
        CURSOR="4",
        WARN="10",
        ALARM="20",
        CURL_LOG=str(curl_log),
        CURL_RC=str(curl_rc),
    )
    proc = subprocess.run(
        ["bash", str(script)],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        env=env,
        check=False,
        timeout=30,
    )
    proc.curl_log = curl_log.read_text(encoding="utf-8") if curl_log.exists() else ""  # type: ignore[attr-defined]
    return proc


def test_missing_webhook_annotates_and_does_not_post(tmp_path: Path) -> None:
    proc = _run_slack(tmp_path, webhook="", curl_rc=0)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "::warning title=PR budget WARN with no Slack webhook::" in proc.stdout
    assert "12 open PR(s), 4 on cursor/ branches" in proc.stdout
    assert proc.curl_log == ""


def test_slack_payload_carries_counts_and_not_the_webhook(tmp_path: Path) -> None:
    proc = _run_slack(tmp_path, webhook=WEBHOOK, curl_rc=0)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "Slack notification posted." in proc.stdout
    args = proc.curl_log.split("\0")
    assert WEBHOOK in args
    payload_arg = next(arg for arg in args if arg.startswith("{"))
    payload = json.loads(payload_arg)
    text = payload["text"]
    assert "secret-token-value" not in text
    assert WEBHOOK not in text
    assert "PR budget WARN" in text
    assert "12 open PR(s), 4 on cursor/ branches" in text
    assert "warn=10" in text and "alarm=20" in text
    assert "actions/runs/1" in text


def test_slack_post_failure_fails_the_script_and_the_step_continues() -> None:
    """``set -e`` plus ``curl -f`` fails the script. The job stays green via continue-on-error.

    Dropping ``set -e`` would make the trailing echo the exit status, so a dead
    webhook would look posted. Dropping continue-on-error would page on it.
    """
    step = _step(SLACK_STEP)
    assert step["continue-on-error"] is True
    assert step["if"] == "steps.count.outputs.level != 'OK'"
    assert "set -euo pipefail" in step["run"]
    assert "curl -fsS" in step["run"]


def test_slack_post_failure_exits_nonzero(tmp_path: Path) -> None:
    proc = _run_slack(tmp_path, webhook=WEBHOOK, curl_rc=22)
    assert proc.returncode != 0
    assert "Slack notification posted." not in proc.stdout
