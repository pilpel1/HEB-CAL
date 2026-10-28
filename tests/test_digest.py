"""סיכום בוקר בטלגרם: לוח זמנים, opt-in, תוכן, ושליחה אידמפוטנטית."""
from __future__ import annotations

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from app.reminders.digest import (
    DEFAULT_HOUR,
    DEFAULT_MINUTE,
    digest_clock,
    digest_coverage,
    digest_last_sent,
    digest_ready,
    digest_weekdays,
    format_digest,
    opted_in_people,
    process_daily_digests,
)
from app.services.recurrence import hebrew_display
from app.services.shifts import weekday_index

TZ = ZoneInfo("Asia/Jerusalem")
THURSDAY = date(2026, 10, 22)
FRIDAY = date(2026, 10, 23)
SATURDAY = date(2026, 10, 24)
SUNDAY = date(2026, 10, 25)


def _at(day: date, hour: int, minute: int = 0) -> datetime:
    return datetime(day.year, day.month, day.day, hour, minute, tzinfo=TZ)


def _person(app, name="דני", chat="42", **flags):
    with app.app_context():
        from app.reminders.repository import create_person

        return create_person(name, None if chat is None else str(chat), **flags)


def _event(app, title, day, **kwargs):
    with app.app_context():
        from app.database import create_event

        return create_event(
            title,
            day.isoformat(),
            hebrew_display(day),
            time=kwargs.get("time"),
            description=kwargs.get("description") or "",
            end_date=kwargs.get("end_date"),
            recurrence=kwargs.get("recurrence"),
            shift=kwargs.get("shift"),
        )


def test_digest_clock_defaults_to_six_am(monkeypatch):
    monkeypatch.delenv("DIGEST_HOUR", raising=False)
    monkeypatch.delenv("DIGEST_MINUTE", raising=False)
    assert DEFAULT_HOUR == 6
    assert DEFAULT_MINUTE == 0
    assert digest_clock() == (6, 0)


def test_digest_clock_env_override_and_invalid_fallback(monkeypatch):
    monkeypatch.setenv("DIGEST_HOUR", "8")
    monkeypatch.setenv("DIGEST_MINUTE", "15")
    assert digest_clock() == (8, 15)
    monkeypatch.setenv("DIGEST_HOUR", "25")
    monkeypatch.setenv("DIGEST_MINUTE", "-1")
    assert digest_clock() == (6, 0)
    monkeypatch.setenv("DIGEST_HOUR", "nope")
    monkeypatch.setenv("DIGEST_MINUTE", "x")
    assert digest_clock() == (6, 0)


def test_digest_weekdays_sun_through_friday_not_saturday():
    assert weekday_index(SUNDAY) == 0
    assert weekday_index(FRIDAY) == 5
    assert weekday_index(SATURDAY) == 6
    for offset in range(6):
        day = SUNDAY + timedelta(days=offset)
        assert digest_weekdays(day) is True, day
    assert digest_weekdays(SATURDAY) is False
    assert digest_coverage(THURSDAY) == [THURSDAY]
    assert digest_coverage(FRIDAY) == [FRIDAY, SATURDAY]
    assert digest_coverage(SATURDAY) == [SATURDAY]


def test_digest_ready_at_six_not_before_and_never_saturday(monkeypatch):
    monkeypatch.delenv("DIGEST_HOUR", raising=False)
    monkeypatch.delenv("DIGEST_MINUTE", raising=False)
    assert digest_ready(_at(THURSDAY, 5, 59)) is False
    assert digest_ready(_at(THURSDAY, 6, 0)) is True
    assert digest_ready(_at(THURSDAY, 6, 1)) is True
    assert digest_ready(_at(FRIDAY, 6, 0)) is True
    assert digest_ready(_at(SATURDAY, 6, 0)) is False
    assert digest_ready(_at(SATURDAY, 12, 0)) is False
    monkeypatch.setenv("DIGEST_HOUR", "8")
    monkeypatch.setenv("DIGEST_MINUTE", "0")
    assert digest_ready(_at(THURSDAY, 6, 0)) is False
    assert digest_ready(_at(THURSDAY, 8, 0)) is True


