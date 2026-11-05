#!/usr/bin/env python3
"""שרת ה-web. יורש LISTEN_FDS מ-systemd כשיש יחידת socket, אחרת כורך את הפורט הקבוע של המופע.

אין פורט זמני, אין סריקה, אין bind לפורט 0. פורט הציבורי הוא HEB_CAL_PORT / data/instance.env.
"""
from __future__ import annotations

import os
import socket
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

SD_LISTEN_FDS_START = 3


def _sanitize_host(value: str) -> str:
    host = (value or "").strip()
    if not host:
        return "127.0.0.1"
    allowed = set("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789.:_[]-")
    if any(ch not in allowed for ch in host):
        return "127.0.0.1"
    return host


def _sanitize_port(value: str, default: int = 5000) -> int:
    text = (value or "").strip()
    if not text.isdigit():
        return default
    port = int(text)
    if port < 1 or port > 65535:
        return default
    return port


def env_bind_host() -> str:
    return _sanitize_host(os.environ.get("HEB_CAL_BIND_HOST", ""))


def env_bind_port() -> int:
    raw = (os.environ.get("HEB_CAL_PORT") or "").strip()
    if raw:
        return _sanitize_port(raw)
    path = ROOT / "data" / "instance.env"
    if path.is_file():
        try:
            for line in path.read_text(encoding="utf-8").splitlines():
                stripped = line.strip().replace("\r", "")
                if stripped.startswith("HEB_CAL_PORT="):
                    return _sanitize_port(stripped.split("=", 1)[1].strip().strip("\"'"))
        except OSError:
            pass
    return 5000


def inherited_listen_fd() -> int | None:
    """מחזיר fd האזנה של systemd, או None אם לא הופעל socket activation.

    LISTEN_PID חייב להיות התהליך הנוכחי. בדיוק fd אחד. ה-socket חייב להיות במצב listen.
    """
    raw_fds = (os.environ.get("LISTEN_FDS") or "").strip()
    if not raw_fds:
        return None
    raw_pid = (os.environ.get("LISTEN_PID") or "").strip()
    if not raw_fds.isdigit() or not raw_pid.isdigit():
        raise SystemExit("LISTEN_FDS/LISTEN_PID לא תקינים.")
    n_fds = int(raw_fds)
    listen_pid = int(raw_pid)
    if listen_pid != os.getpid():
        raise SystemExit("LISTEN_PID לא שייך לתהליך הזה.")
    if n_fds != 1:
        raise SystemExit("HEB-CAL מצפה ל-LISTEN_FDS=1 (בלי פורטים נוספים).")
    fd = SD_LISTEN_FDS_START
    probe = socket.socket(fileno=os.dup(fd))
    try:
        accepting = probe.getsockopt(socket.SOL_SOCKET, socket.SO_ACCEPTCONN)
        if not accepting:
            raise SystemExit("fd של systemd אינו במצב listen.")
    finally:
        probe.close()
    return fd


def peek_sockname(fd: int) -> tuple[str, int]:
    probe = socket.socket(fileno=os.dup(fd))
    try:
        addr = probe.getsockname()
    finally:
        probe.close()
    if not isinstance(addr, tuple) or len(addr) < 2:
        raise SystemExit("כתובת האזנה לא תקינה.")
    return str(addr[0]), int(addr[1])


def serve(app, *, fd: int | None = None, host: str | None = None, port: int | None = None) -> None:
    from werkzeug.serving import make_server

    if fd is not None:
        bound_host, bound_port = peek_sockname(fd)
        server = make_server(bound_host, bound_port, app, threaded=True, fd=fd)
    else:
        bound_host = host if host is not None else env_bind_host()
        bound_port = port if port is not None else env_bind_port()
        if bound_port < 1 or bound_port > 65535:
            raise SystemExit("פורט לא תקין. אין bind לפורט 0 ואין סריקה.")
        server = make_server(bound_host, bound_port, app, threaded=True)
    server.serve_forever()


def main() -> int:
    fd = inherited_listen_fd()
    if fd is not None:
        # שלא יעברו לילדים (רילודר וכו'). ה-fd עצמו נשאר פתוח.
        os.environ.pop("LISTEN_FDS", None)
        os.environ.pop("LISTEN_PID", None)
    from app import app

    serve(app, fd=fd)
    return 0


if __name__ == "__main__":
    sys.exit(main())
