"""CHAOS API client."""

import asyncio
import time
from typing import Any

import httpx
from prometheus_client import CollectorRegistry, Counter, Histogram
from pydantic import SecretStr

from aaisp_exporter.core.config import AuthSettings, CHAOSAPISettings
from aaisp_exporter.core.constants import Subsystem
from aaisp_exporter.core.logging import get_logger

logger = get_logger(__name__)


class CHAOSAPIError(Exception):
    """Base exception for CHAOS API errors."""

    pass


class CHAOSAuthError(CHAOSAPIError):
    """Authentication error."""

    pass


class CHAOSRateLimitError(CHAOSAPIError):
    """Rate limit exceeded."""

    pass


class CHAOSClient:
    """Async HTTP client for the CHAOS API."""

    def __init__(
        self,
        api_settings: CHAOSAPISettings,
        auth_settings: AuthSettings,
        registry: CollectorRegistry | None = None,
    ) -> None:
        """Initialize the CHAOS API client.

        Args:
            api_settings: API connection settings
            auth_settings: Authentication credentials
            registry: Prometheus registry for metrics

        """
        self.api_settings = api_settings
        self.auth_settings = auth_settings
        self.base_url = api_settings.base_url
        self._client: httpx.AsyncClient | None = None
        self._semaphore = asyncio.Semaphore(api_settings.concurrency_limit)

        # Initialize API metrics if registry provided
        if registry is not None:
            self._api_requests_total = Counter(
                "aaisp_api_requests_total",
                "Total API requests made to CHAOS API",
                labelnames=["subsystem", "command", "status_code"],
                registry=registry,
            )

            self._api_request_duration = Histogram(
                "aaisp_api_request_duration_seconds",
                "Duration of API requests to CHAOS API",
                labelnames=["subsystem", "command"],
                registry=registry,
            )
        else:
            self._api_requests_total = None
            self._api_request_duration = None

    async def __aenter__(self) -> "CHAOSClient":
        """Async context manager entry."""
        await self.start()
        return self

    async def __aexit__(self, *args: Any) -> None:
        """Async context manager exit."""
        await self.close()

    async def start(self) -> None:
        """Initialize the HTTP client."""
        if self._client is None:
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(self.api_settings.timeout),
                follow_redirects=True,
                headers={
                    "User-Agent": "AAISP-Prometheus-Exporter/0.1.0",
                },
            )
            logger.info("CHAOS API client initialized", base_url=self.base_url)

    async def close(self) -> None:
        """Close the HTTP client."""
        if self._client is not None:
            await self._client.aclose()
            self._client = None
            logger.info("CHAOS API client closed")

    def _get_auth_params(self) -> dict[str, str]:
        """Get authentication parameters for requests."""
        params: dict[str, str] = {}

        # Prefer control login authentication for read-only operations
        if self.auth_settings.has_control_auth():
            params["control_login"] = self.auth_settings.control_login or ""
            if self.auth_settings.control_password:
                params["control_password"] = self.auth_settings.control_password.get_secret_value()

        # Fall back to account authentication
        elif self.auth_settings.has_account_auth():
            params["account_number"] = self.auth_settings.account_number or ""
            if self.auth_settings.account_password:
                params["account_password"] = self.auth_settings.account_password.get_secret_value()

        return params

    async def request(
        self,
        subsystem: Subsystem | str,
        command: str,
        params: dict[str, Any] | None = None,
        retry_count: int = 0,
    ) -> dict[str, Any]:
        """Make a request to the CHAOS API.

        Args:
            subsystem: API subsystem (broadband, login, etc.)
            command: API command (info, services, quota, etc.)
            params: Additional query parameters
            retry_count: Current retry attempt

        Returns:
            JSON response from the API

        Raises:
            CHAOSAPIError: On API errors
            CHAOSAuthError: On authentication errors
            CHAOSRateLimitError: On rate limiting

        """
        if self._client is None:
            await self.start()

        # Build URL - append /json to get JSON response
        subsystem_str = subsystem.value if isinstance(subsystem, Subsystem) else subsystem
        url = f"{self.base_url}/{subsystem_str}/{command}/json"

        # Merge auth params with request params
        request_params = self._get_auth_params()
        if params:
            request_params.update(params)

        logger.debug(
            "Making CHAOS API request",
            subsystem=subsystem_str,
            command=command,
            url=url,
        )

        # Start timing request
        start_time = time.time()
        status_code = 0

        try:
            async with self._semaphore:
                assert self._client is not None
                response = await self._client.post(
                    url,
                    data=request_params,
                    headers={"Content-Type": "application/x-www-form-urlencoded"},
                )

            status_code = response.status_code

            # Log response status
            logger.debug(
                "CHAOS API response",
                subsystem=subsystem_str,
                command=command,
                status_code=status_code,
            )

            # Check for HTTP errors
            if response.status_code == 401:
                raise CHAOSAuthError("Authentication failed")
            elif response.status_code == 429:
                raise CHAOSRateLimitError("Rate limit exceeded")

            response.raise_for_status()

            # Parse JSON response
            data = response.json()

            # Check for API-level errors in response
            if "error" in data:
                error_msg = data["error"]
                logger.error(
                    "CHAOS API returned error",
                    subsystem=subsystem_str,
                    command=command,
                    error=error_msg,
                )
                raise CHAOSAPIError(f"API error: {error_msg}")

            # Record metrics on success
            duration = time.time() - start_time
            self._record_request_metrics(subsystem_str, command, status_code, duration)

            return data

        except httpx.TimeoutException as e:
            # Record timeout in metrics
            duration = time.time() - start_time
            self._record_request_metrics(subsystem_str, command, 0, duration)

            logger.warning(
                "CHAOS API request timeout",
                subsystem=subsystem_str,
                command=command,
                retry=retry_count,
            )
            if retry_count < self.api_settings.max_retries:
                await asyncio.sleep(2**retry_count)  # Exponential backoff
                return await self.request(subsystem, command, params, retry_count + 1)
            raise CHAOSAPIError(f"Request timeout after {retry_count} retries") from e

        except httpx.HTTPStatusError as e:
            # Record HTTP error in metrics
            duration = time.time() - start_time
            self._record_request_metrics(subsystem_str, command, e.response.status_code, duration)

            logger.error(
                "CHAOS API HTTP error",
                subsystem=subsystem_str,
                command=command,
                status_code=e.response.status_code,
            )
            raise CHAOSAPIError(f"HTTP {e.response.status_code}: {e.response.text}") from e

        except httpx.RequestError as e:
            # Record request error in metrics
            duration = time.time() - start_time
            self._record_request_metrics(subsystem_str, command, 0, duration)

            logger.error(
                "CHAOS API request error",
                subsystem=subsystem_str,
                command=command,
                error=str(e),
            )
            raise CHAOSAPIError(f"Request failed: {e}") from e

    def _record_request_metrics(
        self, subsystem: str, command: str, status_code: int, duration: float
    ) -> None:
        """Record API request metrics.

        Args:
            subsystem: API subsystem
            command: API command
            status_code: HTTP status code (0 for network errors)
            duration: Request duration in seconds

        """
        if self._api_requests_total is not None:
            self._api_requests_total.labels(
                subsystem=subsystem,
                command=command,
                status_code=str(status_code),
            ).inc()

        if self._api_request_duration is not None:
            self._api_request_duration.labels(
                subsystem=subsystem,
                command=command,
            ).observe(duration)

    def _extract_single_object(self, data: dict[str, Any], key: str) -> dict[str, Any]:
        """Extract the first object from a list-or-dict response field."""
        value = data.get(key, {})
        if isinstance(value, list):
            return value[0] if value else {}
        if isinstance(value, dict):
            return value
        return {}

    async def broadband_services(self) -> list[str]:
        """Get list of broadband service IDs.

        Returns:
            List of service identifiers

        """
        response = await self.request(Subsystem.BROADBAND, "services")
        # CHAOS returns "services": ["60865", ...]
        services = response.get("services") or response.get("service") or []
        service_ids: set[str] = set()
        if isinstance(services, list):
            service_ids.update(str(s) for s in services)
        elif isinstance(services, str):
            service_ids.add(services)

        # Try to discover additional services from the service selector options
        # by making a single info call. Some accounts expose extra services only
        # via the <options>/<choice> list.
        try:
            sample_service = next(iter(service_ids), None)
            if sample_service:
                raw_info = await self.request(
                    Subsystem.BROADBAND, "info", {"service": sample_service}
                )
                options = raw_info.get("options") or []
                if isinstance(options, dict):
                    options = [options]
                for opt_group in options:
                    option_list = opt_group.get("option") or []
                    if isinstance(option_list, dict):
                        option_list = [option_list]
                    for option in option_list:
                        if option.get("name") != "service":
                            continue
                        choices = option.get("choice") or []
                        if isinstance(choices, dict):
                            choices = [choices]
                        for choice in choices:
                            val = choice.get("value")
                            if val:
                                service_ids.add(str(val))
        except Exception as e:
            logger.debug("Service discovery via info failed", error=str(e))

        return list(service_ids)

    async def broadband_info(self, service: str) -> dict[str, Any]:
        """Get broadband service information.

        Args:
            service: Service identifier (phone number, line ID, or circuit ID)

        Returns:
            Service information

        """
        response = await self.request(Subsystem.BROADBAND, "info", {"service": service})
        return self._extract_single_object(response, "info")

    async def broadband_quota(self, service: str) -> dict[str, Any]:
        """Get broadband quota information.

        Args:
            service: Service identifier

        Returns:
            Quota information

        """
        response = await self.request(Subsystem.BROADBAND, "quota", {"service": service})
        return self._extract_single_object(response, "quota")

    async def broadband_usage(self, service: str) -> dict[str, Any]:
        """Get broadband usage information.

        Args:
            service: Service identifier

        Returns:
            Usage information

        """
        response = await self.request(Subsystem.BROADBAND, "usage", {"service": service})
        return self._extract_single_object(response, "usage")

    async def login_services(self) -> list[str]:
        """Get list of control login services.

        Returns:
            List of login identifiers

        """
        response = await self.request(Subsystem.LOGIN, "services")
        services = response.get("services") or response.get("service") or []
        if isinstance(services, list):
            return [str(s) for s in services]
        if isinstance(services, str):
            return [services]
        return []

    async def login_info(self, service: str) -> dict[str, Any]:
        """Get login information.

        Args:
            service: Login identifier

        Returns:
            Login information

        """
        return await self.request(Subsystem.LOGIN, "info", {"service": service})

    async def telephony_services(self) -> list[str]:
        """Get list of telephony service IDs.

        Returns:
            List of service identifiers (phone numbers)

        """
        response = await self.request(Subsystem.TELEPHONY, "services")
        services = response.get("services") or response.get("service") or []
        if isinstance(services, list):
            return [str(s) for s in services]
        if isinstance(services, str):
            return [services]
        return []

    async def telephony_info(self, service: str) -> dict[str, Any]:
        """Get telephony service information.

        Args:
            service: Service identifier (phone number)

        Returns:
            Service information

        """
        return await self.request(Subsystem.TELEPHONY, "info", {"service": service})

    async def telephony_ratecard(self) -> dict[str, Any]:
        """Get telephony rate card.

        Returns:
            Rate card information

        """
        return await self.request(Subsystem.TELEPHONY, "ratecard")
