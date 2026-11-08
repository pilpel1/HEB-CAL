"""שער כרטיסי עוזר AI בהגדרות: מוסתר כברירת מחדל, חוזר עם HEB_CAL_AI_SETTINGS_UI."""
from __future__ import annotations

from pathlib import Path

import pytest

from app.settings_flags import AI_SETTINGS_UI_ENV, ai_settings_ui_enabled

REPO = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (None, False),
        ("", False),
        ("0", False),
        ("false", False),
        ("off", False),
        ("1", True),
        ("true", True),
        ("YES", True),
        ("on", True),
    ],
)
def test_ai_settings_ui_flag(monkeypatch, value, expected):
    monkeypatch.delenv(AI_SETTINGS_UI_ENV, raising=False)
    if value is not None:
        monkeypatch.setenv(AI_SETTINGS_UI_ENV, value)
    assert ai_settings_ui_enabled() is expected


def test_env_example_documents_ai_settings_ui_gate():
    env = (REPO / ".env.example").read_text(encoding="utf-8")
    assert "HEB_CAL_AI_SETTINGS_UI=1" in env
    assert "כבוי כברירת מחדל" in env


def test_readme_documents_reenable_not_end_user_switch():
    readme = (REPO / "README.md").read_text(encoding="utf-8")
    mcp_docs = readme.split('<a id="mcp"></a>', 1)[1].split("### התראות", 1)[0]
    assert "HEB_CAL_AI_SETTINGS_UI=1" in mcp_docs
    assert "אין מתג במסך למשתמש הקצה" in mcp_docs
    assert "בקרוב" not in mcp_docs
    assert "coming soon" not in mcp_docs.lower()
