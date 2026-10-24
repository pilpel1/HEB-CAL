"""קונפיגורציה מהסביבה בלבד. שום שדה מהבקשה לא נכנס לכאן."""
from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit

from app.database import BASE_DIR, get_database_path
from app.updates.version import DEFAULT_REPO, parse_github_slug, valid_slug

DOCKER_COMMAND = "docker compose pull && docker compose up -d"
DOCKER_INSTRUCTIONS = "בהתקנת Docker העדכון לא רץ מתוך האפליקציה. בשרת מריצים את הפקודה הזו:"
_LOOPBACK = {"127.0.0.1", "localhost", "::1"}
_DEFAULT_HEALTH = "http://127.0.0.1:5000/api/updates/health"


def _flag(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _blank(name: str) -> str:
    return (os.getenv(name) or "").strip()


@dataclass
class UpdateConfig:
    mode: str
    repo: str
    token: str | None
    restart_command: str | None
    hook_path: str | None
    hook_error: str | None
    health_url: str
    health_error: str | None
    backup_dir: Path
    db_path: Path
    repo_root: Path
    autocheck: bool
    update_dir: Path
    repo_error: str | None

    def __repr__(self) -> str:
        # בלי הטוקן, גם אם מישהו מדפיס את האובייקט.
        return (
            f"UpdateConfig(mode={self.mode!r}, repo={self.repo!r}, "
            f"token={'set' if self.token else 'unset'})"
        )


def _detect_repo() -> tuple[str, str | None]:
    explicit = _blank("HEB_CAL_GITHUB_REPO")
    if explicit:
        if not valid_slug(explicit):
            return DEFAULT_REPO, "HEB_CAL_GITHUB_REPO לא בפורמט owner/name."
        return explicit, None
    try:
        proc = subprocess.run(
            ["git", "remote", "get-url", "origin"],
            cwd=str(BASE_DIR),
            capture_output=True,
            text=True,
            timeout=5,
            shell=False,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return DEFAULT_REPO, None
    # לא קוראים את stderr: כתובת remote עם טוקן עלולה להופיע שם.
    slug = parse_github_slug(proc.stdout or "")
    return (slug or DEFAULT_REPO), None


def _health_url() -> tuple[str, str | None]:
    raw = _blank("HEB_CAL_HEALTH_URL") or _DEFAULT_HEALTH
    parts = urlsplit(raw)
    host = (parts.hostname or "").lower()
    if parts.scheme not in {"http", "https"} or host not in _LOOPBACK:
        return _DEFAULT_HEALTH, "HEB_CAL_HEALTH_URL חייב להצביע ל-localhost על המחשב הזה."
    if parts.username or parts.password:
        return _DEFAULT_HEALTH, "HEB_CAL_HEALTH_URL לא יכול לכלול סיסמה."
    return raw, None


def _hook_path() -> tuple[str | None, str | None]:
    raw = _blank("HEB_CAL_UPDATE_HOOK")
    if not raw:
        return None, None
    if "\n" in raw or "\x00" in raw or any(ch.isspace() for ch in raw):
        return None, "HEB_CAL_UPDATE_HOOK חייב להיות נתיב מלא לקובץ, בלי רווחים."
    path = Path(raw)
    if not path.is_absolute():
        return None, "HEB_CAL_UPDATE_HOOK חייב להיות נתיב מלא לקובץ."
    return str(path), None


def resolve_mode() -> str:
    raw = _blank("HEB_CAL_UPDATE_MODE").lower() or "auto"
    if raw in {"off", "disabled"}:
        return "off"
    if raw == "git":
        return "git"
    if raw == "docker":
        return "docker"
    if raw == "hook":
        return "hook"
    if _flag("HEB_CAL_DOCKER", False) or Path("/.dockerenv").is_file():
        return "docker"
    return "git"


def load_config() -> UpdateConfig:
    update_dir = Path(_blank("HEB_CAL_UPDATE_DIR") or (BASE_DIR / "data"))
    backup_dir = Path(_blank("HEB_CAL_BACKUP_DIR") or (BASE_DIR / "backups"))
    token = _blank("HEB_CAL_GITHUB_TOKEN") or None
    restart = _blank("HEB_CAL_RESTART_COMMAND") or None
    if restart and ("\n" in restart or "\x00" in restart):
        restart = None
    health_url, health_error = _health_url()
    hook_path, hook_error = _hook_path()
    repo, repo_error = _detect_repo()
    return UpdateConfig(
        mode=resolve_mode(),
        repo=repo,
        token=token,
        restart_command=restart,
        hook_path=hook_path,
        hook_error=hook_error,
        health_url=health_url,
        health_error=health_error,
        backup_dir=backup_dir,
        db_path=get_database_path(),
        repo_root=BASE_DIR,
        autocheck=_flag("HEB_CAL_UPDATE_AUTOCHECK", True),
        update_dir=update_dir,
        repo_error=repo_error,
    )


def describe_mode(cfg: UpdateConfig, *, git_checkout: bool) -> dict:
    """מה המסך יכול להציע. `can_apply` לא מגיע מהבקשה."""
    if cfg.repo_error:
        return {
            "can_apply": False,
            "block": cfg.repo_error,
            "instructions": None,
            "docker_command": None,
        }
    if cfg.mode == "off":
        return {
            "can_apply": False,
            "block": "העדכון מהממשק כבוי.",
            "instructions": None,
            "docker_command": None,
        }
    if cfg.health_error:
        return {
            "can_apply": False,
            "block": cfg.health_error,
            "instructions": None,
            "docker_command": None,
        }
    if cfg.mode == "docker" and not cfg.hook_path:
        return {
            "can_apply": False,
            "block": None,
            "instructions": DOCKER_INSTRUCTIONS,
            "docker_command": DOCKER_COMMAND,
        }
    if cfg.mode in {"docker", "hook"}:
        if cfg.hook_error:
            return {
                "can_apply": False,
                "block": cfg.hook_error,
                "instructions": DOCKER_INSTRUCTIONS if cfg.mode == "docker" else None,
                "docker_command": DOCKER_COMMAND if cfg.mode == "docker" else None,
            }
        if not cfg.hook_path:
            return {
                "can_apply": False,
                "block": "הוגדר מצב hook בלי HEB_CAL_UPDATE_HOOK.",
                "instructions": None,
                "docker_command": None,
            }
        hook = Path(cfg.hook_path)
        if not hook.is_file():
            return {
                "can_apply": False,
                "block": "סקריפט העדכון לא נמצא.",
                "instructions": DOCKER_INSTRUCTIONS if cfg.mode == "docker" else None,
                "docker_command": DOCKER_COMMAND if cfg.mode == "docker" else None,
            }
        if not os.access(hook, os.X_OK):
            return {
                "can_apply": False,
                "block": "סקריפט העדכון לא ניתן להרצה.",
                "instructions": DOCKER_INSTRUCTIONS if cfg.mode == "docker" else None,
                "docker_command": DOCKER_COMMAND if cfg.mode == "docker" else None,
            }
        return {
            "can_apply": True,
            "block": None,
            "instructions": DOCKER_INSTRUCTIONS if cfg.mode == "docker" else None,
            "docker_command": DOCKER_COMMAND if cfg.mode == "docker" else None,
        }
    if not git_checkout:
        return {
            "can_apply": False,
            "block": "התיקייה אינה עותק git, אז אי אפשר לעדכן מהממשק.",
            "instructions": None,
            "docker_command": None,
        }
    from app.updates.gitops import restart_block

    block = restart_block(cfg.restart_command, cfg.repo_root)
    if block:
        return {
            "can_apply": False,
            "block": block,
            "instructions": None,
            "docker_command": None,
        }
    return {
        "can_apply": True,
        "block": None,
        "instructions": None,
        "docker_command": None,
    }
