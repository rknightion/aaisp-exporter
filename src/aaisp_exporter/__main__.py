"""Entry point for the AAISP CHAOS API exporter."""

import sys

import uvicorn
from pydantic import ValidationError

from aaisp_exporter.core.config import Settings
from aaisp_exporter.core.logging import configure_logging, get_logger


def main() -> None:
    """Run the AAISP CHAOS API Exporter."""
    # Load settings
    try:
        settings = Settings()

        # Configure logging early
        configure_logging(settings.logging)
        logger = get_logger(__name__)

        # Validate authentication
        settings.validate_auth()

    except ValidationError as e:
        print("=" * 70, file=sys.stderr)
        print("ERROR: Configuration validation failed", file=sys.stderr)
        print("=" * 70, file=sys.stderr)
        print("", file=sys.stderr)
        for error in e.errors():
            field = ".".join(str(x) for x in error["loc"])
            print(f"  {field}: {error['msg']}", file=sys.stderr)
        print("", file=sys.stderr)
        print("Please check your environment variables or .env file.", file=sys.stderr)
        print("", file=sys.stderr)
        print("Required authentication (at least one):", file=sys.stderr)
        print("  - AAISP_EXPORTER_AUTH__CONTROL_LOGIN", file=sys.stderr)
        print("  - AAISP_EXPORTER_AUTH__CONTROL_PASSWORD", file=sys.stderr)
        print("OR", file=sys.stderr)
        print("  - AAISP_EXPORTER_AUTH__ACCOUNT_NUMBER", file=sys.stderr)
        print("  - AAISP_EXPORTER_AUTH__ACCOUNT_PASSWORD", file=sys.stderr)
        print("=" * 70, file=sys.stderr)
        sys.exit(1)

    except ValueError as e:
        print("=" * 70, file=sys.stderr)
        print("ERROR: Configuration error", file=sys.stderr)
        print("=" * 70, file=sys.stderr)
        print("", file=sys.stderr)
        print(f"  {e}", file=sys.stderr)
        print("", file=sys.stderr)
        print("=" * 70, file=sys.stderr)
        sys.exit(1)

    except Exception as e:
        print("=" * 70, file=sys.stderr)
        print("ERROR: Failed to initialize exporter", file=sys.stderr)
        print("=" * 70, file=sys.stderr)
        print("", file=sys.stderr)
        print(f"  {e}", file=sys.stderr)
        print("", file=sys.stderr)
        print("=" * 70, file=sys.stderr)
        sys.exit(1)

    # Run the exporter
    logger.info(
        "Starting AAISP CHAOS API Exporter",
        host=settings.server.host,
        port=settings.server.port,
    )

    uvicorn.run(
        "aaisp_exporter.app:create_app",
        host=settings.server.host,
        port=settings.server.port,
        factory=True,
        log_level=settings.logging.level.lower(),
    )


if __name__ == "__main__":
    main()
