import pytest


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Let Home Assistant load custom_components/ in every test."""


@pytest.fixture
def allow_sockets(socket_enabled):
    """Client tests talk to a fake server on localhost."""
