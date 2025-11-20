# AAISP CHAOS API Prometheus Exporter

[![CI](https://github.com/yourusername/aaisp-exporter/actions/workflows/ci.yml/badge.svg)](https://github.com/yourusername/aaisp-exporter/actions/workflows/ci.yml)
[![Docker Build](https://github.com/yourusername/aaisp-exporter/actions/workflows/docker.yml/badge.svg)](https://github.com/yourusername/aaisp-exporter/actions/workflows/docker.yml)
[![Python 3.13+](https://img.shields.io/badge/python-3.13+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

A Prometheus exporter for Andrews & Arnold (AAISP) CHAOS API that exposes broadband service metrics including quota usage, line speeds, and service status.

## Features

- 📊 **Comprehensive Metrics**: Quota usage, line speeds, service status, and more
- ⚡ **Tiered Collection**: Fast/Medium/Slow tiers for optimal API usage
- 🔒 **Secure**: Supports both control login and account authentication
- 🐳 **Docker Ready**: Multi-arch Docker images (amd64, arm64)
- 📈 **Production Ready**: Structured logging, health checks, error handling
- 🎯 **Async-First**: Built with asyncio for optimal performance

## Quick Start

### Using Docker Compose (Recommended)

1. Clone the repository:
```bash
git clone https://github.com/yourusername/aaisp-exporter.git
cd aaisp-exporter
```

2. Create `.env` file:
```bash
cp .env.example .env
# Edit .env and add your CHAOS API credentials
```

3. Start the exporter:
```bash
docker-compose up -d
```

4. Access metrics at http://localhost:9099/metrics

### Using uv (Development)

1. Install [uv](https://github.com/astral-sh/uv):
```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

2. Clone and setup:
```bash
git clone https://github.com/yourusername/aaisp-exporter.git
cd aaisp-exporter
uv sync
```

3. Configure authentication:
```bash
export AAISP_EXPORTER_AUTH__CONTROL_LOGIN=your_login@a
export AAISP_EXPORTER_AUTH__CONTROL_PASSWORD=your_password
```

4. Run the exporter:
```bash
uv run python -m aaisp_exporter
```

## Configuration

Configuration is done via environment variables. All variables are prefixed with `AAISP_EXPORTER_`.

### Authentication (Required)

You must provide **either** control login or account credentials:

```bash
# Option 1: Control Login (recommended for monitoring)
AAISP_EXPORTER_AUTH__CONTROL_LOGIN=your_login@a
AAISP_EXPORTER_AUTH__CONTROL_PASSWORD=your_password

# Option 2: Account Authentication
AAISP_EXPORTER_AUTH__ACCOUNT_NUMBER=A1234A
AAISP_EXPORTER_AUTH__ACCOUNT_PASSWORD=your_account_password
```

### Server Settings

```bash
AAISP_EXPORTER_SERVER__HOST=0.0.0.0          # Default: 0.0.0.0
AAISP_EXPORTER_SERVER__PORT=9099             # Default: 9099
```

### Logging

```bash
AAISP_EXPORTER_LOGGING__LEVEL=INFO           # Default: INFO
AAISP_EXPORTER_LOGGING__JSON_FORMAT=false    # Default: false
```

### Collection Intervals

```bash
AAISP_EXPORTER_INTERVALS__FAST=60            # Default: 60 seconds
AAISP_EXPORTER_INTERVALS__MEDIUM=300         # Default: 300 seconds
AAISP_EXPORTER_INTERVALS__SLOW=900           # Default: 900 seconds
```

### API Settings

```bash
AAISP_EXPORTER_API__BASE_URL=https://chaos2.aa.net.uk
AAISP_EXPORTER_API__TIMEOUT=30               # Default: 30 seconds
AAISP_EXPORTER_API__MAX_RETRIES=3            # Default: 3
AAISP_EXPORTER_API__CONCURRENCY_LIMIT=5      # Default: 5
```

### Collector Toggles

```bash
AAISP_EXPORTER_COLLECTORS__ENABLE_BROADBAND=true              # Default: true
AAISP_EXPORTER_COLLECTORS__ENABLE_TELEPHONY=false             # Default: false
AAISP_EXPORTER_COLLECTORS__ENABLE_TELEPHONY_RATECARD=false    # Default: false
AAISP_EXPORTER_COLLECTORS__ENABLE_CONTROL_LOGIN=false         # Default: false
```

See `.env.example` for a complete configuration template.

## Metrics

### Broadband Quota Metrics (Fast Tier - 60s)

- `aaisp_broadband_quota_total_bytes` - Total monthly quota in bytes
- `aaisp_broadband_quota_used_bytes` - Used quota in bytes
- `aaisp_broadband_quota_remaining_bytes` - Remaining quota in bytes
- `aaisp_broadband_quota_percentage` - Percentage of quota used
- `aaisp_broadband_quota_timestamp_seconds` - Timestamp of quota snapshot

Labels: `service`, `login`

### Broadband Line Speed Metrics (Medium Tier - 300s)

- `aaisp_broadband_line_sync_download_bps` - Line sync download speed (bps)
- `aaisp_broadband_line_sync_upload_bps` - Line sync upload speed (bps)
- `aaisp_broadband_line_sync_download_adjusted_bps` - Adjusted line sync download speed (bps)

Labels: `service`, `login`

### Broadband Service Info (Medium Tier - 300s)

- `aaisp_broadband_service_info` - Service information (value always 1, info in labels)

Labels: `service`, `login`, `postcode`

### Telephony Service Metrics (Medium Tier - 300s)

- `aaisp_telephony_service_info` - Service information (value always 1, info in labels)
- `aaisp_telephony_calls_total` - Total number of calls (counter)
- `aaisp_telephony_call_duration_seconds_total` - Total call duration in seconds (counter)
- `aaisp_telephony_call_cost_total` - Total call cost (counter)
- `aaisp_telephony_active_calls` - Number of currently active calls

Labels vary by metric:
- Info: `number`, `status`, `call_forwarding`, `voicemail`, `service_type`
- Stats: `number`, `direction` (inbound/outbound), `currency` (for cost)

### Telephony Rate Card Metrics (Slow Tier - 900s)

- `aaisp_telephony_rate_ppm` - Rate per minute (pence) per rate/period (peak/offpeak/weekend)
- `aaisp_telephony_rate_min_charge_pence` - Minimum call charge (pence) per rate
- `aaisp_telephony_prefixes_total` - Number of prefixes mapped to a rate
- `aaisp_telephony_ratecard_last_updated_timestamp_seconds` - When rate card was last updated

Labels: `rate_name` (+ `period` for `aaisp_telephony_rate_ppm`)

### Exporter Metrics

- `aaisp_exporter_up` - Exporter is running (always 1)
- `aaisp_exporter_build_info` - Build information
- `aaisp_collector_duration_seconds` - Collection duration histogram
- `aaisp_collector_errors_total` - Total collection errors
- `aaisp_collector_last_successful_collection_timestamp` - Last successful collection timestamp
- `aaisp_api_requests_total` - Total API requests to CHAOS API
- `aaisp_api_request_duration_seconds` - Duration of API requests

**Note:** Many line quality, session, and QoS metrics are only set if the API provides the data. Missing fields are handled gracefully.

## Endpoints

- `/` - HTML landing page with status information
- `/metrics` - Prometheus metrics endpoint
- `/health` - Health check endpoint (JSON)

## Prometheus Configuration

Add to your `prometheus.yml`:

```yaml
scrape_configs:
  - job_name: 'aaisp'
    static_configs:
      - targets: ['localhost:9099']
    scrape_interval: 60s
```

## Development

### Prerequisites

- Python 3.13+
- [uv](https://github.com/astral-sh/uv) package manager

### Setup Development Environment

```bash
# Clone repository
git clone https://github.com/yourusername/aaisp-exporter.git
cd aaisp-exporter

# Install dependencies with development tools
make dev-install

# Install pre-commit hooks
make pre-commit
```

### Common Development Tasks

```bash
make help          # Show all available commands
make test          # Run tests
make lint          # Run linting
make format        # Format code
make type-check    # Run type checking
make ci            # Run all CI checks
make run           # Run exporter locally
```

### Project Structure

```
aaisp-exporter/
├── src/aaisp_exporter/
│   ├── __main__.py              # Entry point
│   ├── app.py                   # FastAPI application
│   ├── api/
│   │   └── client.py            # CHAOS API client
│   ├── collectors/
│   │   ├── base.py              # Base collector class
│   │   ├── manager.py           # Collector orchestration
│   │   └── broadband.py         # Broadband metrics collector
│   ├── core/
│   │   ├── config.py            # Configuration management
│   │   ├── constants.py         # Constants and enums
│   │   ├── logging.py           # Structured logging
│   │   └── registry.py          # Collector registry
│   └── models/
│       └── ...                  # Data models
├── tests/
│   ├── unit/                    # Unit tests
│   ├── integration/             # Integration tests
│   └── fixtures/                # Test fixtures
├── docs/                        # Documentation
├── .github/workflows/           # CI/CD pipelines
├── pyproject.toml              # Project configuration
├── Dockerfile                  # Multi-stage Docker build
├── docker-compose.yml          # Docker Compose configuration
├── Makefile                    # Development commands
└── todo.txt                    # Implementation roadmap
```

### Running Tests

```bash
# Run all tests
make test

# Run with coverage report
make test-coverage

# Run specific test file
uv run pytest tests/unit/test_client.py -v
```

## Architecture

The exporter uses a **tiered collection system** to optimize API calls:

- **FAST (60s)**: Real-time metrics (quota usage, service status)
- **MEDIUM (300s)**: Operational metrics (line speeds, throughput)
- **SLOW (900s)**: Configuration data (service info, settings)

Collectors are automatically registered using decorators and managed by the `CollectorManager` which orchestrates parallel collection across services.

## Deployment

### Docker

```bash
# Build image
docker build -t aaisp-exporter:latest .

# Run container
docker run -d \
  -p 9099:9099 \
  -e AAISP_EXPORTER_AUTH__CONTROL_LOGIN=your_login@a \
  -e AAISP_EXPORTER_AUTH__CONTROL_PASSWORD=your_password \
  --name aaisp-exporter \
  aaisp-exporter:latest
```

### Docker Compose

```bash
# Start
docker-compose up -d

# View logs
docker-compose logs -f

# Stop
docker-compose down
```

### Kubernetes

Example Kubernetes manifests are available in the `examples/kubernetes/` directory (to be added).

## Troubleshooting

### Authentication Errors

If you see authentication errors, verify:

1. Credentials are correct
2. Control login has access to broadband services
3. No rate limiting is occurring

### Telephony Collector Warnings

**Warning**: `Telephony services query failed` or HTTP 500 errors

**Cause**: Your account may not have AAISP telephony/VoIP services, or the `services` command is not fully implemented for telephony.

**Solution**: This is expected if you don't have VoIP services. Disable the collectors with:
```bash
AAISP_EXPORTER_COLLECTORS__ENABLE_TELEPHONY=false
AAISP_EXPORTER_COLLECTORS__ENABLE_TELEPHONY_RATECARD=false
```

Note: The `ratecard` endpoint works even without telephony services (returns global rates).

### L2TP Tunnel Connections

**Info**: `Detected L2TP tunnel connection - will skip physical line metrics`

**Explanation**: L2TP tunnel connections run over another ISP's infrastructure and don't expose physical line metrics like SNR, attenuation, or sync rates. This is expected behavior.

**Metrics available** for L2TP tunnels:
- Service status (up/down)
- Session uptime
- Basic service info
- Quota and usage (if applicable)

**Metrics NOT available** for L2TP tunnels:
- Line sync rates
- SNR margin
- Line attenuation
- Line errors (FEC/CRC/HEC)

### No Metrics Appearing

Check:

1. Exporter is running: `curl http://localhost:9099/health`
2. Services are being discovered: Check logs for "Found broadband services"
3. No API errors in logs
4. Broadband collector is enabled (default)

### High API Error Rate

- Reduce collection frequency via interval settings
- Check API rate limits
- Verify network connectivity to `chaos2.aa.net.uk`

### Collector Fails to Start

If collectors are failing during startup:

1. Check that the correct authentication credentials are configured
2. Disable unused collectors (domain, telephony) if you don't have those services
3. Review logs for specific error messages
4. Ensure the CHAOS API is accessible from your network

## Contributing

Contributions are welcome! Please:

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Make your changes
4. Run tests and linting (`make ci`)
5. Commit your changes (`git commit -m 'Add amazing feature'`)
6. Push to the branch (`git push origin feature/amazing-feature`)
7. Open a Pull Request

Please ensure:
- All tests pass
- Code is formatted with `ruff`
- Type hints are added
- Documentation is updated

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Acknowledgments

- [Andrews & Arnold](https://aa.net.uk/) for providing the CHAOS API
- Inspired by the architecture of [meraki-dashboard-exporter](https://github.com/yourusername/meraki-dashboard-exporter)
- Built with [FastAPI](https://fastapi.tiangolo.com/), [httpx](https://www.python-httpx.org/), and [prometheus-client](https://github.com/prometheus/client_python)

## Links

- [CHAOS API Documentation](https://aa.net.uk/kb-broadband-chaos.html)
- [Andrews & Arnold](https://aa.net.uk/)
- [Issue Tracker](https://github.com/yourusername/aaisp-exporter/issues)
- [Changelog](CHANGELOG.md)

## Support

For issues related to:
- **This exporter**: Open an issue on GitHub
- **CHAOS API**: Contact Andrews & Arnold support
- **Andrews & Arnold services**: Visit [aa.net.uk](https://aa.net.uk/)
