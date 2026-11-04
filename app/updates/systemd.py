"""יחידות systemd --user של HEB-CAL. בלי סודות ובלי sudo. שם המופע מ-data/instance.env."""
from __future__ import annotations

import importlib.util
import os
import sys
from functools import lru_cache
from pathlib import Path

DEFAULT_INSTANCE_NAME = "heb-cal"
DEFAULT_UNITS = ("heb-cal-web.service", "heb-cal-worker.service")
# תאימות: קוד ישן שמייבא UNITS מקבל את ברירת המחדל של המופע הראשון.
UNITS = DEFAULT_UNITS


@lru_cache(maxsize=1)
def _select():
    path = Path(__file__).resolve().parents[2] / "scripts" / "instance_select.py"
    spec = importlib.util.spec_from_file_location("_hebcal_instance_select", path)
    if spec is None or spec.loader is None:
        raise ImportError(f"לא נמצא {path}")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name or "_hebcal_instance_select"] = mod
    spec.loader.exec_module(mod)
    return mod


def user_units_dir(home: Path | None = None) -> Path:
    override = (os.environ.get("HEB_CAL_UNIT_DIR") or "").strip()
    if override:
        return Path(override)
    return Path(home or Path.home()) / ".config" / "systemd" / "user"


def instance_name(repo_root: Path | None = None) -> str:
    """שם המופע: משתנה סביבה, אחר כך data/instance.env, אחר כך יחידות עם WorkingDirectory הזה."""
    explicit = (os.environ.get("HEB_CAL_INSTANCE_NAME") or "").strip()
    select = _select()
    if select.valid_instance_name(explicit):
        return explicit
    root = Path(repo_root) if repo_root is not None else None
    if root is not None:
        saved = select.load_instance_config(root).name
        if saved:
            return saved
        claimed = select.name_claimed_by_root(user_units_dir(), root)
        if claimed:
            return claimed
    return DEFAULT_INSTANCE_NAME


def unit_filenames(repo_root: Path | None = None) -> tuple[str, str]:
    return _select().unit_names(instance_name(repo_root))


def systemd_user_units_installed(
    repo_root: Path | None = None,
    *,
    home: Path | None = None,
) -> bool:
    """True אם שני קבצי היחידה של המופע הזה קיימים, ומצביעים לריפו הזה כש-repo_root נמסר."""
    base = user_units_dir(home)
    root = Path(repo_root).resolve() if repo_root is not None else None
    names = unit_filenames(repo_root)
    select = _select()
    for name in names:
        path = base / name
        if not path.is_file():
            return False
        if root is None:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            return False
        wd = select.parse_working_directory(text)
        if wd is not None:
            try:
                if wd.resolve() != root:
                    return False
            except OSError:
                return False
        elif str(root) not in text:
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
