"""Pytest configuration and shared fixtures."""

import pytest
from pydantic import SecretStr

from aaisp_exporter.core.config import AuthSettings, Settings


@pytest.fixture
def auth_settings_control() -> AuthSettings:
    """Fixture for control login authentication settings."""
    return AuthSettings(
        control_login="test@a",
        control_password=SecretStr("test_password"),
    )


@pytest.fixture
def auth_settings_account() -> AuthSettings:
    """Fixture for account authentication settings."""
    return AuthSettings(
        account_number="A1234A",
        account_password=SecretStr("test_password"),
    )


@pytest.fixture
def settings(auth_settings_control: AuthSettings) -> Settings:
    """Fixture for application settings with control authentication."""
    return Settings(auth=auth_settings_control)
