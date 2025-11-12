"""Configuration management using pydantic-settings."""

from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

from aaisp_exporter.core.constants import (
    CHAOS_API_BASE_URL,
    DEFAULT_API_TIMEOUT,
    DEFAULT_CONCURRENCY_LIMIT,
    DEFAULT_INTERVALS,
    DEFAULT_LOG_LEVEL,
    DEFAULT_MAX_RETRIES,
    DEFAULT_SERVER_HOST,
    DEFAULT_SERVER_PORT,
    UpdateTier,
)


class CHAOSAPISettings(BaseSettings):
    """CHAOS API connection settings."""

    base_url: str = Field(
        default=CHAOS_API_BASE_URL,
        description="Base URL for the CHAOS API",
    )
    timeout: int = Field(
        default=DEFAULT_API_TIMEOUT,
        description="API request timeout in seconds",
        ge=1,
        le=300,
    )
    max_retries: int = Field(
        default=DEFAULT_MAX_RETRIES,
        description="Maximum number of retries for failed requests",
        ge=0,
        le=10,
    )
    concurrency_limit: int = Field(
        default=DEFAULT_CONCURRENCY_LIMIT,
        description="Maximum concurrent API requests",
        ge=1,
        le=50,
    )


class AuthSettings(BaseSettings):
    """Authentication credentials for CHAOS API."""

    control_login: str | None = Field(
        default=None,
        description="Control pages login (e.g., test@a)",
    )
    control_password: SecretStr | None = Field(
        default=None,
        description="Control pages password",
    )
    account_number: str | None = Field(
        default=None,
        description="Account number (e.g., A1234A)",
    )
    account_password: SecretStr | None = Field(
        default=None,
        description="Account password",
    )

    def has_control_auth(self) -> bool:
        """Check if control authentication is configured."""
        return bool(self.control_login and self.control_password)

    def has_account_auth(self) -> bool:
        """Check if account authentication is configured."""
        return bool(self.account_number and self.account_password)

    def has_any_auth(self) -> bool:
        """Check if any authentication is configured."""
        return self.has_control_auth() or self.has_account_auth()


class UpdateIntervals(BaseSettings):
    """Collection update intervals for different tiers."""

    fast: int = Field(
        default=DEFAULT_INTERVALS[UpdateTier.FAST],
        description="Fast tier update interval in seconds (real-time data)",
        ge=10,
        le=3600,
    )
    medium: int = Field(
        default=DEFAULT_INTERVALS[UpdateTier.MEDIUM],
        description="Medium tier update interval in seconds (operational metrics)",
        ge=60,
        le=3600,
    )
    slow: int = Field(
        default=DEFAULT_INTERVALS[UpdateTier.SLOW],
        description="Slow tier update interval in seconds (configuration data)",
        ge=300,
        le=7200,
    )

    def get_interval(self, tier: UpdateTier) -> int:
        """Get interval for a specific tier."""
        return {
            UpdateTier.FAST: self.fast,
            UpdateTier.MEDIUM: self.medium,
            UpdateTier.SLOW: self.slow,
        }[tier]


class ServerSettings(BaseSettings):
    """HTTP server settings."""

    host: str = Field(
        default=DEFAULT_SERVER_HOST,
        description="Server bind host",
    )
    port: int = Field(
        default=DEFAULT_SERVER_PORT,
        description="Server bind port",
        ge=1,
        le=65535,
    )


class LoggingSettings(BaseSettings):
    """Logging configuration."""

    level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = Field(
        default=DEFAULT_LOG_LEVEL,  # type: ignore[arg-type]
        description="Log level",
    )
    json: bool = Field(
        default=False,
        description="Enable JSON logging",
    )


class CollectorSettings(BaseSettings):
    """Collector-specific settings."""

    enable_broadband: bool = Field(
        default=True,
        description="Enable broadband collector",
    )
    enable_telephony: bool = Field(
        default=False,
        description="Enable telephony collector",
    )
    enable_login: bool = Field(
        default=False,
        description="Enable login collector",
    )


class Settings(BaseSettings):
    """Main application settings."""

    model_config = SettingsConfigDict(
        env_prefix="AAISP_EXPORTER_",
        env_file=".env",
        env_file_encoding="utf-8",
        env_nested_delimiter="__",
        case_sensitive=False,
    )

    # Nested configuration sections
    api: CHAOSAPISettings = Field(default_factory=CHAOSAPISettings)
    auth: AuthSettings = Field(default_factory=AuthSettings)
    intervals: UpdateIntervals = Field(default_factory=UpdateIntervals)
    server: ServerSettings = Field(default_factory=ServerSettings)
    logging: LoggingSettings = Field(default_factory=LoggingSettings)
    collectors: CollectorSettings = Field(default_factory=CollectorSettings)

    def validate_auth(self) -> None:
        """Validate that at least one authentication method is configured."""
        if not self.auth.has_any_auth():
            msg = (
                "No authentication configured. Please provide either:\n"
                "  - AAISP_EXPORTER_AUTH__CONTROL_LOGIN and AAISP_EXPORTER_AUTH__CONTROL_PASSWORD\n"
                "  - AAISP_EXPORTER_AUTH__ACCOUNT_NUMBER and AAISP_EXPORTER_AUTH__ACCOUNT_PASSWORD"
            )
            raise ValueError(msg)
