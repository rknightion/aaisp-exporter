"""Broadband metrics collector."""

from typing import Any

from prometheus_client import Counter, Gauge

from aaisp_exporter.collectors.base import MetricCollector
from aaisp_exporter.core.constants import UpdateTier
from aaisp_exporter.core.logging import get_logger
from aaisp_exporter.core.registry import register_collector

logger = get_logger(__name__)


@register_collector(UpdateTier.FAST)
class BroadbandQuotaCollector(MetricCollector):
    """Collector for broadband quota metrics (FAST tier - 60s)."""

    def _initialize_metrics(self) -> None:
        """Initialize quota metrics."""
        self.quota_total = self._create_gauge(
            "aaisp_broadband_quota_total_bytes",
            "Total monthly quota in bytes",
            labelnames=["service", "login"],
        )

        self.quota_used = self._create_gauge(
            "aaisp_broadband_quota_used_bytes",
            "Used quota in bytes for current month",
            labelnames=["service", "login"],
        )

        self.quota_remaining = self._create_gauge(
            "aaisp_broadband_quota_remaining_bytes",
            "Remaining quota in bytes for current month",
            labelnames=["service", "login"],
        )

        self.quota_percentage = self._create_gauge(
            "aaisp_broadband_quota_percentage",
            "Percentage of quota used",
            labelnames=["service", "login"],
        )

    async def _collect_impl(self) -> None:
        """Collect quota metrics for all broadband services."""
        if not self.settings.collectors.enable_broadband:
            logger.debug("Broadband collector disabled")
            return

        try:
            # Get list of broadband services
            services = await self.client.broadband_services()
            logger.debug("Found broadband services", count=len(services))

            # Collect quota for each service
            for service in services:
                try:
                    await self._collect_service_quota(service)
                except Exception as e:
                    logger.error(
                        "Failed to collect quota for service",
                        service=service,
                        error=str(e),
                    )

        except Exception as e:
            logger.error("Failed to get broadband services", error=str(e))
            raise

    async def _collect_service_quota(self, service: str) -> None:
        """Collect quota metrics for a specific service."""
        try:
            quota_data = await self.client.broadband_quota(service)

            # Extract login from response (if available)
            login = quota_data.get("login", self.settings.auth.control_login or "unknown")

            # Extract quota values
            # Note: Actual field names may differ based on API response
            total = self._parse_bytes(quota_data.get("quota", 0))
            used = self._parse_bytes(quota_data.get("used", 0))
            remaining = self._parse_bytes(quota_data.get("remaining", 0))

            # Calculate percentage if total > 0
            percentage = (used / total * 100) if total > 0 else 0

            # Set metrics
            labels = {"service": service, "login": login}
            self.quota_total.labels(**labels).set(total)
            self.quota_used.labels(**labels).set(used)
            self.quota_remaining.labels(**labels).set(remaining)
            self.quota_percentage.labels(**labels).set(percentage)

            logger.debug(
                "Collected quota metrics",
                service=service,
                total=total,
                used=used,
                remaining=remaining,
            )

        except Exception as e:
            logger.error(
                "Error collecting quota for service",
                service=service,
                error=str(e),
            )
            raise

    def _parse_bytes(self, value: Any) -> float:
        """Parse byte value from API response.

        Args:
            value: Value from API (could be int, string, etc.)

        Returns:
            Byte value as float

        """
        if isinstance(value, (int, float)):
            return float(value)
        elif isinstance(value, str):
            # Try to parse as int
            try:
                return float(value)
            except ValueError:
                return 0.0
        return 0.0


