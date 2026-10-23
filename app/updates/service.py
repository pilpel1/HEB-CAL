"""בדיקה והתחלת עדכון. התהליך שנפתח כאן נפרד, כדי שישרוד את ההפעלה מחדש."""
from __future__ import annotations

import subprocess
import sys
import threading
from datetime import datetime, timezone
from pathlib import Path

from app.database import BASE_DIR
from app.updates.envconfig import describe_mode, load_config
from app.updates.errors import UpdateError
from app.updates.gitops import assert_not_shallow, assert_worktree_clean, is_git_checkout, run_argv
from app.updates.github_api import fetch_latest, release_view
from app.updates.store import (
    acquire_lock,
    blank_status,
    cache_is_stale,
    cache_path,
    mark_lock_pid,
    public_status,
    read_json,
    release_lock,
    status_is_active,
    status_path,
    write_cache,
    write_status,
)
from app.updates.version import installed_version, is_newer, parse_version, read_version_file, tag_matches_version, validate_tag

_HINTS = {
    "git": "העדכון מוריד תג מ-GitHub, מגבה את הנתונים, ומפעיל מחדש.",
    "docker": "בהתקנת Docker לא מעדכנים מתוך המסך.",
    "hook": "העדכון מריץ סקריפט קבוע מההגדרות, אחרי גיבוי.",
    "off": "העדכון מהממשק כבוי.",
}

_autocheck_lock = threading.Lock()
_autocheck_running = False


def _testing() -> bool:
    try:
        from flask import current_app, has_app_context
    except ImportError:
        return False
    return has_app_context() and bool(current_app.config.get("TESTING"))


def _public_cache(payload: dict | None, current: str) -> dict | None:
    if not payload:
        return None
    latest = payload.get("latest")
    available = isinstance(latest, str) and current != "לא ידועה" and is_newer(latest, current)
    highlights = payload.get("highlights") if isinstance(payload.get("highlights"), list) else []
    return {
        "available": available,
        "latest": latest if isinstance(latest, str) else None,
        "highlights": [str(line)[:180] for line in highlights[:6]],
        "url": payload.get("url") if isinstance(payload.get("url"), str) else None,
        "checked_at": payload.get("checked_at"),
        "message": payload.get("message"),
        "error": payload.get("error"),
    }


def read_public_status() -> dict:
    cfg = load_config()
    current = installed_version()
    path = status_path(cfg.update_dir)
    payload = read_json(path)
    if payload and payload.get("state") == "running" and not status_is_active(payload):
        payload = write_status(path, {
            **payload,
            "state": "failed",
            "step": "error",
            "message": "תהליך העדכון נעצר באמצע. הגיבוי, אם נשמר, נמצא בתיקיית backups.",
            "error": "תהליך העדכון נעצר באמצע. הגיבוי, אם נשמר, נמצא בתיקיית backups.",
            "finished_at": datetime.now(timezone.utc).isoformat(),
        })
        release_lock(cfg.update_dir)
    return public_status(payload, current)


def summary() -> dict:
    from app.updates.security import is_admin, issue_csrf

    cfg = load_config()
    current = installed_version()
    info = describe_mode(cfg, git_checkout=is_git_checkout(cfg.repo_root))
    return {
        "current": current,
        "mode": cfg.mode,
        "admin": is_admin(),
        "admin_configured": bool(cfg.admin_password),
        "csrf_token": issue_csrf(),
        "restart_configured": bool(cfg.restart_command),
        "hook_configured": bool(cfg.hook_path) and not cfg.hook_error,
        "can_apply": info["can_apply"],
        "block": info["block"],
        "instructions": info["instructions"],
        "docker_command": info["docker_command"],
        "hint": _HINTS.get(cfg.mode, ""),
        "cached": _public_cache(read_json(cache_path(cfg.update_dir)), current),
        "status": read_public_status(),
    }


def badge() -> dict:
    schedule_autocheck()
    cfg = load_config()
    current = installed_version()
    cached = _public_cache(read_json(cache_path(cfg.update_dir)), current) or {}
    return {
        "available": bool(cached.get("available")),
        "current": current,
        "latest": cached.get("latest"),
    }


