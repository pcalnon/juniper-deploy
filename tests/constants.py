#!/usr/bin/env python
#####################################################################################################################################################################################################
# Project:       Juniper
# Application:   juniper-deploy
# File Name:     constants.py
# Author:        Paul Calnon
#
# Date Created:  2026-03-13
# Last Modified: 2026-04-10
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
