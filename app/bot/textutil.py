"""בריחה ל-HTML של טלגרם, ומזהים ב-<code> (העתקה בלחיצה)."""
from __future__ import annotations

import html

BUTTON_LIMIT = 40


def esc(value) -> str:
    return html.escape("" if value is None else str(value), quote=False)


def code(value) -> str:
    """מספר או קוד להעתקה בלחיצה. parse_mode של הבוט הוא HTML."""
    return f"<code>{esc(value)}</code>"


def clip(value, limit: int = BUTTON_LIMIT) -> str:
    text = " ".join(str(value or "").replace("\n", " ").split())
    if not text:
        return "אירוע"
    if len(text) <= limit:
        return text
    return text[: limit - 1] + "…"


def clean_line(value) -> str:
    text = str(value or "")
    for mark in ("\u200f", "\u200e", "\ufeff", "\u202a", "\u202b", "\u202c"):
        text = text.replace(mark, "")
    return " ".join(text.split())
