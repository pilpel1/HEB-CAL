"""הודעות קישור וניתוק טלגרם."""
from __future__ import annotations

DIGEST_REQUIRES_TELEGRAM = "סיכום בוקר דורש חיבור לטלגרם"
UNLINK_HINT = "דורש חיבור לטלגרם"


def person_has_telegram(person: dict | None) -> bool:
    if not person:
        return False
    return bool(str(person.get("telegram_chat_id") or "").strip())


def unlink_telegram_confirm(name: str, *, receives_reminders: bool = False, daily_digest_enabled: bool = False) -> str:
    """אישור לפני ניתוק צ׳אט. מזכיר אילו פיצ׳רים ייכבו."""
    who = (name or "").strip() or "האדם"
    features: list[str] = []
    if receives_reminders:
        features.append("תזכורות")
    if daily_digest_enabled:
        features.append("סיכום בוקר")
    question = f"בטוח שרוצים לנתק את הטלגרם של {who}?"
    if features:
        question += f" {' ו'.join(features)} ייכבו"
    return question


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
    return unlink_telegram_confirm(
        who,
        receives_reminders=any(person.get("receives_reminders") for person in people),
        daily_digest_enabled=any(person.get("daily_digest_enabled") for person in people),
    )
