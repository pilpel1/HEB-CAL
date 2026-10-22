import json
from datetime import date, datetime, timezone

from flask import jsonify, make_response, request

from . import api
from app.database import (
    add_custom_color,
    create_event,
    delete_event,
    export_data,
    get_all_colors,
    get_all_events,
    get_db,
    get_event,
    import_data,
    update_event,
    upsert_exception,
)
from app.reminders.repository import people_ids, replace_event_reminders
from app.reminders.schedule import OffsetError, parse_reminders_payload
from app.services.shifts import ShiftError, resolve_manual_shift
from app.services.recurrence import (
    RecurrenceError,
    clean_recurrence,
    expand_event,
    is_recurring,
    is_series_date,
    recurrence_fields,
)


REQUIRED_EVENT_FIELDS = ("title", "gregorian_date", "hebrew_date")


def _export_timestamp():
    """UTC stamp in the historical export shape ``YYYY-MM-DDTHH:MM:SSZ``.

    ``utcnow()`` is deprecated and naive. ``isoformat()`` on an aware UTC
    datetime writes ``+00:00``; existing export files use a trailing ``Z``.
    """
    return datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')


def _get_payload():
    return request.get_json(silent=True) or {}


def _validate_event_payload(data):
    missing_fields = [field for field in REQUIRED_EVENT_FIELDS if not data.get(field)]
    if missing_fields:
        return (
            jsonify({"error": f"Missing required fields: {missing_fields}", "success": False}),
            400,
        )

    end_date = data.get("end_date") or None
    gregorian_date = data.get("gregorian_date")
    if end_date:
        try:
            start = datetime.strptime(gregorian_date, "%Y-%m-%d").date()
            end = datetime.strptime(end_date, "%Y-%m-%d").date()
        except (TypeError, ValueError):
            return (
                jsonify({"error": "Invalid date format. Expected YYYY-MM-DD", "success": False}),
                400,
            )
        if end < start:
            return (
                jsonify({
                    "error": "תאריך הסיום חייב להיות זהה או מאוחר מתאריך ההתחלה",
                    "success": False,
                }),
                400,
            )

    return None


def _parse_range_date(value):
    try:
        return date.fromisoformat(value), None
    except (TypeError, ValueError):
        return None, (
            jsonify({"error": "Invalid date format. Expected YYYY-MM-DD", "success": False}),
            400,
        )


def _recurrence_from_payload(data, gregorian_date):
    """'keep' אם המפתח לא נשלח, None אם אין חזרה, dict אם יש."""
    if "recurrence_freq" not in data and not isinstance(data.get("recurrence"), dict):
        return "keep", None
    anchor = datetime.strptime(gregorian_date, "%Y-%m-%d").date()
    source = data["recurrence"] if isinstance(data.get("recurrence"), dict) and "recurrence_freq" not in data else data
    if "recurrence_freq" in data:
        freq = data.get("recurrence_freq")
        calendar_name = data.get("recurrence_calendar")
        until = data.get("recurrence_until")
        count = data.get("recurrence_count")
    else:
        freq = source.get("freq")
        calendar_name = source.get("calendar")
        until = source.get("until")
        count = source.get("count")
    try:
        return clean_recurrence(freq, calendar_name, until, count, anchor), None
    except RecurrenceError as exc:
        return None, (jsonify({"error": str(exc), "success": False}), 400)


def _identity_changed(old, gregorian_date, rule):
    if (old.get("gregorian_date") or "") != gregorian_date:
        return True
    old_rule = recurrence_fields(old)
    new_freq = None if rule is None or rule == "keep" else rule.get("recurrence_freq")
    new_cal = None if rule is None or rule == "keep" else rule.get("recurrence_calendar")
    if rule == "keep":
        return False
    return old_rule["recurrence_freq"] != new_freq or old_rule["recurrence_calendar"] != new_cal


def _serialize_rows(rows):
    return [dict(row) for row in rows]


def _manual_shift(data):
    """('keep' | tuple, data, error response).

    משמרת ידנית לא נבדקת מול הימים המותרים. בלי המפתחות — לא נוגעים בדגל.
    """
    try:
        resolved = resolve_manual_shift(data)
    except ShiftError as exc:
        return "keep", data, (jsonify({"error": str(exc), "success": False}), 400)
    if resolved is None:
        return "keep", data, None
    if not resolved["is_shift"]:
        return (0, None, None), data, None
    adjusted = dict(data)
    adjusted["title"] = resolved["title"]
    adjusted["color"] = resolved["color"]
    adjusted["time"] = None
    adjusted["end_date"] = None
    adjusted["recurrence_freq"] = None
    return (
        (1, resolved["shift_person_id"], resolved["shift_label"]),
        adjusted,
        None,
    )


