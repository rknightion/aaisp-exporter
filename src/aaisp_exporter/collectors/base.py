"""Base collector class for metric collection."""

import time
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any

from prometheus_client import Counter, Gauge, Histogram
from prometheus_client.registry import CollectorRegistry

from aaisp_exporter.core.config import Settings
from aaisp_exporter.core.constants import UpdateTier
from aaisp_exporter.core.logging import get_logger

if TYPE_CHECKING:
    from aaisp_exporter.api.client import CHAOSClient

logger = get_logger(__name__)


class MetricCollector(ABC):
    """Abstract base class for metric collectors."""

    # Class-level shared metrics for all collectors
    _collector_duration: Histogram | None = None
    _collector_errors: Counter | None = None
    _collector_last_success: Gauge | None = None

    # Update tier (set by decorator)
    _update_tier: UpdateTier

    def __init__(
        self,
        client: "CHAOSClient",
        settings: Settings,
        registry: CollectorRegistry,
    ) -> None:
        """Initialize the collector.

        Args:
            client: CHAOS API client
            settings: Application settings
            registry: Prometheus metrics registry

        """
        self.client = client
        self.settings = settings
        self.registry = registry
        self.collector_name = self.__class__.__name__

        # Initialize shared metrics (once for all collectors)
        if MetricCollector._collector_duration is None:
            MetricCollector._collector_duration = Histogram(
                "aaisp_collector_duration_seconds",
                "Time taken to collect metrics",
                ["collector_name", "subsystem"],
                registry=registry,
            )

        if MetricCollector._collector_errors is None:
            MetricCollector._collector_errors = Counter(
                "aaisp_collector_errors_total",
                "Total errors during metric collection",
                ["collector_name", "subsystem", "error_type"],
                registry=registry,
            )

        if MetricCollector._collector_last_success is None:
            MetricCollector._collector_last_success = Gauge(
                "aaisp_collector_last_successful_collection_timestamp",
                "Timestamp of last successful collection",
                ["collector_name"],
                registry=registry,
            )

        # Initialize collector-specific metrics
        self._initialize_metrics()

        logger.info(
            "Initialized collector",
            collector=self.collector_name,
            tier=self._update_tier.value,
        )

    @abstractmethod
    def _initialize_metrics(self) -> None:
        """Initialize Prometheus metrics for this collector.

        Subclasses must implement this to create their specific metrics.
        """
        pass

    @abstractmethod
    async def _collect_impl(self) -> None:
        """Implement the actual metric collection logic.

        Subclasses must implement this to perform data collection.
        """
        pass

    def _get_subsystem_name(self) -> str:
        """Get the subsystem name for this collector."""
        # Extract from collector name (e.g., BroadbandCollector -> broadband)
        name = self.collector_name.replace("Collector", "").lower()
        return name

    async def collect(self) -> None:
        """Collect metrics with automatic error handling and tracking."""
        subsystem = self._get_subsystem_name()
        start_time = time.time()

        try:
            logger.debug("Starting collection", collector=self.collector_name)

            # Perform the actual collection
            await self._collect_impl()

            # Record success
            duration = time.time() - start_time
            if self._collector_duration:
                self._collector_duration.labels(
                    collector_name=self.collector_name,
                    subsystem=subsystem,
                ).observe(duration)

            if self._collector_last_success:
                self._collector_last_success.labels(
                    collector_name=self.collector_name,
                ).set(time.time())

            logger.info(
                "Collection completed successfully",
                collector=self.collector_name,
                duration=f"{duration:.2f}s",
            )

        except Exception as e:
            # Record error
            error_type = type(e).__name__
            if self._collector_errors:
                self._collector_errors.labels(
                    collector_name=self.collector_name,
                    subsystem=subsystem,
                    error_type=error_type,
                ).inc()

            logger.error(
                "Collection failed",
                collector=self.collector_name,
                error=str(e),
                error_type=error_type,
                exc_info=True,
            )

            # Re-raise to allow caller to handle
            raise

    def _create_gauge(
        self,
        name: str,
        documentation: str,
        labelnames: list[str] | None = None,
    ) -> Gauge:
        """Create and register a Gauge metric.

        Args:
            name: Metric name
            documentation: Metric documentation
            labelnames: Label names

        Returns:
            Created Gauge metric

        """
        return Gauge(
            name,
            documentation,
            labelnames=labelnames or [],
            registry=self.registry,
        )

    def _create_counter(
        self,
        name: str,
        documentation: str,
        labelnames: list[str] | None = None,
    ) -> Counter:
        """Create and register a Counter metric.

        Args:
            name: Metric name
            documentation: Metric documentation
            labelnames: Label names

        Returns:
            Created Counter metric

        """
        return Counter(
            name,
            documentation,
            labelnames=labelnames or [],
            registry=self.registry,
        )

    def _create_histogram(
        self,
        name: str,
        documentation: str,
        labelnames: list[str] | None = None,
        buckets: tuple[float, ...] | None = None,
    ) -> Histogram:
        """Create and register a Histogram metric.

        Args:
            name: Metric name
            documentation: Metric documentation
            labelnames: Label names
            buckets: Histogram buckets

        Returns:
            Created Histogram metric

        """
        kwargs: dict[str, Any] = {
            "name": name,
            "documentation": documentation,
            "labelnames": labelnames or [],
            "registry": self.registry,
        }
        if buckets:
            kwargs["buckets"] = buckets

        return Histogram(**kwargs)
