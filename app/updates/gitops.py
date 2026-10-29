"""פעולות קבצים: git רק עם ארגומנטים קבועים, גיבוי SQLite, והפעלה מחדש מההגדרות."""
from __future__ import annotations

import json
import logging
import os
import shlex
import shutil
import sqlite3
import subprocess
import sys
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from app.updates.envconfig import UpdateConfig
from app.updates.errors import UpdateError, redact
from app.updates.store import read_json, write_status
from app.updates.version import valid_slug, validate_sha, validate_tag

logger = logging.getLogger(__name__)

_SHALLOW_NOTE = "העותק הותקן בלי היסטוריה מלאה (shallow). עדכון אוטומטי דורש clone מלא."


def _relative_script(token: str) -> bool:
    """נתיב יחסי לשורש (scripts/restart.sh או ./restart.sh). שם בלי סלאש נשאר ב-PATH."""
    if Path(token).is_absolute():
        return False
    return "/" in token or token.startswith(".")


def restart_argv(command: str, repo_root: Path) -> list[str]:
    if not isinstance(command, str) or "\n" in command or "\x00" in command:
        raise UpdateError("פקודת ההפעלה מחדש לא תקינה.", step="restart")
    root = repo_root if isinstance(repo_root, Path) else Path(repo_root)
    try:
        args = shlex.split(command, posix=True)
    except ValueError as exc:
        raise UpdateError("פקודת ההפעלה מחדש לא תקינה.", step="restart") from exc
    if not args or any(not isinstance(part, str) or part == "" for part in args):
        raise UpdateError("פקודת ההפעלה מחדש לא תקינה.", step="restart")
    if _relative_script(args[0]):
        args[0] = str((root / args[0]).resolve())
    return args


def restart_block(command: str | None, repo_root: Path) -> str | None:
    """הודעה בעברית אם אי אפשר להפעיל מחדש. None אם אפשר."""
    if not command:
        return "לא הוגדרה פקודת הפעלה מחדש (HEB_CAL_RESTART_COMMAND)."
    try:
        args = restart_argv(command, repo_root)
        token = shlex.split(command, posix=True)[0]
    except UpdateError as exc:
        return exc.message
    if not (Path(token).is_absolute() or _relative_script(token)):
        return None
    path = Path(args[0])
    if not path.is_file():
        return "סקריפט ההפעלה מחדש לא נמצא."
    if not os.access(path, os.X_OK):
        return "סקריפט ההפעלה מחדש לא ניתן להרצה."
    return None


def git_auth_env(base: dict, token: str | None) -> dict:
    env = dict(base)
    env["GIT_TERMINAL_PROMPT"] = "0"
    if not token:
        return env
    try:
        count = int(env.get("GIT_CONFIG_COUNT", "0") or "0")
    except ValueError:
        count = 0
    env["GIT_CONFIG_COUNT"] = str(count + 1)
    env[f"GIT_CONFIG_KEY_{count}"] = "http.extraheader"
    env[f"GIT_CONFIG_VALUE_{count}"] = f"AUTHORIZATION: bearer {token}"
    return env


def public_git_url(slug: str) -> str:
    """HTTPS נקי. לא משתמשים ב-remote, כי לפעמים שמור בו טוקן."""
    if not valid_slug(slug):
        raise UpdateError("מאגר GitHub לא תקין.", step="fetch")
    owner, name = slug.split("/")
    return f"https://github.com/{owner}/{name}.git"


