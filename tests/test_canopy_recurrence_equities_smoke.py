#!/usr/bin/env python
#####################################################################################################################################################################################################
# Project:       Juniper
# Application:   juniper-deploy
# File Name:     test_canopy_recurrence_equities_smoke.py
# Author:        Paul Calnon
#
# Date Created:  2026-10-08
#
# License:       MIT License
# Copyright:     Copyright (c) 2024-2026 Paul Calnon
#
# Description:
#    The authenticated canopy -> juniper-recurrence -> juniper-data smoke for `equities_seq`
#    (W1.11 of juniper-ml notes/JUNIPER_2026-10-03_JUNIPER-RECURRENCE_EQUITIES-END-TO-END-AUDIT-AND-DEVELOPMENT-PLAN.md).
#    It drives the deployed dashboard the way an operator does: select Recurrence (LMU), stage
#    `equities_seq`, Start. It then checks the three hops:
#
#      1. canopy answers Start with 200, and the fit completes with a REGRESSION metrics block
#         (mse / rmse / mae / r2, finite and mutually consistent; no accuracy);
#      2. juniper-data minted the dataset the fit consumed from the request canopy staged, so
#         nothing on the way dropped or rewrote it;
#      3. juniper-data labels that dataset `regression` at generator >= 6.0.0 (X8,
#         juniper-data#437).
#
#    WHY CHECK 3 READS THE PRODUCER'S METADATA. A recurrence fit reads `y_reg_*`, and
#    `equities_seq` emits it under 5.0.0 and 6.0.0 alike: X8 changed the stored meta, not the
#    arrays. So the metrics block cannot tell the two contracts apart. Published juniper-data
#    <= 0.16.0 serves 5.0.0 / `classification`; checks 1 and 2 pass against it, and check 3
#    FAILS and names the version and label it saw. That failure is the point of the check,
#    not a flake, and it stays red until the stack's juniper-data serves 6.0.0.
#
#    THE REQUEST is the plan's recurrence-ready dataset bundle (W1.1 Details; documented in
#    juniper-data#451) at its smallest: one symbol and a pinned 17-month window, so the
#    `dataset_id` is stable and a repeat run is a cache hit rather than a fresh Yahoo / SEC
#    fetch. canopy's Start body carries only `d` / `theta` / `ridge`, so the model half of the
#    bundle (the RFF readout) cannot cross canopy 0.8.x. `d=16, ridge=1.0` keeps the fit off the
#    service's unregularised default. The metrics are in-sample (W0.7): this checks their
#    SHAPE, never their quality.
#
#    WHERE IT RUNS. It is built for the test-runner image (`juniper-deploy-test`): the compose
#    `test-runner` service reaches canopy and juniper-data by service name and hands the keys
#    over as Docker secrets. On a host with no stack it skips, like the other live modules.
#    `scripts/test_canopy_recurrence_smoke.sh` runs it in an isolated compose project,
#    optionally against a juniper-data image built from a checkout (the W1.11 slip rule's
#    "smoke green against a `main` checkout of juniper-data").
#
#    SIDE EFFECTS on the stack it targets: canopy's model selection, one staged dataset that
#    Start consumes, one recurrence fit, and one juniper-data artifact. The selection is
#    restored afterwards when it was not Recurrence before.
#
#####################################################################################################################################################################################################

from __future__ import annotations

import math
import os
import time
from typing import Any
from urllib.parse import quote

import pytest
import requests

from constants import (
    CONTROL_TIMEOUT,
    DEFAULT_RECURRENCE_SMOKE_TIMEOUT,
    DEFAULT_TIMEOUT,
    ENV_CANOPY_API_KEY,
    ENV_CANOPY_API_KEY_FILE,
    ENV_DATA_API_KEY,
    ENV_DATA_API_KEY_FILE,
    ENV_RECURRENCE_SMOKE_TIMEOUT,
    RECURRENCE_SMOKE_POLL_INTERVAL,
)

#: canopy's registry key for the LMU model, and the key its startup default serves.
RECURRENCE_MODEL = "recurrence"
DEFAULT_MODEL = "cascor"

EQUITIES_SEQ = "equities_seq"

#: The dataset half of the recurrence-ready bundle (W1.1(a)), at its smallest. `start_date` is
#: pinned because `end_date` defaults to the wall clock, and both are pinned so the id is
#: stable. `purchase_date` keeps its default (2000-01-03), which is before `start_date`, so
#: W1.8's refusal under `drop` does not apply.
DATASET_PARAMS: dict[str, Any] = {
    "symbols": ["AAPL"],
    "fundamentals_fill": "drop",
    "normalize_features": False,
    "regression_target": "log_return",
    "start_date": "2023-01-03",
    "end_date": "2024-06-03",
}

