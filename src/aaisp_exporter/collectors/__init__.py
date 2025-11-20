"""Metric collectors module."""

# Import collector modules to trigger @register_collector decorators
from aaisp_exporter.collectors import broadband  # noqa: F401
from aaisp_exporter.collectors import telephony  # noqa: F401

__all__ = ["broadband", "telephony"]
