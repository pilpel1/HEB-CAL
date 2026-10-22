from flask import jsonify, request

from . import api
from app.services.colors import (
    ColorError,
    create_color,
    delete_color,
    get_color,
    list_colors,
    update_color,
)


def _payload():
    return request.get_json(silent=True) or {}


def _color_error(exc: ColorError, status=400):
    return jsonify({"error": str(exc), "success": False}), status


@api.route("/colors", methods=["GET"])
def get_colors():
    return jsonify(list_colors())


@api.route("/colors", methods=["POST"])
def add_color():
    data = _payload()
    try:
        created = create_color(data.get("name"), data.get("color_code"))
    except ColorError as exc:
        return _color_error(exc)
    return jsonify(created), 201


@api.route("/colors/<int:color_id>", methods=["GET"])
def get_one_color(color_id):
    color = get_color(color_id)
    if color is None:
        return jsonify({"error": "הצבע לא נמצא", "success": False}), 404
    return jsonify(color)


@api.route("/colors/<int:color_id>", methods=["PUT"])
def edit_color(color_id):
    data = _payload()
    try:
        updated = update_color(color_id, data.get("name"), data.get("color_code"))
    except ColorError as exc:
        status = 404 if str(exc) == "הצבע לא נמצא" else 400
        return _color_error(exc, status)
    return jsonify(updated)


@api.route("/colors/<int:color_id>", methods=["DELETE"])
def remove_color(color_id):
    try:
        delete_color(color_id)
    except ColorError as exc:
        status = 404 if str(exc) == "הצבע לא נמצא" else 400
        return _color_error(exc, status)
    return jsonify({"success": True})
