"""בוט טלגרם בלי מודל שפה: תפריט, רשימות, ו-CRUD על היומן.

הטוקן נשאר ב-``TELEGRAM_BOT_TOKEN``. כאן רק החלטה מה לענות.
"""

from app.bot.dispatch import handle_update

__all__ = ["handle_update"]
