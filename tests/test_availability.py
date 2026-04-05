#!/usr/bin/env python
#####################################################################################################################################################################################################
# Project:       Juniper
# Application:   juniper-deploy
# File Name:     test_availability.py
# Author:        Paul Calnon
#
# Date Created:  2026-03-14
# Last Modified: 2026-03-14
#
# License:       MIT License
# Copyright:     Copyright (c) 2024-2026 Paul Calnon
#
# Description:
#    Tests for the service availability checking mechanism in conftest.py.
#    Validates that _check_service_available() correctly skips when a service
#    is unreachable and that all require_* fixtures are properly registered
#    with session scope.
#
#    These tests always PASS regardless of whether Docker services are running.
#
#####################################################################################################################################################################################################

import pytest

from conftest import _check_service_available


# ---------------------------------------------------------------------------
# Skip mechanism tests
# ---------------------------------------------------------------------------
class TestCheckServiceAvailable:
    """Verify _check_service_available() correctly triggers pytest.skip."""

    def test_unreachable_service_triggers_skip(self):
        """Connecting to a guaranteed-unreachable address produces pytest.skip."""
        with pytest.raises(pytest.skip.Exception):
            _check_service_available("http://localhost:1", "test-unreachable-service", timeout=1)

    def test_skip_message_contains_service_name(self):
        """The skip reason should identify which service is down."""
        with pytest.raises(pytest.skip.Exception, match="test-service-name"):
            _check_service_available("http://localhost:1", "test-service-name", timeout=1)

    def test_skip_message_contains_url(self):
        """The skip reason should include the URL that was unreachable."""
        with pytest.raises(pytest.skip.Exception, match="localhost:1"):
            _check_service_available("http://localhost:1", "test-service", timeout=1)

    def test_skip_message_contains_docker_hint(self):
        """The skip reason should hint at how to start services."""
        with pytest.raises(pytest.skip.Exception, match="docker compose up"):
            _check_service_available("http://localhost:1", "test-service", timeout=1)


# ---------------------------------------------------------------------------
# Fixture registration and scope tests
# ---------------------------------------------------------------------------
class TestFixtureRegistration:
    """Verify require_* fixtures are registered with the correct scope."""

    def _get_fixturedefs(self, request, name):
        """Return FixtureDef list for a fixture name, or None if not registered."""
        return request.session._fixturemanager.getfixturedefs(name, request.node)

    def test_require_data_fixture_exists(self, request):
        """The require_data fixture is registered in conftest."""
        assert self._get_fixturedefs(request, "require_data") is not None

    def test_require_cascor_fixture_exists(self, request):
        """The require_cascor fixture is registered in conftest."""
        assert self._get_fixturedefs(request, "require_cascor") is not None

    def test_require_canopy_fixture_exists(self, request):
        """The require_canopy fixture is registered in conftest."""
        assert self._get_fixturedefs(request, "require_canopy") is not None

    def test_require_all_services_fixture_exists(self, request):
        """The require_all_services fixture is registered in conftest."""
        assert self._get_fixturedefs(request, "require_all_services") is not None

    def test_all_availability_fixtures_are_session_scoped(self, request):
        """All require_* fixtures must be session-scoped to run before class/function fixtures."""
        for name in ("require_data", "require_cascor", "require_canopy", "require_all_services"):
            fixturedefs = self._get_fixturedefs(request, name)
            assert fixturedefs is not None, f"{name} fixture not found"
            assert fixturedefs[-1].scope == "session", (
                f"{name} fixture must be session-scoped, got {fixturedefs[-1].scope}"
            )
