#!/usr/bin/env python3
"""Interactive CHAOS2 API lab tool.

This tool complements the Prometheus exporter by providing a richer, more
exploratory interface for authenticated CHAOS2 API calls.  It supports both a
one-shot CLI mode and an interactive shell with history, request presets, and
response logging so you can quickly prototype new queries.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import shlex
import sys
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

import httpx
from rich.console import Console
from rich.json import JSON
from rich.panel import Panel
from rich.table import Table

# Make the project sources importable when running from the scripts directory
SCRIPT_PATH = Path(__file__).resolve()
PROJECT_ROOT = SCRIPT_PATH.parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from aaisp_exporter.api.client import (  # noqa: E402
    CHAOSAPIError,
    CHAOSAuthError,
    CHAOSRateLimitError,
)
from aaisp_exporter.core.config import AuthSettings, Settings  # noqa: E402


DEFAULT_SUBSYSTEM = "broadband"
HISTORY_LIMIT = 200
LOGS_DIR = SCRIPT_PATH.parent / "logs"
HISTORY_FILE = SCRIPT_PATH.parent / ".chaos2_lab_history"

LOGS_DIR.mkdir(exist_ok=True)

# Curated hints based on the official CHAOS2 documentation.
STANDARD_COMMANDS: dict[str, list[str]] = {
    "broadband": [
        "services",
        "info",
        "usage",
        "quota",
        "availability",
        "check",
        "order",
        "cease",
        "adjust",
        "settings",
    ],
    "telephony": [
        "services",
        "info",
        "usage",
        "ratecard",
        "order",
        "cease",
    ],
    "login": ["services", "info", "adjust", "settings"],
    "domain": ["services", "info", "order", "settings"],
    "email": ["services", "info", "settings"],
    "sim": ["services", "info", "usage", "order", "settings"],
}

KNOWN_SUBSYSTEMS = sorted(STANDARD_COMMANDS.keys())


def parse_kv_pairs(pairs: Iterable[str]) -> dict[str, str]:
    """Parse key=value strings into a dictionary."""

    parsed: dict[str, str] = {}
    for raw in pairs:
        if "=" not in raw:
            msg = f"Parameter '{raw}' is not in key=value format"
            raise ValueError(msg)
        key, value = raw.split("=", 1)
        key = key.strip()
        value = value.strip()
        if not key:
            msg = f"Invalid parameter '{raw}'"
            raise ValueError(msg)
        parsed[key] = value
    return parsed


def sanitize_payload(payload: dict[str, str]) -> dict[str, str]:
    """Mask secrets before logging or printing."""

    masked: dict[str, str] = {}
    for key, value in payload.items():
        lowered = key.lower()
        if any(token in lowered for token in {"password", "secret"}):
            masked[key] = "***"
        else:
            masked[key] = value
    return masked


def format_json(data: Any) -> JSON:
    """Return a Rich JSON renderable for the provided structure."""

    try:
        rendered = json.dumps(data, indent=2, ensure_ascii=False)
    except TypeError:
        rendered = json.dumps(str(data), indent=2, ensure_ascii=False)
    return JSON(rendered, indent=2)


def write_log_entry(entry: dict[str, Any]) -> Path:
    """Persist a request/response pair to scripts/logs."""

    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S_%f")
    path = LOGS_DIR / f"chaos2_lab_{timestamp}.json"
    with path.open("w", encoding="utf-8") as handle:
        json.dump(entry, handle, indent=2)
    return path


@dataclass
class APIResult:
    """Container for API call metadata."""

    url: str
    status_code: int
    duration: float
    payload: dict[str, str]
    data: Any

    @property
    def has_api_error(self) -> bool:
        return isinstance(self.data, dict) and "error" in self.data


class ChaosAPISession:
    """Lightweight helper around httpx for interactive exploration."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._client: httpx.AsyncClient | None = None
        self._semaphore = asyncio.Semaphore(settings.api.concurrency_limit)

    async def __aenter__(self) -> "ChaosAPISession":
        await self.start()
        return self

    async def __aexit__(self, *exc_info: object) -> None:  # noqa: ANN002
        await self.close()

    async def start(self) -> None:
        if self._client is None:
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(self.settings.api.timeout),
                follow_redirects=True,
                headers={"User-Agent": "AAISP-CHAOS-Lab/1.0"},
            )

    async def close(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    def _auth_payload(self) -> dict[str, str]:
        return _auth_payload(self.settings.auth)

    async def request(
        self,
        subsystem: str,
        command: str,
        params: dict[str, str] | None = None,
    ) -> APIResult:
        if not subsystem:
            raise ValueError("Subsystem must be provided")
        if not command:
            raise ValueError("Command must be provided")

        if self._client is None:
            await self.start()

        params = params or {}
        base_url = self.settings.api.base_url.rstrip("/")
        subsystem_slug = subsystem.strip("/")
        url = f"{base_url}/{subsystem_slug}/{command.strip('/')}/json"

        payload = self._auth_payload()
        payload.update(params)
        request_payload = sanitize_payload(payload)

        attempts = self.settings.api.max_retries + 1
        last_error: Exception | None = None
        for attempt in range(attempts):
            try:
                start = time.perf_counter()
                async with self._semaphore:
                    assert self._client is not None
                    response = await self._client.post(
                        url,
                        data=payload,
                        headers={"Content-Type": "application/x-www-form-urlencoded"},
                    )

                if response.status_code == 401:
                    raise CHAOSAuthError("Authentication failed")
                if response.status_code == 429:
                    raise CHAOSRateLimitError("Rate limit exceeded")

                response.raise_for_status()
                data = response.json()
                duration = time.perf_counter() - start
                return APIResult(url, response.status_code, duration, request_payload, data)

            except httpx.TimeoutException as exc:
                last_error = CHAOSAPIError(
                    f"Request timed out (attempt {attempt + 1}/{attempts})",
                )
                if attempt + 1 == attempts:
                    raise last_error from exc
                await asyncio.sleep(2**attempt)

            except httpx.HTTPStatusError as exc:
                last_error = CHAOSAPIError(
                    f"HTTP {exc.response.status_code}: {exc.response.text[:200]}",
                )
                raise last_error from exc

            except httpx.RequestError as exc:
                last_error = CHAOSAPIError(str(exc))
                raise last_error from exc

        assert last_error is not None
        raise last_error


def _auth_payload(auth: AuthSettings) -> dict[str, str]:
    """Build authentication payload based on configured credentials."""

    payload: dict[str, str] = {}
    if auth.control_login and auth.control_password:
        payload["control_login"] = auth.control_login
        payload["control_password"] = auth.control_password.get_secret_value()
    if not payload and auth.account_number and auth.account_password:
        payload["account_number"] = auth.account_number
        payload["account_password"] = auth.account_password.get_secret_value()
    return payload


class ChaosLabShell:
    """Interactive prompt for quick ad-hoc experimentation."""

    def __init__(
        self,
        session: ChaosAPISession,
        console: Console,
        *,
        default_subsystem: str,
        log_requests: bool,
        raw_output: bool,
    ) -> None:
        self.session = session
        self.console = console
        self.default_subsystem = default_subsystem
        self.log_requests = log_requests
        self.raw_output = raw_output
        self.default_params: dict[str, str] = {}
        self.history = self._load_history()
        self.last_result: APIResult | None = None

    async def run(self) -> None:
        self._print_welcome()
        while True:
            try:
                prompt = f"[bold green]{self.default_subsystem}[/bold green] λ "
                line = self.console.input(prompt).strip()
            except EOFError:
                self.console.print()
                break
            except KeyboardInterrupt:
                self.console.print()
                continue

            if not line:
                continue
            if line.lower() in {"exit", "quit"}:
                break
            if line.startswith(":"):
                handled = self._handle_meta(line[1:])
                if handled:
                    continue

            await self._dispatch_line(line)

    def _handle_meta(self, command_line: str) -> bool:
        tokens = shlex.split(command_line)
        if not tokens:
            return True
        command = tokens[0].lower()
        args = tokens[1:]

        if command in {"use", "subsystem"}:
            if not args:
                self.console.print("[yellow]Usage:[/yellow] :use <subsystem>")
                return True
            self.default_subsystem = args[0].lower()
            self.console.print(f"Default subsystem set to {self.default_subsystem}")
            return True

        if command in {"params", "defaults"}:
            if not self.default_params:
                self.console.print("[dim]No default parameters set[/dim]")
            else:
                table = Table("Key", "Value")
                for key, value in self.default_params.items():
                    table.add_row(key, value)
                self.console.print(table)
            return True

        if command == "set":
            if len(args) < 2:
                self.console.print("[yellow]Usage:[/yellow] :set <key> <value>")
                return True
            key, value = args[0], " ".join(args[1:])
            self.default_params[key] = value
            self.console.print(f"Saved default parameter {key}={value}")
            return True

        if command == "unset":
            if not args:
                self.console.print("[yellow]Usage:[/yellow] :unset <key>")
                return True
            removed = self.default_params.pop(args[0], None)
            if removed is None:
                self.console.print(f"[dim]No default '{args[0]}' to remove[/dim]")
            else:
                self.console.print(f"Removed default for {args[0]}")
            return True

        if command == "clear":
            self.default_params.clear()
            self.console.print("Cleared all default parameters")
            return True

        if command in {"raw", "pretty"}:
            if not args:
                self.raw_output = not self.raw_output
            else:
                self.raw_output = args[0].lower() in {"1", "true", "on", "yes"}
            mode = "raw" if self.raw_output else "pretty"
            self.console.print(f"Response output set to {mode}")
            return True

        if command == "history":
            limit = int(args[0]) if args else 20
            for line in self.history[-limit:]:
                self.console.print(line)
            return True

        if command in {"commands", "help"}:
            subsystem = args[0].lower() if args else self.default_subsystem
            self._show_commands(subsystem)
            return True

        if command == "log":
            if not args:
                self.log_requests = not self.log_requests
            else:
                self.log_requests = args[0].lower() in {"1", "true", "on", "yes"}
            state = "enabled" if self.log_requests else "disabled"
            self.console.print(f"Logging {state}")
            return True

        if command == "last":
            if not self.last_result:
                self.console.print("[dim]No request executed yet[/dim]")
            else:
                self._render_result(self.last_result)
            return True

        if command == "save":
            if not args:
                self.console.print("[yellow]Usage:[/yellow] :save <path>")
                return True
            if not self.last_result:
                self.console.print("[red]Nothing to save yet[/red]")
                return True
            path = Path(args[0]).expanduser()
            entry = self._result_to_log_dict(self.last_result)
            with path.open("w", encoding="utf-8") as handle:
                json.dump(entry, handle, indent=2)
            self.console.print(f"Saved last response to {path}")
            return True

        if command in {"auth", "whoami"}:
            self._show_auth_info()
            return True

        if command == "subs":
            table = Table("Subsystem", "Hints")
            for subsystem in KNOWN_SUBSYSTEMS:
                hints = ", ".join(STANDARD_COMMANDS[subsystem])
                table.add_row(subsystem, hints)
            self.console.print(table)
            return True

        return False

    async def _dispatch_line(self, line: str) -> None:
        try:
            subsystem, command, params = self._parse_request_line(line)
        except ValueError as exc:
            self.console.print(f"[red]{exc}[/red]")
            return

        merged = {**self.default_params, **params}
        await self._run_request(subsystem, command, merged)

    def _parse_request_line(self, line: str) -> tuple[str, str, dict[str, str]]:
        tokens = shlex.split(line)
        if not tokens:
            raise ValueError("Empty request")

        subsystem = self.default_subsystem
        command = tokens[0]
        cursor = 1

        # Allow shorthand like "broadband info" or "broadband/info".
        lowered = command.lower()
        if lowered in KNOWN_SUBSYSTEMS:
            if len(tokens) < 2:
                raise ValueError("Command missing after subsystem")
            subsystem = lowered
            command = tokens[1]
            cursor = 2
        elif "/" in command:
            maybe_subsystem, maybe_command = command.split("/", 1)
            if maybe_subsystem.lower() in KNOWN_SUBSYSTEMS and maybe_command:
                subsystem = maybe_subsystem.lower()
                command = maybe_command
        elif command.startswith(".") and self.last_result:
            # Allow repeating last subsystem with ".command" syntax.
            command = command[1:]

        params = parse_kv_pairs(tokens[cursor:]) if len(tokens) > cursor else {}
        return subsystem, command, params

    async def _run_request(self, subsystem: str, command: str, params: dict[str, str]) -> None:
        try:
            result = await self.session.request(subsystem, command, params)
        except (CHAOSAPIError, CHAOSAuthError, CHAOSRateLimitError) as exc:
            self.console.print(f"[red]{exc}[/red]")
            return

        self.last_result = result
        self._append_history(subsystem, command, params)
        self._render_result(result)
        if self.log_requests:
            entry = self._result_to_log_dict(result)
            path = write_log_entry(entry)
            self.console.print(f"[dim]Logged to {path}[/dim]")

    def _render_result(self, result: APIResult) -> None:
        summary = Table(box=None, show_header=False)
        summary.add_row("URL", result.url)
        summary.add_row("Status", str(result.status_code))
        summary.add_row("Time", f"{result.duration:.3f}s")
        if result.payload:
            summary.add_row("Parameters", json.dumps(result.payload))

        self.console.print(Panel(summary, title="Request", border_style="cyan"))

        if self.raw_output:
            text = json.dumps(result.data, indent=2, ensure_ascii=False)
            self.console.print(text)
        else:
            style = "red" if result.has_api_error else "green"
            self.console.print(
                Panel(
                    format_json(result.data),
                    title="API Response" if not result.has_api_error else "API Response (error)",
                    border_style=style,
                )
            )

    def _append_history(self, subsystem: str, command: str, params: dict[str, str]) -> None:
        params_json = json.dumps(params, sort_keys=True)
        record = f"{datetime.now().isoformat()} {subsystem} {command} {params_json}"
        self.history.append(record)
        if len(self.history) > HISTORY_LIMIT:
            self.history = self.history[-HISTORY_LIMIT:]
        with HISTORY_FILE.open("w", encoding="utf-8") as handle:
            handle.write("\n".join(self.history) + "\n")

    def _load_history(self) -> list[str]:
        if HISTORY_FILE.exists():
            return HISTORY_FILE.read_text(encoding="utf-8").splitlines()
        return []

    def _result_to_log_dict(self, result: APIResult) -> dict[str, Any]:
        return {
            "timestamp": datetime.utcnow().isoformat(),
            "request": {
                "url": result.url,
                "parameters": result.payload,
            },
            "response": {
                "status_code": result.status_code,
                "duration_seconds": result.duration,
                "body": result.data,
            },
        }

    def _print_welcome(self) -> None:
        table = Table(box=None, show_header=False)
        table.add_row("Authenticated as", describe_auth(self.session.settings.auth))
        table.add_row("Base URL", self.session.settings.api.base_url)
        table.add_row("Default subsystem", self.default_subsystem)
        table.add_row("Hints", "Type :commands to list common actions")
        self.console.print(Panel(table, title="CHAOS2 Lab", border_style="magenta"))

    def _show_commands(self, subsystem: str) -> None:
        commands = STANDARD_COMMANDS.get(subsystem.lower())
        if not commands:
            self.console.print(f"[yellow]No curated commands for '{subsystem}'[/yellow]")
            return
        table = Table(title=f"{subsystem} commands")
        table.add_column("Command")
        for cmd in commands:
            table.add_row(cmd)
        self.console.print(table)

    def _show_auth_info(self) -> None:
        self.console.print(describe_auth(self.session.settings.auth))


def describe_auth(auth: AuthSettings) -> str:
    if auth.control_login:
        return f"control_login={auth.control_login}"
    if auth.account_number:
        return f"account_number={auth.account_number}"
    return "<no credentials>"


def run_cli() -> None:
    parser = argparse.ArgumentParser(
        description="CHAOS2 Lab - interactive CLI for Andrews & Arnold's CHAOS2 API",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  python chaos2_lab.py broadband services\n"
            "  python chaos2_lab.py telephony info service=02012345678\n"
            "  python chaos2_lab.py --subsystem login --command services\n"
            "Run without positional arguments to drop into the interactive lab shell."
        ),
    )

    parser.add_argument("subsystem", nargs="?", help="Subsystem to query (e.g. broadband)")
    parser.add_argument("command", nargs="?", help="Command to run (e.g. services)")
    parser.add_argument(
        "parameters",
        nargs="*",
        help="Optional key=value parameters sent with the request",
    )
    parser.add_argument(
        "--raw",
        action="store_true",
        help="Output raw JSON instead of Rich panels",
    )
    parser.add_argument(
        "--no-log",
        action="store_true",
        help="Disable JSON logging of requests and responses",
    )

    args = parser.parse_args()
    console = Console()

    try:
        settings = Settings()
        settings.validate_auth()
    except Exception as exc:  # noqa: BLE001
        console.print(f"[red]Unable to load settings: {exc}[/red]")
        raise SystemExit(1) from exc

    if args.subsystem and not args.command:
        console.print(
            "[yellow]A subsystem was provided without a command; starting interactive mode."
        )

    if not args.subsystem or not args.command:
        asyncio.run(
            run_interactive(
                settings,
                console,
                default_subsystem=(args.subsystem or DEFAULT_SUBSYSTEM),
                log_requests=not args.no_log,
                raw_output=args.raw,
            )
        )
        return

    try:
        params = parse_kv_pairs(args.parameters)
    except ValueError as exc:
        console.print(f"[red]{exc}[/red]")
        raise SystemExit(1) from exc

    asyncio.run(
        run_single(
            settings,
            console,
            args.subsystem,
            args.command,
            params,
            log_requests=not args.no_log,
            raw_output=args.raw,
        )
    )


