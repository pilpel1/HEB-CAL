"""CRUD לצבעי אירועים: HEX, רקע בהיר, ברירות מחדל, ומחיקה בשימוש."""
from pathlib import Path

from app.services.colors import light_background_from_hex, normalize_hex, parse_hex_rgb

REPO = Path(__file__).resolve().parent.parent
SAMPLE_EVENT = {
    "title": "אירוע צבע",
    "gregorian_date": "2025-03-14",
    "hebrew_date": "י״ד אדר 5785",
    "time": "10:30",
    "description": "",
}


def test_light_background_from_hex_uses_rgb_channels():
    assert parse_hex_rgb("#ff8800") == (255, 136, 0)
    assert normalize_hex("#F80") == "#ff8800"
    assert light_background_from_hex("#ff8800") == "rgba(255, 136, 0, 0.2)"
    assert light_background_from_hex("00ffcc") == "rgba(0, 255, 204, 0.2)"
    assert "rgba(#" not in light_background_from_hex("#8800ff")


def test_get_colors_includes_four_defaults(client):
    colors = client.get("/api/colors").get_json()
    codes = {row["color_code"]: row for row in colors}
    assert set(codes) >= {"cyan", "yellow", "orange", "green"}
    for code in ("cyan", "yellow", "orange", "green"):
        assert codes[code]["is_default"] is True
        assert codes[code]["name"]
        assert codes[code]["background_color"].startswith("rgba(")


def test_post_color_computes_rgba_background_and_ignores_broken_client_value(client):
    created = client.post(
        "/api/colors",
        json={
            "name": "סגול",
            "color_code": "#8800ff",
            "background_color": "rgba(#8800ff, 0.2)",
        },
    )
    assert created.status_code == 201
    body = created.get_json()
    assert body["name"] == "סגול"
    assert body["color_code"] == "#8800ff"
    assert body["background_color"] == "rgba(136, 0, 255, 0.2)"
    assert "rgba(#" not in body["background_color"]
    assert body["is_default"] is False

    listed = client.get("/api/colors").get_json()
    assert any(row["id"] == body["id"] and row["color_code"] == "#8800ff" for row in listed)


def test_post_color_normalizes_short_hex(client):
    created = client.post("/api/colors", json={"name": "ורוד", "color_code": "#f0c"})
    assert created.status_code == 201
    body = created.get_json()
    assert body["color_code"] == "#ff00cc"
    assert body["background_color"] == "rgba(255, 0, 204, 0.2)"


def test_post_color_rejects_empty_name_and_invalid_hex(client):
    empty = client.post("/api/colors", json={"name": "   ", "color_code": "#ff8800"})
    assert empty.status_code == 400
    assert "שם" in empty.get_json()["error"]

    missing = client.post("/api/colors", json={"color_code": "#ff8800"})
    assert missing.status_code == 400

    bad_hex = client.post("/api/colors", json={"name": "שבור", "color_code": "not-a-color"})
    assert bad_hex.status_code == 400
    assert "HEX" in bad_hex.get_json()["error"]

    hash_in_rgba = client.post(
        "/api/colors", json={"name": "שבור2", "color_code": "rgba(#ff0000, 0.2)"}
    )
    assert hash_in_rgba.status_code == 400


def test_post_color_rejects_duplicate_name_or_code(client):
    first = client.post("/api/colors", json={"name": "טורקיז", "color_code": "#40e0d0"})
    assert first.status_code == 201
    dup_name = client.post("/api/colors", json={"name": "טורקיז", "color_code": "#41e0d0"})
    assert dup_name.status_code == 400
    dup_code = client.post("/api/colors", json={"name": "טורקיז אחר", "color_code": "#40E0D0"})
    assert dup_code.status_code == 400
    default_name = client.post("/api/colors", json={"name": "ציאן", "color_code": "#123456"})
    assert default_name.status_code == 400


def test_cannot_delete_default_color(client):
    colors = client.get("/api/colors").get_json()
    cyan = next(row for row in colors if row["color_code"] == "cyan")
    deleted = client.delete(f"/api/colors/{cyan['id']}")
    assert deleted.status_code == 400
    assert "ברירת מחדל" in deleted.get_json()["error"]
    still = client.get(f"/api/colors/{cyan['id']}")
    assert still.status_code == 200


def test_cannot_change_default_color_code(client):
    colors = client.get("/api/colors").get_json()
    green = next(row for row in colors if row["color_code"] == "green")
    updated = client.put(
        f"/api/colors/{green['id']}",
        json={"name": "ירוק", "color_code": "#00aa00"},
    )
    assert updated.status_code == 400
    after = client.get(f"/api/colors/{green['id']}").get_json()
    assert after["color_code"] == "green"


