"""Initial Watari command-line entrypoint."""

from __future__ import annotations

import sys
from importlib.metadata import version


HELP = (
    "usage: watari [--help | --version]\n\n"
    "Watari CLI\n\n"
    "options:\n"
    "  --help     show this help and exit\n"
    "  --version  show version and exit\n"
)
USAGE_ERROR = (
    "usage: watari [--help | --version]\n"
    "watari: error: expected exactly one of --help or --version\n"
)


def _dispatch(arguments: list[str]) -> int:
    try:
        from .router import dispatch
    except ModuleNotFoundError as error:
        if error.name != f"{__package__}.router":
            raise
        sys.stderr.write(USAGE_ERROR)
        return 2
    return dispatch(arguments)


def main() -> int:
    """Handle only the two B002 package-level options."""

    arguments = sys.argv[1:]
    if arguments == ["--help"]:
        sys.stdout.write(HELP)
        return 0
    if arguments == ["--version"]:
        sys.stdout.write(f"watari {version('watari-cli')}\n")
        return 0
    if "--help" in arguments or "--version" in arguments:
        sys.stderr.write(USAGE_ERROR)
        return 2
    return _dispatch(arguments)
