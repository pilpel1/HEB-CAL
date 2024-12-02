from flask import Blueprint, jsonify, request
from datetime import datetime
from convertdate import hebrew
import logging
from hebrew_numbers import int_to_gematria
import calendar
from app.services.jewish_calendar import JewishCalendarService


# הגדרת לוגים
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

api = Blueprint('api', __name__)

def get_hebrew_month_name(month_num):
    months = {
        1: 'ניסן',
        2: 'אייר',
        3: 'סיון',
        4: 'תמוז',
        5: 'אב',
        6: 'אלול',
        7: 'תשרי',
        8: 'חשון',
        9: 'כסלו',
        10: 'טבת',
        11: 'שבט',
        12: 'אדר',
        13: 'אדר ב'
    }
    return months.get(month_num, '')

def get_hebrew_day(day):
    days = {
        1: 'א', 2: 'ב', 3: 'ג', 4: 'ד', 5: 'ה', 6: 'ו', 7: 'ז', 8: 'ח', 9: 'ט', 10: 'י',
        11: 'יא', 12: 'יב', 13: 'יג', 14: 'יד', 15: 'טו', 16: 'טז', 17: 'יז', 18: 'יח', 19: 'יט', 20: 'כ',
        21: 'כא', 22: 'כב', 23: 'כג', 24: 'כד', 25: 'כה', 26: 'כו', 27: 'כז', 28: 'כח', 29: 'כט', 30: 'ל'
    }
    return days.get(day, '')

@api.route('/hebrew-date/<date_str>')
def get_hebrew_date(date_str):
    try:
        # המר את המחרוזת לאובייקט תאריך
        gregorian_date = datetime.strptime(date_str, '%Y-%m-%d')
        
        # המר לתאריך עברי
        heb_year, heb_month, heb_day = hebrew.from_gregorian(
            gregorian_date.year,
            gregorian_date.month,
            gregorian_date.day
        )
        
        # החזר את התאריך העברי כמחרוזת
        return jsonify({
            'hebrew_date': f"{get_hebrew_day(heb_day)} {get_hebrew_month_name(heb_month)} {heb_year}"
        })
    except Exception as e:
        logging.error(f"Error converting date {date_str}: {str(e)}")
        return jsonify({'error': str(e)}), 400

from app.api import events

@api.route('/calendar/<int:year>/<int:month>')
def get_calendar(year, month):
    # יצירת לוח שנה חדש
    cal = calendar.monthcalendar(year, month)
    
    # חישוב מספר הימים בחודש
    num_days = calendar.monthrange(year, month)[1]
    
    calendar_data = []
    hebrew_months_set = set()
    
    # הוספת ימים ריקים בהתחלה
    first_day = datetime(year, month, 1)
    padding_start = first_day.weekday()
    calendar_data = [{'gregorian_day': None}] * ((padding_start + 1) % 7)
    
    # מילוי הימים בחודש
    for day in range(1, num_days + 1):
        hebrew_date = hebrew.from_gregorian(year, month, day)
        hebrew_day = hebrew_date[2]
        hebrew_month_name = get_hebrew_month_name(hebrew_date[1])
        hebrew_months_set.add(hebrew_month_name)
        
        is_hebrew_month_start = hebrew_day == 1
        
        calendar_data.append({
            'gregorian_day': day,
            'hebrew_day': hebrew_day,
            'hebrew_month': hebrew_month_name if is_hebrew_month_start else '',
            'is_hebrew_month_start': is_hebrew_month_start
        })
    
    # הוספת ימים ריקים בסוף
    padding_end = 7 - (len(calendar_data) % 7)
    if padding_end < 7:
        calendar_data.extend([{'gregorian_day': None}] * padding_end)
    
    # הגדרת שמות חודשים לועזיים בעברית
    gregorian_months = {
        1: 'ינואר', 2: 'פברואר', 3: 'מרץ', 4: 'אפריל', 
        5: 'מאי', 6: 'יוני', 7: 'יולי', 8: 'אוגוסט',
        9: 'ספטמבר', 10: 'אוקטובר', 11: 'נובמבר', 12: 'דצמבר'
    }
    
    # קבלת השנה העברית מהיום הראשון של החודש
    first_day_hebrew = hebrew.from_gregorian(year, month, 1)
    hebrew_year = first_day_hebrew[0]
    
    # המרת השנה העברית למחרוזת (לדוגמה: תשפ"ה)
    hebrew_year_str = int_to_gematria(hebrew_year % 5000, gershayim=True)
    hebrew_year_str = 'ה' + "'" + hebrew_year_str  # הוספת ה' בהתחלה
    
    # מיון החודשים העבריים לפי הסדר הנכון
    hebrew_months_order = {
        'ניסן': 1, 'אייר': 2, 'סיון': 3, 'תמוז': 4, 'אב': 5, 'אלול': 6,
        'תשרי': 7, 'חשון': 8, 'כסלו': 9, 'טבת': 10, 'שבט': 11, 'אדר': 12, 'אדר ב': 13
    }
    sorted_hebrew_months = sorted(hebrew_months_set, key=lambda x: hebrew_months_order.get(x, 99))
    
    return jsonify({
        'calendar': calendar_data,
        'month_name': gregorian_months[month],
        'hebrew_months': sorted_hebrew_months,
        'hebrew_year': hebrew_year_str
    })

@api.route('/jewish-events/<date>')
def get_jewish_events(date):
    logger.debug(f"Starting get_jewish_events for date: {date}")
    try:
        # המרת התאריך מהמחרוזת לאובייקט תאריך
        try:
            date_obj = datetime.strptime(date, '%Y-%m-%d').date()
            logger.debug(f"Successfully parsed date: {date} to {date_obj}")
        except ValueError as e:
            logger.error(f"Error parsing date {date}: {str(e)}")
            return jsonify({'error': f'Invalid date format: {date}. Use YYYY-MM-DD'}), 400
        
        # קבלת האירועים היהודיים מהשירות
        logger.debug(f"Calling JewishCalendarService.get_all_jewish_events with {date_obj}")
        events = JewishCalendarService.get_all_jewish_events(date_obj)
        logger.debug(f"Found events for {date}: {events}")
        
        return jsonify(events)
    except Exception as e:
        logger.error(f"Unexpected error in get_jewish_events: {str(e)}", exc_info=True)
        return jsonify({'error': str(e)}), 500