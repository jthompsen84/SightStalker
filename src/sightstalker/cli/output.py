"""
sightstalker.cli.output — central command wrapper and output policy.

Every CLI command runs through ``run_cli_command``, which guarantees:

- in ``--json`` mode, exactly one JSON object is written to stdout for handled
  success/failure, with the stable ``{ok, command, data, warnings, errors}``
  envelope, and stderr stays empty on success;
- in human mode, Rich output goes to stdout and warnings/errors to stderr;
- exceptions are mapped — via the project resilience classifier — to a stable
  exit code, stable public ``type`` label, and an enriched, sanitized error
  entry (adding ``kind``/``severity``/``recoverability``/``exit_code``/``code``/
  ``details``); never a raw traceback, raw URL secret, DB URL, or payload.

As of v0.4.1 the wrapper also configures redacted loguru logging per command
verbosity/JSON rules. Logging setup is skipped for trivial commands.
"""

from __future__ import annotations

import json
from collections.abc import Callable

import typer
from rich.console import Console

from sightstalker.cli.errors import map_exception_full
from sightstalker.cli.exit_codes import EXIT_OK
from sightstalker.cli.types import CommandOutcome

# Commands that never emit logs and can skip logging setup entirely.
_TRIVIAL_COMMANDS = frozenset({"version", "config.show"})


def _emit_json(payload: dict[str, object]) -> None:
    """Write exactly one compact JSON object to stdout."""
    # ``print`` (not Rich) to guarantee a single clean line with no markup.
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True))


def _json_success(command: str, outcome: CommandOutcome) -> None:
    _emit_json(
        {
            "ok": True,
            "command": command,
            "data": outcome.data,
            "warnings": list(outcome.warnings),
            "errors": [],
        }
    )


def _json_failure(
    command: str, entry: dict[str, object], warnings: list[str]
) -> None:
    _emit_json(
        {
            "ok": False,
            "command": command,
            "data": None,
            "warnings": list(warnings),
            "errors": [entry],
        }
    )


def _maybe_configure_logging(
    command: str, *, json_output: bool, verbose: bool
) -> None:
    """Configure redacted loguru logging unless the command is trivial.

    Importing this lazily keeps loguru out of the CLI import path.
    """
    if command in _TRIVIAL_COMMANDS and not verbose:
        return
    from sightstalker.resilience import configure_cli_logging

    configure_cli_logging(verbose=verbose, json_output=json_output)


def run_cli_command(
    command: str,
    *,
    json_output: bool,
    verbose: bool,
    handler: Callable[[], CommandOutcome],
) -> None:
    """Execute ``handler`` and emit a redacted, exit-coded result.

    Always terminates by raising ``typer.Exit`` so the process exit code
    reflects the outcome. ``KeyboardInterrupt`` and ``SystemExit`` propagate.
    """
    stdout = Console()
    stderr = Console(stderr=True)

    _maybe_configure_logging(command, json_output=json_output, verbose=verbose)

    try:
        outcome = handler()
    except Exception as exc:  # noqa: BLE001 - sanitized and exit-coded below
        code, entry, warnings, operator = map_exception_full(exc)
        if json_output:
            from sightstalker.resilience import operator_error_to_json

            _json_failure(command, operator_error_to_json(operator), warnings)
        else:
            for warning in warnings:
                stderr.print(f"[yellow]warning:[/yellow] {warning}")
            stderr.print(f"[red]error:[/red] {entry['message']}")
            if verbose:
                stderr.print(
                    f"[dim]({entry['type']} · {operator.kind} · "
                    f"{operator.recoverability})[/dim]"
                )
        raise typer.Exit(code)

    if json_output:
        _json_success(command, outcome)
    else:
        outcome.human(stdout)
        for warning in outcome.warnings:
            stderr.print(f"[yellow]warning:[/yellow] {warning}")
    raise typer.Exit(EXIT_OK)


__all__ = ["run_cli_command"]
