"""ה-endpoints החודשיים שהלוח האינסופי טוען (חודש = בקשה אחת לכל סוג נתונים)."""
import calendar
from datetime import date

import pytest


def test_jewish_month_keys_are_iso_dates_inside_the_month(client):
    response = client.get("/api/jewish-events/month/2025/3")
    assert response.status_code == 200
    body = response.get_json()
    assert body
    for key, events in body.items():
        parsed = date.fromisoformat(key)
        assert (parsed.year, parsed.month) == (2025, 3)
        assert events, f"{key} returned an empty list instead of being omitted"


def test_jewish_month_matches_per_day_endpoint(client):
    """אותו שירות מאחורי שני ה-endpoints — החודשי לא אמור לאבד או להמציא אירועים."""
    month_body = client.get("/api/jewish-events/month/2025/4").get_json()
    for day in range(1, calendar.monthrange(2025, 4)[1] + 1):
        key = date(2025, 4, day).isoformat()
        per_day = client.get(f"/api/jewish-events/{key}").get_json()
        assert month_body.get(key, []) == per_day, key


def test_jewish_month_contains_known_events(client):
    march = client.get("/api/jewish-events/month/2025/3").get_json()
    assert "פורים" in [e["name"] for e in march["2025-03-14"]]

    april = client.get("/api/jewish-events/month/2025/4").get_json()
    assert "פרשת ויקרא" in [e["name"] for e in april["2025-04-05"]]


@pytest.mark.parametrize("year, month", [(2025, 0), (2025, 13), (0, 5), (10000, 1)])
def test_jewish_month_rejects_invalid_year_or_month(client, year, month):
    response = client.get(f"/api/jewish-events/month/{year}/{month}")
    assert response.status_code == 400


def test_calendar_month_has_every_day_with_hebrew_data(client):
    response = client.get("/api/calendar/2026/7")
    assert response.status_code == 200
    days = [d for d in response.get_json()["calendar"] if d["gregorian_day"]]
    assert [d["gregorian_day"] for d in days] == list(range(1, 32))
    for day in days:
        assert day["hebrew_month"]
        assert day["hebrew_year"]
        assert day["is_hebrew_month_start"] == (day["hebrew_day"] == 1)
    # א' אב תשפ"ו = 15.7.2026 (ט' באב = 23.7.2026)
    first_of_av = next(d for d in days if d["is_hebrew_month_start"])
    assert (first_of_av["gregorian_day"], first_of_av["hebrew_month"]) == (15, "אב")


def test_calendar_leap_year_keeps_adar_numbering(client):
    """חודש 12 בשנה מעוברת = אדר א׳, חודש 13 = אדר ב׳. שנה פשוטה: «אדר»."""
    feb = [d for d in client.get("/api/calendar/2024/2").get_json()["calendar"] if d["gregorian_day"]]
    march = [d for d in client.get("/api/calendar/2024/3").get_json()["calendar"] if d["gregorian_day"]]
    assert next(d for d in feb if d["is_hebrew_month_start"])["hebrew_month"] == "אדר א׳"
    adar_ii = next(d for d in march if d["gregorian_day"] == 11)
    assert adar_ii["is_hebrew_month_start"]
    assert adar_ii["hebrew_month"] == "אדר ב׳"
    plain = [d for d in client.get("/api/calendar/2025/3").get_json()["calendar"] if d["gregorian_day"]]
    adar = next(d for d in plain if d["is_hebrew_month_start"] and d["hebrew_month"].startswith("אדר"))
    assert adar["hebrew_month"] == "אדר"
