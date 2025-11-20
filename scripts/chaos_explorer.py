#!/usr/bin/env python3
"""
CHAOS2 API Explorer - Interactive CLI tool for exploring the A&A CHAOS2 API

This script allows you to make authenticated API calls to the CHAOS2 API
and explore available services, commands, and responses.

Usage:
    python chaos_explorer.py <subsystem> <command> [param1=value1 param2=value2 ...]

Examples:
    python chaos_explorer.py broadband services
    python chaos_explorer.py broadband info service=01234567890
    python chaos_explorer.py telephony ratecard
    python chaos_explorer.py login services
"""

import argparse
import asyncio
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict

from rich.console import Console
from rich.json import JSON
from rich.panel import Panel
from rich.syntax import Syntax

# Add parent directory to path to import from aaisp_exporter
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from aaisp_exporter.api.client import CHAOSClient
from aaisp_exporter.core.config import Settings


# Constants
SCRIPT_DIR = Path(__file__).parent
LOGS_DIR = SCRIPT_DIR / "logs"
HISTORY_FILE = SCRIPT_DIR / ".chaos_history"

# Ensure logs directory exists
LOGS_DIR.mkdir(exist_ok=True)

# Rich console for pretty printing
console = Console()


def parse_arguments() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="CHAOS2 API Explorer - Explore the A&A CHAOS2 API",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s broadband services
  %(prog)s broadband info service=01234567890
  %(prog)s telephony info service=02012345678
  %(prog)s login services
  %(prog)s broadband quota service=01234567890

Common subsystems: broadband, telephony, login, domain, email, sim
Common commands: services, info, usage, quota, availability, check, order, cease
        """,
    )

    parser.add_argument(
        "subsystem",
        help="API subsystem (e.g., broadband, telephony, login)",
    )

    parser.add_argument(
        "command",
        help="API command (e.g., services, info, usage)",
    )

    parser.add_argument(
        "parameters",
        nargs="*",
        help="Additional parameters as key=value pairs (e.g., service=01234567890)",
    )

    parser.add_argument(
        "--no-log",
        action="store_true",
        help="Disable logging to file",
    )

    parser.add_argument(
        "--raw",
        action="store_true",
        help="Output raw JSON without pretty printing",
    )

    return parser.parse_args()


def parse_parameters(param_list: list[str]) -> Dict[str, str]:
    """Parse key=value parameters into a dictionary."""
    params = {}
    for param in param_list:
        if "=" not in param:
            console.print(
                f"[yellow]Warning: Ignoring invalid parameter '{param}' "
                f"(expected format: key=value)[/yellow]"
            )
            continue

        key, value = param.split("=", 1)
        params[key.strip()] = value.strip()

    return params


def save_to_history(subsystem: str, command: str, params: Dict[str, str]) -> None:
    """Save command to history file."""
    timestamp = datetime.now().isoformat()
    history_entry = {
        "timestamp": timestamp,
        "subsystem": subsystem,
        "command": command,
        "parameters": params,
    }

    with open(HISTORY_FILE, "a") as f:
        f.write(json.dumps(history_entry) + "\n")


def save_to_log(
    subsystem: str,
    command: str,
    params: Dict[str, str],
    response: Any,
    error: str | None = None,
) -> Path:
    """Save request and response to a timestamped log file."""
    timestamp = datetime.now()
    log_filename = timestamp.strftime("chaos_explorer_%Y%m%d_%H%M%S.json")
    log_path = LOGS_DIR / log_filename

    log_entry = {
        "timestamp": timestamp.isoformat(),
        "request": {
            "subsystem": subsystem,
            "command": command,
            "parameters": params,
        },
        "response": response if not error else None,
        "error": error,
    }

    with open(log_path, "w") as f:
        json.dump(log_entry, f, indent=2)

    return log_path


def display_response(response: Any, raw: bool = False) -> None:
    """Display the API response with pretty printing."""
    if raw:
        # Raw JSON output
        print(json.dumps(response, indent=2))
    else:
        # Pretty printed with Rich
        console.print()
        console.print(
            Panel(
                JSON(json.dumps(response), indent=2),
                title="[bold cyan]API Response[/bold cyan]",
                border_style="cyan",
            )
        )
        console.print()


def display_error(error_msg: str) -> None:
    """Display an error message."""
    console.print()
    console.print(
        Panel(
            f"[bold red]{error_msg}[/bold red]",
            title="[bold red]Error[/bold red]",
            border_style="red",
        )
    )
    console.print()


async def make_api_call(
    subsystem: str, command: str, params: Dict[str, str]
) -> Any:
    """Make an API call using the CHAOSClient."""
    # Load settings from environment
    settings = Settings()

    # Create client and make request
    async with CHAOSClient(settings.api, settings.auth) as client:
        response = await client.request(subsystem, command, params)
        return response


async def main() -> int:
    """Main entry point."""
    args = parse_arguments()

    subsystem = args.subsystem
    command = args.command
    params = parse_parameters(args.parameters)

    # Display request info
    if not args.raw:
        console.print()
        console.print(f"[bold cyan]Subsystem:[/bold cyan] {subsystem}")
        console.print(f"[bold cyan]Command:[/bold cyan] {command}")
        if params:
            console.print(f"[bold cyan]Parameters:[/bold cyan] {params}")
        console.print()
        console.print("[dim]Making API request...[/dim]")

    try:
        # Make the API call
        response = await make_api_call(subsystem, command, params)

        # Check for API-level errors
        if isinstance(response, dict) and "error" in response:
            error_msg = response.get("error", "Unknown error")
            display_error(f"API Error: {error_msg}")

            # Log even errors
            if not args.no_log:
                log_path = save_to_log(subsystem, command, params, response, error_msg)
                if not args.raw:
                    console.print(f"[dim]Response logged to: {log_path}[/dim]")

            return 1

        # Display the response
        display_response(response, args.raw)

        # Save to history
        save_to_history(subsystem, command, params)

        # Save to log file
        if not args.no_log:
            log_path = save_to_log(subsystem, command, params, response)
            if not args.raw:
                console.print(f"[dim]Response logged to: {log_path}[/dim]")
                console.print()

        return 0

    except Exception as e:
        error_msg = f"Request failed: {type(e).__name__}: {str(e)}"
        display_error(error_msg)

        # Log the error
        if not args.no_log:
            log_path = save_to_log(subsystem, command, params, None, error_msg)
            if not args.raw:
                console.print(f"[dim]Error logged to: {log_path}[/dim]")

        return 1


if __name__ == "__main__":
    try:
        exit_code = asyncio.run(main())
        sys.exit(exit_code)
    except KeyboardInterrupt:
        console.print("\n[yellow]Interrupted by user[/yellow]")
        sys.exit(130)
