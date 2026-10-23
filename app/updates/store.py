"""מצב העדכון על הדיסק, כדי שהמסך ימשיך לעקוב אחרי שהאפליקציה עולה מחדש."""
from __future__ import annotations

import json
import os
import shutil
from datetime import datetime, timedelta, timezone
from pathlib import Path

from app.updates.errors import redact

PUBLIC_STATUS_KEYS = ("state", "step", "message", "target", "current", "error", "started_at", "finished_at", "lines")
_LOCK_NAME = "update.lockdir"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def status_path(update_dir: Path) -> Path:
    return update_dir / "update-status.json"


def cache_path(update_dir: Path) -> Path:
    return update_dir / "update-check.json"


def _atomic_write(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, path)


def read_json(path: Path) -> dict | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def blank_status(current: str) -> dict:
    return {
        "state": "idle",
        "step": "",
        "message": "",
        "target": None,
        "current": current,
        "error": None,
        "started_at": None,
        "finished_at": None,
        "lines": [],
        "pid": None,
    }


def public_status(payload: dict | None, current: str) -> dict:
    source = payload or blank_status(current)
    view = {}
    for key in PUBLIC_STATUS_KEYS:
        view[key] = source.get(key)
    lines = view.get("lines") or []
    if not isinstance(lines, list):
        lines = []
    view["lines"] = [redact(str(line))[:180] for line in lines[-8:]]
    if isinstance(view.get("message"), str):
        view["message"] = redact(view["message"])[:240]
    if isinstance(view.get("error"), str):
        view["error"] = redact(view["error"])[:240]
    view["state"] = view.get("state") or "idle"
    return view


def write_status(path: Path, payload: dict) -> dict:
    current = dict(payload)
    for secret_key in ("token", "password", "authorization", "secret", "csrf_token"):
        current.pop(secret_key, None)
    message = current.get("message")
    if isinstance(message, str) and message:
        lines = list(current.get("lines") or [])
        if not lines or lines[-1] != message:
            lines.append(message)
        current["lines"] = [redact(str(line))[:180] for line in lines[-12:]]
        current["message"] = redact(message)[:240]
    if isinstance(current.get("error"), str):
        current["error"] = redact(current["error"])[:240]
    _atomic_write(path, current)
    return current


def cache_is_stale(payload: dict | None, now: datetime | None = None, hours: int = 24) -> bool:
    if not payload or not payload.get("checked_at"):
        return True
    try:
        checked = datetime.fromisoformat(str(payload["checked_at"]))
    except ValueError:
        return True
    if checked.tzinfo is None:
        checked = checked.replace(tzinfo=timezone.utc)
    moment = now or datetime.now(timezone.utc)
    return moment - checked >= timedelta(hours=hours)


def write_cache(path: Path, payload: dict) -> dict:
    body = dict(payload)
    body["checked_at"] = body.get("checked_at") or _now()
    # המטמון לא שומר טוקן גם אם מישהו דחף בטעות.
    body.pop("token", None)
    body.pop("password", None)
    if isinstance(body.get("error"), str):
        body["error"] = redact(body["error"])
    _atomic_write(path, body)
    return body


def _pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def lock_dir(update_dir: Path) -> Path:
    return update_dir / _LOCK_NAME


def _lock_stale(path: Path) -> bool:
    pid_file = path / "pid"
    try:
        age = datetime.now(timezone.utc).timestamp() - path.stat().st_mtime
    except OSError:
        return True
    if pid_file.is_file():
        try:
            pid = int(pid_file.read_text(encoding="utf-8").strip())
        except (OSError, ValueError):
            return age > 30
        return not _pid_alive(pid)
    return age > 30


def acquire_lock(update_dir: Path) -> None:
    from app.updates.errors import UpdateError

    path = lock_dir(update_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        path.mkdir()
    except FileExistsError:
        if not _lock_stale(path):
            raise UpdateError("עדכון כבר רץ.", step="busy")
        shutil.rmtree(path, ignore_errors=True)
        try:
            path.mkdir()
        except FileExistsError as exc:
            raise UpdateError("עדכון כבר רץ.", step="busy") from exc


def mark_lock_pid(update_dir: Path, pid: int) -> None:
    pid_file = lock_dir(update_dir) / "pid"
    try:
        pid_file.write_text(str(int(pid)), encoding="utf-8")
    except OSError:
        return


def release_lock(update_dir: Path) -> None:
    shutil.rmtree(lock_dir(update_dir), ignore_errors=True)


def status_is_active(payload: dict | None) -> bool:
    if not payload or payload.get("state") != "running":
        return False
    pid = payload.get("pid")
    if isinstance(pid, int) or (isinstance(pid, str) and str(pid).isdigit()):
        return _pid_alive(int(pid))
    started = payload.get("started_at")
    if not isinstance(started, str):
        return True
    try:
        moment = datetime.fromisoformat(started)
    except ValueError:
        return False
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return datetime.now(timezone.utc) - moment < timedelta(seconds=30)
