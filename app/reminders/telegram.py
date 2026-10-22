"""קריאות HTTP ל-Bot API. בלי ספריית בוט ובלי AI.

הטוקן מגיע מהקורא (``TELEGRAM_BOT_TOKEN``). אסור לכתוב אותו ללוג.
"""
from __future__ import annotations

import html
import json
import urllib.error
import urllib.request


class TelegramError(RuntimeError):
    pass


def telegram_api(token: str, method: str, payload: dict | None = None, *, timeout: float = 30):
    url = f"https://api.telegram.org/bot{token}/{method}"
    data = None
    headers = {}
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(url, data=data, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise TelegramError(f"{method} failed: HTTP {exc.code} {detail[:300]}") from exc
    except urllib.error.URLError as exc:
        raise TelegramError(f"{method} failed: {exc.reason}") from exc
    if not body.get("ok"):
        raise TelegramError(f"{method} failed: {body.get('description', body)}")
    return body.get("result")


def send_message(token: str, chat_id, text: str) -> bool:
    telegram_api(
        token,
        "sendMessage",
        {"chat_id": chat_id, "text": text, "parse_mode": "HTML"},
    )
    return True


def chat_id_reply(chat_id) -> str:
    """המזהה ב-<code> כדי שלחיצה עליו בטלגרם תעתיק (parse_mode HTML)."""
    safe_id = html.escape(str(chat_id), quote=False)
    return (
        f"מזהה הצ'אט שלך: <code>{safe_id}</code>\n"
        "מעתיקים את המספר להגדרות, תחת תזכורות."
    )


def start_chat_id(update: dict):
    """מחזיר chat id אם ההודעה היא /start, אחרת None."""
    if not isinstance(update, dict):
        return None
    message = update.get("message") or {}
    text = (message.get("text") or "").strip()
    if not text.startswith("/start"):
        return None
    command = text.split()[0]
    if command != "/start" and not command.startswith("/start@"):
        return None
    chat = message.get("chat") or {}
    chat_id = chat.get("id")
    if isinstance(chat_id, bool) or chat_id is None:
        return None
    return chat_id


def consume_updates(token: str, offset: int | None, *, long_poll: int = 0, api=telegram_api) -> int | None:
    """קורא עדכונים, עונה ל-/start, ומחזיר את ה-offset הבא."""
    payload = {"timeout": int(long_poll), "allowed_updates": ["message"]}
    if offset is not None:
        payload["offset"] = offset
    timeout = max(10, int(long_poll) + 10)
    updates = api(token, "getUpdates", payload, timeout=timeout) or []
    next_offset = offset
    for update in updates:
        update_id = update.get("update_id")
        if isinstance(update_id, int):
            next_offset = update_id + 1
        chat_id = start_chat_id(update)
        if chat_id is None:
            continue
        api(
            token,
            "sendMessage",
            {
                "chat_id": chat_id,
                "text": chat_id_reply(chat_id),
                "parse_mode": "HTML",
            },
        )
    return next_offset
