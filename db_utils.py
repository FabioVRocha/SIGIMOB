"""Shared helpers for database connectivity."""

from __future__ import annotations

from typing import Union


def decode_psycopg_unicode_error(err: UnicodeDecodeError) -> str:
    """Return a readable message from psycopg2 UnicodeDecodeError details."""
    raw: Union[bytes, bytearray, None] = getattr(err, "object", None)
    if isinstance(raw, (bytes, bytearray)):
        try:
            return raw.decode("latin-1")
        except Exception:
            return repr(raw)
    return str(err)