def check_for_updates(fetcher=None) -> dict:
    cfg = load_config()
    current = read_version_file()
    fetch = fetcher or (lambda: fetch_latest(cfg.repo, cfg.token))
    path = cache_path(cfg.update_dir)
    try:
        release = fetch()
    except UpdateError as exc:
        write_cache(path, {
            "ok": False,
            "current": current,
            "available": False,
            "latest": None,
            "highlights": [],
            "url": None,
            "message": exc.message,
            "error": exc.message,
        })
        raise
    view = release_view(release, current)
    view["ok"] = True
    view["error"] = None
    saved = write_cache(path, view)
    view["checked_at"] = saved.get("checked_at")
    return view


def schedule_autocheck() -> None:
    global _autocheck_running
    if _testing():
        return
    cfg = load_config()
    if not cfg.autocheck:
        return
    if not cache_is_stale(read_json(cache_path(cfg.update_dir))):
        return
    with _autocheck_lock:
        if _autocheck_running:
            return
        _autocheck_running = True

    def _run() -> None:
        global _autocheck_running
        try:
            check_for_updates()
        except Exception:
            return
        finally:
            with _autocheck_lock:
                _autocheck_running = False

    threading.Thread(target=_run, name="heb-cal-update-check", daemon=True).start()


def spawn_updater(version: str, tag: str, mode: str, status_file: Path) -> int:
    """פותח תהליך מנותק. הארגומנטים הם רק גרסה, תג, ומצב — לא פקודה מהבקשה."""
    validate_tag(tag)
    if mode not in {"git", "hook"}:
        raise UpdateError("מצב עדכון לא תקין.", step="start")
    if not tag_matches_version(tag, version):
        raise UpdateError("תג הגרסה לא תקין.", step="start")
    command = [
        sys.executable,
        "-m",
        "app.updates.runner",
        "--target",
        version,
        "--tag",
        tag,
        "--mode",
        mode,
        "--status",
        str(status_file),
    ]
    log_path = status_file.parent / "update-runner.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    handle = open(log_path, "ab")
    try:
        proc = subprocess.Popen(
            command,
            cwd=str(BASE_DIR),
            start_new_session=True,
            stdin=subprocess.DEVNULL,
            stdout=handle,
            stderr=subprocess.STDOUT,
            close_fds=True,
            shell=False,
        )
    except OSError as exc:
        raise UpdateError("לא הצלחנו להתחיל את תהליך העדכון.", step="start") from exc
    finally:
        handle.close()
    return proc.pid


def start_apply(requested_version, *, spawner=None) -> dict:
    cfg = load_config()
    info = describe_mode(cfg, git_checkout=is_git_checkout(cfg.repo_root))
    if not info["can_apply"]:
        raise UpdateError(
            info["block"] or info["instructions"] or "אי אפשר לעדכן מהממשק במצב הזה.",
            step="start",
        )
    if cfg.mode == "git":
        def _run(args):
            return run_argv(args, cwd=cfg.repo_root, timeout=15)

        assert_not_shallow(_run)
        assert_worktree_clean(_run)
    release = fetch_latest(cfg.repo, cfg.token)
    if release is None:
        raise UpdateError("לא נמצאה גרסה ב-GitHub.", step="fetch")
    current = read_version_file()
    if not is_newer(release.version, current):
        raise UpdateError("אתם על הגרסה האחרונה.", step="version")
    if requested_version not in (None, ""):
        if not isinstance(requested_version, str) or parse_version(requested_version) != parse_version(release.version):
            raise UpdateError("אפשר לעדכן רק לגרסה שמפורסמת ב-GitHub.", step="version")
    mode = "hook" if cfg.mode in {"hook", "docker"} else "git"
    path = status_path(cfg.update_dir)
    if status_is_active(read_json(path)):
        raise UpdateError("עדכון כבר רץ.", step="busy")
    acquire_lock(cfg.update_dir)
    try:
        write_status(path, {
            **blank_status(current),
            "state": "running",
            "step": "start",
            "message": "מתחילים את העדכון",
            "target": release.version,
            "started_at": datetime.now(timezone.utc).isoformat(),
        })
        spawn = spawner or spawn_updater
        pid = spawn(release.version, release.tag, mode, path)
        mark_lock_pid(cfg.update_dir, pid)
    except Exception:
        release_lock(cfg.update_dir)
        write_status(path, {
            **blank_status(current),
            "state": "failed",
            "step": "start",
            "message": "לא הצלחנו להתחיל את העדכון.",
            "error": "לא הצלחנו להתחיל את העדכון.",
            "finished_at": datetime.now(timezone.utc).isoformat(),
        })
        raise
    return {
        "started": True,
        "target": release.version,
        "message": "העדכון התחיל. אפשר להשאיר את העמוד פתוח.",
    }
