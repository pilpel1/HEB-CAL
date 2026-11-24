"""קריאות HTTP ל-Bot API. בלי ספריית בוט ובלי AI.

הטוקן מגיע מהקורא (``TELEGRAM_BOT_TOKEN``). אסור לכתוב אותו ללוג.
"""
from __future__ import annotations

import html
import json
import sys
import urllib.error
import urllib.request


class TelegramError(RuntimeError):
    def __init__(self, message: str, *, status_code: int | None = None):
        super().__init__(message)
        self.status_code = status_code

    @property
    def is_conflict(self) -> bool:
        if self.status_code == 409:
            return True
        text = str(self).lower()
        return "http 409" in text or "error_code\":409" in text or "error_code': 409" in text


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
        raise TelegramError(
            f"{method} failed: HTTP {exc.code} {detail[:300]}",
            status_code=exc.code,
        ) from exc
    except urllib.error.URLError as exc:
        raise TelegramError(f"{method} failed: {exc.reason}") from exc
    if not body.get("ok"):
        raw_code = body.get("error_code")
        code = raw_code if isinstance(raw_code, int) else None
        raise TelegramError(
            f"{method} failed: {body.get('description', body)}",
            status_code=code,
        )
    return body.get("result")


def publish_bot_commands(token: str, api=telegram_api) -> bool:
    """רושם את תפריט הפקודות (הכפתור ליד שורת הכתיבה). כשל לא מפיל את ה-worker."""
    if not (token or "").strip():
        return False
    from app.bot.commands import command_menu_payload

    try:
        api(token, "setMyCommands", command_menu_payload())
    except TelegramError as exc:
        print(f"setMyCommands failed: {exc}", file=sys.stderr)
        return False
    print("telegram command menu updated")
    return True


def send_message(token: str, chat_id, text: str, *, reply_markup: dict | None = None) -> bool:
    payload = {"chat_id": chat_id, "text": text, "parse_mode": "HTML"}
    if reply_markup:
        payload["reply_markup"] = reply_markup
    telegram_api(token, "sendMessage", payload)
    return True


def send_widget(
    token: str,
    chat_id,
    *,
    html: str,
    chat_data: str | None = None,
    public_data: str | None = None,
    caption: str | None = None,
    allow_queries: bool = False,
    reply_markup: dict | None = None,
    api=telegram_api,
) -> dict:
    """Bot API 10.4 sendWidget. מעלה TelegramError אם השרת לא תומך."""
    payload: dict = {"chat_id": chat_id, "html": html}
    if chat_data is not None:
        payload["chat_data"] = chat_data
    if public_data is not None:
        payload["public_data"] = public_data
    if caption:
        payload["caption"] = caption
        payload["parse_mode"] = "HTML"
    if allow_queries:
        payload["allow_queries"] = True
    if reply_markup:
        payload["reply_markup"] = reply_markup
    return api(token, "sendWidget", payload)


def edit_message_widget_data(
    token: str,
    *,
    chat_id=None,
    message_id: int | None = None,
    inline_message_id: str | None = None,
    chat_data: str | None = None,
    public_data: str | None = None,
    api=telegram_api,
) -> bool:
    payload: dict = {}
    if inline_message_id:
        payload["inline_message_id"] = inline_message_id
    else:
        payload["chat_id"] = chat_id
        payload["message_id"] = message_id
    if chat_data is not None:
        payload["chat_data"] = chat_data
    if public_data is not None:
        payload["public_data"] = public_data
    api(token, "editMessageWidgetData", payload)
    return True


def answer_widget_query(token: str, widget_query_id: str, *, api=telegram_api) -> bool:
    api(token, "answerWidgetQuery", {"widget_query_id": widget_query_id})
    return True


CALLBACK_ACK = "פותח…"


def callback_id_of(update: dict) -> str | None:
    query = update.get("callback_query") if isinstance(update, dict) else None
    if not isinstance(query, dict):
        return None
    callback_id = query.get("id")
    if not callback_id:
        return None
    return str(callback_id)


def ack_callback(token: str, api, callback_id: str) -> bool:
    """עוצר את שעון החול על הכפתור לפני כל עבודה על היומן."""
    try:
        api(
            token,
            "answerCallbackQuery",
            {"callback_query_id": callback_id, "text": CALLBACK_ACK},
        )
    except TelegramError as exc:
        print(f"answerCallbackQuery failed: {exc}", file=sys.stderr)
        return False
    return True


