"""Broadband metrics collector."""

from datetime import datetime
from typing import Any

from prometheus_client import Gauge

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

        self.quota_timestamp = self._create_gauge(
            "aaisp_broadband_quota_timestamp_seconds",
            "Timestamp of quota snapshot (epoch seconds)",
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
            if not quota_data:
                logger.debug("No quota data returned", service=service)
                return

            login = quota_data.get("login", self.settings.auth.control_login or "unknown")

            # API returns quota as quota_monthly/quota_remaining fields.
            total = self._parse_bytes(
                quota_data.get("quota_monthly", quota_data.get("quota"))
            )
            remaining = self._parse_bytes(
                quota_data.get("quota_remaining", quota_data.get("remaining"))
            )

            if total is None and remaining is None:
                logger.debug("Quota fields missing", service=service)
                return

            used = None
            if total is not None and remaining is not None:
                used = max(total - remaining, 0)
            elif quota_data.get("used") is not None:
                used = self._parse_bytes(quota_data.get("used"))

            percentage = None
            if used is not None and total not in (None, 0):
                percentage = (used / total) * 100

            labels = {"service": service, "login": login}
            if total is not None:
                self.quota_total.labels(**labels).set(total)
            if used is not None:
                self.quota_used.labels(**labels).set(used)
            if remaining is not None:
                self.quota_remaining.labels(**labels).set(remaining)
            if percentage is not None:
                self.quota_percentage.labels(**labels).set(percentage)

            ts = quota_data.get("quota_timestamp")
            if ts:
                parsed_ts = self._parse_timestamp(ts)
                if parsed_ts is not None:
                    self.quota_timestamp.labels(**labels).set(parsed_ts)

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

    def _parse_bytes(self, value: Any) -> float | None:
        """Parse byte value from API response.

        Args:
            value: Value from API (could be int, string, etc.)

        Returns:
            Byte value as float

        """
        if value is None:
            return None
        if isinstance(value, (int, float)):
            return float(value)
        if isinstance(value, str):
            try:
                return float(value)
            except ValueError:
                return None
        return None

    def _parse_timestamp(self, value: Any) -> float | None:
        """Parse timestamp string to epoch seconds."""
        if value is None:
            return None
        if isinstance(value, (int, float)):
            return float(value)
        if isinstance(value, str):
            # CHAOS returns "YYYY-MM-DD HH:MM:SS"
            try:
                dt = datetime.strptime(value, "%Y-%m-%d %H:%M:%S")
                return dt.timestamp()
            except ValueError:
                try:
                    return float(value)
                except ValueError:
                    return None
        return None


@register_collector(UpdateTier.MEDIUM)
class BroadbandInfoCollector(MetricCollector):
    """Collector for broadband info and line speed metrics (MEDIUM tier - 300s)."""

    def _initialize_metrics(self) -> None:
        """Initialize info and speed metrics."""
        self.line_sync_download = self._create_gauge(
            "aaisp_broadband_line_sync_download_bps",
            "Line sync download speed in bits per second",
            labelnames=["service", "login"],
        )

        self.line_sync_upload = self._create_gauge(
            "aaisp_broadband_line_sync_upload_bps",
            "Line sync upload speed in bits per second",
            labelnames=["service", "login"],
        )

        self.line_sync_download_adjusted = self._create_gauge(
            "aaisp_broadband_line_sync_download_adjusted_bps",
            "Adjusted line sync download speed in bits per second",
            labelnames=["service", "login"],
        )

        self.service_info = self._create_gauge(
            "aaisp_broadband_service_info",
            "Service information (value always 1, info in labels)",
            labelnames=[
                "service",
                "login",
                "postcode",
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
            if not info_data:
                logger.debug("No broadband info returned", service=service)
                return

            login = info_data.get("login", self.settings.auth.control_login or "unknown")
            postcode = info_data.get("postcode", "unknown")
            base_labels = {"service": service, "login": login}

            sync_down = self._parse_speed(info_data.get("tx_rate"))
            if sync_down is not None:
                self.line_sync_download.labels(**base_labels).set(sync_down)

            sync_up = self._parse_speed(info_data.get("rx_rate"))
            if sync_up is not None:
                self.line_sync_upload.labels(**base_labels).set(sync_up)

            adjusted_down = self._parse_speed(info_data.get("tx_rate_adjusted"))
            if adjusted_down is not None:
                self.line_sync_download_adjusted.labels(**base_labels).set(adjusted_down)

            self.service_info.labels(
                **base_labels,
                postcode=postcode,
            ).set(1.0)

            logger.debug(
                "Collected broadband info metrics",
                service=service,
                sync_down=sync_down,
                sync_up=sync_up,
                adjusted_down=adjusted_down,
            )

        except Exception as e:
            logger.error(
                "Error collecting info for service",
                service=service,
                error=str(e),
            )
            raise

    def _parse_speed(self, value: Any) -> float | None:
        """Parse speed value from API response (convert to bps).

        Args:
            value: Value from API (could be in Kbps, Mbps, etc.)

        Returns:
            Speed in bits per second

        """
        if value is None:
            return None
        if isinstance(value, (int, float)):
            return float(value)
        if isinstance(value, str):
            try:
                return float(value)
            except ValueError:
                return None
        return None
