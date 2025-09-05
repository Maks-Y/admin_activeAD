"""Simple helpers for parsing user commands.

The real project uses a more advanced NLP module.  For the unit tests in this
kata we only need very small parsing capabilities which are implemented here.
"""

from __future__ import annotations

import email.message
import re
from datetime import datetime
from typing import List, Tuple

from dateparser.search import search_dates


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


def parse_hr_mail(msg: email.message.Message) -> tuple[str | None, datetime | None]:
    """Extract employee name and dismissal date from an HR e-mail.

    Parameters
    ----------
    msg:
        ``email.message.Message`` instance representing the incoming e-mail.

    Returns
    -------
    tuple(fio, date)
        * fio -- extracted full name or ``None`` when not found.
        * date -- parsed ``datetime`` object or ``None`` when not found.
    """

    # Extract plain text payload from the message
    parts: List[str] = []
    if msg.is_multipart():
        for part in msg.walk():
            if part.get_content_type() == "text/plain":
                payload = part.get_payload(decode=True)
                if payload:
                    charset = part.get_content_charset() or "utf-8"
                    parts.append(payload.decode(charset, errors="ignore"))
    else:
        payload = msg.get_payload(decode=True)
        if isinstance(payload, bytes):
            parts.append(payload.decode(msg.get_content_charset() or "utf-8", errors="ignore"))
        elif isinstance(payload, str):
            parts.append(payload)

    body = "\n".join(parts)

    # Extract FIO (full name) - three capitalized words
    fio: str | None = None
    match = re.search(r"([А-ЯЁ][а-яё]+\s+[А-ЯЁ][а-яё]+\s+[А-ЯЁ][а-яё]+)", body)
    if match:
        fio = match.group(1).strip()

    # Extract first date occurrence using dateparser
    date: datetime | None = None
    try:
        found = search_dates(body, languages=["ru"])
    except Exception:
        found = None
    if found:
        date = found[0][1]

    return fio, date


__all__ = ["parse_command", "parse_hr_mail"]

