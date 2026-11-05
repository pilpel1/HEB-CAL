import json
from datetime import date, datetime, timezone

from flask import jsonify, make_response, request

from . import api
from app.database import (
    export_data,
    get_all_events,
    get_event,
    import_data,
)
from app.reminders.schedule import reminder_timezone
from app.services import event_ops
from app.services.event_ops import EventOpError
from app.services.recurrence import RecurrenceError, expand_event


def _export_timestamp():
    """UTC stamp in the historical export shape ``YYYY-MM-DDTHH:MM:SSZ``.

    ``utcnow()`` is deprecated and naive. ``isoformat()`` on an aware UTC
    datetime writes ``+00:00``; existing export files use a trailing ``Z``.
    """
    return datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')


def _get_payload():
    return request.get_json(silent=True) or {}


def _op_error(exc: EventOpError):
    return jsonify({"error": exc.message, "success": False}), exc.status


def _parse_range_date(value):
    try:
        return date.fromisoformat(value), None
    except (TypeError, ValueError):
        return None, (
            jsonify({"error": "Invalid date format. Expected YYYY-MM-DD", "success": False}),
            400,
        )


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
    return jsonify(event_ops.list_range(start, end))


@api.route('/events/<int:event_id>', methods=['GET'])
def get_single_event(event_id):
    event = get_event(event_id)
    if event is None:
        return jsonify({"error": "Event not found"}), 404
    occurrence_date = (request.args.get("occurrence_date") or "").strip()
    if occurrence_date:
        payload = event_ops.occurrence_payload(event, occurrence_date)
        if payload is None:
            return jsonify({"error": "Occurrence not found"}), 404
        return jsonify(payload)
    return jsonify(event)


@api.route('/events', methods=['POST'])
def add_event():
    try:
        event_id = event_ops.create(_get_payload())
    except EventOpError as exc:
        return _op_error(exc)
    return jsonify({"success": True, "id": event_id})


@api.route('/events/<int:event_id>', methods=['PUT'])
def update_single_event(event_id):
    try:
        result = event_ops.update(event_id, _get_payload())
    except EventOpError as exc:
        return _op_error(exc)
    if result["scope"] == "occurrence":
        return jsonify({"success": True, "scope": "occurrence"})
    return jsonify({"success": True})


@api.route('/events/<int:event_id>', methods=['DELETE'])
def delete_single_event(event_id):
    try:
        scope = event_ops.delete(
            event_id,
            request.args.get("scope") or "all",
            request.args.get("occurrence_date") or "",
        )
    except EventOpError as exc:
        return _op_error(exc)
    if scope == "occurrence":
        return jsonify({"success": True, "scope": "occurrence"})
    return jsonify({"success": True})


def _text_matches(value, needle):
    if not needle:
        return True
    return needle.casefold() in (value or "").casefold()


def _search_date(raw):
    if not raw:
        return None
    try:
        return date.fromisoformat(str(raw)[:10])
    except (TypeError, ValueError):
        return None


@api.route('/events/search')
def search_events():
    search_term = request.args.get('query', '').strip()
    events = [
        event for event in get_all_events()
        if not search_term or search_term.casefold() in (event.get("title") or "").casefold()
    ]
    return jsonify(events)


@api.route('/events/advanced-search')
def advanced_search_events():
    raw_search_params = request.args.get('advanced_search', '')
    if not raw_search_params:
        return jsonify([])

    try:
        search_params = json.loads(raw_search_params)
    except json.JSONDecodeError:
        return jsonify({"error": "Invalid advanced_search payload"}), 400

    title = (search_params.get("title") or "").strip()
    description = (search_params.get("description") or "").strip()
    color = search_params.get("color")
    range_from = _search_date(search_params.get("startDate"))
    range_to = _search_date(search_params.get("endDate"))
    time_filter = search_params.get("timeFilter")
    today = datetime.now(reminder_timezone()).date()

    events = []
    for event in get_all_events():
        if title and not _text_matches(event.get("title"), title):
            continue
        if description and not _text_matches(event.get("description"), description):
            continue
        if color:
            if color == "null":
                if event.get("color") is not None:
                    continue
            elif event.get("color") != color:
                continue
        events.append(event)

    if range_from or range_to:
        window_start = range_from or date.min
        window_end = range_to or date.max
        expanded = []
        for event in events:
            try:
                expanded.extend(
                    expand_event(event, event.get("exceptions") or [], window_start, window_end)
                )
            except RecurrenceError:
                continue
        events = expanded

    if time_filter == "past":
        kept = []
        for event in events:
            start = _search_date(event.get("gregorian_date"))
            end = _search_date(event.get("end_date")) or start
            until = _search_date(event.get("recurrence_until"))
            recurring = bool(event.get("recurrence_freq"))
            if recurring and not range_from and not range_to:
                if until and until < today and (not end or end < today) and start and start < today:
                    kept.append(event)
                continue
            if start and start < today and (not end or end < today):
                kept.append(event)
        events = kept
    elif time_filter == "future":
        kept = []
        for event in events:
            start = _search_date(event.get("gregorian_date"))
            end = _search_date(event.get("end_date")) or start
            until = _search_date(event.get("recurrence_until"))
            recurring = bool(event.get("recurrence_freq"))
            if recurring and not range_from and not range_to:
                if until is None or until >= today:
                    kept.append(event)
                continue
            if (start and start >= today) or (end and end >= today):
                kept.append(event)
        events = kept

    events.sort(key=lambda item: (item.get("gregorian_date") or "", item.get("time") or "", item.get("id") or 0))
    return jsonify(events)


@api.route('/events/test', methods=['GET'])
def test_events():
    try:
        events = get_all_events()
        return jsonify({
            "status": "success",
            "message": "החיבור תקין",
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

