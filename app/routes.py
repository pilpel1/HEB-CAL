from datetime import datetime
from flask import jsonify, request
from app import app
from app.services.jewish_calendar import JewishCalendarService
from app.database import get_db
import logging
import json


# הגדרת לוגים
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

@app.route('/api/jewish-events/<date>')
def get_jewish_events(date):
    try:
        logger.debug(f"Getting Jewish events for date: {date}")
        # המרת התאריך מהמחרוזת לאובייקט תאריך
        date_obj = datetime.strptime(date, '%Y-%m-%d')
        
        # קבלת האירועים היהודיים
        events = JewishCalendarService.get_all_jewish_events(date_obj)
        logger.debug(f"Found Jewish events: {events}")
        
        return jsonify(events)
    except Exception as e:
        logger.error(f"Error in get_jewish_events: {str(e)}", exc_info=True)
        return jsonify({'error': str(e)}), 400

@app.route('/api/events')
def get_events():
    try:
        db = get_db()
        cursor = db.cursor()
        cursor.execute('SELECT * FROM events')
        events = cursor.fetchall()
        
        # המרת השורות למילון
        events_list = []
        for event in events:
            events_list.append({
                'id': event[0],
                'title': event[1],
                'gregorian_date': event[2],
                'hebrew_date': event[3],
                'time': event[4],
                'description': event[5],
                'end_date': event[6],
                'color': event[7]
            })
        
        return jsonify(events_list)
    except Exception as e:
        print(f"Error in get_events: {str(e)}")
        return jsonify({'error': str(e)}), 400

@app.route('/api/events', methods=['POST'])
def create_event():
    try:
        event_data = request.json
        db = get_db()
        cursor = db.cursor()
        
        cursor.execute('''
            INSERT INTO events (title, gregorian_date, hebrew_date, time, description, end_date, color)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (
            event_data['title'],
            event_data['gregorian_date'],
            event_data['hebrew_date'],
            event_data.get('time'),
            event_data.get('description', ''),
            event_data.get('end_date'),
            event_data.get('color')
        ))
        
        db.commit()
        return jsonify({'success': True})
    except Exception as e:
        print(f"Error in create_event: {str(e)}")
        return jsonify({'error': str(e)}), 400

@app.route('/api/events/<int:event_id>', methods=['PUT'])
def update_event(event_id):
    try:
        event_data = request.json
        db = get_db()
        cursor = db.cursor()
        
        cursor.execute('''
            UPDATE events
            SET title = ?, gregorian_date = ?, hebrew_date = ?, 
                time = ?, description = ?, end_date = ?, color = ?
            WHERE id = ?
        ''', (
            event_data['title'],
            event_data['gregorian_date'],
            event_data['hebrew_date'],
            event_data.get('time'),
            event_data.get('description', ''),
            event_data.get('end_date'),
            event_data.get('color'),
            event_id
        ))
        
        db.commit()
        return jsonify({'success': True})
    except Exception as e:
        print(f"Error in update_event: {str(e)}")
        return jsonify({'error': str(e)}), 400

@app.route('/api/events/<int:event_id>', methods=['DELETE'])
def delete_event(event_id):
    try:
        db = get_db()
        cursor = db.cursor()
        cursor.execute('DELETE FROM events WHERE id = ?', (event_id,))
        db.commit()
        return jsonify({'success': True})
    except Exception as e:
        print(f"Error in delete_event: {str(e)}")
        return jsonify({'error': str(e)}), 400

@app.route('/api/events/search')
def search_events():
    try:
        search_term = request.args.get('query', '')
        db = get_db()
        cursor = db.cursor()
        
        # חיפוש בשם האירוע עם תמיכה בחיפוש חלקי
        cursor.execute('''
            SELECT * FROM events 
            WHERE title LIKE ? 
            ORDER BY gregorian_date
        ''', (f'%{search_term}%',))
        
        events = cursor.fetchall()
        
        events_list = []
        for event in events:
            events_list.append({
                'id': event[0],
                'title': event[1],
                'gregorian_date': event[2],
                'hebrew_date': event[3],
                'time': event[4],
                'description': event[5],
                'end_date': event[6],
                'color': event[7]
            })
        
        return jsonify(events_list)
    except Exception as e:
        logger.error(f"Error in search_events: {str(e)}", exc_info=True)
        return jsonify({'error': str(e)}), 400

@app.route('/api/events/advanced-search')
def advanced_search_events():
    try:
        # קבלת פרמטי החיפוש מה-query string
        search_params = request.args.get('advanced_search', '')
        if not search_params:
            return jsonify([])
            
        search_params = json.loads(search_params)
        
        db = get_db()
        cursor = db.cursor()
        
        # בניית שאילתת SQL דינמית
        query = 'SELECT * FROM events WHERE 1=1'
        params = []
        
        # חיפוש בכותרת
        if search_params.get('title'):
            query += ' AND title LIKE ?'
            params.append(f'%{search_params["title"]}%')
        
        # חיפוש בתיאור
        if search_params.get('description'):
            query += ' AND description LIKE ?'
            params.append(f'%{search_params["description"]}%')
        
        # חיפוש לפי תאריך התחלה
        if search_params.get('startDate'):
            query += ' AND (gregorian_date >= ? OR (end_date IS NOT NULL AND end_date >= ?))'
            params.extend([search_params['startDate'], search_params['startDate']])
        
        # חיפוש לפי תאריך סיום
        if search_params.get('endDate'):
            query += ' AND (gregorian_date <= ? OR (end_date IS NOT NULL AND gregorian_date <= ?))'
            params.extend([search_params['endDate'], search_params['endDate']])
        
        # סינון לפי זמן (עבר/עתיד)
        today = datetime.now().strftime('%Y-%m-%d')
        if search_params.get('timeFilter') == 'past':
            query += ' AND (gregorian_date < ? AND (end_date IS NULL OR end_date < ?))'
            params.extend([today, today])
        elif search_params.get('timeFilter') == 'future':
            query += ' AND (gregorian_date >= ? OR (end_date IS NOT NULL AND end_date >= ?))'
            params.extend([today, today])
        
        # חיפוש לפי צבע
        if search_params.get('color'):
            if search_params['color'] == 'null':
                query += ' AND color IS NULL'
            else:
                query += ' AND color = ?'
                params.append(search_params['color'])
        
        # הוספת מיון לפי תאריך
        query += ' ORDER BY gregorian_date'
        
        # ביצוע השאילתה
        cursor.execute(query, params)
        events = cursor.fetchall()
        
        # המרת התוצאות למילון
        events_list = []
        for event in events:
            events_list.append({
                'id': event[0],
                'title': event[1],
                'gregorian_date': event[2],
                'hebrew_date': event[3],
                'time': event[4],
                'description': event[5],
                'end_date': event[6],
                'color': event[7]
            })
        
        return jsonify(events_list)
        
    except Exception as e:
        logger.error(f"Error in advanced_search_events: {str(e)}", exc_info=True)
        return jsonify({'error': str(e)}), 400