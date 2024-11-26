from flask import Flask, render_template, jsonify, request
from app.database import init_db, close_db
from datetime import datetime
import calendar
from pyluach import dates, hebrewcal

app = Flask(__name__)

# אתחול בסיס הנתונים
with app.app_context():
    init_db()

# רישום פונקציית הסגירה
app.teardown_appcontext(close_db)

# רישום ה-Blueprint של ה-API
from app.api import api
app.register_blueprint(api, url_prefix='/api')

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/add_event')
def add_event():
    return render_template('add_event.html')

@app.route('/events_list')
def events_list():
    return render_template('events_list.html')

def get_hebrew_month_name(month):
    hebrew_months = {
        1: 'תשרי',
        2: 'חשון',
        3: 'כסלו',
        4: 'טבת',
        5: 'שבט',
        6: 'אדר',
        7: 'ניסן',
        8: 'אייר',
        9: 'סיון',
        10: 'תמוז',
        11: 'אב',
        12: 'אלול',
        13: 'אדר א׳',
        14: 'אדר ב׳'
    }
    return hebrew_months.get(month, '')

# API Endpoints
@app.route('/api/calendar/<int:year>/<int:month>')
def get_calendar(year, month):
    # שמות חודשים בעברית
    hebrew_months = ['ינואר', 'פברואר', 'מרץ', 'אפריל', 'מאי', 'יוני', 
                    'יולי', 'אוגוסט', 'ספטמבר', 'אוקטובר', 'נובמבר', 'דצמבר']
    
    # קבלת לוח השנה הלועזי
    cal = calendar.monthcalendar(year, month)
    
    # מערך לשמירת כל הימים בחודש
    calendar_data = []
    
    for week in cal:
        for day in week:
            if day == 0:
                calendar_data.append({})
            else:
                # יצירת תאריך לועזי
                gregorian_date = dates.GregorianDate(year, month, day)
                
                # המרה לתאריך עברי
                hebrew_date = gregorian_date.to_heb()
                
                calendar_data.append({
                    'gregorian_day': day,
                    'hebrew_day': hebrew_date.day,
                    'hebrew_month': get_hebrew_month_name(hebrew_date.month),
                    'is_hebrew_month_start': hebrew_date.day == 1
                })
    
    # קבלת השנה העברית מהיום הראשון של החודש
    first_day = dates.GregorianDate(year, month, 1)
    hebrew_first_day = first_day.to_heb()
    
    return jsonify({
        'month_name': hebrew_months[month - 1],
        'hebrew_months': list(set(d.get('hebrew_month') for d in calendar_data if d.get('hebrew_month'))),
        'hebrew_year': hebrew_first_day.year,
        'calendar': calendar_data
    })

@app.route('/api/hebrew-date/<date>')
def get_hebrew_date(date):
    try:
        year, month, day = map(int, date.split('-'))
        gregorian_date = dates.GregorianDate(year, month, day)
        hebrew_date = gregorian_date.to_heb()
        return jsonify({
            'hebrew_date': f"{hebrew_date.day} {get_hebrew_month_name(hebrew_date.month)} {hebrew_date.year}"
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 400