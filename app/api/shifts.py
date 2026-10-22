"""מתג משמרות לבית, ורשת שבוע לאדם."""
from flask import jsonify, request

from app.reminders.repository import get_person
from app.services.shifts import (
    ShiftError,
    default_week_start,
    parse_week_start,
    save_shift_week,
    set_shifts_enabled,
    shifts_enabled,
    validate_shift_week,
    week_view,
)

from . import api


def _payload():
    return request.get_json(silent=True) or {}


def _shift_error(exc: ShiftError):
    return jsonify({"error": str(exc), "success": False}), 400


def _as_bool(value):
    if isinstance(value, bool):
        return value
    if value in (0, 1):
        return bool(value)
    return None


@api.route("/shifts/settings", methods=["GET"])
def get_shift_settings():
    return jsonify({"enabled": shifts_enabled()})


@api.route("/shifts/settings", methods=["PUT"])
def put_shift_settings():
    data = _payload()
    if "enabled" not in data:
        return jsonify({"error": "חסר enabled", "success": False}), 400
    enabled = _as_bool(data.get("enabled"))
    if enabled is None:
        return jsonify({"error": "enabled חייב להיות true או false", "success": False}), 400
    return jsonify({"enabled": set_shifts_enabled(enabled), "success": True})


def _person_or_404(person_id):
    try:
        person_id = int(person_id)
    except (TypeError, ValueError):
        return None, (jsonify({"error": "חסר אדם", "success": False}), 400)
    person = get_person(person_id)
    if person is None:
        return None, (jsonify({"error": "האדם לא נמצא", "success": False}), 404)
    return person, None


@api.route("/shifts/week", methods=["GET"])
def get_shift_week():
    person, error = _person_or_404(request.args.get("person_id"))
    if error:
        return error
    raw_week = (request.args.get("week_start") or "").strip()
    try:
        start = parse_week_start(raw_week) if raw_week else default_week_start()
    except ShiftError as exc:
        return _shift_error(exc)
    return jsonify(week_view(person, start))


@api.route("/shifts/week", methods=["PUT"])
def put_shift_week():
    data = _payload()
    person, error = _person_or_404(data.get("person_id"))
    if error:
        return error
    if not shifts_enabled():
        return jsonify({"error": "המשמרות כבויות בבית הזה", "success": False}), 400
    try:
        start = parse_week_start(data.get("week_start"))
        validate_shift_week(person, start, data.get("cells"))
        result = save_shift_week(person, start, data.get("cells"))
    except ShiftError as exc:
        return _shift_error(exc)
    return jsonify(result)