@register_collector(UpdateTier.MEDIUM)
class BroadbandInfoCollector(MetricCollector):
    """Collector for broadband info and line speed metrics (MEDIUM tier - 300s)."""

    def _initialize_metrics(self) -> None:
        """Initialize info and speed metrics."""
        self.line_sync_download = self._create_gauge(
            "aaisp_broadband_line_sync_download_bps",
            "Line sync download speed in bits per second",
            labelnames=["service", "login", "line_type"],
        )

        self.line_sync_upload = self._create_gauge(
            "aaisp_broadband_line_sync_upload_bps",
            "Line sync upload speed in bits per second",
            labelnames=["service", "login", "line_type"],
        )

        self.throughput_download = self._create_gauge(
            "aaisp_broadband_throughput_download_bps",
            "Actual download throughput in bits per second",
            labelnames=["service", "login", "line_type"],
        )

        self.throughput_upload = self._create_gauge(
            "aaisp_broadband_throughput_upload_bps",
            "Actual upload throughput in bits per second",
            labelnames=["service", "login", "line_type"],
        )

        self.service_up = self._create_gauge(
            "aaisp_broadband_service_up",
            "Service operational status (1 = up, 0 = down)",
            labelnames=["service", "login", "line_type"],
        )

        self.line_state = self._create_gauge(
            "aaisp_broadband_line_state",
            "Line state (1 = in sync, 0 = out of sync)",
            labelnames=["service", "login", "line_type"],
        )

        self.service_info = self._create_gauge(
            "aaisp_broadband_service_info",
            "Service information (value always 1, info in labels)",
            labelnames=[
                "service",
                "login",
                "line_type",
                "package",
                "care_level",
                "router_type",
                "ipv4_address",
                "ipv6_prefix",
            ],
        )

    async def _collect_impl(self) -> None:
        """Collect info metrics for all broadband services."""
        if not self.settings.collectors.enable_broadband:
            logger.debug("Broadband collector disabled")
            return

        try:
            # Get list of broadband services
            services = await self.client.broadband_services()
            logger.debug("Found broadband services for info", count=len(services))

            # Collect info for each service
            for service in services:
                try:
                    await self._collect_service_info(service)
                except Exception as e:
                    logger.error(
                        "Failed to collect info for service",
                        service=service,
                        error=str(e),
                    )

        except Exception as e:
            logger.error("Failed to get broadband services", error=str(e))
            raise

    async def _collect_service_info(self, service: str) -> None:
        """Collect info metrics for a specific service."""
        try:
            info_data = await self.client.broadband_info(service)

            # Extract fields (actual field names depend on API response)
            # NOTE: Field names are assumptions and need validation against real API
            login = info_data.get("login", self.settings.auth.control_login or "unknown")
            line_type = info_data.get("technology", "unknown")  # ADSL, VDSL, FTTP
            package = info_data.get("package", "unknown")

            # Line speeds (may be in different units - check API response)
            sync_down = self._parse_speed(info_data.get("sync_down", 0))
            sync_up = self._parse_speed(info_data.get("sync_up", 0))
            throughput_down = self._parse_speed(info_data.get("throughput_down", 0))
            throughput_up = self._parse_speed(info_data.get("throughput_up", 0))

            # Service status
            status = info_data.get("status", "unknown")
            is_up = 1.0 if status.lower() in ["up", "active", "connected"] else 0.0

            # Line state (in sync vs out of sync)
            # Field name assumption - may be "line_status", "sync_status", etc.
            line_status = info_data.get("line_status", info_data.get("sync_status", "unknown"))
            is_in_sync = 1.0 if line_status.lower() in ["up", "in sync", "synced", "connected"] else 0.0

            # Extended service info fields
            care_level = info_data.get("care_level", info_data.get("care", "unknown"))
            router_type = info_data.get("router_type", info_data.get("router", "unknown"))
            ipv4_address = info_data.get("ipv4", info_data.get("ipv4_address", "unknown"))
            ipv6_prefix = info_data.get("ipv6_prefix", info_data.get("ipv6", "unknown"))

            # Set metrics
            speed_labels = {"service": service, "login": login, "line_type": line_type}
            self.line_sync_download.labels(**speed_labels).set(sync_down)
            self.line_sync_upload.labels(**speed_labels).set(sync_up)
            self.throughput_download.labels(**speed_labels).set(throughput_down)
            self.throughput_upload.labels(**speed_labels).set(throughput_up)
            self.service_up.labels(**speed_labels).set(is_up)
            self.line_state.labels(**speed_labels).set(is_in_sync)

            info_labels = {
                **speed_labels,
                "package": package,
                "care_level": care_level,
                "router_type": router_type,
                "ipv4_address": ipv4_address,
                "ipv6_prefix": ipv6_prefix,
            }
            self.service_info.labels(**info_labels).set(1.0)

            logger.debug(
                "Collected info metrics",
                service=service,
                line_type=line_type,
                sync_down=sync_down,
                sync_up=sync_up,
                status=status,
                line_status=line_status,
            )

        except Exception as e:
            logger.error(
                "Error collecting info for service",
                service=service,
                error=str(e),
            )
            raise

    def _parse_speed(self, value: Any) -> float:
        """Parse speed value from API response (convert to bps).

        Args:
            value: Value from API (could be in Kbps, Mbps, etc.)

        Returns:
            Speed in bits per second

        """
        if isinstance(value, (int, float)):
            # Assume already in bps
            return float(value)
        elif isinstance(value, str):
            try:
                return float(value)
            except ValueError:
                return 0.0
        return 0.0


