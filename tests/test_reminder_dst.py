"""הפרש תזכורת במעבר שעון ישראל 2026 — דקות אמיתיות, תצוגה מקומית.

אביב: יום ו׳ 27.3.2026 בשעה 02:00 השעון קופץ ל-03:00 (חור 02:00–03:00).
סתיו: יום א׳ 25.10.2026 בשעה 02:00 השעון חוזר ל-01:00 (01:00–02:00 פעמיים).
``==`` על אותו ZoneInfo מתעלם מ-fold, לכן הבדיקות נועלות fold, utcoffset ו-UTC.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from app.reminders.schedule import (
    browser_body,
    event_start,
    fire_at,
    in_browser_window,
    is_due,
    occurrence_start,
    reminder_message,
)

TZ = ZoneInfo("Asia/Jerusalem")
UTC = timezone.utc

SPRING = "2026-03-27"
AUTUMN = "2026-10-25"


def _utc(moment: datetime) -> datetime:
    return moment.astimezone(UTC)


def _person(client, chat_id="555"):
    response = client.post(
        "/api/reminder-people",
        json={"name": "דני", "telegram_chat_id": chat_id},
    )
    assert response.status_code == 201
    return response.get_json()


def _event(client, person_id, **extra):
    payload = {
        "title": extra.pop("title", "מעבר שעון"),
        "hebrew_date": "א",
        "reminders": [{"offset_minutes": extra.pop("offset", 0), "recipient_ids": [person_id]}],
        **extra,
    }
    response = client.post("/api/events", json=payload)
    assert response.status_code == 200, response.get_json()
    return response.get_json()


def test_israel_2026_transition_dates():
    assert datetime(2026, 3, 27, 1, 0, tzinfo=TZ).utcoffset() == timedelta(hours=2)
    assert datetime(2026, 3, 27, 3, 0, tzinfo=TZ).utcoffset() == timedelta(hours=3)
    assert datetime(2026, 10, 25, 0, 30, tzinfo=TZ).utcoffset() == timedelta(hours=3)
    assert datetime(2026, 10, 25, 2, 30, tzinfo=TZ).utcoffset() == timedelta(hours=2)
    assert (
        datetime(2026, 10, 25, 1, 30, tzinfo=TZ, fold=0).utcoffset()
        != datetime(2026, 10, 25, 1, 30, tzinfo=TZ, fold=1).utcoffset()
    )


def test_autumn_offset_subtracts_real_minutes():
    """25.10 03:30 (אחרי החזרה, UTC+2) פחות שעתיים = 01:30 השני, לא הראשון."""
    start = event_start({"gregorian_date": AUTUMN, "time": "03:30"}, tz=TZ, default_time="09:00")
    fire = fire_at({"gregorian_date": AUTUMN, "time": "03:30"}, 120, tz=TZ, default_time="09:00")

    assert start.hour == 3 and start.minute == 30
    assert start.utcoffset() == timedelta(hours=2)
    assert fire.hour == 1 and fire.minute == 30
    assert fire.fold == 1
    assert fire.utcoffset() == timedelta(hours=2)
    assert _utc(start) - _utc(fire) == timedelta(hours=2)
    assert _utc(fire) == datetime(2026, 10, 24, 23, 30, tzinfo=UTC)
    # שעת הקיר הראשונה של 01:30 היא שעה מוקדם יותר — זו התזכורת השבורה
    assert _utc(fire) != _utc(datetime(2026, 10, 25, 1, 30, tzinfo=TZ, fold=0))

    text = reminder_message({"title": "חזרה", "hebrew_date": ""}, 120, start)
    assert "2026-10-25 03:30" in text
    assert "23:30" not in text


def test_spring_offset_subtracts_real_minutes():
    """27.3 04:00 (אחרי הקפיצה, UTC+3) פחות 3 שעות = 00:00, לא 01:00."""
    start = event_start({"gregorian_date": SPRING, "time": "04:00"}, tz=TZ, default_time="09:00")
    fire = fire_at({"gregorian_date": SPRING, "time": "04:00"}, 180, tz=TZ, default_time="09:00")

    assert start.utcoffset() == timedelta(hours=3)
    assert fire == datetime(2026, 3, 27, 0, 0, tzinfo=TZ)
    assert fire.utcoffset() == timedelta(hours=2)
    assert _utc(start) - _utc(fire) == timedelta(hours=3)
    assert _utc(fire) == datetime(2026, 3, 26, 22, 0, tzinfo=UTC)

    # 03:30 פחות 90 דקות נוחת בחור אם מחשבים שעון קיר (02:00). ב-UTC זו 01:00.
    into_gap = fire_at({"gregorian_date": SPRING, "time": "03:30"}, 90, tz=TZ, default_time="09:00")
    assert into_gap.hour == 1 and into_gap.minute == 0
    assert into_gap.utcoffset() == timedelta(hours=2)
    assert _utc(datetime(2026, 3, 27, 3, 30, tzinfo=TZ)) - _utc(into_gap) == timedelta(minutes=90)


def test_all_day_and_default_time_across_both_transitions():
    winter_morning = fire_at(
        {"gregorian_date": AUTUMN, "time": None}, 0, tz=TZ, default_time="09:00"
    )
    assert winter_morning.hour == 9 and winter_morning.minute == 0
    assert winter_morning.utcoffset() == timedelta(hours=2)

    autumn_eve = fire_at(
        {"gregorian_date": AUTUMN, "time": ""}, 720, tz=TZ, default_time="09:00"
    )
    assert autumn_eve == datetime(2026, 10, 24, 22, 0, tzinfo=TZ)
    assert autumn_eve.utcoffset() == timedelta(hours=3)
    assert _utc(winter_morning) - _utc(autumn_eve) == timedelta(hours=12)

    spring_morning = event_start({"gregorian_date": SPRING, "time": None}, tz=TZ, default_time="09:00")
    assert spring_morning.hour == 9
    assert spring_morning.utcoffset() == timedelta(hours=3)
    spring_eve = fire_at({"gregorian_date": SPRING, "time": None}, 720, tz=TZ, default_time="09:00")
    assert spring_eve == datetime(2026, 3, 26, 20, 0, tzinfo=TZ)
    assert spring_eve.utcoffset() == timedelta(hours=2)
    assert _utc(spring_morning) - _utc(spring_eve) == timedelta(hours=12)

    # ברירת מחדל שנפלה על השעה החסרה / הכפולה
    skipped = event_start({"gregorian_date": SPRING, "time": ""}, tz=TZ, default_time="02:30")
    assert skipped.hour == 3 and skipped.minute == 30
    assert skipped.utcoffset() == timedelta(hours=3)
    assert _utc(skipped) == datetime(2026, 3, 27, 0, 30, tzinfo=UTC)

    repeated = event_start({"gregorian_date": AUTUMN, "time": None}, tz=TZ, default_time="01:30")
    assert repeated.hour == 1 and repeated.minute == 30
    assert repeated.fold == 0
    assert repeated.utcoffset() == timedelta(hours=3)


def test_nonexistent_and_ambiguous_local_times():
    gap = event_start({"gregorian_date": SPRING, "time": "02:30"}, tz=TZ, default_time="09:00")
    assert gap.hour == 3 and gap.minute == 30 and gap.fold == 0
    assert gap.utcoffset() == timedelta(hours=3)
    edge = event_start({"gregorian_date": SPRING, "time": "02:00"}, tz=TZ, default_time="09:00")
    assert edge == datetime(2026, 3, 27, 3, 0, tzinfo=TZ)
    assert _utc(edge) == datetime(2026, 3, 27, 0, 0, tzinfo=UTC)

    # אירוע חד-פעמי לא זז גם אם now אחריו, והנרמול נשאר
    pinned = occurrence_start(
        {"gregorian_date": SPRING, "time": "02:30"},
        now=datetime(2030, 1, 1, tzinfo=TZ),
        tz=TZ,
        default_time="09:00",
    )
    assert pinned == gap

    first = event_start({"gregorian_date": AUTUMN, "time": "01:30"}, tz=TZ, default_time="09:00")
    assert first.fold == 0
    assert first.utcoffset() == timedelta(hours=3)
    assert _utc(first) == datetime(2026, 10, 24, 22, 30, tzinfo=UTC)
    # 02:00 כבר חד-משמעי (סוף השעה הכפולה)
    after = event_start({"gregorian_date": AUTUMN, "time": "02:00"}, tz=TZ, default_time="09:00")
    assert after.fold == 0
    assert after.utcoffset() == timedelta(hours=2)


def test_due_comparison_and_browser_window_use_utc():
    fire = datetime(2026, 10, 25, 1, 30, tzinfo=TZ, fold=1)
    first = datetime(2026, 10, 25, 1, 30, tzinfo=TZ, fold=0)
    # אותה שעת קיר, שעה אמיתית לפני — עדיין לא הגיע
    assert not is_due(fire, first, None)
    assert is_due(fire, datetime(2026, 10, 25, 1, 30, tzinfo=TZ, fold=1), None)
    assert is_due(fire, datetime(2026, 10, 24, 23, 30, tzinfo=UTC), None)
    assert not is_due(fire, datetime(2026, 10, 24, 23, 29, tzinfo=UTC), None)
    assert not is_due(fire, datetime(2026, 10, 25, 3, 0, tzinfo=TZ), "2026-10-24T23:30:00Z")

    assert not in_browser_window(fire, first, within_seconds=0, grace_seconds=0)
    assert not in_browser_window(fire, first, within_seconds=3599, grace_seconds=0)
    assert in_browser_window(fire, first, within_seconds=3600, grace_seconds=0)
    # 01:00 הראשון מול 01:30 השני: שעון הקיר אומר חצי שעה, בפועל שעה וחצי
    early_fire = datetime(2026, 10, 25, 1, 0, tzinfo=TZ, fold=0)
    later = datetime(2026, 10, 25, 1, 30, tzinfo=TZ, fold=1)
    assert not in_browser_window(early_fire, later, within_seconds=0, grace_seconds=30 * 60)
    assert in_browser_window(early_fire, later, within_seconds=0, grace_seconds=90 * 60)

    early = browser_body({"title": "x"}, 0, fire, fire, first)
    assert early.startswith("בקרוב")
    assert "01:30" in early
    on_time = browser_body({"title": "x"}, 0, fire, fire, fire)
    assert on_time.startswith("עכשיו")

    # אביב: 03:10 פחות שעתיים אמיתיות הוא 00:10, לא 01:10
    spring_fire = datetime(2026, 3, 27, 0, 5, tzinfo=TZ)
    spring_now = datetime(2026, 3, 27, 3, 10, tzinfo=TZ)
    assert not in_browser_window(spring_fire, spring_now, within_seconds=0, grace_seconds=2 * 3600)
    assert in_browser_window(
        spring_fire, spring_now, within_seconds=0, grace_seconds=2 * 3600 + 5 * 60
    )


def test_recurring_occurrences_across_both_transitions():
    autumn = {
        "gregorian_date": "2026-09-25",
        "time": "04:00",
        "recurrence_freq": "monthly",
        "recurrence_calendar": "gregorian",
        "recurrence_count": 3,
    }
    before_repeat = datetime(2026, 10, 25, 1, 0, tzinfo=TZ, fold=0)
    fire = fire_at(autumn, 180, now=before_repeat, tz=TZ, default_time="09:00")
    assert fire.day == 25 and fire.hour == 1 and fire.minute == 0
    assert fire.fold == 1
    assert fire.utcoffset() == timedelta(hours=2)
    assert _utc(datetime(2026, 10, 25, 4, 0, tzinfo=TZ)) - _utc(fire) == timedelta(hours=3)

    ambiguous = {
        "gregorian_date": "2026-09-25",
        "time": "01:30",
        "recurrence_freq": "monthly",
        "recurrence_calendar": "gregorian",
        "recurrence_count": 4,
    }
    passed = occurrence_start(
        ambiguous,
        now=datetime(2026, 10, 25, 1, 30, tzinfo=TZ, fold=1),
        tz=TZ,
        default_time="09:00",
    )
    assert passed.date().isoformat() == "2026-11-25"
    still_first = occurrence_start(
        ambiguous,
        now=datetime(2026, 10, 25, 1, 29, tzinfo=TZ, fold=0),
        tz=TZ,
        default_time="09:00",
    )
    assert still_first.date().isoformat() == AUTUMN
    assert still_first.fold == 0
    assert still_first.utcoffset() == timedelta(hours=3)

    spring = {
        "gregorian_date": "2026-02-27",
        "time": "04:00",
        "recurrence_freq": "monthly",
        "recurrence_calendar": "gregorian",
        "recurrence_count": 3,
    }
    spring_fire = fire_at(
        spring, 180, now=datetime(2026, 3, 26, 12, 0, tzinfo=TZ), tz=TZ, default_time="09:00"
    )
    assert spring_fire == datetime(2026, 3, 27, 0, 0, tzinfo=TZ)
    assert _utc(datetime(2026, 3, 27, 4, 0, tzinfo=TZ)) - _utc(spring_fire) == timedelta(hours=3)

    gap_series = {
        "gregorian_date": "2026-02-27",
        "time": "02:30",
        "recurrence_freq": "monthly",
        "recurrence_calendar": "gregorian",
        "recurrence_count": 3,
    }
    shifted = occurrence_start(
        gap_series,
        now=datetime(2026, 3, 27, 3, 0, tzinfo=TZ),
        tz=TZ,
        default_time="09:00",
    )
    assert shifted == datetime(2026, 3, 27, 3, 30, tzinfo=TZ)

    all_day = {
        "gregorian_date": "2026-09-25",
        "time": None,
        "recurrence_freq": "monthly",
        "recurrence_calendar": "gregorian",
        "recurrence_count": 3,
    }
    oct_default = fire_at(
        all_day, 0, now=datetime(2026, 10, 25, 8, 0, tzinfo=TZ), tz=TZ, default_time="09:00"
    )
    assert oct_default.month == 10 and oct_default.hour == 9
    assert oct_default.utcoffset() == timedelta(hours=2)
    oct_eve = fire_at(
        all_day, 720, now=datetime(2026, 10, 24, 12, 0, tzinfo=TZ), tz=TZ, default_time="09:00"
    )
    assert oct_eve == datetime(2026, 10, 24, 22, 0, tzinfo=TZ)
    assert oct_eve.utcoffset() == timedelta(hours=3)

    spring_all_day = {
        "gregorian_date": "2026-02-27",
        "time": None,
        "recurrence_freq": "monthly",
        "recurrence_calendar": "gregorian",
        "recurrence_count": 3,
    }
    spring_eve = fire_at(
        spring_all_day,
        720,
        now=datetime(2026, 3, 26, 12, 0, tzinfo=TZ),
        tz=TZ,
        default_time="09:00",
    )
    assert spring_eve == datetime(2026, 3, 26, 20, 0, tzinfo=TZ)
    assert spring_eve.utcoffset() == timedelta(hours=2)


def test_due_query_on_both_transitions_and_sent_at_stays_utc(client, app):
    from app.database import get_db
    from app.reminders.due import browser_due, telegram_due
    from app.reminders.repository import mark_reminder_sent
    from app.reminders.worker import process_due_reminders

    person = _person(client)
    _event(
        client,
        person["id"],
        title="אחרי החזרה",
        gregorian_date=AUTUMN,
        time="03:30",
        offset=120,
    )
    _event(
        client,
        person["id"],
        title="אחרי הקפיצה",
        gregorian_date=SPRING,
        time="04:00",
        offset=180,
    )
    _event(
        client,
        person["id"],
        title="כל היום סתיו",
        gregorian_date=AUTUMN,
        time=None,
        offset=720,
    )
    _event(
        client,
        person["id"],
        title="כל היום אביב",
        gregorian_date=SPRING,
        time=None,
        offset=720,
    )

    with app.app_context():
        # 01:30 הראשון הוא שעה לפני המועד האמיתי של "אחרי החזרה".
        # "כל היום סתיו" כבר נדלק ב-22:00 של הערב הקודם.
        early = telegram_due(now=datetime(2026, 10, 25, 1, 30, tzinfo=TZ, fold=0))
        assert all("אחרי החזרה" not in item["text"] for item in early)
        assert any("כל היום סתיו" in item["text"] for item in early)
        autumn = telegram_due(now=datetime(2026, 10, 25, 1, 30, tzinfo=TZ, fold=1))
        timed = next(item for item in autumn if "אחרי החזרה" in item["text"])
        assert timed["fire_at"].startswith("2026-10-25T01:30:00+02:00")
        assert "2026-10-25 03:30" in timed["text"]

        all_day = telegram_due(now=datetime(2026, 10, 24, 22, 0, tzinfo=TZ))
        assert [item["text"].split("\n", 1)[0] for item in all_day] == ["תזכורת: כל היום סתיו"]
        assert all_day[0]["fire_at"].startswith("2026-10-24T22:00:00+03:00")
        assert "2026-10-25 09:00" in all_day[0]["text"]
        assert telegram_due(now=datetime(2026, 10, 24, 21, 0, tzinfo=TZ)) == []

        hidden = browser_due(
            now=datetime(2026, 10, 25, 1, 30, tzinfo=TZ, fold=0),
            within_seconds=90,
            grace_seconds=900,
        )
        assert hidden == []
        shown = browser_due(
            now=datetime(2026, 10, 25, 1, 30, tzinfo=TZ, fold=1),
            within_seconds=0,
            grace_seconds=0,
        )
        assert [item["title"] for item in shown] == ["אחרי החזרה"]
        assert shown[0]["body"].startswith("עכשיו")
        assert "2026-10-25 03:30" in shown[0]["body"]

        mark_reminder_sent(
            timed["id"],
            datetime(2026, 10, 25, 1, 30, tzinfo=TZ, fold=1),
            occurrence_date=timed["occurrence_date"],
            chat_id="555",
        )
        stored = get_db().execute(
            "SELECT sent_at FROM reminder_sends WHERE reminder_id = ? AND chat_id = '555'",
            (timed["id"],),
        ).fetchone()["sent_at"]
        assert stored == "2026-10-24T23:30:00Z"
        left = telegram_due(now=datetime(2026, 10, 25, 1, 30, tzinfo=TZ, fold=1))
        assert all("אחרי החזרה" not in item["text"] for item in left)

        almost = telegram_due(now=datetime(2026, 3, 26, 23, 59, tzinfo=TZ))
        assert all("אחרי הקפיצה" not in item["text"] for item in almost)
        assert any("כל היום אביב" in item["text"] for item in almost)
        spring = telegram_due(now=datetime(2026, 3, 27, 0, 0, tzinfo=TZ))
        spring_titles = {item["text"].split("\n", 1)[0] for item in spring}
        assert spring_titles == {"תזכורת: אחרי הקפיצה", "תזכורת: כל היום אביב"}
        jump = next(item for item in spring if "אחרי הקפיצה" in item["text"])
        assert jump["fire_at"].startswith("2026-03-27T00:00:00+02:00")
        assert "2026-03-27 04:00" in jump["text"]
        day = next(item for item in spring if "כל היום אביב" in item["text"])
        assert day["fire_at"].startswith("2026-03-26T20:00:00+02:00")
        assert "2026-03-27 09:00" in day["text"]

        opened = browser_due(
            now=datetime(2026, 3, 27, 0, 0, tzinfo=TZ),
            within_seconds=0,
            grace_seconds=0,
        )
        assert [item["title"] for item in opened] == ["אחרי הקפיצה"]

        before = datetime.now(UTC) - timedelta(seconds=2)
        assert process_due_reminders(
            now=datetime(2026, 3, 27, 0, 0, tzinfo=TZ),
            send=lambda token, chat_id, text: True,
            token="t",
        ) == 2
        after = datetime.now(UTC) + timedelta(seconds=2)
        rows = get_db().execute(
            "SELECT sent_at FROM reminder_sends WHERE chat_id = '555' ORDER BY sent_at"
        ).fetchall()
        stamps = [row["sent_at"] for row in rows]
        assert stored in stamps
        fresh = [stamp for stamp in stamps if stamp != stored]
        assert len(fresh) == 2
        for stamp in fresh:
            assert stamp.endswith("Z")
            parsed = datetime.strptime(stamp, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)
            assert before <= parsed <= after
        assert telegram_due(now=datetime(2026, 3, 27, 0, 0, tzinfo=TZ)) == []


def test_recurring_due_across_dst(client, app):
    from app.reminders.due import telegram_due

    person = _person(client, chat_id="777")
    _event(
        client,
        person["id"],
        title="חודשי סתיו",
        gregorian_date="2026-09-25",
        time="04:00",
        offset=180,
        recurrence_freq="monthly",
        recurrence_calendar="gregorian",
        recurrence_count=3,
    )
    _event(
        client,
        person["id"],
        title="חודשי אביב",
        gregorian_date="2026-02-27",
        time="04:00",
        offset=180,
        recurrence_freq="monthly",
        recurrence_calendar="gregorian",
        recurrence_count=3,
    )
    _event(
        client,
        person["id"],
        title="חודשי בחור",
        gregorian_date="2026-02-27",
        time="02:30",
        offset=0,
        recurrence_freq="monthly",
        recurrence_calendar="gregorian",
        recurrence_count=3,
    )

    with app.app_context():
        assert telegram_due(now=datetime(2026, 10, 25, 1, 0, tzinfo=TZ, fold=0)) == []
        autumn = telegram_due(now=datetime(2026, 10, 25, 1, 0, tzinfo=TZ, fold=1))
        assert len(autumn) == 1
        assert autumn[0]["occurrence_date"] == AUTUMN
        assert autumn[0]["fire_at"].startswith("2026-10-25T01:00:00+02:00")
        assert "2026-10-25 04:00" in autumn[0]["text"]

        assert telegram_due(now=datetime(2026, 3, 26, 23, 59, tzinfo=TZ)) == []
        spring = telegram_due(now=datetime(2026, 3, 27, 0, 0, tzinfo=TZ))
        assert len(spring) == 1
        assert spring[0]["occurrence_date"] == SPRING
        assert "חודשי אביב" in spring[0]["text"]
        assert spring[0]["fire_at"].startswith("2026-03-27T00:00:00+02:00")

        pending = telegram_due(now=datetime(2026, 3, 27, 3, 29, tzinfo=TZ))
        assert all("חודשי בחור" not in item["text"] for item in pending)
        gap = telegram_due(now=datetime(2026, 3, 27, 3, 30, tzinfo=TZ))
        hole = next(item for item in gap if "חודשי בחור" in item["text"])
        assert "2026-03-27 03:30" in hole["text"]
        assert hole["fire_at"].startswith("2026-03-27T03:30:00+03:00")
