"""יורש LISTEN_FDS בבטחה, בלי פורט 0 ובלי סריקה."""
from __future__ import annotations

import errno
import importlib.util
import os
import signal
import socket
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent


def _load():
    path = REPO / "scripts" / "run_web.py"
    spec = importlib.util.spec_from_file_location("hebcal_run_web", path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name or "hebcal_run_web"] = mod
    spec.loader.exec_module(mod)
    return mod


run_web = _load()


def _wsgi_ok(environ, start_response):
    start_response("200 OK", [("Content-Type", "text/plain; charset=utf-8")])
    return [b"ok"]


def _wait_http(url: str, timeout: float = 4.0) -> bytes:
    deadline = time.monotonic() + timeout
    last = None
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=0.4) as response:
                return response.read()
        except (urllib.error.URLError, TimeoutError, ConnectionError, OSError) as exc:
            last = exc
            time.sleep(0.05)
    raise AssertionError(f"no answer from {url}: {last}")


def test_inherited_listen_fd_absent_is_none(monkeypatch):
    monkeypatch.delenv("LISTEN_FDS", raising=False)
    monkeypatch.delenv("LISTEN_PID", raising=False)
    assert run_web.inherited_listen_fd() is None


def test_inherited_listen_fd_rejects_wrong_pid_and_count(monkeypatch):
    monkeypatch.setenv("LISTEN_FDS", "1")
    monkeypatch.setenv("LISTEN_PID", "1")
    with pytest.raises(SystemExit):
        run_web.inherited_listen_fd()
    monkeypatch.setenv("LISTEN_PID", str(os.getpid()))
    monkeypatch.setenv("LISTEN_FDS", "2")
    with pytest.raises(SystemExit, match="LISTEN_FDS=1"):
        run_web.inherited_listen_fd()
    monkeypatch.setenv("LISTEN_FDS", "nope")
    with pytest.raises(SystemExit):
        run_web.inherited_listen_fd()


def test_inherited_listen_fd_requires_listening_socket(monkeypatch):
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        monkeypatch.setenv("LISTEN_FDS", "1")
        monkeypatch.setenv("LISTEN_PID", str(os.getpid()))
        monkeypatch.setattr(run_web, "SD_LISTEN_FDS_START", sock.fileno())
        with pytest.raises(SystemExit, match="listen"):
            run_web.inherited_listen_fd()
        sock.bind(("127.0.0.1", 0))
        sock.listen(8)
        assert run_web.inherited_listen_fd() == sock.fileno()
    finally:
        sock.close()


def test_env_bind_port_never_zero(monkeypatch, tmp_path):
    monkeypatch.setenv("HEB_CAL_PORT", "0")
    assert run_web.env_bind_port() == 5000
    monkeypatch.setenv("HEB_CAL_PORT", "-3")
    assert run_web.env_bind_port() == 5000
    monkeypatch.setenv("HEB_CAL_PORT", "65536")
    assert run_web.env_bind_port() == 5000
    monkeypatch.setenv("HEB_CAL_PORT", "5001")
    assert run_web.env_bind_port() == 5001
    monkeypatch.delenv("HEB_CAL_PORT", raising=False)
    monkeypatch.setattr(run_web, "ROOT", tmp_path)
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "instance.env").write_text(
        "HEB_CAL_INSTANCE_NAME=gisim\nHEB_CAL_PORT=5007\n",
        encoding="utf-8",
    )
    assert run_web.env_bind_port() == 5007


def test_serve_rejects_port_zero():
    with pytest.raises(SystemExit, match="פורט 0"):
        run_web.serve(_wsgi_ok, host="127.0.0.1", port=0)


def test_serve_on_inherited_listen_fd():
    listen = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listen.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    listen.bind(("127.0.0.1", 0))
    listen.listen(16)
    _host, port = listen.getsockname()
    holder = {}

    def _run():
        try:
            run_web.serve(_wsgi_ok, fd=listen.fileno())
        except Exception as exc:  # pragma: no cover
            holder["err"] = exc

    thread = threading.Thread(target=_run, daemon=True)
    thread.start()
    try:
        body = _wait_http(f"http://127.0.0.1:{port}/")
        assert body == b"ok"
    finally:
        listen.close()