#: The LMU hyperparameters canopy's Start body can carry.
HYPERPARAMS: dict[str, Any] = {"d": 16, "ridge": 1.0}

#: The recurrence model's regression metric set (juniper-recurrence-model `model.py`).
REGRESSION_METRICS = ("mse", "rmse", "mae", "r2")
CLASSIFICATION_METRICS = ("accuracy",)

#: X8 (juniper-data#437): `equities_seq` is declared `regression` from generator 6.0.0.
FIRST_REGRESSION_GENERATOR_MAJOR = 6

PLAN = "juniper-ml notes/JUNIPER_2026-10-03_JUNIPER-RECURRENCE_EQUITIES-END-TO-END-AUDIT-AND-DEVELOPMENT-PLAN.md"


def _fit_timeout() -> float:
    raw = os.environ.get(ENV_RECURRENCE_SMOKE_TIMEOUT, "") or str(DEFAULT_RECURRENCE_SMOKE_TIMEOUT)
    assert raw.replace(".", "", 1).isdigit(), f"{ENV_RECURRENCE_SMOKE_TIMEOUT}={raw!r} is not a number of seconds"
    return float(raw)


def _body(resp: requests.Response) -> Any:
    """The response body as JSON when it is JSON, else its text (bounded)."""
    try:
        return resp.json()
    except ValueError:
        return resp.text[:500]


def _auth_hint(status_code: int, env_name: str, file_env_name: str) -> str:
    if status_code in (401, 403):
        return f" -- no accepted API key reached the service: set {env_name}, or {file_env_name} to a file holding it (the compose test-runner mounts it from /run/secrets)"
    return ""


def _backend_type(canopy_url: str, http: requests.Session) -> str | None:
    """The backend canopy is running now, or None when it will not say."""
    try:
        resp = http.get(f"{canopy_url}/api/train/status", timeout=DEFAULT_TIMEOUT)
    except requests.RequestException:
        return None
    if resp.status_code != 200:
        return None
    body = _body(resp)
    return body.get("backend") if isinstance(body, dict) else None


def _poll_until_terminal(canopy_url: str, http: requests.Session, budget: float) -> dict[str, Any]:
    """Poll canopy's status until the fit completes or fails, or the budget runs out.

    A non-200 poll (a 429 from canopy's rate limiter, a transient 5xx) is not a verdict: it is
    recorded and the poll continues, so only a terminal status or the budget ends it.
    """
    deadline = time.monotonic() + budget
    last: dict[str, Any] = {}
    while True:
        try:
            resp = http.get(f"{canopy_url}/api/train/status", timeout=DEFAULT_TIMEOUT)
            body = _body(resp)
            if resp.status_code == 200 and isinstance(body, dict):
                last = body
                if body.get("completed") or body.get("failed"):
                    return body
            else:
                last = {**last, "_last_poll": f"HTTP {resp.status_code}: {body}"}
        except requests.RequestException as exc:
            last = {**last, "_last_poll": f"no answer: {type(exc).__name__}"}
        if time.monotonic() >= deadline:
            return {**last, "_timed_out_after_s": budget}
        time.sleep(RECURRENCE_SMOKE_POLL_INTERVAL)


