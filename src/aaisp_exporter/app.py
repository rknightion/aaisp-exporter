"""FastAPI application for the AAISP CHAOS API exporter."""

from contextlib import asynccontextmanager
from typing import Any, AsyncIterator

from fastapi import FastAPI
from fastapi.responses import HTMLResponse, PlainTextResponse
from prometheus_client import REGISTRY, CollectorRegistry, generate_latest
from prometheus_client import Gauge as PrometheusGauge

from aaisp_exporter import __version__
from aaisp_exporter.api.client import CHAOSClient
from aaisp_exporter.collectors.manager import CollectorManager
from aaisp_exporter.core.config import Settings
from aaisp_exporter.core.logging import configure_logging, get_logger

logger = get_logger(__name__)


class ExporterApp:
    """Main exporter application."""

    def __init__(self, settings: Settings | None = None) -> None:
        """Initialize the exporter application.

        Args:
            settings: Application settings (if None, will load from env)

        """
        self.settings = settings or Settings()
        self.registry = CollectorRegistry()
        self.client: CHAOSClient | None = None
        self.collector_manager: CollectorManager | None = None

        # Configure logging
        configure_logging(self.settings.logging)

        # Initialize build info metric
        self._build_info = PrometheusGauge(
            "aaisp_exporter_build_info",
            "Exporter build information",
            labelnames=["version"],
            registry=self.registry,
        )
        self._build_info.labels(version=__version__).set(1)

        # Exporter up metric
        self._exporter_up = PrometheusGauge(
            "aaisp_exporter_up",
            "Exporter is running",
            registry=self.registry,
        )
        self._exporter_up.set(1)

    @asynccontextmanager
    async def lifespan(self, app: FastAPI) -> AsyncIterator[None]:
        """Manage application lifecycle.

        Args:
            app: FastAPI application instance

        """
        # Startup
        logger.info("Starting AAISP CHAOS API Exporter", version=__version__)

        # Validate authentication
        try:
            self.settings.validate_auth()
        except ValueError as e:
            logger.error("Authentication validation failed", error=str(e))
            raise

        # Initialize CHAOS API client with registry for metrics
        self.client = CHAOSClient(
            api_settings=self.settings.api,
            auth_settings=self.settings.auth,
            registry=self.registry,
        )
        await self.client.start()

        # Initialize collector manager
        self.collector_manager = CollectorManager(
            client=self.client,
            settings=self.settings,
            registry=self.registry,
        )

        # Start collection loops
        await self.collector_manager.start()

        logger.info(
            "Exporter started successfully",
            host=self.settings.server.host,
            port=self.settings.server.port,
        )

        yield

        # Shutdown
        logger.info("Shutting down exporter")

        if self.collector_manager:
            await self.collector_manager.stop()

        if self.client:
            await self.client.close()

        logger.info("Exporter shutdown complete")

    def create_app(self) -> FastAPI:
        """Create and configure the FastAPI application.

        Returns:
            Configured FastAPI application

        """
        app = FastAPI(
            title="AAISP CHAOS API Prometheus Exporter",
            description="Prometheus exporter for Andrews & Arnold CHAOS API",
            version=__version__,
            lifespan=self.lifespan,
        )

        @app.get("/", response_class=HTMLResponse)
        async def root() -> str:
            """Root endpoint with HTML landing page."""
            status = "Running"
            if self.collector_manager:
                manager_status = self.collector_manager.get_status()
            else:
                manager_status = {"running": False, "collectors": {}}

            html = f"""
            <!DOCTYPE html>
            <html>
            <head>
                <title>AAISP CHAOS API Exporter</title>
                <style>
                    body {{
                        font-family: Arial, sans-serif;
                        max-width: 800px;
                        margin: 50px auto;
                        padding: 20px;
                    }}
                    h1 {{ color: #333; }}
                    .status {{ color: green; font-weight: bold; }}
                    .info {{ background: #f5f5f5; padding: 15px; border-radius: 5px; }}
                    pre {{ background: #f0f0f0; padding: 10px; border-radius: 3px; }}
                    a {{ color: #0066cc; text-decoration: none; }}
                    a:hover {{ text-decoration: underline; }}
                </style>
            </head>
            <body>
                <h1>AAISP CHAOS API Prometheus Exporter</h1>
                <p class="status">Status: {status}</p>
                <p>Version: {__version__}</p>

                <h2>Endpoints</h2>
                <ul>
                    <li><a href="/metrics">/metrics</a> - Prometheus metrics</li>
                    <li><a href="/health">/health</a> - Health check</li>
                </ul>

                <h2>Configuration</h2>
                <div class="info">
                    <p><strong>API Base URL:</strong> {self.settings.api.base_url}</p>
                    <p><strong>Update Intervals:</strong></p>
                    <ul>
                        <li>Fast: {self.settings.intervals.fast}s</li>
                        <li>Medium: {self.settings.intervals.medium}s</li>
                        <li>Slow: {self.settings.intervals.slow}s</li>
                    </ul>
                </div>

                <h2>Collector Status</h2>
                <pre>{self._format_collector_status(manager_status)}</pre>

                <h2>Documentation</h2>
                <p>For more information about the CHAOS API, visit
                <a href="https://aa.net.uk/kb-broadband-chaos.html">AA CHAOS API Documentation</a></p>
            </body>
            </html>
            """
            return html

        @app.get("/metrics", response_class=PlainTextResponse)
        async def metrics() -> bytes:
            """Prometheus metrics endpoint."""
            return generate_latest(self.registry)

        @app.get("/health")
        async def health() -> dict[str, Any]:
            """Health check endpoint."""
            healthy = True
            details: dict[str, Any] = {
                "status": "healthy",
                "version": __version__,
            }

            # Check if collector manager is running
            if self.collector_manager:
                manager_status = self.collector_manager.get_status()
                details["collectors"] = manager_status
                if not manager_status.get("running", False):
                    healthy = False
                    details["status"] = "unhealthy"
            else:
                healthy = False
                details["status"] = "unhealthy"
                details["error"] = "Collector manager not initialized"

            # Check if API client is connected
            if self.client and self.client._client is None:
                healthy = False
                details["status"] = "unhealthy"
                details["error"] = "API client not connected"

            return details

        return app

    def _format_collector_status(self, status: dict[str, Any]) -> str:
        """Format collector status for display.

        Args:
            status: Collector manager status

        Returns:
            Formatted status string

        """
        lines = []
        lines.append(f"Running: {status.get('running', False)}")
        lines.append("")

        collectors = status.get("collectors", {})
        intervals = status.get("intervals", {})

        for tier, collector_list in collectors.items():
            interval = intervals.get(tier, "unknown")
            lines.append(f"{tier.upper()} ({interval}s):")
            for collector in collector_list:
                lines.append(f"  - {collector}")
            lines.append("")

        return "\n".join(lines)


# Create default app instance
def create_app(settings: Settings | None = None) -> FastAPI:
    """Create FastAPI application instance.

    Args:
        settings: Application settings

    Returns:
        FastAPI application

    """
    exporter = ExporterApp(settings)
    return exporter.create_app()
