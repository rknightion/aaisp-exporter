"""Collector manager for orchestrating metric collection."""

import asyncio
from typing import TYPE_CHECKING

from prometheus_client.registry import CollectorRegistry

from aaisp_exporter.collectors.base import MetricCollector
from aaisp_exporter.core.config import Settings
from aaisp_exporter.core.constants import UpdateTier
from aaisp_exporter.core.logging import get_logger
from aaisp_exporter.core.registry import get_collectors

if TYPE_CHECKING:
    from aaisp_exporter.api.client import CHAOSClient

logger = get_logger(__name__)


class CollectorManager:
    """Manages and orchestrates metric collectors."""

    def __init__(
        self,
        client: "CHAOSClient",
        settings: Settings,
        registry: CollectorRegistry,
    ) -> None:
        """Initialize the collector manager.

        Args:
            client: CHAOS API client
            settings: Application settings
            registry: Prometheus metrics registry

        """
        self.client = client
        self.settings = settings
        self.registry = registry
        self.collectors: dict[UpdateTier, list[MetricCollector]] = {
            UpdateTier.FAST: [],
            UpdateTier.MEDIUM: [],
            UpdateTier.SLOW: [],
        }
        self._tasks: list[asyncio.Task[None]] = []
        self._running = False

        # Initialize collectors
        self._initialize_collectors()

    def _initialize_collectors(self) -> None:
        """Initialize all registered collectors."""
        for tier in UpdateTier:
            collector_classes = get_collectors(tier)
            for collector_class in collector_classes:
                try:
                    collector = collector_class(
                        client=self.client,
                        settings=self.settings,
                        registry=self.registry,
                    )
                    self.collectors[tier].append(collector)
                    logger.info(
                        "Registered collector",
                        collector=collector_class.__name__,
                        tier=tier.value,
                    )
                except Exception as e:
                    logger.error(
                        "Failed to initialize collector",
                        collector=collector_class.__name__,
                        error=str(e),
                        exc_info=True,
                    )

    async def collect_tier(self, tier: UpdateTier) -> None:
        """Collect metrics for a specific tier.

        Args:
            tier: The update tier to collect

        """
        collectors = self.collectors[tier]
        if not collectors:
            logger.debug("No collectors registered for tier", tier=tier.value)
            return

        logger.debug(
            "Collecting tier",
            tier=tier.value,
            collectors=len(collectors),
        )

        # Collect from all collectors in this tier (in parallel)
        await asyncio.gather(
            *[collector.collect() for collector in collectors],
            return_exceptions=True,
        )

    async def _collection_loop(self, tier: UpdateTier) -> None:
        """Run collection loop for a specific tier.

        Args:
            tier: The update tier

        """
        interval = self.settings.intervals.get_interval(tier)
        logger.info(
            "Starting collection loop",
            tier=tier.value,
            interval=f"{interval}s",
            collectors=len(self.collectors[tier]),
        )

        while self._running:
            try:
                await self.collect_tier(tier)
            except Exception as e:
                logger.error(
                    "Error in collection loop",
                    tier=tier.value,
                    error=str(e),
                    exc_info=True,
                )

            # Wait for next interval
            await asyncio.sleep(interval)

    async def start(self) -> None:
        """Start all collection loops."""
        if self._running:
            logger.warning("Collector manager already running")
            return

        self._running = True
        logger.info("Starting collector manager")

        # Start collection loops for each tier
        for tier in UpdateTier:
            if self.collectors[tier]:
                task = asyncio.create_task(self._collection_loop(tier))
                self._tasks.append(task)

        logger.info(
            "Collector manager started",
            tiers=len(self._tasks),
        )

        # Run initial collection for all tiers immediately
        await asyncio.gather(
            *[self.collect_tier(tier) for tier in UpdateTier],
            return_exceptions=True,
        )

    async def stop(self) -> None:
        """Stop all collection loops."""
        if not self._running:
            return

        logger.info("Stopping collector manager")
        self._running = False

        # Cancel all tasks
        for task in self._tasks:
            task.cancel()

        # Wait for tasks to complete
        await asyncio.gather(*self._tasks, return_exceptions=True)
        self._tasks.clear()

        logger.info("Collector manager stopped")

    def get_status(self) -> dict[str, Any]:
        """Get status of the collector manager.

        Returns:
            Status dictionary

        """
        return {
            "running": self._running,
            "collectors": {
                tier.value: [c.collector_name for c in collectors]
                for tier, collectors in self.collectors.items()
            },
            "intervals": {
                tier.value: self.settings.intervals.get_interval(tier)
                for tier in UpdateTier
            },
        }


from typing import Any  # noqa: E402 (import at end)