def test_new_person_digest_defaults_off(app):
    linked = _person(app, "דני", chat="42")
    unlinked = _person(app, "נועה", chat=None, daily_digest_enabled=True)
    opted = _person(app, "רינה", chat="99", daily_digest_enabled=True)
    assert linked["daily_digest_enabled"] is False
    assert unlinked["daily_digest_enabled"] is True
    assert opted["daily_digest_enabled"] is True
    with app.app_context():
        recipients = opted_in_people()
    assert [person["id"] for person in recipients] == [opted["id"]]


def test_opt_in_gate_skips_flag_off_unlinked_and_empty_token(app):
    _person(app, "כבוי", chat="1")
    _person(app, "בלי צ׳אט", chat=None, daily_digest_enabled=True)
    on = _person(app, "דלוק", chat="42", daily_digest_enabled=True)
    sent = []

    def send(token, chat_id, text):
        sent.append((token, str(chat_id), text))

    with app.app_context():
        assert process_daily_digests(now=_at(THURSDAY, 6, 0), send=send, token="") == 0
        assert sent == []
        assert digest_last_sent(on["id"]) is None
        assert process_daily_digests(now=_at(THURSDAY, 6, 0), send=send, token="tok") == 1
        assert [item[1] for item in sent] == ["42"]
        assert digest_last_sent(on["id"]) == THURSDAY


def test_saturday_never_sends_even_if_opted_in(app):
    _person(app, "דני", chat="42", daily_digest_enabled=True)
    sent = []

    def send(token, chat_id, text):
        sent.append(text)

    with app.app_context():
        assert process_daily_digests(now=_at(SATURDAY, 8, 0), send=send, token="tok") == 0
    assert sent == []


def test_idempotent_once_per_local_day(app):
    person = _person(app, "דני", chat="42", daily_digest_enabled=True)
    sent = []

    def send(token, chat_id, text):
        sent.append(text)

    with app.app_context():
        assert process_daily_digests(now=_at(THURSDAY, 6, 0), send=send, token="tok") == 1
        assert process_daily_digests(now=_at(THURSDAY, 9, 0), send=send, token="tok") == 0
        assert len(sent) == 1
        assert digest_last_sent(person["id"]) == THURSDAY
        assert process_daily_digests(now=_at(FRIDAY, 6, 0), send=send, token="tok") == 1
        assert len(sent) == 2
        assert digest_last_sent(person["id"]) == FRIDAY


def test_failed_send_is_not_marked_and_retries(app):
    person = _person(app, "דני", chat="42", daily_digest_enabled=True)
    calls = {"n": 0}

    def send(token, chat_id, text):
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("boom")

    with app.app_context():
        assert process_daily_digests(now=_at(THURSDAY, 6, 0), send=send, token="tok") == 0
        assert digest_last_sent(person["id"]) is None
        assert process_daily_digests(now=_at(THURSDAY, 6, 1), send=send, token="tok") == 1
        assert digest_last_sent(person["id"]) == THURSDAY
    assert calls["n"] == 2


def test_empty_day_message(app):
    _person(app, "דני", chat="42", daily_digest_enabled=True)
    sent = []

    def send(token, chat_id, text):
        sent.append(text)

    with app.app_context():
        assert process_daily_digests(now=_at(THURSDAY, 6, 0), send=send, token="tok") == 1
    text = sent[0]
    assert "אין אירועים היום" in text
    assert "סיכום בוקר" in text
    assert "יום חמישי" in text
    assert "יום שבת" not in text


