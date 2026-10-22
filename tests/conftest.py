"""Pytest fixtures — Flask client + temp SQLite (never data/calendar.db)."""
from __future__ import annotations

import os
import tempfile
from pathlib import Path

# חייב לפני כל import מ-app (app/__init__.py מאתחל DB בהעלאה).
_fd, _TEST_DB = tempfile.mkstemp(prefix="heb-cal-pytest-", suffix=".sqlite")
os.close(_fd)
os.environ["DATABASE_PATH"] = _TEST_DB

_REPO_DATA_DB = (Path(__file__).resolve().parent.parent / "data" / "calendar.db").resolve()
assert Path(os.environ["DATABASE_PATH"]).resolve() != _REPO_DATA_DB

from app import app as flask_app  # noqa: E402


import pytest


@pytest.fixture(scope="session")
def app():
    flask_app.config.update(TESTING=True)
    return flask_app


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture(autouse=True)
def _empty_events_table(app):
    """מבודד בדיקות API — מנקה אירועים בין מקרי בדיקה."""
    with app.app_context():
        from app.database import get_db

        db = get_db()
        db.execute("DELETE FROM reminder_sends")
        db.execute("DELETE FROM reminders")
        db.execute("DELETE FROM event_exceptions")
        db.execute("DELETE FROM reminder_people")
        db.execute("DELETE FROM events")
        db.execute(
            "DELETE FROM event_colors WHERE lower(color_code) NOT IN ('cyan', 'yellow', 'orange', 'green')"
        )
        db.execute("UPDATE household_settings SET shifts_enabled = 0 WHERE id = 1")
        db.commit()
    yield
