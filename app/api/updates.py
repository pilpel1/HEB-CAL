"""נקודות העדכון. פקודת ההפעלה מחדש לא מתקבלת מהבקשה."""
from __future__ import annotations

from flask import jsonify, request

from app.api import api
from app.updates.config import load_config
from app.updates.errors import UpdateError
from app.updates.security import login_admin, logout_admin, require_admin, require_csrf
from app.updates.service import badge, check_for_updates, read_public_status, start_apply, summary
from app.updates.version import installed_version


def _json(payload: dict, code: int = 200):
    response = jsonify(payload)
    response.status_code = code
    response.headers["Cache-Control"] = "no-store"
    return response


def _guard_write():
    return require_csrf() or require_admin()


@api.route("/updates/health")
def updates_health():
    return _json({"ok": True, "version": installed_version()})


@api.route("/updates/badge")
def updates_badge():
    return _json(badge())


@api.route("/updates")
def updates_summary():
    return _json(summary())


@api.route("/updates/status")
def updates_status():
    denied = require_admin()
    if denied:
        return denied
    return _json(read_public_status())


@api.route("/updates/login", methods=["POST"])
def updates_login():
    denied = require_csrf()
    if denied:
        return denied
    body = request.get_json(silent=True) or {}
    password = body.get("password") if isinstance(body, dict) else ""
    if not isinstance(password, str):
        password = ""
    return login_admin(password, load_config().admin_password)


@api.route("/updates/logout", methods=["POST"])
def updates_logout():
    denied = _guard_write()
    if denied:
        return denied
    return logout_admin()


@api.route("/updates/check", methods=["POST"])
def updates_check():
    denied = _guard_write()
    if denied:
        return denied
    try:
        return _json(check_for_updates())
    except UpdateError as exc:
        return _json({"error": exc.message}, 400)


@api.route("/updates/apply", methods=["POST"])
def updates_apply():
    denied = _guard_write()
    if denied:
        return denied
    body = request.get_json(silent=True) or {}
    if not isinstance(body, dict):
        body = {}
    # רק המספר, ורק כדי לוודא שהוא זהה למה ש-GitHub פרסם. תג ופקודה מהבקשה לא נקראים.
    try:
        payload = start_apply(body.get("version"))
    except UpdateError as exc:
        code = 409 if exc.step == "busy" else 400
        return _json({"error": exc.message}, code)
    return _json(payload, 202)
