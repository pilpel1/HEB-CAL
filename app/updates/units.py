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
    """מחזיר יחידות מהגיבוי, ומוחק socket שנוסף ולא היה קודם."""
    base = user_units_dir()
    names = instance_unit_names(repo_root)
    backed = set()
    has_backup = backup_dir is not None and Path(backup_dir).is_dir()
    if has_backup:
        base.mkdir(parents=True, exist_ok=True)
        for path in Path(backup_dir).iterdir():
            if not path.is_file() or path.name not in names:
                continue
            shutil.copy2(path, base / path.name)
            backed.add(path.name)
    socket_name = socket_filename(repo_root)
    extra = base / socket_name
    dropped_socket = False
    if socket_name not in backed:
        if not has_backup and not extra.is_file() and not systemd_user_units_installed(repo_root):
            return
        env = systemd_user_env()
        for argv in (
            ["systemctl", "--user", "--no-block", "stop", socket_name],
            ["systemctl", "--user", "disable", socket_name],
        ):
            try:
                run_argv(argv, cwd=repo_root, env=env, timeout=30)
            except UpdateError:
                pass
        if extra.is_file():
            extra.unlink()
            dropped_socket = True
    if has_backup or dropped_socket or systemd_user_units_installed(repo_root):
        _daemon_reload(repo_root)


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
