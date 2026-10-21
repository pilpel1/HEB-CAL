"""אנשים לתזכורות + תזכורות שהדפדפן צריך להציג."""
from flask import jsonify, request

from app.reminders.due import browser_due
from app.reminders.repository import (
    create_person,
    delete_person,
    get_person,
    list_people,
    update_person,
)
from app.reminders.schedule import reminder_timezone

from . import api


def _payload():
    return request.get_json(silent=True) or {}


def _person_error(exc: ValueError):
    return jsonify({"error": str(exc), "success": False}), 400


@api.route("/reminder-people", methods=["GET"])
def get_reminder_people():
    return jsonify(list_people())


@api.route("/reminder-people", methods=["POST"])
def add_reminder_person():
    data = _payload()
    try:
        person = create_person(data.get("name"), data.get("telegram_chat_id"))
    except ValueError as exc:
        return _person_error(exc)
    return jsonify(person), 201


@api.route("/reminder-people/<int:person_id>", methods=["PUT"])
def edit_reminder_person(person_id):
    data = _payload()
    try:
        person = update_person(person_id, data.get("name"), data.get("telegram_chat_id"))
    except ValueError as exc:
        return _person_error(exc)
    if person is None:
        return jsonify({"error": "האדם לא נמצא", "success": False}), 404
    return jsonify(person)


@api.route("/reminder-people/<int:person_id>", methods=["DELETE"])
def remove_reminder_person(person_id):
    if not delete_person(person_id):
        return jsonify({"error": "האדם לא נמצא", "success": False}), 404
    return jsonify({"success": True})


@api.route("/reminders/due", methods=["GET"])
def get_due_reminders():
    """תזכורות לחלון הקרוב. הדפדפן הפתוח מציג אותן דרך Notification API.

    אותו אובייקט (title, body, tag) הוא מה ש-Web Push ישלח אחר כך. השדה
    ``push`` מסמן שהערוץ הזה עדיין לא פעיל — חסר HTTPS ו-service worker.
    """
    try:
        within = int(request.args.get("within_seconds", 90))
    except (TypeError, ValueError):
        within = 90
    try:
        grace = int(request.args.get("grace_seconds", 900))
    except (TypeError, ValueError):
        grace = 900

    now_local = reminder_timezone()
    from datetime import datetime

    return jsonify({
        "server_now": datetime.now(now_local).isoformat(),
        "reminders": browser_due(within_seconds=within, grace_seconds=grace),
        "push": {
            "supported": False,
            "reason": "Web Push needs HTTPS and a service worker (planned).",
        },
    })
