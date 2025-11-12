"""Tests for configuration module."""

import pytest
from pydantic import SecretStr, ValidationError

from aaisp_exporter.core.config import (
    AuthSettings,
    CHAOSAPISettings,
    Settings,
    UpdateIntervals,
)
from aaisp_exporter.core.constants import UpdateTier


class TestAuthSettings:
    """Tests for AuthSettings."""

    def test_has_control_auth_with_credentials(self) -> None:
        """Test has_control_auth returns True when credentials are set."""
        auth = AuthSettings(
            control_login="test@a",
            control_password=SecretStr("password"),
        )
        assert auth.has_control_auth() is True

    def test_has_control_auth_without_credentials(self) -> None:
        """Test has_control_auth returns False when credentials are missing."""
        auth = AuthSettings()
        assert auth.has_control_auth() is False

    def test_has_account_auth_with_credentials(self) -> None:
        """Test has_account_auth returns True when credentials are set."""
        auth = AuthSettings(
            account_number="A1234A",
            account_password=SecretStr("password"),
        )
        assert auth.has_account_auth() is True

    def test_has_account_auth_without_credentials(self) -> None:
        """Test has_account_auth returns False when credentials are missing."""
        auth = AuthSettings()
        assert auth.has_account_auth() is False

    def test_has_any_auth_with_control(self) -> None:
        """Test has_any_auth returns True with control auth."""
        auth = AuthSettings(
            control_login="test@a",
            control_password=SecretStr("password"),
        )
        assert auth.has_any_auth() is True

    def test_has_any_auth_with_account(self) -> None:
        """Test has_any_auth returns True with account auth."""
        auth = AuthSettings(
            account_number="A1234A",
            account_password=SecretStr("password"),
        )
        assert auth.has_any_auth() is True

    def test_has_any_auth_without_credentials(self) -> None:
        """Test has_any_auth returns False without credentials."""
        auth = AuthSettings()
        assert auth.has_any_auth() is False


class TestUpdateIntervals:
    """Tests for UpdateIntervals."""

    def test_default_intervals(self) -> None:
        """Test default interval values."""
        intervals = UpdateIntervals()
        assert intervals.fast == 60
        assert intervals.medium == 300
        assert intervals.slow == 900

    def test_get_interval(self) -> None:
        """Test get_interval returns correct values."""
        intervals = UpdateIntervals()
        assert intervals.get_interval(UpdateTier.FAST) == 60
        assert intervals.get_interval(UpdateTier.MEDIUM) == 300
        assert intervals.get_interval(UpdateTier.SLOW) == 900

    def test_custom_intervals(self) -> None:
        """Test custom interval values."""
        intervals = UpdateIntervals(fast=30, medium=120, slow=600)
        assert intervals.fast == 30
        assert intervals.medium == 120
        assert intervals.slow == 600

    def test_interval_validation_min(self) -> None:
        """Test interval validation for minimum values."""
        with pytest.raises(ValidationError):
            UpdateIntervals(fast=5)  # Below minimum of 10

    def test_interval_validation_max(self) -> None:
        """Test interval validation for maximum values."""
        with pytest.raises(ValidationError):
            UpdateIntervals(slow=10000)  # Above maximum of 7200


class TestCHAOSAPISettings:
    """Tests for CHAOSAPISettings."""

    def test_default_settings(self) -> None:
        """Test default API settings."""
        api = CHAOSAPISettings()
        assert api.base_url == "https://chaos2.aa.net.uk"
        assert api.timeout == 30
        assert api.max_retries == 3
        assert api.concurrency_limit == 5

    def test_custom_settings(self) -> None:
        """Test custom API settings."""
        api = CHAOSAPISettings(
            base_url="https://custom.api.url",
            timeout=60,
            max_retries=5,
            concurrency_limit=10,
        )
        assert api.base_url == "https://custom.api.url"
        assert api.timeout == 60
        assert api.max_retries == 5
        assert api.concurrency_limit == 10


class TestSettings:
    """Tests for Settings."""

    def test_validate_auth_with_control_auth(self) -> None:
        """Test validate_auth succeeds with control authentication."""
        settings = Settings(
            auth=AuthSettings(
                control_login="test@a",
                control_password=SecretStr("password"),
            ),
        )
        # Should not raise
        settings.validate_auth()

    def test_validate_auth_with_account_auth(self) -> None:
        """Test validate_auth succeeds with account authentication."""
        settings = Settings(
            auth=AuthSettings(
                account_number="A1234A",
                account_password=SecretStr("password"),
            ),
        )
        # Should not raise
        settings.validate_auth()

    def test_validate_auth_without_credentials(self) -> None:
        """Test validate_auth raises ValueError without any authentication."""
        settings = Settings(auth=AuthSettings())
        with pytest.raises(ValueError, match="No authentication configured"):
            settings.validate_auth()

    def test_nested_configuration(self) -> None:
        """Test nested configuration structure."""
        settings = Settings()
        assert isinstance(settings.api, CHAOSAPISettings)
        assert isinstance(settings.auth, AuthSettings)
        assert isinstance(settings.intervals, UpdateIntervals)
