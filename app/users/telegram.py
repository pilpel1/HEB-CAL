"""הודעות קישור וניתוק טלגרם."""
from __future__ import annotations

DIGEST_REQUIRES_TELEGRAM = "סיכום בוקר דורש חיבור לטלגרם"
UNLINK_HINT = "דורש חיבור לטלגרם"
UNLINK_CONFIRM_CONSEQUENCES = (
    "סיכום הבוקר ייכבה ותזכורות לא יגיעו בטלגרם (רק בדפדפן)."
)


def person_has_telegram(person: dict | None) -> bool:
    if not person:
        return False
    return bool(str(person.get("telegram_chat_id") or "").strip())


def unlink_telegram_confirm(name: str) -> str:
    """אישור לפני ניתוק צ׳אט: סיכום נכבה, תזכורות נשארות בדפדפן."""
    who = (name or "").strip() or "האדם"
    return f"בטוח שרוצים לנתק את הטלגרם של {who}? {UNLINK_CONFIRM_CONSEQUENCES}"


def unlink_telegram_confirm_people(people: list[dict]) -> str:
    names = [(person.get("name") or "").strip() or "האדם" for person in people]
    if not names:
        who = "האדם"
    elif len(names) == 1:
        who = names[0]
    elif len(names) == 2:
        who = f"{names[0]} ו{names[1]}"
    else:
        who = ", ".join(names[:-1]) + f" ו{names[-1]}"
    return unlink_telegram_confirm(who)
