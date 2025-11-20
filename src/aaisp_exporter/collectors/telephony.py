"""Telephony metrics collectors."""

from collections import Counter
from typing import Any

from prometheus_client import Counter, Gauge

from aaisp_exporter.collectors.base import MetricCollector
from aaisp_exporter.core.constants import UpdateTier
from aaisp_exporter.core.logging import get_logger
from aaisp_exporter.core.registry import register_collector

logger = get_logger(__name__)


@register_collector(UpdateTier.MEDIUM)
class TelephonyInfoCollector(MetricCollector):
    """Collector for telephony service information (MEDIUM tier - 300s)."""

    def _initialize_metrics(self) -> None:
        """Initialize telephony metrics."""
        self.service_info = self._create_gauge(
            "aaisp_telephony_service_info",
            "Telephony service information (value always 1, info in labels)",
            labelnames=[
                "number",
                "status",
                "call_forwarding",
                "voicemail",
                "service_type",
            ],
        )

        self.call_count_total = self._create_counter(
            "aaisp_telephony_calls_total",
            "Total number of calls",
            labelnames=["number", "direction"],
        )

        self.call_duration_seconds_total = self._create_counter(
            "aaisp_telephony_call_duration_seconds_total",
            "Total call duration in seconds",
            labelnames=["number", "direction"],
        )

        self.call_cost_total = self._create_counter(
            "aaisp_telephony_call_cost_total",
            "Total call cost",
            labelnames=["number", "direction", "currency"],
        )

        # Gauge for current active calls
        self.active_calls = self._create_gauge(
            "aaisp_telephony_active_calls",
            "Number of currently active calls",
            labelnames=["number"],
        )

    async def _collect_impl(self) -> None:
        """Collect telephony metrics for all services."""
        if not self.settings.collectors.enable_telephony:
            logger.debug("Telephony collector disabled")
            return

        try:
            # Get list of telephony services
            services = await self.client.telephony_services()

            if not services:
                logger.info(
                    "No telephony services found for this account",
                    help="If you don't have AAISP telephony/VoIP services, "
                         "disable with AAISP_EXPORTER_COLLECTORS__ENABLE_TELEPHONY=false",
                )
                return

            logger.debug("Found telephony services", count=len(services))

            # Collect info for each service
            for service in services:
                try:
                    await self._collect_service_info(service)
                except Exception as e:
                    logger.error(
                        "Failed to collect info for telephony service",
                        service=service,
                        error=str(e),
                    )

        except Exception as e:
            error_msg = str(e)

            # Handle HTTP 500 errors - likely no telephony services or command not implemented
            if "500" in error_msg or "Internal Server Error" in error_msg:
                logger.warning(
                    "Telephony services query failed",
                    help="This account may not have telephony services, or the 'services' command "
                         "is not fully implemented for telephony. This is expected if you don't have "
                         "VoIP services. Disable with AAISP_EXPORTER_COLLECTORS__ENABLE_TELEPHONY=false",
                )
                return  # Gracefully skip - not a fatal error

            # For other errors, log and raise
            logger.error("Failed to get telephony services", error=error_msg)
            raise

    async def _collect_service_info(self, number: str) -> None:
        """Collect info metrics for a specific telephony service.

        Args:
            number: Phone number identifier

        """
        try:
            info_data = await self.client.telephony_info(number)

            # Extract service information
            # NOTE: Field names are assumptions and may need adjustment based on actual API
            status = info_data.get("status", "unknown")
            call_forwarding = info_data.get("call_forwarding", info_data.get("forwarding", "unknown"))
            voicemail = info_data.get("voicemail", info_data.get("voicemail_enabled", "unknown"))
            service_type = info_data.get("service_type", info_data.get("type", "unknown"))

            # Set service info metric
            info_labels = {
                "number": number,
                "status": status,
                "call_forwarding": str(call_forwarding).lower(),
                "voicemail": str(voicemail).lower(),
                "service_type": service_type,
            }
            self.service_info.labels(**info_labels).set(1.0)

            # Extract call statistics if available
            # These might be in various formats depending on API
            call_stats = info_data.get("call_stats", info_data.get("statistics", {}))

            # Inbound calls
            inbound_count = self._parse_int(call_stats.get("inbound_calls", call_stats.get("calls_in", None)))
            inbound_duration = self._parse_float(
                call_stats.get("inbound_duration", call_stats.get("duration_in", None))
            )
            inbound_cost = self._parse_float(call_stats.get("inbound_cost", call_stats.get("cost_in", None)))

            if inbound_count is not None and inbound_count > 0:
                self.call_count_total.labels(number=number, direction="inbound").inc(inbound_count)
            if inbound_duration is not None and inbound_duration > 0:
                self.call_duration_seconds_total.labels(number=number, direction="inbound").inc(inbound_duration)
            if inbound_cost is not None and inbound_cost > 0:
                currency = info_data.get("currency", "GBP")
                self.call_cost_total.labels(number=number, direction="inbound", currency=currency).inc(inbound_cost)

            # Outbound calls
            outbound_count = self._parse_int(call_stats.get("outbound_calls", call_stats.get("calls_out", None)))
            outbound_duration = self._parse_float(
                call_stats.get("outbound_duration", call_stats.get("duration_out", None))
            )
            outbound_cost = self._parse_float(call_stats.get("outbound_cost", call_stats.get("cost_out", None)))

            if outbound_count is not None and outbound_count > 0:
                self.call_count_total.labels(number=number, direction="outbound").inc(outbound_count)
            if outbound_duration is not None and outbound_duration > 0:
                self.call_duration_seconds_total.labels(number=number, direction="outbound").inc(outbound_duration)
            if outbound_cost is not None and outbound_cost > 0:
                currency = info_data.get("currency", "GBP")
                self.call_cost_total.labels(number=number, direction="outbound", currency=currency).inc(outbound_cost)

            # Active calls (current state)
            active = self._parse_int(info_data.get("active_calls", info_data.get("current_calls", None)))
            if active is not None:
                self.active_calls.labels(number=number).set(active)

            logger.debug(
                "Collected telephony metrics",
                number=number,
                status=status,
                inbound_calls=inbound_count,
                outbound_calls=outbound_count,
            )

        except Exception as e:
            logger.error(
                "Error collecting info for telephony service",
                number=number,
                error=str(e),
            )
            raise

    def _parse_int(self, value: Any) -> int | None:
        """Parse integer value from API response."""
        if value is None:
            return None
        if isinstance(value, int):
            return value
        elif isinstance(value, (float, str)):
            try:
                return int(float(value))
            except (ValueError, TypeError):
                return None
        return None

    def _parse_float(self, value: Any) -> float | None:
        """Parse float value from API response."""
        if value is None:
            return None
        if isinstance(value, (int, float)):
            return float(value)
        elif isinstance(value, str):
            try:
                return float(value)
            except (ValueError, TypeError):
                return None
        return None


