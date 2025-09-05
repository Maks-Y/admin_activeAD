"""Simple helpers for parsing user commands.

The real project uses a more advanced NLP module.  For the unit tests in this
kata we only need very small parsing capabilities which are implemented here.
"""

from __future__ import annotations

from typing import List, Tuple


ALIASES = {
    "reset password": "reset",
    "reset": "reset",
    "schedule block": "disable",
    "block": "disable",
    "disable": "disable",
    "list jobs": "jobs",
    "jobs": "jobs",
    "admin menu": "admin",
    "admin": "admin",
}


def parse_command(text: str) -> Tuple[str, List[str]]:
    """Parse plain or button text into a command and list of arguments.

    Parameters
    ----------
    text:
        Incoming message text.  It can be either a human typed command or the
        label from one of the reply buttons.

    Returns
    -------
    tuple(command, args)
        * command -- canonical command name (e.g. ``"reset"``).  Empty string
          when the text cannot be interpreted.
        * args -- list of arguments following the command.
    """

    cleaned = text.strip().lower()
    for alias, cmd in ALIASES.items():
        if cleaned.startswith(alias):
            rest = text[len(alias) :].strip()
            args = rest.split() if rest else []
            return cmd, args
    return "", [text]


__all__ = ["parse_command"]