def deliver_outgoing(token: str, api, outgoing: dict) -> None:
    """שולח תשובה אחת. עריכת הודעה נכשלת? נשלחת הודעה חדשה.

    ``widget``: מילון ל-sendWidget. אם נכשל - נופלים ל-``text`` אם יש.
    ``widget_edit``: chat_data/public_data ל-editMessageWidgetData.
    ``widget_query_id``: answerWidgetQuery.
    """
    callback_id = outgoing.get("callback_id")
    if callback_id:
        payload = {"callback_query_id": callback_id}
        toast = (outgoing.get("toast") or "").strip()
        if toast:
            payload["text"] = toast[:200]
        try:
            api(token, "answerCallbackQuery", payload)
        except TelegramError as exc:
            print(f"answerCallbackQuery failed: {exc}", file=sys.stderr)

    widget_query_id = outgoing.get("widget_query_id")
    if widget_query_id:
        try:
            answer_widget_query(token, str(widget_query_id), api=api)
        except TelegramError as exc:
            print(f"answerWidgetQuery failed: {exc}", file=sys.stderr)

    widget_edit = outgoing.get("widget_edit")
    if isinstance(widget_edit, dict):
        try:
            edit_message_widget_data(
                token,
                chat_id=outgoing.get("chat_id"),
                message_id=widget_edit.get("message_id") or outgoing.get("edit_id"),
                inline_message_id=widget_edit.get("inline_message_id"),
                chat_data=widget_edit.get("chat_data"),
                public_data=widget_edit.get("public_data"),
                api=api,
            )
        except TelegramError as exc:
            print(f"editMessageWidgetData failed: {exc}", file=sys.stderr)

    if outgoing.get("skip"):
        return

    widget = outgoing.get("widget")
    if isinstance(widget, dict) and widget.get("html"):
        try:
            send_widget(
                token,
                outgoing["chat_id"],
                html=widget["html"],
                chat_data=widget.get("chat_data"),
                public_data=widget.get("public_data"),
                caption=widget.get("caption"),
                allow_queries=bool(widget.get("allow_queries")),
                reply_markup=outgoing.get("markup"),
                api=api,
            )
            return
        except TelegramError as exc:
            print(f"sendWidget failed, falling back to text: {exc}", file=sys.stderr)
            if not outgoing.get("text"):
                return

    if not outgoing.get("text"):
        return
    body = {
        "chat_id": outgoing["chat_id"],
        "text": outgoing["text"],
        "parse_mode": "HTML",
    }
    if outgoing.get("markup"):
        body["reply_markup"] = outgoing["markup"]
    edit_id = outgoing.get("edit_id")
    if edit_id and not widget:
        edited = dict(body)
        edited["message_id"] = edit_id
        try:
            api(token, "editMessageText", edited)
            return
        except TelegramError as exc:
            if "not modified" in str(exc).lower():
                return
            print(f"editMessageText failed: {exc}", file=sys.stderr)
    api(token, "sendMessage", body)


def chat_id_reply(chat_id) -> str:
    """המזהה ב-<code> כדי שלחיצה עליו בטלגרם תעתיק (parse_mode HTML)."""
    safe_id = html.escape(str(chat_id), quote=False)
    return (
        f"מזהה הצ'אט שלך: <code>{safe_id}</code>\n"
        "שולחים /start, מעתיקים את המספר, "
        "מדביקים בהגדרות → משתמשים בשדה מזהה צ׳אט של האדם, ושומרים."
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
    """קורא עדכונים, מפעיל את תפריט הבוט, ומחזיר את ה-offset הבא."""
    payload = {
        "timeout": int(long_poll),
        "allowed_updates": ["message", "callback_query", "widget_query"],
    }
    if offset is not None:
        payload["offset"] = offset
    timeout = max(10, int(long_poll) + 10)
    updates = api(token, "getUpdates", payload, timeout=timeout) or []
    next_offset = offset
    if not updates:
        return next_offset
    # התשובה לכפתור יוצאת לפני פתיחת בסיס הנתונים, כדי שהשעון ייעצר מיד.
    acked: set[str] = set()
    for update in updates:
        update_id = update.get("update_id")
        if isinstance(update_id, int):
            next_offset = update_id + 1
        callback_id = callback_id_of(update)
        if callback_id and ack_callback(token, api, callback_id):
            acked.add(callback_id)
    from app import app as flask_app
    from app.bot.dispatch import handle_update

    with flask_app.app_context():
        for update in updates:
            try:
                outgoing = handle_update(update)
            except Exception as exc:
                print(f"bot update failed: {exc}", file=sys.stderr)
                continue
            if not outgoing or outgoing.get("skip"):
                continue
            if outgoing.get("callback_id") in acked:
                outgoing = dict(outgoing)
                outgoing["callback_id"] = None
            try:
                deliver_outgoing(token, api, outgoing)
            except TelegramError as exc:
                print(f"bot send failed: {exc}", file=sys.stderr)
    return next_offset
