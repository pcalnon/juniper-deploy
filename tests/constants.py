#!/usr/bin/env python
#####################################################################################################################################################################################################
# Project:       Juniper
# Application:   juniper-deploy
# File Name:     constants.py
# Author:        Paul Calnon
#
# Date Created:  2026-03-13
# Last Modified: 2026-10-08
#
# License:       MIT License
# Copyright:     Copyright (c) 2024-2026 Paul Calnon
#
# Description:
#    Shared constants for the Juniper integration test suite. Extracted from
#    conftest.py so that test modules can import them with a standard Python
#    import (conftest.py is pytest-special and not importable as a module).
#
#####################################################################################################################################################################################################

# Default HTTP request timeout in seconds
DEFAULT_TIMEOUT = 10

# ─── Default service URLs (host-side ports exposed by docker-compose.yml) ───
# Used by conftest.py when the corresponding ENV_* override is unset.
DEFAULT_DATA_URL = "http://localhost:8100"
DEFAULT_CASCOR_URL = "http://localhost:8201"
DEFAULT_CANOPY_URL = "http://localhost:8050"

# URL juniper-cascor uses internally to reach juniper-data (docker network).
DEFAULT_INTERNAL_DATA_URL = "http://juniper-data:8100"

# ─── Environment variable names for URL overrides ───────────────────────────
ENV_DATA_URL = "JUNIPER_TEST_DATA_URL"
ENV_CASCOR_URL = "JUNIPER_TEST_CASCOR_URL"
ENV_CANOPY_URL = "JUNIPER_TEST_CANOPY_URL"
ENV_INTERNAL_DATA_URL = "JUNIPER_TEST_INTERNAL_DATA_URL"

# ─── Environment variable names for API key overrides ───────────────────────
ENV_DATA_API_KEY = "JUNIPER_TEST_DATA_API_KEY"  # nosec B105 — env var name, not a key value
ENV_CASCOR_API_KEY = "JUNIPER_TEST_CASCOR_API_KEY"  # nosec B105 — env var name, not a key value
ENV_CANOPY_API_KEY = "JUNIPER_TEST_CANOPY_API_KEY"  # nosec B105 — env var name, not a key value

# *_FILE indirection, the stack's Docker-secret convention. Read only when the plain variable
# above is unset: conftest takes the first non-comment line of the file and, within it, the first
# comma-separated entry, so an accept-list file such as juniper_data_api_keys works unchanged.
# The compose `test-runner` service points these at /run/secrets/<name>, so no key value ever
# sits in its environment (`docker inspect` shows the path, not the key).
ENV_DATA_API_KEY_FILE = "JUNIPER_TEST_DATA_API_KEY_FILE"  # nosec B105 — env var name, not a key value
ENV_CASCOR_API_KEY_FILE = "JUNIPER_TEST_CASCOR_API_KEY_FILE"  # nosec B105 — env var name, not a key value
ENV_CANOPY_API_KEY_FILE = "JUNIPER_TEST_CANOPY_API_KEY_FILE"  # nosec B105 — env var name, not a key value

# ─── canopy -> recurrence -> juniper-data smoke (test_canopy_recurrence_equities_smoke.py) ───
# Budget for the one-shot fit, from Start to a terminal status. A cold `equities_seq` request
# fetches from Yahoo Finance and SEC EDGAR inside juniper-data, and canopy's own recurrence
# adapter gives up at 300 s, so this sits above that: a canopy-side timeout then surfaces as the
# `failed` status it produces, not as this budget running out first.
ENV_RECURRENCE_SMOKE_TIMEOUT = "JUNIPER_TEST_RECURRENCE_SMOKE_TIMEOUT"
DEFAULT_RECURRENCE_SMOKE_TIMEOUT = 360
# Seconds between status polls. canopy rate-limits at 60 requests a minute by default, so a
# 3 s poll stays far below it.
RECURRENCE_SMOKE_POLL_INTERVAL = 3
# HTTP timeout for canopy's control calls. Selecting a model re-creates canopy's backend and
# shuts the old one down, which can take longer than DEFAULT_TIMEOUT.
CONTROL_TIMEOUT = 60
