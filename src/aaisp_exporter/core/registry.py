"""Collector registry for automatic collector discovery."""

from typing import TYPE_CHECKING, Any

from aaisp_exporter.core.constants import UpdateTier

if TYPE_CHECKING:
    from aaisp_exporter.collectors.base import MetricCollector

# Registry: tier -> list of collector classes
_collector_registry: dict[UpdateTier, list[type["MetricCollector"]]] = {
    UpdateTier.FAST: [],
    UpdateTier.MEDIUM: [],
    UpdateTier.SLOW: [],
}


def register_collector(tier: UpdateTier) -> Any:
    """Decorator to register a collector for a specific update tier.

    Args:
        tier: The update tier for this collector

    Returns:
        Decorator function

    """

    def decorator(cls: type["MetricCollector"]) -> type["MetricCollector"]:
        """Register the collector class."""
        _collector_registry[tier].append(cls)
        cls._update_tier = tier
        return cls

    return decorator


def get_collectors(tier: UpdateTier) -> list[type["MetricCollector"]]:
    """Get all collectors registered for a specific tier.

    Args:
        tier: The update tier

    Returns:
        List of collector classes

    """
    return _collector_registry[tier]


def get_all_collectors() -> dict[UpdateTier, list[type["MetricCollector"]]]:
    """Get all registered collectors.

    Returns:
        Dictionary mapping tiers to collector classes

    """
    return _collector_registry.copy()