def _parsed_reminders(data):
    """None = המפתח לא נשלח (בעדכון משאירים את הקיים). שגיאה = tuple של תשובה."""
    if "reminders" not in data:
        return None, None
    try:
        parsed = parse_reminders_payload(data.get("reminders"), people_ids())
    except OffsetError as exc:
        return None, (jsonify({"error": str(exc), "success": False}), 400)
    return parsed, None


def _load_import_payload():
    uploaded_file = request.files.get('file')
    if uploaded_file:
        try:
            return json.load(uploaded_file.stream)
        except json.JSONDecodeError as exc:
            raise ValueError("Uploaded file is not valid JSON") from exc

    payload = request.get_json(silent=True)
    if payload is None:
        raise ValueError("Missing JSON payload or uploaded file")
    return payload


@api.route('/events', methods=['GET'])
def get_events():
    """בלי from/to — שורות הסדרה (אירוע ישן = שורה אחת).

    עם from ו-to — מופעים שנוגעים בטווח, כולל חריגות.
    """
    start_raw = request.args.get("from") or request.args.get("start")
    end_raw = request.args.get("to") or request.args.get("end")
    if not start_raw and not end_raw:
        return jsonify(get_all_events())
    if not start_raw or not end_raw:
        return jsonify({"error": "from and to are both required", "success": False}), 400
    start, start_error = _parse_range_date(start_raw)
    if start_error:
        return start_error
    end, end_error = _parse_range_date(end_raw)
    if end_error:
        return end_error
    if end < start:
        return jsonify({"error": "to is before from", "success": False}), 400

    rows = []
    for event in get_all_events():
        rows.extend(expand_event(event, event.get("exceptions") or [], start, end))
    return jsonify(rows)


def _occurrence_payload(event, occurrence_date):
    """מופע אחד לעריכה, בתוספת ``series`` (השורת אב) כדי שאפשר לעבור ל"כל הסדרה"."""
    if not is_recurring(event):
        return event
    try:
        original = date.fromisoformat(occurrence_date)
    except ValueError:
        return None
    if not is_series_date(event, original):
        return None
    # המופע יכול היה לזוז לפני או אחרי תאריך המקור
    window_start = original
    window_end = original
    for ex in event.get("exceptions") or []:
        if (ex.get("original_date") or "")[:10] != occurrence_date:
            continue
        for key in ("gregorian_date", "end_date"):
            raw = ex.get(key)
            if not raw:
                continue
            try:
                moved = date.fromisoformat(raw[:10])
            except ValueError:
                continue
            window_start = min(window_start, moved)
            window_end = max(window_end, moved)
    matches = [
        row for row in expand_event(event, event.get("exceptions") or [], window_start, window_end)
        if row.get("occurrence_date") == occurrence_date
    ]
    if not matches:
        # נמחק
        return None
    payload = matches[0]
    payload["series"] = {
        key: event.get(key)
        for key in (
            "id", "title", "gregorian_date", "hebrew_date", "time", "description",
            "end_date", "color", "recurrence_freq", "recurrence_calendar",
            "recurrence_until", "recurrence_count", "reminders",
        )
    }
    return payload


@api.route('/events/<int:event_id>', methods=['GET'])
def get_single_event(event_id):
    event = get_event(event_id)
    if event is None:
        return jsonify({"error": "Event not found"}), 404
    occurrence_date = (request.args.get("occurrence_date") or "").strip()
    if occurrence_date:
        payload = _occurrence_payload(event, occurrence_date)
        if payload is None:
            return jsonify({"error": "Occurrence not found"}), 404
        return jsonify(payload)
    return jsonify(event)


@api.route('/events', methods=['POST'])
def add_event():
    data = _get_payload()
    validation_error = _validate_event_payload(data)
    if validation_error:
        return validation_error

    reminders, reminder_error = _parsed_reminders(data)
    if reminder_error:
        return reminder_error

    shift, data, shift_error = _manual_shift(data)
    if shift_error:
        return shift_error

    rule, recurrence_error = _recurrence_from_payload(data, data["gregorian_date"])
    if recurrence_error:
        return recurrence_error
    if rule == "keep" or (shift != "keep" and shift[0]):
        rule = None

    event_id = create_event(
        title=data['title'],
        gregorian_date=data['gregorian_date'],
        hebrew_date=data['hebrew_date'],
        time=data.get('time') or None,
        description=data.get('description', ''),
        end_date=data.get('end_date'),
        color=data.get('color'),
        recurrence=rule,
        shift=None if shift == "keep" else shift,
    )

    if event_id:
        replace_event_reminders(event_id, reminders or [])
        return jsonify({"success": True, "id": event_id})

    return jsonify({"error": "Failed to create event", "success": False}), 400


