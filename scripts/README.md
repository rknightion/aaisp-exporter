# CHAOS2 API Explorer

An interactive command-line tool for exploring the Andrews & Arnold CHAOS2 API. This script allows you to make authenticated API calls and discover new data points that could be exposed via the Prometheus exporter.

## Prerequisites

- Python 3.11+
- Valid A&A credentials configured in `.env` file (either control login or account credentials)
- Project dependencies installed: `uv sync`

## Usage

### Basic Syntax

```bash
uv run python scripts/chaos_explorer.py <subsystem> <command> [param1=value1 param2=value2 ...]
```

### Examples

#### List all broadband services
```bash
uv run python scripts/chaos_explorer.py broadband services
```

#### Get information about a specific broadband service
```bash
uv run python scripts/chaos_explorer.py broadband info service=01234567890
```

#### Check quota for a broadband service
```bash
uv run python scripts/chaos_explorer.py broadband quota service=01234567890
```

#### Get usage data for a service
```bash
uv run python scripts/chaos_explorer.py broadband usage service=01234567890
```

#### List telephony services
```bash
uv run python scripts/chaos_explorer.py telephony services
```

#### Get telephony rate card
```bash
uv run python scripts/chaos_explorer.py telephony ratecard
```

#### Get login services
```bash
uv run python scripts/chaos_explorer.py login services
```

#### Get info about a specific login
```bash
uv run python scripts/chaos_explorer.py login info service=test@a
```

### Options

- `--no-log` - Disable logging responses to files
- `--raw` - Output raw JSON without pretty printing (useful for piping to other tools)

### Examples with Options

```bash
# Get raw JSON output (no colors/formatting)
uv run python scripts/chaos_explorer.py broadband services --raw

# Make a request without logging to file
uv run python scripts/chaos_explorer.py broadband info service=01234567890 --no-log
```

## Available Subsystems

The CHAOS2 API supports the following subsystems:

- **broadband** - ADSL/VDSL/FTTP services
- **telephony** - VoIP and phone services
- **login** - Control login management
- **domain** - Domain name services
- **email** - Email services
- **sim** - Mobile SIM services

## Common Commands

Most subsystems support these standard commands:

- **services** - List all service IDs for the subsystem
- **info** - Get detailed information about a specific service (requires `service=<id>`)
- **usage** - Get usage data for a service (requires `service=<id>`)
- **availability** - Check availability for new services
- **check** - Validate an order without submitting it
- **order** - Place an order (requires additional parameters)
- **adjust** - Modify service settings (requires additional parameters)
- **cease** - Cancel a service (requires `service=<id>`)

### Subsystem-Specific Commands

#### Broadband
- **quota** - Get quota information (monthly quota and remaining)
- **kill** - Restart PPP connection

#### Telephony
- **ratecard** - Get rate information and charges

## Service Identifiers

Different subsystems use different formats for service identifiers:

- **Broadband**: Phone number (e.g., `01234567890`), A&A line ID (5 digits), or carrier circuit ID
- **Telephony**: Phone numbers (e.g., `02012345678`)
- **Login**: Control login username (e.g., `test@a`)

## Output and Logging

### Pretty Printed Output

By default, responses are displayed with:
- Syntax-highlighted JSON
- Formatted panels with borders
- Clear error messages

### Response Logs

All requests and responses are automatically saved to:
```
scripts/logs/chaos_explorer_YYYYMMDD_HHMMSS.json
```

Each log file contains:
- Timestamp
- Request details (subsystem, command, parameters)
- Full API response
- Any errors encountered

### Command History

All commands are logged to `scripts/.chaos_history` for easy reference. This file contains:
- Timestamp
- Subsystem and command
- Parameters used

You can review your command history:
```bash
cat scripts/.chaos_history | jq
```

## Tips for API Exploration

1. **Start with `services`** - Always begin by listing available services for a subsystem
2. **Use `info` to discover fields** - The info command shows all available data for a service
3. **Check the API response structure** - Look for nested objects that might contain useful metrics
4. **Pay attention to `options` objects** - These show available values for parameters
5. **Test with your actual service IDs** - Replace example service IDs with real ones from your account

## Finding New Metrics

When looking for new data to expose via the Prometheus exporter:

1. Explore different subsystems and commands
2. Look for numeric fields that change over time (good candidates for metrics)
3. Note any fields related to status, state, or health
4. Check for timestamp fields that could indicate when data was last updated
5. Look for quota/usage/limit fields that could be monitored

## Authentication

The script uses the same authentication as the main exporter:

- **Control Login** (recommended for monitoring):
  - `AAISP_EXPORTER_AUTH__CONTROL_LOGIN`
  - `AAISP_EXPORTER_AUTH__CONTROL_PASSWORD`

- **Account Credentials** (for full access including orders):
  - `AAISP_EXPORTER_AUTH__ACCOUNT_NUMBER`
  - `AAISP_EXPORTER_AUTH__ACCOUNT_PASSWORD`

Make sure your `.env` file is properly configured with these credentials.

## Troubleshooting

### Authentication Errors (401)
- Verify your credentials in `.env`
- Check that you're using the correct format (control login should end with `@a`)

### Rate Limiting (429)
- The API includes rate limiting to prevent abuse
- Space out your requests if you encounter this error

### API-Level Errors
- Look for an `error` field in the response
- Check the `options` object for validation requirements
- Ensure service IDs are in the correct format

### No Response or Timeout
- Check your internet connection
- Verify the CHAOS2 API is accessible: `https://chaos2.aa.net.uk/`

## Further Reading

- Full API documentation: `docs/chaos2.pdf.md`
- Official A&A CHAOS2 API docs: https://support.aa.net.uk/CHAOS_API
