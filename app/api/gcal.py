"""API לחיבור יומן גוגל. התשובות לא כוללות את הכתובת הסודית."""
from __future__ import annotations

from flask import jsonify, request

from app.api import api
from app.gcal.errors import GcalUserError
from app.gcal.repository import create_source, delete_source, list_sources, update_source
from app.gcal.sync import sync_enabled, sync_source


def _payload():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return None
    return data


def _error(exc: GcalUserError, status: int = 400):
    return jsonify({"error": str(exc), "success": False}), status


@api.route("/gcal/sources", methods=["GET"])
def gcal_list_sources():
    return jsonify(list_sources())


@api.route("/gcal/sources", methods=["POST"])
def gcal_create_source():
    data = _payload()
    if data is None:
        return jsonify({"error": "חסר גוף בקשה", "success": False}), 400
    try:
        saved = create_source(
            data.get("label"),
            data.get("ical_url"),
            data.get("color"),
            data.get("enabled", True),
        )
    except GcalUserError as exc:
        return _error(exc)
    if saved.get("enabled"):
        try:
            saved = sync_source(saved["id"])
        except GcalUserError as exc:
            return _error(exc)
    return jsonify(saved), 201


@api.route("/gcal/sources/<int:source_id>", methods=["PUT"])
def gcal_update_source(source_id):
    data = _payload()
    if data is None:
        return jsonify({"error": "חסר גוף בקשה", "success": False}), 400
    try:
        saved = update_source(source_id, data)
    except GcalUserError as exc:
        status = 404 if str(exc) == "החיבור לא נמצא" else 400
        return _error(exc, status)
    return jsonify(saved)


@api.route("/gcal/sources/<int:source_id>", methods=["DELETE"])
def gcal_delete_source(source_id):
    try:
        deleted = delete_source(source_id)
    except GcalUserError as exc:
        return _error(exc)
    if not deleted:
        return jsonify({"error": "החיבור לא נמצא", "success": False}), 404
    return jsonify({"success": True})


@api.route("/gcal/sources/<int:source_id>/sync", methods=["POST"])
def gcal_sync_one(source_id):
    try:
        saved = sync_source(source_id)
    except GcalUserError as exc:
        status = 404 if str(exc) == "החיבור לא נמצא" else 400
        return _error(exc, status)
    return jsonify(saved)


@api.route("/gcal/sync", methods=["POST"])
def gcal_sync_all():
    try:
        rows = sync_enabled()
    except GcalUserError as exc:
        return _error(exc)
    return jsonify(rows)
