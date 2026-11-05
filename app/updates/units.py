"""כתיבת יחידות systemd --user אחרי checkout, וגיבוי שלהן לחזרה לאחור.

אין פורט חדש: רק התבניות של המופע הקיים (data/instance.env).
"""
from __future__ import annotations

import os
import shutil
from pathlib import Path

from app.updates.errors import UpdateError
from app.updates.gitops import run_argv
from app.updates.systemd import (
    instance_name,
    systemd_user_env,
    systemd_user_units_installed,
    unit_filenames,
    user_units_dir,
)

UNIT_BACKUP_DIRNAME = "unit-backup"


def socket_filename(repo_root: Path | None = None) -> str:
    from app.updates.systemd import _select

    return _select().socket_unit_name(instance_name(repo_root))


def instance_unit_names(repo_root: Path | None = None) -> tuple[str, str, str]:
    web, worker = unit_filenames(repo_root)
    return web, worker, socket_filename(repo_root)


def backup_instance_units(repo_root: Path, dest_dir: Path) -> Path | None:
    """עותק של יחידות המופע הזה. None אם אין מה לגבות."""
    base = user_units_dir()
    copied = False
    dest_dir.mkdir(parents=True, exist_ok=True)
    for name in instance_unit_names(repo_root):
        src = base / name
        if not src.is_file():
            continue
        shutil.copy2(src, dest_dir / name)
        os.chmod(dest_dir / name, 0o644)
        copied = True
    return dest_dir if copied else None


def restore_instance_units(repo_root: Path, backup_dir: Path | None) -> None:
    """מחזיר יחידות מהגיבוי, ומוחק socket שנוסף ולא היה קודם.

    בשדרוג הראשון ל-socket: עוצרים web+worker (חוסם) *לפני* הסוקט, אחר כך
    משחזרים את קבצי היחידה הישנים. בלי זה ה-fd נשאר אצל התהליך החדש, הסוקט
    מנותק ב-systemd, ו-flask הישן נכשל ב-EADDRINUSE אחרי daemon-reload.
    """
    base = user_units_dir()
    web_name, worker_name, socket_name = instance_unit_names(repo_root)
    names = (web_name, worker_name, socket_name)
    backed: dict[str, Path] = {}
    has_backup = backup_dir is not None and Path(backup_dir).is_dir()
    if has_backup:
        for path in Path(backup_dir).iterdir():
            if path.is_file() and path.name in names:
                backed[path.name] = path
    extra = base / socket_name
    drop_socket = socket_name not in backed
    if drop_socket:
        if not has_backup and not extra.is_file() and not systemd_user_units_installed(repo_root):
            return
        env = systemd_user_env()
        _systemctl_user(repo_root, env, ["stop", web_name, worker_name])
        _systemctl_user(repo_root, env, ["stop", socket_name])
        _systemctl_user(repo_root, env, ["disable", socket_name])
        if extra.is_file():
            extra.unlink()
    if has_backup:
        base.mkdir(parents=True, exist_ok=True)
        for name, path in backed.items():
            shutil.copy2(path, base / name)
    if has_backup or drop_socket or systemd_user_units_installed(repo_root):
        _daemon_reload(repo_root)


def _systemctl_user(repo_root: Path, env: dict, args: list[str]) -> None:
    try:
        run_argv(["systemctl", "--user", *args], cwd=repo_root, env=env, timeout=30)
    except UpdateError:
        pass


def install_runtime_units(repo_root: Path, backup_dir: Path) -> Path | None:
    """גיבוי, ואז install_services.sh --units-only. None אם אין יחידות למופע הזה."""
    if not systemd_user_units_installed(repo_root):
        return None
    saved = backup_instance_units(repo_root, backup_dir)
    script = Path(repo_root) / "scripts" / "install_services.sh"
    if not script.is_file():
        raise UpdateError("סקריפט התקנת היחידות חסר.", step="units")
    env = systemd_user_env()
    env["HEB_CAL_SKIP_LINGER"] = "1"
    env["HEB_CAL_INSTANCE_NAME"] = instance_name(repo_root)
    proc = run_argv(
        ["bash", str(script), "--units-only"],
        cwd=repo_root,
        env=env,
        timeout=60,
    )
    if proc.returncode != 0:
        raise UpdateError("עדכון יחידות systemd נכשל.", step="units")
    return saved


def _daemon_reload(repo_root: Path) -> None:
    proc = run_argv(
        ["systemctl", "--user", "daemon-reload"],
        cwd=repo_root,
        env=systemd_user_env(),
        timeout=30,
    )
    if proc.returncode != 0:
        raise UpdateError("לא הצלחנו לרענן את systemd.", step="rollback")
