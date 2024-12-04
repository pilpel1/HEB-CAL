from app.database import get_db
import logging

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

class EventService:
    @staticmethod
    def get_all_events():
        logger.debug("Getting all events")
        try:
            db = get_db()
            cursor = db.cursor()
            cursor.execute('SELECT * FROM events ORDER BY gregorian_date, time')
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
            logger.debug(f"Found {len(events_list)} events")
            return events_list
        except Exception as e:
            logger.error(f"Error getting all events: {str(e)}", exc_info=True)
            return []
    
    @staticmethod
    def get_event(event_id):
        logger.debug(f"Getting event {event_id}")
        try:
            db = get_db()
            cursor = db.cursor()
            cursor.execute('SELECT * FROM events WHERE id = ?', (event_id,))
            event = cursor.fetchone()
            if event:
                return {
                    'id': event[0],
                    'title': event[1],
                    'gregorian_date': event[2],
                    'hebrew_date': event[3],
                    'time': event[4],
                    'description': event[5],
                    'end_date': event[6],
                    'color': event[7]
                }
            return None
        except Exception as e:
            logger.error(f"Error getting event {event_id}: {str(e)}", exc_info=True)
            return None
    
    @staticmethod
    def create_event(event_data):
        logger.debug(f"Creating event: {event_data}")
        try:
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
            return True
        except Exception as e:
            logger.error(f"Error creating event: {str(e)}", exc_info=True)
            return False
    
    @staticmethod
    def update_event(event_id, event_data):
        logger.debug(f"Updating event {event_id}: {event_data}")
        try:
            db = get_db()
            cursor = db.cursor()
            cursor.execute('''
                UPDATE events
                SET title = ?, gregorian_date = ?, hebrew_date = ?, time = ?, description = ?, end_date = ?, color = ?
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
            return True
        except Exception as e:
            logger.error(f"Error updating event {event_id}: {str(e)}", exc_info=True)
            return False
    
    @staticmethod
    def delete_event(event_id):
        logger.debug(f"Deleting event {event_id}")
        try:
            db = get_db()
            cursor = db.cursor()
            cursor.execute('DELETE FROM events WHERE id = ?', (event_id,))
            db.commit()
            return True
        except Exception as e:
            logger.error(f"Error deleting event {event_id}: {str(e)}", exc_info=True)
            return False 