@api.route('/events/<int:event_id>', methods=['PUT'])
def update_single_event(event_id):
    data = _get_payload()
    validation_error = _validate_event_payload(data)
    if validation_error:
        return validation_error

    reminders, reminder_error = _parsed_reminders(data)
    if reminder_error:
        return reminder_error

    existing = get_event(event_id)
    if existing is None:
        return jsonify({"error": "Event not found", "success": False}), 404

    scope = (data.get("scope") or "all").strip()
    if scope == "occurrence" and data.get("is_shift"):
        return jsonify({"error": "משמרת נשמרת על האירוע כולו", "success": False}), 400
    if scope == "occurrence":
        if not is_recurring(existing):
            return jsonify({"error": "לאירוע אין חזרה", "success": False}), 400
        occurrence_date = (data.get("occurrence_date") or "").strip()
        try:
            original = date.fromisoformat(occurrence_date)
        except ValueError:
            return jsonify({"error": "חסר תאריך מופע", "success": False}), 400
        if not is_series_date(existing, original):
            return jsonify({"error": "התאריך אינו מופע בסדרה", "success": False}), 400
        end_date = data.get("end_date") or None
        if end_date:
            try:
                if date.fromisoformat(end_date) < date.fromisoformat(data["gregorian_date"]):
                    return jsonify({
                        "error": "תאריך הסיום חייב להיות זהה או מאוחר מתאריך ההתחלה",
                        "success": False,
                    }), 400
            except ValueError:
                return jsonify({"error": "Invalid date format. Expected YYYY-MM-DD", "success": False}), 400
        upsert_exception(
            event_id,
            occurrence_date,
            "edited",
            {
                "title": data["title"],
                "gregorian_date": data["gregorian_date"],
                "hebrew_date": data["hebrew_date"],
                "time": data.get("time") or None,
                "description": data.get("description", ""),
                "end_date": end_date,
                "color": data.get("color"),
            },
        )
        return jsonify({"success": True, "scope": "occurrence"})

    if scope != "all":
        return jsonify({"error": "scope חייב להיות all או occurrence", "success": False}), 400

    shift, data, shift_error = _manual_shift(data)
    if shift_error:
        return shift_error
    marking_shift = shift != "keep" and shift[0]

    rule, recurrence_error = _recurrence_from_payload(data, data["gregorian_date"])
    if recurrence_error:
        return recurrence_error
    if marking_shift:
        rule = None

    clear_exceptions = _identity_changed(existing, data["gregorian_date"], rule) or marking_shift
    success = update_event(
        event_id,
        data['title'],
        data['gregorian_date'],
        data['hebrew_date'],
        data.get('time') or None,
        data.get('description', ''),
        data.get('end_date'),
        data.get('color'),
        recurrence=rule,
        clear_exceptions=clear_exceptions,
        shift=shift,
    )

    if success:
        if reminders is not None:
            replace_event_reminders(event_id, reminders)
        return jsonify({"success": True})

    return jsonify({"error": "Failed to update event", "success": False}), 400


@api.route('/events/<int:event_id>', methods=['DELETE'])
def delete_single_event(event_id):
    scope = (request.args.get("scope") or "all").strip()
    if scope == "occurrence":
        existing = get_event(event_id)
        if existing is None:
            return jsonify({"error": "Event not found", "success": False}), 404
        if not is_recurring(existing):
            return jsonify({"error": "לאירוע אין חזרה", "success": False}), 400
        occurrence_date = (request.args.get("occurrence_date") or "").strip()
        try:
            original = date.fromisoformat(occurrence_date)
        except ValueError:
            return jsonify({"error": "חסר תאריך מופע", "success": False}), 400
        if not is_series_date(existing, original):
            return jsonify({"error": "התאריך אינו מופע בסדרה", "success": False}), 400
        upsert_exception(event_id, occurrence_date, "deleted", {"gregorian_date": occurrence_date})
        return jsonify({"success": True, "scope": "occurrence"})
    if scope != "all":
        return jsonify({"error": "scope חייב להיות all או occurrence", "success": False}), 400
    success = delete_event(event_id)
    if success:
        return jsonify({"success": True})
    return jsonify({"error": "Failed to delete event", "success": False}), 404


