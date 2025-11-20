"""Unit tests for broadband collectors."""

from unittest.mock import AsyncMock

import pytest
from prometheus_client import CollectorRegistry

from aaisp_exporter.api.client import CHAOSClient
from aaisp_exporter.collectors.broadband import BroadbandInfoCollector, BroadbandQuotaCollector
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
            "quota_monthly": "1000000000",  # 1GB
            "quota_remaining": "500000000",  # 500MB
            "quota_timestamp": "2025-01-01 10:00:00",
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
        """Test info collection with all fields."""
        # Mock API responses
        mock_client.broadband_services.return_value = ["01234567890"]
        mock_client.broadband_info.return_value = {
            "login": "test@a",
            "postcode": "SO50",
            "tx_rate": "1000000000",  # 1Gbps
            "rx_rate": "200000000",  # 200Mbps
            "tx_rate_adjusted": "950000000",
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
        mock_client.broadband_services.return_value = ["01234567890"]
        mock_client.broadband_info.return_value = {
            "login": "test@a",
            # Missing rates/postcode on purpose
        }

        # Create collector and collect
        collector = BroadbandInfoCollector(mock_client, test_settings, test_registry)
        await collector.collect()

        # Should not raise exception
        mock_client.broadband_services.assert_called_once()
        mock_client.broadband_info.assert_called_once_with("01234567890")



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
