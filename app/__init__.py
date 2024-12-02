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

# יבוא השירות של לוח השנה העברי
from app.services.jewish_calendar import JewishCalendarService

# רישום ה-Blueprint של ה-API
from app.api import api
app.register_blueprint(api, url_prefix='/api')

# טעינת הנתיבים
from app import routes

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/add_event')
def add_event():
    return render_template('add_event.html')

@app.route('/events_list')
def events_list():
    return render_template('events_list.html')