async def run_single(
    settings: Settings,
    console: Console,
    subsystem: str,
    command: str,
    params: dict[str, str],
    *,
    log_requests: bool,
    raw_output: bool,
) -> None:
    async with ChaosAPISession(settings) as session:
        try:
            result = await session.request(subsystem, command, params)
        except (CHAOSAPIError, CHAOSAuthError, CHAOSRateLimitError) as exc:
            console.print(f"[red]{exc}[/red]")
            raise SystemExit(1) from exc

        shell = ChaosLabShell(
            session,
            console,
            default_subsystem=subsystem,
            log_requests=log_requests,
            raw_output=raw_output,
        )
        shell.last_result = result
        shell._render_result(result)
        if log_requests:
            entry = shell._result_to_log_dict(result)
            path = write_log_entry(entry)
            console.print(f"[dim]Logged to {path}[/dim]")


async def run_interactive(
    settings: Settings,
    console: Console,
    *,
    default_subsystem: str,
    log_requests: bool,
    raw_output: bool,
) -> None:
    async with ChaosAPISession(settings) as session:
        shell = ChaosLabShell(
            session,
            console,
            default_subsystem=default_subsystem,
            log_requests=log_requests,
            raw_output=raw_output,
        )
        await shell.run()


if __name__ == "__main__":
    run_cli()
