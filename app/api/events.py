from flask import jsonify, request
from app.api import api
from app.database import create_event, get_event, get_all_events, update_event, delete_event, add_custom_color, get_all_colors
from datetime import datetime


@api.route('/events', methods=['GET'])
def get_events():
    events = get_all_events()
    return jsonify(events)

@api.route('/events/<int:event_id>', methods=['GET'])
def get_single_event(event_id):
    event = get_event(event_id)
    if event is None:
        return jsonify({"error": "Event not found"}), 404
    return jsonify(event)

@api.route('/events', methods=['POST'])
def add_event():
    data = request.get_json()
    print(f"Received data: {data}")  # לוג של המידע שהתקבל
    
    # בדיקת שדות חובה
    required_fields = ['title', 'gregorian_date', 'hebrew_date']
    missing_fields = [field for field in required_fields if field not in data]
    if missing_fields:
        print(f"Missing fields: {missing_fields}")  # לוג של שדות חסרים
        return jsonify({"error": f"Missing required fields: {missing_fields}", "success": False}), 400
    
    # טיפול בשדות אופציונליים
    time = data.get('time')
    if time == '':  # אם זה מחרוזת ריקה
        time = None
    
    try:
        success = create_event(
            title=data['title'],
            gregorian_date=data['gregorian_date'],
            hebrew_date=data['hebrew_date'],
            time=time,
            description=data.get('description', ''),
            end_date=data.get('end_date'),
            color=data.get('color')
        )
        
        if success:
            return jsonify({"success": True})
        else:
            print("Failed to create event in database")  # לוג של כישלון
            return jsonify({"error": "Failed to create event", "success": False}), 400
            
    except Exception as e:
        print(f"Error creating event: {str(e)}")  # לוג של שגיאות
        return jsonify({"error": f"Error creating event: {str(e)}", "success": False}), 400

@api.route('/events/<int:event_id>', methods=['PUT'])
def update_single_event(event_id):
    data = request.get_json()
    print(f"Updating event {event_id} with data: {data}")  # לוג של המידע שהתקבל
    
    # עדכון הולידציה - הסרת time מהשדות הנדרשים
    required_fields = ['title', 'gregorian_date', 'hebrew_date']
    missing_fields = [field for field in required_fields if field not in data]
    if missing_fields:
        print(f"Missing fields: {missing_fields}")  # לוג של שדות חסרים
        return jsonify({"error": f"Missing required fields: {missing_fields}", "success": False}), 400
    
    try:
        success = update_event(
            event_id,
            data['title'],
            data['gregorian_date'],
            data['hebrew_date'],
            data.get('time') or None,
            data.get('description', ''),
            data.get('end_date'),
            data.get('color')
        )
        
        if success:
            return jsonify({"success": True})
        else:
            print(f"Failed to update event {event_id}")  # לוג של כישלון
            return jsonify({"error": "Failed to update event", "success": False}), 400
            
    except Exception as e:
        print(f"Error updating event {event_id}: {str(e)}")  # לוג של שגיאות
        return jsonify({"error": f"Error updating event: {str(e)}", "success": False}), 400

@api.route('/events/<int:event_id>', methods=['DELETE'])
def delete_single_event(event_id):
    success = delete_event(event_id)
    if success:
        return jsonify({"success": True})
    return jsonify({"error": "Failed to delete event", "success": False}), 404

@api.route('/events/test', methods=['GET'])
def test_events():
    try:
        events = get_all_events()
        return jsonify({
            "status": "success",
            "message": "החיבור לדאטהבייס תקין",
            "events_count": len(events)
        })
    except Exception as e:
        return jsonify({
            "status": "error",
            "message": str(e)
        }), 500

@api.route('/colors', methods=['GET'])
def get_colors():
    colors = get_all_colors()
    return jsonify(colors)

@api.route('/colors', methods=['POST'])
def add_color():
    data = request.get_json()
    success = add_custom_color(
        data['name'],
        data['color_code'],
        data.get('background_color', f"rgba({data['color_code']}, 0.2)")
    )
    if success:
        return jsonify({"message": "Color added successfully"})
    return jsonify({"error": "Failed to add color"}), 400 