@api.route('/events/search')
def search_events():
    search_term = request.args.get('query', '').strip()
    db = get_db()
    rows = db.execute(
        '''
        SELECT * FROM events
        WHERE title LIKE ?
        ORDER BY gregorian_date
        ''',
        (f'%{search_term}%',),
    ).fetchall()
    return jsonify(_serialize_rows(rows))


@api.route('/events/advanced-search')
def advanced_search_events():
    raw_search_params = request.args.get('advanced_search', '')
    if not raw_search_params:
        return jsonify([])

    try:
        search_params = json.loads(raw_search_params)
    except json.JSONDecodeError:
        return jsonify({"error": "Invalid advanced_search payload"}), 400

    query = 'SELECT * FROM events WHERE 1=1'
    params = []

    if search_params.get('title'):
        query += ' AND title LIKE ?'
        params.append(f'%{search_params["title"]}%')

    if search_params.get('description'):
        query += ' AND description LIKE ?'
        params.append(f'%{search_params["description"]}%')

    if search_params.get('startDate'):
        query += ' AND (gregorian_date >= ? OR (end_date IS NOT NULL AND end_date >= ?))'
        params.extend([search_params['startDate'], search_params['startDate']])

    if search_params.get('endDate'):
        query += ' AND (gregorian_date <= ? OR (end_date IS NOT NULL AND gregorian_date <= ?))'
        params.extend([search_params['endDate'], search_params['endDate']])

    today = datetime.now().strftime('%Y-%m-%d')
    if search_params.get('timeFilter') == 'past':
        # סדרה שעדיין רצה לא נחשבת "עבר" רק כי העוגן כבר היה
        query += (
            ' AND (gregorian_date < ? AND (end_date IS NULL OR end_date < ?)'
            ' AND (recurrence_freq IS NULL OR recurrence_freq = \'\''
            ' OR (recurrence_until IS NOT NULL AND recurrence_until < ?)))'
        )
        params.extend([today, today, today])
    elif search_params.get('timeFilter') == 'future':
        query += (
            ' AND (gregorian_date >= ? OR (end_date IS NOT NULL AND end_date >= ?)'
            ' OR (recurrence_freq IS NOT NULL AND recurrence_freq != \'\''
            ' AND (recurrence_until IS NULL OR recurrence_until >= ?)))'
        )
        params.extend([today, today, today])

    if search_params.get('color'):
        if search_params['color'] == 'null':
            query += ' AND color IS NULL'
        else:
            query += ' AND color = ?'
            params.append(search_params['color'])

    query += ' ORDER BY gregorian_date'
    rows = get_db().execute(query, params).fetchall()
    return jsonify(_serialize_rows(rows))


@api.route('/events/test', methods=['GET'])
def test_events():
    try:
        events = get_all_events()
        return jsonify({
            "status": "success",
            "message": "החיבור לדאטהבייס תקין",
            "events_count": len(events),
        })
    except Exception as exc:
        return jsonify({
            "status": "error",
            "message": str(exc),
        }), 500


@api.route('/events/export', methods=['GET'])
def export_events():
    payload = {
        "version": 1,
        "exported_at": _export_timestamp(),
        **export_data(),
    }
    response = make_response(json.dumps(payload, ensure_ascii=False, indent=2))
    response.headers['Content-Type'] = 'application/json; charset=utf-8'
    response.headers['Content-Disposition'] = 'attachment; filename=heb-cal-events.json'
    return response


@api.route('/events/import', methods=['POST'])
def import_events():
    try:
        payload = _load_import_payload()
        mode = request.form.get('mode') or request.args.get('mode') or 'merge'
        result = import_data(payload, mode=mode)
        return jsonify(result)
    except ValueError as exc:
        return jsonify({"error": str(exc), "success": False}), 400


@api.route('/colors', methods=['GET'])
def get_colors():
    return jsonify(get_all_colors())


@api.route('/colors', methods=['POST'])
def add_color():
    data = _get_payload()
    if not data.get('name') or not data.get('color_code'):
        return jsonify({"error": "Missing required fields: ['name', 'color_code']"}), 400

    success = add_custom_color(
        data['name'],
        data['color_code'],
        data.get('background_color', f"rgba({data['color_code']}, 0.2)"),
    )
    if success:
        return jsonify({"message": "Color added successfully"})
    return jsonify({"error": "Failed to add color"}), 400