"""Constants and enumerations for the AAISP exporter."""

from enum import Enum


class UpdateTier(str, Enum):
    """Collection update tiers based on data volatility."""

    FAST = "fast"  # 60 seconds - real-time data (quota usage, line status)
    MEDIUM = "medium"  # 300 seconds - operational metrics (speeds, throughput)
    SLOW = "slow"  # 900 seconds - configuration data (service info, settings)


class Subsystem(str, Enum):
    """CHAOS API subsystems."""

    BROADBAND = "broadband"
    LOGIN = "login"
    TELEPHONY = "telephony"
    DOMAIN = "domain"
    EMAIL = "email"
    SIM = "sim"


# Default update intervals in seconds
DEFAULT_INTERVALS = {
    UpdateTier.FAST: 60,
    UpdateTier.MEDIUM: 300,
    UpdateTier.SLOW: 900,
}

# CHAOS API base URL
CHAOS_API_BASE_URL = "https://chaos2.aa.net.uk"

# Default exporter settings
DEFAULT_SERVER_HOST = "0.0.0.0"
DEFAULT_SERVER_PORT = 9099
DEFAULT_LOG_LEVEL = "INFO"
DEFAULT_API_TIMEOUT = 30
DEFAULT_MAX_RETRIES = 3
DEFAULT_CONCURRENCY_LIMIT = 5