@pytest.fixture(scope="module")
def equities_fit(require_canopy, canopy_url: str, canopy_http: requests.Session):
    """Select Recurrence, stage `equities_seq`, Start, and wait for a terminal status.

    Runs once for the module; every check below reads the record it yields. A refusal BEFORE
    Start (the selection or the staging) fails here, naming the step and canopy's answer,
    because no check below would mean anything. From Start on, the record carries the outcome
    and the checks judge it, so a fit that fails says so in the check that needs it.
    """
    before = _backend_type(canopy_url, canopy_http)
    try:
        select = canopy_http.post(f"{canopy_url}/api/model/select", json={"nn_model": RECURRENCE_MODEL}, timeout=CONTROL_TIMEOUT)
        if select.status_code != 200:
            pytest.fail(f"POST /api/model/select {{nn_model: {RECURRENCE_MODEL!r}}} -> HTTP {select.status_code}: {_body(select)}" + _auth_hint(select.status_code, ENV_CANOPY_API_KEY, ENV_CANOPY_API_KEY_FILE))
        selected = _body(select)
        backend = selected.get("backend") if isinstance(selected, dict) else None
        if backend != "recurrence":
            pytest.fail(f"canopy recorded the Recurrence (LMU) selection but runs the {backend!r} backend, so a Start would not reach juniper-recurrence. canopy routes the model to the service only when JUNIPER_CANOPY_RECURRENCE_SERVICE_URL is set (compose sets it to http://juniper-recurrence:8210). Answer: {selected}")

        stage = canopy_http.post(f"{canopy_url}/api/stage_dataset", json={"nn_dataset_type": EQUITIES_SEQ, "nn_dataset_params": DATASET_PARAMS}, timeout=CONTROL_TIMEOUT)
        staged = _body(stage)
        if stage.status_code != 200:
            pytest.fail(f"POST /api/stage_dataset {{nn_dataset_type: {EQUITIES_SEQ!r}}} -> HTTP {stage.status_code}: {staged}")

        # The dataset rides in the Start body too. A staged config takes precedence over it in
        # canopy (X6 / design §4.9), and the two agree, so either path fits the same request.
        start = canopy_http.post(f"{canopy_url}/api/train/start", json={"dataset": {"generator": EQUITIES_SEQ, "params": DATASET_PARAMS}, **HYPERPARAMS}, timeout=CONTROL_TIMEOUT)
        record: dict[str, Any] = {
            "staged": staged.get("data") if isinstance(staged, dict) else staged,
            "start_status": start.status_code,
            "start_body": _body(start),
            "status": {},
            "metrics": None,
            "dataset": None,
        }
        if start.status_code == 200:
            record["status"] = _poll_until_terminal(canopy_url, canopy_http, _fit_timeout())
            metrics = canopy_http.get(f"{canopy_url}/api/metrics", timeout=DEFAULT_TIMEOUT)
            record["metrics"] = _body(metrics) if metrics.status_code == 200 else f"HTTP {metrics.status_code}: {_body(metrics)}"
            dataset = canopy_http.get(f"{canopy_url}/api/dataset", timeout=DEFAULT_TIMEOUT)
            record["dataset"] = _body(dataset) if dataset.status_code == 200 else f"HTTP {dataset.status_code}: {_body(dataset)}"
        yield record
    finally:
        # Leave the dashboard on the backend it was on. Best effort: a smoke must not fail on
        # its own cleanup, and a refused swap (a fit still running) leaves Recurrence selected.
        if before is not None and before != "recurrence":
            try:
                canopy_http.post(f"{canopy_url}/api/model/select", json={"nn_model": DEFAULT_MODEL}, timeout=CONTROL_TIMEOUT)
            except requests.RequestException:
                # Unreachable canopy at teardown: the checks above already reported on it.
                pass


@pytest.fixture(scope="module")
def fit_dataset_id(equities_fit: dict[str, Any]) -> str:
    """The `dataset_id` the fit consumed, as canopy reports it (`GET /api/dataset`)."""
    dataset = equities_fit["dataset"]
    dataset_id = dataset.get("dataset_name") if isinstance(dataset, dict) else None
    if not dataset_id:
        status = equities_fit["status"]
        pytest.fail(f"canopy reports no dataset for the fit (GET /api/dataset: {dataset!r}), so there is no artifact to inspect. Start answered HTTP {equities_fit['start_status']}; the fit's last status was {status.get('fsm_status')!r}, completion_reason {status.get('completion_reason')!r}.")
    return str(dataset_id)


@pytest.fixture(scope="module")
def data_version(require_data, data_url: str) -> str:
    """juniper-data's self-reported version (`/v1/health` is auth-exempt)."""
    try:
        body = _body(requests.get(f"{data_url}/v1/health", timeout=DEFAULT_TIMEOUT))
    except requests.RequestException:
        return "unknown"
    return str(body.get("version", "unknown")) if isinstance(body, dict) else "unknown"


@pytest.fixture(scope="module")
def dataset_meta(require_data, data_url: str, data_http: requests.Session, fit_dataset_id: str) -> dict[str, Any]:
    """juniper-data's stored metadata for the dataset the fit consumed."""
    resp = data_http.get(f"{data_url}/v1/datasets/{quote(fit_dataset_id, safe='')}", timeout=DEFAULT_TIMEOUT)
    body = _body(resp)
    if resp.status_code != 200 or not isinstance(body, dict):
        pytest.fail(f"GET /v1/datasets/{fit_dataset_id} on juniper-data -> HTTP {resp.status_code}: {body}" + _auth_hint(resp.status_code, ENV_DATA_API_KEY, ENV_DATA_API_KEY_FILE))
    return body


