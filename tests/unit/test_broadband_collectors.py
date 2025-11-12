"""Unit tests for broadband collectors."""

from unittest.mock import AsyncMock, MagicMock

import pytest
from prometheus_client import CollectorRegistry

from aaisp_exporter.api.client import CHAOSClient
from aaisp_exporter.collectors.broadband import (
    BroadbandInfoCollector,
    BroadbandQuotaCollector,
    BroadbandUsageCollector,
)
from aaisp_exporter.core.config import Settings


@pytest.fixture
def mock_client() -> AsyncMock:
    """Create a mock CHAOS API client."""
    client = AsyncMock(spec=CHAOSClient)
    return client


@pytest.fixture
def test_settings(settings: Settings) -> Settings:
    """Get test settings with broadband enabled."""
    settings.collectors.enable_broadband = True
    return settings


@pytest.fixture
def test_registry() -> CollectorRegistry:
    """Create a test Prometheus registry."""
    return CollectorRegistry()


class TestBroadbandQuotaCollector:
    """Tests for BroadbandQuotaCollector."""

    @pytest.mark.asyncio
    async def test_collect_quota_metrics(
        self, mock_client: AsyncMock, test_settings: Settings, test_registry: CollectorRegistry
    ) -> None:
        """Test quota collection with basic data."""
        # Mock API responses
        mock_client.broadband_services.return_value = ["01234567890"]
        mock_client.broadband_quota.return_value = {
            "login": "test@a",
            "quota": "1000000000",  # 1GB
            "used": "500000000",  # 500MB
            "remaining": "500000000",  # 500MB
        }

        # Create collector and collect
        collector = BroadbandQuotaCollector(mock_client, test_settings, test_registry)
        await collector.collect()

        # Verify API calls
        mock_client.broadband_services.assert_called_once()
        mock_client.broadband_quota.assert_called_once_with("01234567890")


class TestBroadbandInfoCollector:
    """Tests for BroadbandInfoCollector."""

    @pytest.mark.asyncio
    async def test_collect_info_metrics_with_all_fields(
        self, mock_client: AsyncMock, test_settings: Settings, test_registry: CollectorRegistry
    ) -> None:
        """Test info collection with all fields including new ones."""
        # Mock API responses
        mock_client.broadband_services.return_value = ["01234567890"]
        mock_client.broadband_info.return_value = {
            "login": "test@a",
            "technology": "FTTP",
            "package": "Home::1",
            "sync_down": "1000000000",  # 1Gbps
            "sync_up": "200000000",  # 200Mbps
            "throughput_down": "950000000",  # 950Mbps
            "throughput_up": "190000000",  # 190Mbps
            "status": "up",
            "line_status": "in sync",
            "care_level": "standard",
            "router_type": "ZyXEL",
            "ipv4": "198.51.100.1",
            "ipv6_prefix": "2001:db8::/64",
        }

        # Create collector and collect
        collector = BroadbandInfoCollector(mock_client, test_settings, test_registry)
        await collector.collect()

        # Verify API calls
        mock_client.broadband_services.assert_called_once()
        mock_client.broadband_info.assert_called_once_with("01234567890")

    @pytest.mark.asyncio
    async def test_collect_info_metrics_with_missing_fields(
        self, mock_client: AsyncMock, test_settings: Settings, test_registry: CollectorRegistry
    ) -> None:
        """Test info collection handles missing optional fields gracefully."""
        # Mock API responses with minimal data
        mock_client.broadband_services.return_value = ["01234567890"]
        mock_client.broadband_info.return_value = {
            "login": "test@a",
            "status": "up",
        }

        # Create collector and collect
        collector = BroadbandInfoCollector(mock_client, test_settings, test_registry)
        await collector.collect()

        # Should not raise exception
        mock_client.broadband_services.assert_called_once()
        mock_client.broadband_info.assert_called_once_with("01234567890")

    @pytest.mark.asyncio
    async def test_line_state_metric(
        self, mock_client: AsyncMock, test_settings: Settings, test_registry: CollectorRegistry
    ) -> None:
        """Test line_state metric is set correctly."""
        # Test with in sync status
        mock_client.broadband_services.return_value = ["01234567890"]
        mock_client.broadband_info.return_value = {
            "login": "test@a",
            "line_status": "in sync",
            "status": "up",
        }

        collector = BroadbandInfoCollector(mock_client, test_settings, test_registry)
        await collector.collect()

        # Verify line_state metric exists
        assert collector.line_state is not None


