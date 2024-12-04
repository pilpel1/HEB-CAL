from flask import Blueprint, jsonify, request
from datetime import datetime
from app.services.jewish_calendar import JewishCalendarService
from app.services.calendar_service import CalendarService

api = Blueprint('api', __name__)

@api.route('/calendar/<int:year>/<int:month>')
def get_calendar(year, month):
    try:
        calendar_data = CalendarService.get_calendar_data(year, month)
        return jsonify(calendar_data)
    except Exception as e:
        return jsonify({'error': str(e)}), 400

@api.route('/hebrew-date/<date>')
def get_hebrew_date(date):
    try:
        date_obj = datetime.strptime(date, '%Y-%m-%d')
        hebrew_date = JewishCalendarService.get_hebrew_date(date_obj)
        return jsonify({'hebrew_date': hebrew_date})
    except Exception as e:
        return jsonify({'error': str(e)}), 400 