@pytest.mark.full_stack
def test_canopy_start_answers_200_and_the_fit_reports_a_regression_metrics_block(equities_fit: dict[str, Any]) -> None:
    """The W1.11 acceptance: select `equities_seq`, start, expect 200 and a regression metrics block."""
    assert equities_fit["start_status"] == 200, f"POST /api/train/start -> HTTP {equities_fit['start_status']}: {equities_fit['start_body']}"

    status = equities_fit["status"]
    assert status.get("backend") == "recurrence", f"the fit ran on canopy's {status.get('backend')!r} backend, not juniper-recurrence: {status}"
    if status.get("failed"):
        pytest.fail(f"the recurrence fit FAILED: {status.get('completion_reason')!r}. That is canopy relaying juniper-recurrence's answer, or juniper-data's through it. Staged: {equities_fit['staged']}")
    assert status.get("completed") is True, f"the fit reached no terminal status within {status.get('_timed_out_after_s', _fit_timeout())} s (raise {ENV_RECURRENCE_SMOKE_TIMEOUT} for a cold equities fetch). Last status: {status}"

    metrics = equities_fit["metrics"]
    assert isinstance(metrics, dict) and metrics, f"GET /api/metrics after a completed fit answered {metrics!r}"
    missing = [key for key in REGRESSION_METRICS if key not in metrics]
    assert not missing, f"the metrics block lacks the regression metrics {missing}: {metrics}"
    not_finite = {key: metrics[key] for key in REGRESSION_METRICS if not (isinstance(metrics[key], (int, float)) and not isinstance(metrics[key], bool) and math.isfinite(metrics[key]))}
    assert not not_finite, f"regression metrics that are not finite numbers: {not_finite} (block: {metrics})"
    assert math.isclose(metrics["rmse"], math.sqrt(metrics["mse"]), rel_tol=1e-6, abs_tol=1e-12), f"rmse {metrics['rmse']} is not sqrt(mse {metrics['mse']}): the block is not one fit's regression metrics"
    classification = [key for key in CLASSIFICATION_METRICS if key in metrics]
    assert not classification, f"a regression fit reported classification metrics {classification}: {metrics}"


@pytest.mark.full_stack
def test_juniper_data_minted_the_request_canopy_staged(dataset_meta: dict[str, Any], fit_dataset_id: str) -> None:
    """canopy and juniper-recurrence forwarded the staged request intact (cf. F-C2 / F-C3, W1.2)."""
    assert dataset_meta.get("generator") == EQUITIES_SEQ, f"{fit_dataset_id} was minted by generator {dataset_meta.get('generator')!r}, not {EQUITIES_SEQ!r}"
    params = dataset_meta.get("params") or {}
    changed = {key: {"staged": expected, "minted": params.get(key, "<absent>")} for key, expected in DATASET_PARAMS.items() if params.get(key, "<absent>") != expected}
    assert not changed, f"juniper-data minted {fit_dataset_id} from different parameters than canopy staged: {changed}"


@pytest.mark.full_stack
def test_juniper_data_labels_equities_seq_regression(dataset_meta: dict[str, Any], fit_dataset_id: str, data_version: str) -> None:
    """X8 is deployed: the dataset the fit consumed is `regression`, at generator >= 6.0.0.

    Fails against published juniper-data <= 0.16.0 BY DESIGN, and says so.
    """
    task_type = dataset_meta.get("task_type")
    generator_version = str(dataset_meta.get("generator_version"))
    if task_type != "regression":
        pytest.fail(
            f"juniper-data {data_version} served {EQUITIES_SEQ} at generator {generator_version} with task_type {task_type!r} "
            f"(n_classes {dataset_meta.get('n_classes')!r}) for {fit_dataset_id}. That is the contract published juniper-data <= 0.16.0 ships. "
            f"X8 (juniper-data#437) declares it 'regression' at 6.0.0, first released in juniper-data 0.17.0. "
            f"The fit itself ran: the arrays did not change, only the label. Until the stack's juniper-data serves 6.0.0, canopy and this stack disagree with the producer about the dataset "
            f"(F-P4 / F-DEP1, W1.11 in {PLAN}). Move the juniper-data pin, or run against an image built from juniper-data main."
        )
    major_text = generator_version.split(".", 1)[0]
    assert major_text.isdigit(), f"{fit_dataset_id} carries generator_version {generator_version!r}, which is not X.Y.Z"
    assert int(major_text) >= FIRST_REGRESSION_GENERATOR_MAJOR, f"{fit_dataset_id} is labelled 'regression' at generator {generator_version}, below the {FIRST_REGRESSION_GENERATOR_MAJOR}.0.0 that X8 introduced; the label and the version disagree"
    assert dataset_meta.get("n_classes") is None, f"a 'regression' artifact still carries n_classes {dataset_meta.get('n_classes')!r} (X8 nulls it)"
