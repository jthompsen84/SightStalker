"""
sightstalker.cli.exit_codes — stable named exit-code constants.

The CLI maps every handled outcome to one of these process exit codes so that
operators and machine consumers get a stable contract. Exit code 6
(``EXIT_SECURITY``) is produced by unsafe-URL / unsafe-config refusal paths.
"""

from __future__ import annotations

EXIT_OK = 0
EXIT_GENERAL_ERROR = 1
EXIT_USAGE = 2
EXIT_PERSISTENCE = 3
EXIT_BROWSER = 4
EXIT_DIAGNOSTIC = 5
EXIT_SECURITY = 6

__all__ = [
    "EXIT_BROWSER",
    "EXIT_DIAGNOSTIC",
    "EXIT_GENERAL_ERROR",
    "EXIT_OK",
    "EXIT_PERSISTENCE",
    "EXIT_SECURITY",
    "EXIT_USAGE",
]