def test_edit_and_delete_unused_custom_color(client):
    created = client.post("/api/colors", json={"name": "חום", "color_code": "#8b4513"})
    assert created.status_code == 201
    color_id = created.get_json()["id"]

    updated = client.put(
        f"/api/colors/{color_id}",
        json={"name": "חום כהה", "color_code": "#5c3310"},
    )
    assert updated.status_code == 200
    body = updated.get_json()
    assert body["name"] == "חום כהה"
    assert body["color_code"] == "#5c3310"
    assert body["background_color"] == "rgba(92, 51, 16, 0.2)"

    deleted = client.delete(f"/api/colors/{color_id}")
    assert deleted.status_code == 200
    assert deleted.get_json()["success"] is True
    missing = client.get(f"/api/colors/{color_id}")
    assert missing.status_code == 404


def test_delete_color_in_use_is_blocked(client):
    created = client.post("/api/colors", json={"name": "ליים", "color_code": "#b4ff00"})
    hex_code = created.get_json()["color_code"]
    color_id = created.get_json()["id"]

    event = client.post("/api/events", json={**SAMPLE_EVENT, "color": hex_code})
    assert event.status_code == 200

    blocked = client.delete(f"/api/colors/{color_id}")
    assert blocked.status_code == 400
    assert "שימוש" in blocked.get_json()["error"]
    assert client.get(f"/api/colors/{color_id}").status_code == 200


def test_edit_custom_hex_retargets_existing_events(client):
    created = client.post("/api/colors", json={"name": "נייבי", "color_code": "#001f5b"})
    color_id = created.get_json()["id"]
    old_code = created.get_json()["color_code"]
    event = client.post("/api/events", json={**SAMPLE_EVENT, "color": old_code})
    assert event.status_code == 200
    events = client.get("/api/events").get_json()
    event_id = next(row["id"] for row in events if row["title"] == SAMPLE_EVENT["title"])

    updated = client.put(
        f"/api/colors/{color_id}",
        json={"name": "נייבי", "color_code": "#002266"},
    )
    assert updated.status_code == 200
    after = client.get(f"/api/events/{event_id}").get_json()
    assert after["color"] == "#002266"


def test_event_can_use_new_custom_color(client):
    created = client.post("/api/colors", json={"name": "זהב", "color_code": "#d4af37"})
    hex_code = created.get_json()["color_code"]
    event = client.post("/api/events", json={**SAMPLE_EVENT, "color": hex_code})
    assert event.status_code == 200
    stored = client.get("/api/events").get_json()
    match = next(row for row in stored if row["title"] == SAMPLE_EVENT["title"])
    assert match["color"] == "#d4af37"


def test_missing_color_is_404(client):
    assert client.get("/api/colors/999999").status_code == 404
    deleted = client.delete("/api/colors/999999")
    assert deleted.status_code == 404
    updated = client.put("/api/colors/999999", json={"name": "אין", "color_code": "#123456"})
    assert updated.status_code == 404


def test_get_colors_is_not_cached(client):
    response = client.get("/api/colors")
    assert response.status_code == 200
    assert response.headers["Cache-Control"] == "no-store"


def test_color_pickers_share_one_palette_source(client):
    settings = client.get("/settings").get_data(as_text=True)
    picker = settings.split('id="personColorPicker"', 1)[1].split("</div>", 1)[0]
    assert "is-none" in picker
    assert "color-cyan" not in picker
    assert 'data-color="orange"' not in picker
    assert 'data-color="green"' not in picker

    js = (REPO / "app/static/js/events/event-colors.js").read_text(encoding="utf-8")
    assert "cache: 'no-store'" in js
    assert "eventColorLoadSeq" in js
    assert "function paintColorPicker" in js
    assert "personColorPicker" in js
    assert "paintPersonColorSwatches" in js
    assert "colorsForPicker" in js

    shifts = (REPO / "app/static/js/events/shifts.js").read_text(encoding="utf-8")
    assert "paletteColorCodes()" in shifts
    assert "function applyShiftColorDot" in shifts
    assert "eventColorSwatchCss" in shifts
    assert "color-${" not in shifts

    listing = (REPO / "app/templates/events_list.html").read_text(encoding="utf-8")
    assert "eventColorName" in listing


def test_event_form_gets_colors_from_api_not_hardcoded_swatches(client):
    modal = (REPO / "app/templates/partials/quick_event_modal.html").read_text(
        encoding="utf-8"
    )
    assert 'class="quick-color-swatch is-none is-selected"' in modal
    assert "color-cyan" not in modal
    home = client.get("/").get_data(as_text=True)
    listing = client.get("/events_list").get_data(as_text=True)
    assert "js/events/event-colors.js" in home
    assert "js/events/event-colors.js" in listing
    js = (REPO / "app/static/js/events/event-colors.js").read_text(encoding="utf-8")
    assert "paintEventFormSwatches" in js
    assert "/api/colors" in js
    api_src = (REPO / "app/api/colors.py").read_text(encoding="utf-8")
    assert "rgba({" not in api_src
    assert "light_background_from_hex" in (REPO / "app/services/colors.py").read_text(
        encoding="utf-8"
    )
