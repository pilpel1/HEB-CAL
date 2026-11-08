"""Pytest fixtures — Flask client + temp SQLite (never data/calendar.db)."""
from __future__ import annotations

import os
import tempfile
from pathlib import Path

# חייב לפני כל import מ-app (app/__init__.py מאתחל DB בהעלאה).
_fd, _TEST_DB = tempfile.mkstemp(prefix="heb-cal-pytest-", suffix=".sqlite")
os.close(_fd)
os.environ["DATABASE_PATH"] = _TEST_DB
os.environ["HEB_CAL_UNIT_DIR"] = tempfile.mkdtemp(prefix="heb-cal-pytest-units-")

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
        tables = {
            row[0]
            for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
        if "users" in tables:
            db.execute("DELETE FROM users")
        if "reminder_people" in tables:
            db.execute("DELETE FROM reminder_people")
        db.execute("DELETE FROM events")
        if db.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'gcal_sources'"
        ).fetchone():
            db.execute("DELETE FROM gcal_sources")
        if db.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'bot_sessions'"
        ).fetchone():
            db.execute("DELETE FROM bot_sessions")
        if "mcp_keys" in tables:
            db.execute("DELETE FROM mcp_keys")
        if "oauth_codes" in tables:
            db.execute("DELETE FROM oauth_codes")
        if "oauth_grants" in tables:
            db.execute("DELETE FROM oauth_grants")
        if "oauth_clients" in tables:
            db.execute("DELETE FROM oauth_clients")
        db.execute(
            "DELETE FROM event_colors WHERE lower(color_code) NOT IN ('cyan', 'yellow', 'orange', 'green')"
        )
        db.execute("UPDATE household_settings SET shifts_enabled = 0 WHERE id = 1")
        if db.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'live_sync'"
        ).fetchone():
            db.execute(
                "UPDATE live_sync SET revision = 0, origin = NULL, event_ids = '[]', "
                "action = NULL, updated_at = NULL WHERE id = 1"
            )
        db.commit()
    yield