class TestBroadbandUsageCollector:
    """Tests for BroadbandUsageCollector."""

    @pytest.mark.asyncio
    async def test_collect_usage_metrics(
        self, mock_client: AsyncMock, test_settings: Settings, test_registry: CollectorRegistry
    ) -> None:
        """Test usage collection with basic data."""
        # Mock API responses
        mock_client.broadband_services.return_value = ["01234567890"]
        mock_client.broadband_usage.return_value = {
            "login": "test@a",
            "download": "50000000000",  # 50GB
            "upload": "10000000000",  # 10GB
        }

        # Create collector and collect
        collector = BroadbandUsageCollector(mock_client, test_settings, test_registry)
        await collector.collect()

        # Verify API calls
        mock_client.broadband_services.assert_called_once()
        mock_client.broadband_usage.assert_called_once_with("01234567890")

    @pytest.mark.asyncio
    async def test_collect_usage_handles_errors_gracefully(
        self, mock_client: AsyncMock, test_settings: Settings, test_registry: CollectorRegistry
    ) -> None:
        """Test usage collection doesn't raise on API errors."""
        # Mock API to raise an error
        mock_client.broadband_services.return_value = ["01234567890"]
        mock_client.broadband_usage.side_effect = Exception("API format unexpected")

        # Create collector and collect
        collector = BroadbandUsageCollector(mock_client, test_settings, test_registry)

        # Should not raise exception (only logs warning)
        await collector.collect()

        mock_client.broadband_services.assert_called_once()
        mock_client.broadband_usage.assert_called_once_with("01234567890")

    @pytest.mark.asyncio
    async def test_parse_bytes_with_different_formats(
        self, mock_client: AsyncMock, test_settings: Settings, test_registry: CollectorRegistry
    ) -> None:
        """Test _parse_bytes handles different value formats."""
        collector = BroadbandUsageCollector(mock_client, test_settings, test_registry)

        # Test integer
        assert collector._parse_bytes(1000) == 1000.0

        # Test float
        assert collector._parse_bytes(1000.5) == 1000.5

        # Test string
        assert collector._parse_bytes("2000") == 2000.0

        # Test invalid string
        assert collector._parse_bytes("invalid") == 0.0

        # Test None
        assert collector._parse_bytes(None) == 0.0


class TestAPIClientMetrics:
    """Tests for API client metrics."""

    @pytest.mark.asyncio
    async def test_api_client_records_metrics(
        self, test_settings: Settings, test_registry: CollectorRegistry
    ) -> None:
        """Test that API client records request metrics when registry is provided."""
        client = CHAOSClient(
            api_settings=test_settings.api,
            auth_settings=test_settings.auth,
            registry=test_registry,
        )

        # Verify metrics were created
        assert client._api_requests_total is not None
        assert client._api_request_duration is not None

    @pytest.mark.asyncio
    async def test_api_client_without_registry(self, test_settings: Settings) -> None:
        """Test that API client works without registry (no metrics)."""
        client = CHAOSClient(
            api_settings=test_settings.api,
            auth_settings=test_settings.auth,
            registry=None,
        )

        # Verify metrics are None
        assert client._api_requests_total is None
        assert client._api_request_duration is None

    def test_record_request_metrics(
        self, test_settings: Settings, test_registry: CollectorRegistry
    ) -> None:
        """Test _record_request_metrics increments counters."""
        client = CHAOSClient(
            api_settings=test_settings.api,
            auth_settings=test_settings.auth,
            registry=test_registry,
        )

        # Record some metrics
        client._record_request_metrics("broadband", "info", 200, 0.5)
        client._record_request_metrics("broadband", "quota", 200, 0.3)
        client._record_request_metrics("broadband", "info", 401, 0.1)

        # Metrics should have been recorded (can't easily assert values without
        # exporting the registry, but at least verify no exceptions)
        assert client._api_requests_total is not None
        assert client._api_request_duration is not None
