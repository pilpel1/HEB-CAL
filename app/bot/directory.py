"""קישור צ'אט לאדם. אותו שדה ``telegram_chat_id`` שהאתר כבר שומר."""
from __future__ import annotations

from app.reminders.repository import create_person, get_person, list_people, update_person


def people_for_chat(chat_id) -> list[dict]:
    cid = str(chat_id)
    return [person for person in list_people() if (person.get("telegram_chat_id") or "") == cid]


def link_status(person_id: int, chat_id) -> dict | None:
    person = get_person(person_id)
    if person is None:
        return None
    cid = str(chat_id)
    others = [
        other
        for other in people_for_chat(cid)
        if other["id"] != person["id"]
    ]
    current = person.get("telegram_chat_id") or ""
    return {
        "person": person,
        "others": others,
        "already": current == cid,
        "replaces": bool(current) and current != cid,
        "old_chat": current or None,
    }


def link_person(person_id: int, chat_id, *, exclusive: bool) -> dict | None:
    person = get_person(person_id)
    if person is None:
        return None
    cid = str(chat_id)
    if exclusive:
        for other in people_for_chat(cid):
            if other["id"] != person_id:
                update_person(other["id"], other["name"], None)
    return update_person(person_id, person["name"], cid)


def unlink_person(person_id: int) -> dict | None:
    person = get_person(person_id)
    if person is None:
        return None
    return update_person(person_id, person["name"], None)


def set_works_shifts(person_id: int, enabled: bool) -> dict | None:
    person = get_person(person_id)
    if person is None:
        return None
    return update_person(
        person_id,
        person["name"],
        person.get("telegram_chat_id"),
        works_shifts=bool(enabled),
    )


def set_daily_digest(person_id: int, enabled: bool) -> dict | None:
    person = get_person(person_id)
    if person is None:
        return None
    return update_person(
        person_id,
        person["name"],
        person.get("telegram_chat_id"),
        daily_digest_enabled=bool(enabled),
    )


def add_linked_person(name: str, chat_id) -> dict:
    return create_person(name, str(chat_id))
