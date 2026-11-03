"""נעילת מופע יחיד ל-reminder_worker. fcntl, משתחררת ביציאת התהליך."""
from __future__ import annotations

import fcntl
import os
from pathlib import Path

# EX_TEMPFAIL. יחידת systemd מסמנת RestartPreventExitStatus=75 כדי לא ללולאה.
LOCK_BUSY_EXIT = 75
DEFAULT_LOCK_NAME = "reminder_worker.lock"


class WorkerLock:
    def __init__(self, path: Path, fd: int):
        self.path = path
        self.fd = fd

    def close(self) -> None:
        if self.fd < 0:
            return
        try:
            fcntl.flock(self.fd, fcntl.LOCK_UN)
        except OSError:
            pass
        try:
            os.close(self.fd)
        except OSError:
            pass
        self.fd = -1

    def __enter__(self) -> "WorkerLock":
        return self

    def __exit__(self, *exc) -> None:
        self.close()


def default_lock_path(root: Path | None = None) -> Path:
    """נעילה תחת data/ של המופע הזה — כל clone שומר קובץ נפרד."""
    if root is None:
        root = Path(__file__).resolve().parent.parent.parent
    return Path(root) / "data" / DEFAULT_LOCK_NAME


def acquire_worker_lock(path: Path | None = None) -> WorkerLock | None:
    """נעילה בלעדית ולא-חוסמת. None אם כבר רץ מופע אחר."""
    lock_path = Path(path) if path is not None else default_lock_path()
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(lock_path, os.O_CREAT | os.O_RDWR, 0o644)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        os.close(fd)
        return None
    except OSError:
        os.close(fd)
        raise
    try:
        os.ftruncate(fd, 0)
        os.write(fd, f"{os.getpid()}\n".encode("ascii"))
        os.fsync(fd)
    except OSError:
        try:
            fcntl.flock(fd, fcntl.LOCK_UN)
        except OSError:
            pass
        os.close(fd)
        raise
    return WorkerLock(lock_path, fd)
