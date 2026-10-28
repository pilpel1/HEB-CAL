"""פקודות ש-on_command באמת מטפל בהן. אותו סדר מוצג בתפריט של טלגרם.

בלי language_code: כל הממשק עברי, גם למי שהשפה בטלגרם אינה עברית.
BotFather כותב לאותה רשימה; ה-worker קורא ל-setMyCommands בהפעלה כדי שלא יישאר פער אחרי דיפלוי.
"""
from __future__ import annotations

BOT_COMMANDS: tuple[tuple[str, str], ...] = (
    ("start", "תפריט ראשי"),
    ("today", "אירועי היום"),
    ("week", "אירועי השבוע"),
    ("add", "הוספת אירוע"),
    ("find", "חיפוש אירוע"),
    ("settings", "הגדרות"),
    ("digest", "סיכום בוקר — הפעלה/כיבוי"),
    ("help", "תפריט ראשי"),
    ("menu", "תפריט ראשי"),
)


def command_menu_payload() -> dict:
    return {
        "commands": [
            {"command": name, "description": description}
            for name, description in BOT_COMMANDS
        ]
    }