@register_collector(UpdateTier.SLOW)
class TelephonyRateCardCollector(MetricCollector):
    """Collector for telephony rate card information (SLOW tier - 900s)."""

    def _initialize_metrics(self) -> None:
        """Initialize rate card metrics."""
        self.rate_ppm = self._create_gauge(
            "aaisp_telephony_rate_ppm",
            "Telephony rate per minute in pence for period",
            labelnames=["rate_name", "period"],
        )

        self.rate_min_charge = self._create_gauge(
            "aaisp_telephony_rate_min_charge_pence",
            "Minimum call charge in pence for rate",
            labelnames=["rate_name"],
        )

        self.rate_prefixes_total = self._create_gauge(
            "aaisp_telephony_prefixes_total",
            "Number of dial prefixes mapped to this rate",
            labelnames=["rate_name"],
        )

        self.ratecard_last_updated = self._create_gauge(
            "aaisp_telephony_ratecard_last_updated_timestamp_seconds",
            "Unix timestamp when rate card was last updated",
        )

    async def _collect_impl(self) -> None:
        """Collect rate card metrics."""
        if not self.settings.collectors.enable_telephony_ratecard:
            logger.debug("Telephony ratecard collector disabled")
            return

        try:
            ratecard_data = await self.client.telephony_ratecard()

            rate_card = ratecard_data.get("rate_card", {})
            codes_raw = rate_card.get("codes", {}).get("code", [])
            rates_raw = rate_card.get("rates", {}).get("rate", [])

            codes: list[dict[str, Any]] = []
            if isinstance(codes_raw, list):
                codes = codes_raw
            elif isinstance(codes_raw, dict):
                codes = [codes_raw]

            rates: list[dict[str, Any]] = []
            if isinstance(rates_raw, list):
                rates = rates_raw
            elif isinstance(rates_raw, dict):
                rates = [rates_raw]

            logger.debug(
                "Parsed telephony ratecard",
                rate_entries=len(rates),
                code_entries=len(codes),
            )

            prefix_counts: Counter[str] = Counter()
            for code in codes:
                rate_name = code.get("rate")
                if rate_name:
                    prefix_counts[str(rate_name)] += 1

            for rate in rates:
                try:
                    rate_name_raw = rate.get("rate")
                    if not rate_name_raw:
                        continue
                    rate_name = str(rate_name_raw)
                    for period_key, period_label in [
                        ("peak_ppm", "peak"),
                        ("offpeak_ppm", "offpeak"),
                        ("weekend_ppm", "weekend"),
                    ]:
                        val = self._parse_float(rate.get(period_key))
                        if val is not None:
                            self.rate_ppm.labels(
                                rate_name=rate_name,
                                period=period_label,
                            ).set(val)

                    min_charge = self._parse_float(rate.get("min_charge"))
                    if min_charge is not None:
                        self.rate_min_charge.labels(rate_name=rate_name).set(min_charge)

                    self.rate_prefixes_total.labels(rate_name=rate_name).set(
                        float(prefix_counts.get(rate_name, 0))
                    )

                except Exception as e:
                    logger.warning("Failed to parse rate entry", error=str(e), rate=rate)

            # Set last updated timestamp
            import time

            self.ratecard_last_updated.set(time.time())

            logger.debug("Collected ratecard metrics", rates_count=len(rates))

        except Exception as e:
            error_msg = str(e)

            # Handle HTTP 500 errors - likely no telephony services
            if "500" in error_msg or "Internal Server Error" in error_msg:
                logger.warning(
                    "Telephony ratecard query failed",
                    help="This account may not have telephony services. This is expected if you don't have "
                         "VoIP services. Disable with AAISP_EXPORTER_COLLECTORS__ENABLE_TELEPHONY_RATECARD=false",
                )
                return  # Gracefully skip - not a fatal error

            # For other errors, log and raise
            logger.error("Failed to collect telephony ratecard", error=error_msg)
            raise

    def _parse_float(self, value: Any) -> float | None:
        """Parse float value from API response."""
        if value is None:
            return None
        if isinstance(value, (int, float)):
            return float(value)
        elif isinstance(value, str):
            try:
                return float(value)
            except (ValueError, TypeError):
                return None
        return None