@register_collector(UpdateTier.SLOW)
class BroadbandUsageCollector(MetricCollector):
    """Collector for broadband usage metrics (SLOW tier - 900s).

    NOTE: The format of the /broadband/usage API response is unknown and needs
    validation against the real CHAOS API. This collector makes assumptions about
    the response structure and may need adjustment.
    """

    def _initialize_metrics(self) -> None:
        """Initialize usage metrics."""
        # NOTE: Using Gauge for now - may need to change to Counter depending on API format
        self.usage_download = self._create_gauge(
            "aaisp_broadband_usage_download_bytes",
            "Download usage in bytes (current period)",
            labelnames=["service", "login"],
        )

        self.usage_upload = self._create_gauge(
            "aaisp_broadband_usage_upload_bytes",
            "Upload usage in bytes (current period)",
            labelnames=["service", "login"],
        )

    async def _collect_impl(self) -> None:
        """Collect usage metrics for all broadband services."""
        if not self.settings.collectors.enable_broadband:
            logger.debug("Broadband collector disabled")
            return

        try:
            # Get list of broadband services
            services = await self.client.broadband_services()
            logger.debug("Found broadband services for usage", count=len(services))

            # Collect usage for each service
            for service in services:
                try:
                    await self._collect_service_usage(service)
                except Exception as e:
                    logger.error(
                        "Failed to collect usage for service",
                        service=service,
                        error=str(e),
                    )

        except Exception as e:
            logger.error("Failed to get broadband services", error=str(e))
            raise

    async def _collect_service_usage(self, service: str) -> None:
        """Collect usage metrics for a specific service.

        NOTE: The API response format is unknown. This implementation assumes:
        - Response contains "download" and "upload" fields with byte values
        - Values represent current period totals (not time-series)

        This will need adjustment after testing against real API.
        """
        try:
            usage_data = await self.client.broadband_usage(service)

            # Extract login from response (if available)
            login = usage_data.get("login", self.settings.auth.control_login or "unknown")

            # Extract usage values
            # NOTE: Field names and structure are assumptions
            # The API may return:
            # - Simple totals: {"download": 123456, "upload": 654321}
            # - Time-series data: {"usage": [{"time": "...", "download": ..., "upload": ...}]}
            # - Aggregated data: {"total_download": ..., "total_upload": ...}
            #
            # For now, assume simple totals. Will need adjustment after API testing.
            download_bytes = self._parse_bytes(
                usage_data.get("download", usage_data.get("download_bytes", 0))
            )
            upload_bytes = self._parse_bytes(
                usage_data.get("upload", usage_data.get("upload_bytes", 0))
            )

            # Set metrics
            labels = {"service": service, "login": login}
            self.usage_download.labels(**labels).set(download_bytes)
            self.usage_upload.labels(**labels).set(upload_bytes)

            logger.debug(
                "Collected usage metrics",
                service=service,
                download=download_bytes,
                upload=upload_bytes,
            )

        except Exception as e:
            logger.warning(
                "Error collecting usage for service (API format may not match expectations)",
                service=service,
                error=str(e),
            )
            # Don't raise - usage collection is experimental until API format is validated

    def _parse_bytes(self, value: Any) -> float:
        """Parse byte value from API response.

        Args:
            value: Value from API (could be int, string, etc.)

        Returns:
            Byte value as float

        """
        if isinstance(value, (int, float)):
            return float(value)
        elif isinstance(value, str):
            try:
                return float(value)
            except ValueError:
                logger.warning("Could not parse bytes value", value=value)
                return 0.0
        return 0.0
