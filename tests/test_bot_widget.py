"""ווידג'ט סיכום היום בטלגרם - HTML, מגבלת גודל, ו-dispatch."""
from __future__ import annotations

from datetime import date

import pytest

from app.bot.widget import (
    WIDGET_ZLIB_MAX,
    build_today_digest_widget_html,
    today_digest_widget_payload,
    widget_fits,
    widget_zlib_size,
)


def test_widget_html_is_rtl_hebrew_and_uses_telegram_widget():
    html = build_today_digest_widget_html(date(2026, 11, 24), ["• 09:00 | בדיקה"])
    assert 'dir="rtl"' in html
    assert 'lang="he"' in html
    assert "TelegramWidget" in html
    assert "סיכום היום" in html
    assert "• 09:00 | בדיקה" in html
    assert "רענון" in html
    assert widget_fits(html)
    assert widget_zlib_size(html) <= WIDGET_ZLIB_MAX


def test_widget_payload_for_sendWidget():
    payload = today_digest_widget_payload(date(2026, 11, 24), ["• בוקר | אביחי"])
    assert "html" in payload
    assert payload["allow_queries"] is True
    assert "chat_data" in payload
    assert "2026-11-24" in payload["chat_data"]
    assert widget_zlib_size(payload["html"]) <= WIDGET_ZLIB_MAX


def test_oversized_widget_rejected(monkeypatch):
    import app.bot.widget as widget_mod

    monkeypatch.setattr(widget_mod, "WIDGET_ZLIB_MAX", 10)
    with pytest.raises(ValueError):
        today_digest_widget_payload(date(2026, 11, 24), ["• שורה ארוכה מאוד " * 20])


def test_dispatch_today_widget_returns_widget_payload(app, client):
    from app.bot.dispatch import handle_update
    from app.reminders.repository import create_person

    with app.app_context():
        create_person("דני", "42", receives_reminders=True)
        outgoing = handle_update(
            {
                "update_id": 1,
                "callback_query": {
                    "id": "cb1",
                    "data": "today_widget",
                    "message": {"message_id": 9, "chat": {"id": 42}},
                },
            }
        )
        via_command = handle_update(
            {
                "update_id": 2,
                "message": {"text": "/today", "chat": {"id": 42}},
            }
        )
    assert outgoing.get("chat_id") == 42
    assert outgoing.get("widget")
    assert outgoing["widget"]["html"]
    assert "TelegramWidget" in outgoing["widget"]["html"]
    # fallback text also present
    assert "סיכום היום" in (outgoing.get("text") or "")
    assert via_command.get("widget")
    assert "סיכום היום" in (via_command.get("text") or "")


def test_menu_has_today_widget_button():
    from app.bot import ui

    flat = [label for row in ui.menu_rows() for label, _cb in row]
    assert "☀️ סיכום היום" in flat
    callbacks = [cb for row in ui.menu_rows() for _label, cb in row]
    assert "today_widget" in callbacks