def run_argv(args: list[str], *, cwd: Path, env: dict | None = None, timeout: int = 60) -> subprocess.CompletedProcess:
    if not args or any(not isinstance(part, str) for part in args):
        raise UpdateError("פקודה פנימית לא תקינה.", step="error")
    try:
        return subprocess.run(
            args,
            cwd=str(cwd),
            env=env,
            timeout=timeout,
            capture_output=True,
            text=True,
            shell=False,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise UpdateError("הפעולה לקחה יותר מדי זמן.", step="error") from exc
    except OSError as exc:
        raise UpdateError("לא הצלחנו להריץ פעולה במערכת.", step="error") from exc


def _safe_relpath(path: str) -> str | None:
    text = (path or "").strip().replace("\\", "/")
    if len(text) >= 2 and text[0] == '"' and text[-1] == '"':
        text = text[1:-1]
    if not text or text.startswith("/") or text.startswith("-") or ":" in text:
        return None
    parts = [part for part in text.split("/") if part]
    if not parts or any(part in {".", ".."} for part in parts):
        return None
    return "/".join(parts)[:120]


def parse_porcelain(stdout: str) -> list[tuple[str, str]]:
    rows: list[tuple[str, str]] = []
    for raw in (stdout or "").splitlines():
        if not raw:
            continue
        if raw.startswith("?? "):
            path = _safe_relpath(raw[3:])
            if path:
                rows.append(("??", path))
            continue
        if len(raw) < 4:
            continue
        code = raw[:2]
        path = raw[3:]
        if " -> " in path:
            path = path.split(" -> ", 1)[-1]
        safe = _safe_relpath(path)
        if safe:
            rows.append((code, safe))
    return rows


def _file_list(paths: list[str], limit: int = 4) -> str:
    unique: list[str] = []
    for path in paths:
        if path not in unique:
            unique.append(path)
    extra = len(unique) - limit
    shown = ", ".join(unique[:limit])
    if extra > 0:
        shown = f"{shown} ועוד {extra}"
    return shown


def _dirty_message(tracked: list[str], conflicts: list[str]) -> str:
    parts: list[str] = []
    if tracked:
        parts.append(
            "יש שינויים מקומיים בקוד. העדכון רץ רק על עותק נקי. "
            f"קבצים: {_file_list(tracked)}. "
            "בטלו (git checkout -- קובץ) או שמרו בצד (git stash) ואז עדכנו שוב."
        )
    if conflicts:
        first = conflicts[0]
        parts.append(
            "יש קבצים מקומיים שלא בגיט שיתנגשו עם הגרסה החדשה. "
            f"קבצים: {_file_list(conflicts)}. "
            f"העבירו הצידה: mv {first} {first}.local ואז עדכנו שוב."
        )
    return " ".join(parts)[:240]


def _tag_has_path(run, tag: str, path: str) -> bool:
    validate_tag(tag)
    proc = run(["git", "cat-file", "-e", f"refs/tags/{tag}:{path}"])
    return proc.returncode == 0


def _tag_has_prefix(run, tag: str, directory: str) -> bool:
    validate_tag(tag)
    prefix = directory.rstrip("/")
    proc = run(["git", "ls-tree", "-r", "--name-only", f"refs/tags/{tag}", prefix])
    if proc.returncode != 0:
        return False
    for line in (proc.stdout or "").splitlines():
        name = line.strip()
        if name == prefix or name.startswith(prefix + "/"):
            return True
    return False


def _same_blob(run, tag: str, path: str) -> bool:
    validate_tag(tag)
    tagged = run(["git", "rev-parse", "--verify", f"refs/tags/{tag}:{path}"])
    working = run(["git", "hash-object", "--", path])
    if tagged.returncode != 0 or working.returncode != 0:
        return False
    left = (tagged.stdout or "").strip()
    right = (working.stdout or "").strip()
    return bool(left) and left == right


def _unlink_untracked(repo_root: Path, rel: str) -> None:
    root = repo_root.resolve()
    target = (root / rel).resolve()
    if not target.is_file() or not target.is_relative_to(root):
        return
    try:
        target.unlink()
    except OSError:
        return


def assert_worktree_clean(run, tag: str | None = None, repo_root: Path | None = None) -> None:
    """עותק נקי משינויים במעקב. קבצים לא-מעקב מותרים אם הם לא דורסים קובץ בתג."""
    proc = run(["git", "status", "--porcelain", "--untracked-files=all"])
    if proc.returncode != 0:
        raise UpdateError("לא הצלחנו לבדוק את מצב ה-git.", step="checkout")
    tracked: list[str] = []
    untracked: list[str] = []
    for code, path in parse_porcelain(proc.stdout or ""):
        if code == "??":
            untracked.append(path)
        else:
            tracked.append(path)
    conflicts: list[str] = []
    if tag:
        validate_tag(tag)
        for path in untracked:
            if path.endswith("/"):
                if _tag_has_prefix(run, tag, path):
                    conflicts.append(path.rstrip("/"))
                continue
            if not _tag_has_path(run, tag, path):
                continue
            if _same_blob(run, tag, path):
                if repo_root is not None:
                    _unlink_untracked(repo_root, path)
                continue
            conflicts.append(path)
    if tracked or conflicts:
        raise UpdateError(_dirty_message(tracked, conflicts), step="checkout")


def assert_not_shallow(run) -> None:
    proc = run(["git", "rev-parse", "--is-shallow-repository"])
    if proc.returncode != 0:
        raise UpdateError("לא הצלחנו לבדוק את עותק ה-git.", step="fetch")
    if (proc.stdout or "").strip() == "true":
        raise UpdateError(_SHALLOW_NOTE, step="fetch")


def assert_tag_exists(run, tag: str) -> str:
    validate_tag(tag)
    proc = run(["git", "rev-parse", "--verify", f"refs/tags/{tag}^{{commit}}"])
    if proc.returncode != 0:
        raise UpdateError("התג לא נמצא אחרי ההורדה.", step="fetch")
    sha = (proc.stdout or "").strip()
    return validate_sha(sha)


def assert_fast_forward(run, head_sha: str, tag: str) -> None:
    validate_sha(head_sha)
    tip = assert_tag_exists(run, tag)
    proc = run(["git", "merge-base", "--is-ancestor", head_sha, tip])
    if proc.returncode != 0:
        raise UpdateError(
            "הגרסה החדשה אינה המשך ישיר של ההתקנה. לא מעדכנים בכוח.",
            step="checkout",
        )


def checkout_ref(run, ref: str, *, missing: str) -> None:
    proc = run(["git", "checkout", "--detach", ref])
    if proc.returncode != 0:
        raise UpdateError(missing, step="checkout")


def current_head(run) -> str:
    proc = run(["git", "rev-parse", "HEAD"])
    if proc.returncode != 0:
        raise UpdateError("לא הצלחנו לקרוא את הגרסה המותקנת.", step="checkout")
    return validate_sha((proc.stdout or "").strip())


def is_git_checkout(root: Path) -> bool:
    return (root / ".git").exists()


def backup_sqlite(live: Path, dest: Path) -> None:
    if not live.is_file():
        raise UpdateError("מסד הנתונים לא נמצא.", step="backup")
    dest.parent.mkdir(parents=True, exist_ok=True)
    source = sqlite3.connect(str(live))
    target = sqlite3.connect(str(dest))
    try:
        source.execute("PRAGMA busy_timeout = 15000")
        source.backup(target)
    except sqlite3.Error as exc:
        raise UpdateError("הגיבוי נכשל.", step="backup") from exc
    finally:
        target.close()
        source.close()
    os.chmod(dest, 0o600)


def restore_sqlite(backup: Path, live: Path) -> None:
    if not backup.is_file():
        raise UpdateError("קובץ הגיבוי חסר.", step="rollback")
    live.parent.mkdir(parents=True, exist_ok=True)
    temporary = live.with_name(live.name + ".restore")
    shutil.copy2(backup, temporary)
    os.chmod(temporary, 0o600)
    for suffix in ("-wal", "-shm"):
        sidecar = Path(str(live) + suffix)
        if sidecar.exists():
            sidecar.unlink()
    os.replace(temporary, live)


def backup_name(dest_dir: Path, version: str) -> Path:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    safe_version = version.replace("/", "")
    return dest_dir / f"calendar-before-{safe_version}-{stamp}.sqlite"


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def wait_until_healthy(url: str, version: str, *, timeout: float, opener, sleep) -> None:
    deadline = time.monotonic() + timeout
    while True:
        try:
            with opener(url) as response:
                raw = response.read(100_000)
            body = json.loads(raw.decode("utf-8"))
            if isinstance(body, dict) and body.get("ok") is True and body.get("version") == version:
                return
        except Exception:
            pass
        if time.monotonic() >= deadline:
            raise UpdateError("האפליקציה לא עלתה אחרי העדכון.", step="health")
        sleep(1)


class LiveOps:
    """המימוש האמיתי. הבדיקות מחליפות את המחלקה הזו במזויפת."""

    def __init__(self, cfg: UpdateConfig, status_file: Path, target_version: str):
        self.cfg = cfg
        self.status_file = status_file
        self.target_version = target_version
        self.payload = read_json(status_file) or {}

    def write(self, **fields) -> None:
        self.payload.update(fields)
        self.payload = write_status(self.status_file, self.payload)

    def _git(self, args: list[str], *, env: dict | None = None, timeout: int = 60):
        return run_argv(["git", *args], cwd=self.cfg.repo_root, env=env, timeout=timeout)

    def backup_database(self) -> Path:
        dest = backup_name(self.cfg.backup_dir, self.target_version)
        backup_sqlite(self.cfg.db_path, dest)
        self.payload["backup"] = str(dest)
        self.write(message="הגיבוי נשמר")
        return dest

    def restore_database(self, backup: Path) -> None:
        restore_sqlite(Path(backup), self.cfg.db_path)

    def current_sha(self) -> str:
        return current_head(lambda args: self._git(args[1:]))

    def ensure_clean(self, tag: str | None = None) -> None:
        assert_worktree_clean(
            lambda args: self._git(args[1:]),
            tag=tag,
            repo_root=self.cfg.repo_root,
        )

    def ensure_not_shallow(self) -> None:
        assert_not_shallow(lambda args: self._git(args[1:]))

    def fetch(self, tag: str) -> None:
        validate_tag(tag)
        url = public_git_url(self.cfg.repo)
        env = git_auth_env(os.environ.copy(), self.cfg.token)
        proc = run_argv(
            ["git", "fetch", url, f"refs/tags/{tag}:refs/tags/{tag}"],
            cwd=self.cfg.repo_root,
            env=env,
            timeout=90,
        )
        if proc.returncode != 0:
            logger.warning("git fetch failed: %s", redact(proc.stderr or ""))
            raise UpdateError("לא הצלחנו להוריד את הגרסה.", step="fetch")

    def ensure_fast_forward(self, sha: str, tag: str) -> None:
        assert_fast_forward(lambda args: self._git(args[1:]), sha, tag)

    def checkout(self, tag: str) -> None:
        validate_tag(tag)
        checkout_ref(
            lambda args: self._git(args[1:]),
            f"refs/tags/{tag}",
            missing="לא הצלחנו לעבור לגרסה החדשה.",
        )

    def checkout_sha(self, sha: str) -> None:
        validate_sha(sha)
        checkout_ref(
            lambda args: self._git(args[1:]),
            sha,
            missing="לא הצלחנו לחזור לגרסה הקודמת.",
        )

    def pip_install(self) -> None:
        requirements = self.cfg.repo_root / "requirements.txt"
        if not requirements.is_file():
            raise UpdateError("חסר קובץ requirements.txt.", step="install")
        proc = run_argv(
            [sys.executable, "-m", "pip", "install", "-r", "requirements.txt"],
            cwd=self.cfg.repo_root,
            timeout=300,
        )
        if proc.returncode != 0:
            raise UpdateError("התקנת החבילות נכשלה.", step="install")

    def migrate(self) -> None:
        # תהליך חדש, כדי לטעון את הקוד שאחרי ה-checkout ולא את מה שכבר בזיכרון.
        proc = run_argv(
            [sys.executable, "-c", "import app"],
            cwd=self.cfg.repo_root,
            timeout=120,
        )
        if proc.returncode != 0:
            raise UpdateError("עדכון מסד הנתונים נכשל.", step="migrate")

    def run_hook(self, version: str) -> None:
        path = self.cfg.hook_path
        if not path:
            raise UpdateError("לא הוגדר סקריפט עדכון.", step="hook")
        hook = Path(path)
        if not hook.is_file():
            raise UpdateError("סקריפט העדכון לא נמצא.", step="hook")
        if not os.access(hook, os.X_OK):
            raise UpdateError("סקריפט העדכון לא ניתן להרצה.", step="hook")
        env = os.environ.copy()
        env["HEB_CAL_TARGET_VERSION"] = version
        proc = run_argv([str(hook)], cwd=self.cfg.repo_root, env=env, timeout=300)
        if proc.returncode != 0:
            raise UpdateError("סקריפט העדכון נכשל.", step="hook")

    def _restart(self, action: str) -> None:
        if action not in {"restart", "stop"}:
            raise UpdateError("פעולת הפעלה לא תקינה.", step="restart")
        if not self.cfg.restart_command:
            raise UpdateError("לא הוגדרה פקודת הפעלה מחדש.", step="restart")
        env = os.environ.copy()
        env["HEB_CAL_UPDATE_ACTION"] = action
        proc = run_argv(
            restart_argv(self.cfg.restart_command, self.cfg.repo_root),
            cwd=self.cfg.repo_root,
            env=env,
            timeout=60,
        )
        if proc.returncode != 0:
            raise UpdateError("ההפעלה מחדש נכשלה.", step="restart")

    def restart(self) -> None:
        self._restart("restart")

    def stop_app(self) -> None:
        self._restart("stop")

    def restart_configured(self) -> bool:
        return bool(self.cfg.restart_command)

    def wait_healthy(self, version: str) -> None:
        opener = urllib.request.build_opener(_NoRedirect)

        def open_url(url):
            return opener.open(url, timeout=3)

        wait_until_healthy(
            self.cfg.health_url,
            version,
            timeout=45,
            opener=open_url,
            sleep=time.sleep,
        )