def test_friday_digest_includes_saturday_and_labels_days(app):
    danny = _person(app, "דני", chat="42", daily_digest_enabled=True, works_shifts=1)
    _event(app, "קניות", FRIDAY, time="10:00")
    _event(app, "ארוחת שבת", SATURDAY)
    _event(app, "בוקר", FRIDAY, shift=(1, danny["id"], "בוקר"))
    _event(app, "רק ראשון", SUNDAY)
    sent = []

    def send(token, chat_id, text):
        sent.append(text)

    with app.app_context():
        assert process_daily_digests(now=_at(FRIDAY, 6, 0), send=send, token="tok") == 1
        people = {danny["id"]: danny}
        body = format_digest([FRIDAY, SATURDAY], people)
    text = sent[0]
    assert text == body
    assert "יום שישי" in text
    assert "יום שבת" in text
    assert "<b>קניות</b>" in text
    assert "10:00" in text
    assert "<b>ארוחת שבת</b>" in text
    assert "<b>בוקר</b>" in text
    assert "משמרת · דני" in text
    assert "רק ראשון" not in text
    assert "מזהה:" not in text
    friday_at = text.index("יום שישי")
    saturday_at = text.index("יום שבת")
    assert friday_at < text.index("קניות") < saturday_at < text.index("ארוחת שבת")
    empty_sat = text[saturday_at:]
    assert "אין אירועים היום" not in empty_sat


def test_friday_empty_days_say_so_per_day(app):
    _person(app, "דני", chat="42", daily_digest_enabled=True)
    with app.app_context():
        text = format_digest([FRIDAY, SATURDAY], {})
    assert text.count("אין אירועים היום") == 2
    assert text.index("יום שישי") < text.index("אין אירועים היום")
    assert "יום שבת" in text


def test_shared_chat_sends_once(app):
    danny = _person(app, "דני", chat="42", daily_digest_enabled=True)
    noa = _person(app, "נועה", chat="42", daily_digest_enabled=True)
    sent = []

    def send(token, chat_id, text):
        sent.append(str(chat_id))

    with app.app_context():
        assert process_daily_digests(now=_at(THURSDAY, 6, 0), send=send, token="tok") == 1
        assert digest_last_sent(danny["id"]) == THURSDAY
        assert digest_last_sent(noa["id"]) == THURSDAY
    assert sent == ["42"]


def test_too_early_does_not_send(app):
    _person(app, "דני", chat="42", daily_digest_enabled=True)
    sent = []

    def send(token, chat_id, text):
        sent.append(text)

    with app.app_context():
        assert process_daily_digests(now=_at(THURSDAY, 5, 59), send=send, token="tok") == 0
    assert sent == []


def test_weekday_digest_is_that_day_only(app):
    _person(app, "דני", chat="42", daily_digest_enabled=True)
    _event(app, "רק חמישי", THURSDAY)
    _event(app, "רק שישי", FRIDAY)
    sent = []

    def send(token, chat_id, text):
        sent.append(text)

    with app.app_context():
        process_daily_digests(now=_at(THURSDAY, 6, 0), send=send, token="tok")
    text = sent[0]
    assert "<b>רק חמישי</b>" in text
    assert "רק שישי" not in text
    assert "יום שבת" not in text


def test_recurring_occurrence_appears_without_series_id(app):
    _event(
        app,
        "יום הולדת",
        date(2025, 10, 22),
        recurrence={
            "recurrence_freq": "yearly",
            "recurrence_calendar": "gregorian",
        },
    )
    _person(app, "דני", chat="42", daily_digest_enabled=True)
    with app.app_context():
        from app.reminders.repository import list_people

        people = {person["id"]: person for person in list_people()}
        text = format_digest([THURSDAY], people)
    assert "<b>יום הולדת</b>" in text
    assert "מזהה:" not in text


def test_process_scheduled_runs_digest_after_reminders(app, monkeypatch):
    import app.reminders.worker as worker

    calls = []
    monkeypatch.setattr(worker, "process_due_reminders", lambda **kwargs: calls.append(("due", kwargs)) or 0)
    monkeypatch.setattr(
        worker, "process_daily_digests", lambda **kwargs: calls.append(("digest", kwargs)) or 2
    )
    assert worker.process_scheduled(now=_at(THURSDAY, 6, 0), send=None, token="t") == 2
    assert [item[0] for item in calls] == ["due", "digest"]