_CHILD_SERVE = r"""
import os
import sys
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

repo = Path(sys.argv[1])
marker = sys.argv[2].encode("ascii")
src_fd = int(sys.argv[3])
if src_fd != 3:
    os.dup2(src_fd, 3)
os.environ["LISTEN_FDS"] = "1"
os.environ["LISTEN_PID"] = str(os.getpid())
spec = spec_from_file_location("hebcal_run_web_child", repo / "scripts" / "run_web.py")
mod = module_from_spec(spec)
spec.loader.exec_module(mod)

def app(environ, start_response):
    start_response("200 OK", [("Content-Type", "text/plain; charset=utf-8")])
    return [marker]

fd = mod.inherited_listen_fd()
if fd is None:
    raise SystemExit("no inherited listen fd")
mod.serve(app, fd=fd)
"""


def _kill_proc(proc: subprocess.Popen | None) -> None:
    if proc is None or proc.poll() is not None:
        return
    try:
        proc.send_signal(signal.SIGTERM)
        proc.wait(timeout=2)
    except (ProcessLookupError, subprocess.TimeoutExpired):
        try:
            proc.kill()
            proc.wait(timeout=2)
        except (ProcessLookupError, subprocess.TimeoutExpired):
            pass


def _spawn_inherited_child(listen: socket.socket, marker: str, log_path: Path) -> subprocess.Popen:
    listen_fd = listen.fileno()
    handle = open(log_path, "ab")
    try:
        proc = subprocess.Popen(
            [sys.executable, "-c", _CHILD_SERVE, str(REPO), marker, str(listen_fd)],
            pass_fds=(listen_fd,),
            start_new_session=True,
            stdin=subprocess.DEVNULL,
            stdout=handle,
            stderr=subprocess.STDOUT,
            close_fds=True,
            cwd=str(REPO),
        )
    finally:
        handle.close()
    return proc


def test_parent_listen_socket_queues_across_child_restart(tmp_path):
    """הסוקט אצל ההורה נשאר כשהילד מת; חיבור ברווח נכנס לתור, לא ECONNREFUSED."""
    if os.name != "posix":
        pytest.skip("socket activation is a Linux systemd path")

    listen = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listen.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    listen.bind(("127.0.0.1", 0))
    listen.listen(16)
    _host, port = listen.getsockname()
    first = None
    second = None
    try:
        first = _spawn_inherited_child(listen, "first", tmp_path / "first.log")
        try:
            warmup = _wait_http(f"http://127.0.0.1:{port}/")
        except AssertionError:
            log = (tmp_path / "first.log").read_bytes()
            raise AssertionError(
                f"child {first.pid} poll={first.poll()} log={log!r}"
            ) from None
        assert warmup == b"first"
        _kill_proc(first)
        assert first.poll() is not None

        accepting = listen.getsockopt(socket.SOL_SOCKET, socket.SO_ACCEPTCONN)
        assert accepting
        probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            probe.bind(("127.0.0.1", port))
            raise AssertionError("listen port was released after child exit")
        except OSError as exc:
            assert exc.errno in {errno.EADDRINUSE, errno.EACCES}
        finally:
            probe.close()

        result: dict = {}
        connected = threading.Event()

        def _queued_client() -> None:
            try:
                client = socket.create_connection(("127.0.0.1", port), timeout=3)
            except OSError as exc:
                result["err"] = exc
                connected.set()
                return
            connected.set()
            try:
                client.sendall(b"GET / HTTP/1.1\r\nHost: 127.0.0.1\r\nConnection: close\r\n\r\n")
                client.settimeout(8)
                chunks = []
                while True:
                    buf = client.recv(4096)
                    if not buf:
                        break
                    chunks.append(buf)
                result["data"] = b"".join(chunks)
            except OSError as exc:
                result["err"] = exc
            finally:
                client.close()

        thread = threading.Thread(target=_queued_client, daemon=True)
        thread.start()
        assert connected.wait(4), result
        assert not isinstance(result.get("err"), ConnectionRefusedError), result
        assert "data" not in result

        second = _spawn_inherited_child(listen, "second", tmp_path / "second.log")
        thread.join(8)
        assert not thread.is_alive(), result
        assert "err" not in result, result
        body = result.get("data") or b""
        assert b"second" in body
        assert b"first" not in body
        assert _wait_http(f"http://127.0.0.1:{port}/") == b"second"
    finally:
        _kill_proc(first)
        _kill_proc(second)
        listen.close()


def test_serve_binds_explicit_instance_port_not_scan():
    probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    probe.bind(("127.0.0.1", 0))
    port = probe.getsockname()[1]
    probe.close()
    thread = threading.Thread(
        target=lambda: run_web.serve(_wsgi_ok, host="127.0.0.1", port=port),
        daemon=True,
    )
    thread.start()
    body = _wait_http(f"http://127.0.0.1:{port}/")
    assert body == b"ok"
