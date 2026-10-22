"""המרה דו-כיוונית לבורר התאריך העברי במודל."""
from datetime import date

from pyluach.dates import HebrewDate

from app.services.hebrew_format import format_hebrew_year


def _gregorian(hebrew_date) -> str:
    greg = hebrew_date.to_greg()
    return date(greg.year, greg.month, greg.day).isoformat()


def test_screenshot_date_round_trips(client):
    forward = client.get("/api/hebrew-date/2026-10-28")
    assert forward.status_code == 200, forward.get_json()
    body = forward.get_json()
    assert body["gregorian_date"] == "2026-10-28"
    assert body["year"] == 5787
    assert body["month"] == 8
    assert body["day"] == 17
    assert body["leap"] is True
    assert "חשון" in body["hebrew_date"]
    assert format_hebrew_year(5787) in body["hebrew_date"]
    assert body["adjusted"] is False

    back = client.get(
        f"/api/gregorian-from-hebrew?year={body['year']}&month={body['month']}&day={body['day']}"
    )
    assert back.status_code == 200, back.get_json()
    assert back.get_json()["gregorian_date"] == "2026-10-28"
    assert back.get_json()["hebrew_date"] == body["hebrew_date"]


def test_leap_year_picker_lists_adar_one_and_two(client):
    response = client.get("/api/gregorian-from-hebrew?year=5787&month=13&day=14")
    assert response.status_code == 200, response.get_json()
    body = response.get_json()
    names = {item["value"]: item["name"] for item in body["months"]}
    assert names[12] == "אדר א׳"
    assert names[13] == "אדר ב׳"
    assert body["month"] == 13
    assert body["leap"] is True
    assert body["adjusted"] is False
    assert "אדר ב׳" in body["hebrew_date"]
    assert body["gregorian_date"] == _gregorian(HebrewDate(5787, 13, 14))

    adar_one = client.get("/api/gregorian-from-hebrew?year=5787&month=12&day=14")
    assert adar_one.get_json()["gregorian_date"] == _gregorian(HebrewDate(5787, 12, 14))
    assert "אדר א׳" in adar_one.get_json()["hebrew_date"]


def test_plain_year_has_single_adar_and_maps_adar_two(client):
    plain = client.get("/api/gregorian-from-hebrew?year=5786&month=12&day=14")
    assert plain.status_code == 200, plain.get_json()
    body = plain.get_json()
    names = [item["name"] for item in body["months"]]
    assert names[-1] == "אדר"
    assert "אדר א׳" not in names
    assert "אדר ב׳" not in names
    assert body["leap"] is False
    assert body["gregorian_date"] == _gregorian(HebrewDate(5786, 12, 14))

    moved = client.get("/api/gregorian-from-hebrew?year=5786&month=13&day=1")
    assert moved.status_code == 200, moved.get_json()
    shifted = moved.get_json()
    assert shifted["adjusted"] is True
    assert shifted["month"] == 12
    assert shifted["day"] == 1
    assert shifted["gregorian_date"] == _gregorian(HebrewDate(5786, 12, 1))
    assert all(item["value"] != 13 for item in shifted["months"])


def test_short_month_clamps_the_day(client):
    response = client.get("/api/gregorian-from-hebrew?year=5786&month=8&day=30")
    assert response.status_code == 200, response.get_json()
    body = response.get_json()
    assert body["adjusted"] is True
    assert body["day"] == 29
    assert body["days_in_month"] == 29
    assert body["gregorian_date"] == _gregorian(HebrewDate(5786, 8, 29))

    full = client.get("/api/gregorian-from-hebrew?year=5785&month=8&day=30")
    assert full.get_json()["adjusted"] is False
    assert full.get_json()["day"] == 30
    assert full.get_json()["days_in_month"] == 30


def test_hebrew_years_mark_leap_years(client):
    response = client.get("/api/hebrew-years?from=5784&to=5787")
    assert response.status_code == 200, response.get_json()
    years = {row["year"]: row for row in response.get_json()["years"]}
    assert [year for year in years if years[year]["leap"]] == [5784, 5787]
    assert years[5787]["label"] == format_hebrew_year(5787)
    assert client.get("/api/hebrew-years?from=5900&to=5700").status_code == 400
    assert client.get("/api/hebrew-years?from=1&to=900").status_code == 400


def test_bad_hebrew_parts_are_rejected(client):
    assert client.get("/api/gregorian-from-hebrew").status_code == 400
    assert client.get("/api/gregorian-from-hebrew?year=5786&month=0&day=1").status_code == 400
    assert client.get("/api/gregorian-from-hebrew?year=0&month=1&day=1").status_code == 400
    assert client.get("/api/gregorian-from-hebrew?year=5786&month=8&day=0").status_code == 400
    assert client.get("/api/hebrew-date/not-a-date").status_code == 400
    assert client.get("/api/hebrew-date/2026-02-31").status_code == 400
