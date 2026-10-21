import json
from datetime import datetime, timezone

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


def _serialize_rows(rows):
    return [dict(row) for row in rows]


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
    return jsonify(get_all_events())


@api.route('/events/<int:event_id>', methods=['GET'])
def get_single_event(event_id):
    event = get_event(event_id)
    if event is None:
        return jsonify({"error": "Event not found"}), 404
    return jsonify(event)


@api.route('/events', methods=['POST'])
def add_event():
    data = _get_payload()
    validation_error = _validate_event_payload(data)
    if validation_error:
        return validation_error

    success = create_event(
        title=data['title'],
        gregorian_date=data['gregorian_date'],
        hebrew_date=data['hebrew_date'],
        time=data.get('time') or None,
        description=data.get('description', ''),
        end_date=data.get('end_date'),
        color=data.get('color'),
    )

    if success:
        return jsonify({"success": True})

    return jsonify({"error": "Failed to create event", "success": False}), 400


@api.route('/events/<int:event_id>', methods=['PUT'])
def update_single_event(event_id):
    data = _get_payload()
    validation_error = _validate_event_payload(data)
    if validation_error:
        return validation_error

    success = update_event(
        event_id,
        data['title'],
        data['gregorian_date'],
        data['hebrew_date'],
        data.get('time') or None,
        data.get('description', ''),
        data.get('end_date'),
        data.get('color'),
    )

    if success:
        return jsonify({"success": True})

    return jsonify({"error": "Failed to update event", "success": False}), 400


@api.route('/events/<int:event_id>', methods=['DELETE'])
def delete_single_event(event_id):
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
        query += ' AND (gregorian_date < ? AND (end_date IS NULL OR end_date < ?))'
        params.extend([today, today])
    elif search_params.get('timeFilter') == 'future':
        query += ' AND (gregorian_date >= ? OR (end_date IS NOT NULL AND end_date >= ?))'
        params.extend([today, today])

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