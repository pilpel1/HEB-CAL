"""יחידות systemd --user של HEB-CAL. בלי סודות ובלי sudo."""
from __future__ import annotations

import os
from pathlib import Path

WEB_UNIT = "heb-cal-web.service"
WORKER_UNIT = "heb-cal-worker.service"
UNITS = (WEB_UNIT, WORKER_UNIT)


def user_units_dir(home: Path | None = None) -> Path:
    override = (os.environ.get("HEB_CAL_UNIT_DIR") or "").strip()
    if override:
        return Path(override)
    return Path(home or Path.home()) / ".config" / "systemd" / "user"


def systemd_user_units_installed(
    repo_root: Path | None = None,
    *,
    home: Path | None = None,
) -> bool:
    """True אם שני קבצי היחידה קיימים, ומצביעים לריפו הזה כש-repo_root נמסר."""
    base = user_units_dir(home)
    root = str(Path(repo_root).resolve()) if repo_root is not None else None
    for name in UNITS:
        path = base / name
        if not path.is_file():
            return False
        if root is None:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            return False
        if root not in text:
            return False
    return True


def systemd_user_env(base: dict | None = None) -> dict[str, str]:
    env = {key: str(value) for key, value in dict(base or os.environ).items()}
    if not (env.get("XDG_RUNTIME_DIR") or "").strip():
        runtime = f"/run/user/{os.getuid()}"
        if os.path.isdir(runtime):
            env["XDG_RUNTIME_DIR"] = runtime
    return env


def bundled_restart_script(repo_root: Path) -> Path:
    return Path(repo_root) / "scripts" / "restart.sh"
