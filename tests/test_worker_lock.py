"""נעילת מופע יחיד ל-reminder_worker, ו-backoff ל-Telegram 409."""
from __future__ import annotations

import subprocess
import sys
import threading
import time
from pathlib import Path

from app.reminders.instance_lock import LOCK_BUSY_EXIT, acquire_worker_lock, default_lock_path
from app.reminders.telegram import TelegramError
from app.reminders.worker import (
    CONFLICT_BACKOFF_MAX,
    CONFLICT_BACKOFF_START,
    _update_loop,
    next_update_delay,
)

REPO = Path(__file__).resolve().parent.parent


def test_default_lock_path_is_under_data():
    path = default_lock_path(REPO)
    assert path == REPO / "data" / "reminder_worker.lock"


def test_two_repo_roots_have_separate_lock_files(tmp_path):
    first = tmp_path / "family1"
    second = tmp_path / "family2"
    assert default_lock_path(first) == first / "data" / "reminder_worker.lock"
    assert default_lock_path(second) == second / "data" / "reminder_worker.lock"
    assert default_lock_path(first) != default_lock_path(second)
    a = acquire_worker_lock(default_lock_path(first))
    b = acquire_worker_lock(default_lock_path(second))
    assert a is not None
    assert b is not None
    a.close()
    b.close()


def test_lock_can_be_reacquired_after_close(tmp_path):
    lock_path = tmp_path / "reminder_worker.lock"
    first = acquire_worker_lock(lock_path)
    assert first is not None
    assert lock_path.is_file()
    first.close()
    second = acquire_worker_lock(lock_path)
    assert second is not None
    second.close()


def test_second_process_does_not_take_the_lock(tmp_path):
    lock_path = tmp_path / "reminder_worker.lock"
    held = acquire_worker_lock(lock_path)
    assert held is not None
    code = (
        "from pathlib import Path\n"
        "from app.reminders.instance_lock import acquire_worker_lock\n"
        f"got = acquire_worker_lock(Path({str(lock_path)!r}))\n"
        "raise SystemExit(0 if got is None else 1)\n"
    )
    proc = subprocess.run(
        [sys.executable, "-c", code],
        cwd=REPO,
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    held.close()
    proc = subprocess.run(
        [sys.executable, "-c", code],
        cwd=REPO,
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    assert proc.returncode == 1, proc.stderr


def test_lock_busy_exit_matches_systemd_prevent_status():
    worker_unit = (REPO / "deploy/systemd/heb-cal-worker.service").read_text(encoding="utf-8")
    assert f"RestartPreventExitStatus={LOCK_BUSY_EXIT}" in worker_unit
    assert LOCK_BUSY_EXIT == 75


def test_conflict_backoff_doubles_and_caps():
    conflict = TelegramError("getUpdates failed: HTTP 409 Conflict", status_code=409)
    delay, nxt = next_update_delay(conflict, CONFLICT_BACKOFF_START)
    assert delay == CONFLICT_BACKOFF_START == 5
    assert nxt == 10
    delay, nxt = next_update_delay(conflict, 40)
    assert delay == 40
    assert nxt == CONFLICT_BACKOFF_MAX == 60
    delay, nxt = next_update_delay(conflict, 60)
    assert delay == 60
    assert nxt == 60
    other = TelegramError("getUpdates failed: HTTP 500", status_code=500)
    delay, nxt = next_update_delay(other, 40)
    assert delay == 1
    assert nxt == CONFLICT_BACKOFF_START


def test_telegram_error_conflict_from_json_code():
    err = TelegramError("getUpdates failed: Conflict: terminated by other getUpdates", status_code=409)
    assert err.is_conflict
    plain = TelegramError("getUpdates failed: HTTP 401", status_code=401)
    assert not plain.is_conflict


def test_update_loop_backs_off_on_409():
    stop = threading.Event()
    delays = []
    calls = {"n": 0}

    def consume(token, offset, long_poll=0):
        calls["n"] += 1
        raise TelegramError("getUpdates failed: HTTP 409 Conflict", status_code=409)

    original = threading.Event.wait

    def wait_and_record(self, timeout=None):
        delays.append(timeout)
        if len(delays) >= 3:
            stop.set()
            return True
        return original(self, 0)

    threading.Event.wait = wait_and_record
    try:
        started = time.monotonic()
        _update_loop(stop, consume=consume, token_fn=lambda: "token")
        elapsed = time.monotonic() - started
    finally:
        threading.Event.wait = original
        stop.set()
    assert calls["n"] >= 3
    assert delays[:3] == [5, 10, 20]
    assert elapsed < 1.0


def test_update_loop_idles_without_telegram_token():
    stop = threading.Event()
    calls = []

    def consume(token, offset, long_poll=0):
        calls.append(token)
        raise AssertionError("getUpdates must not run without a token")

    original = threading.Event.wait

    def wait_and_stop(self, timeout=None):
        stop.set()
        return True

    threading.Event.wait = wait_and_stop
    try:
        _update_loop(stop, consume=consume, token_fn=lambda: "")
    finally:
        threading.Event.wait = original
        stop.set()
    assert calls == []
