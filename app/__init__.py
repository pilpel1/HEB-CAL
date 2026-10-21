import os

from flask import Flask, redirect, render_template, url_for

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover - optional dependency during bootstrap
    load_dotenv = None

from app.database import init_db, close_db

if load_dotenv is not None:
    load_dotenv()

app = Flask(__name__)
app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", "dev-secret-key-change-me")

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
    # הדף הישן הוחלף במודל המשותף — סימניות ישנות מגיעות לניהול אירועים
    return redirect(url_for('events_list'))

@app.route('/events_list')
def events_list():
    return render_template('events_list.html')

@app.route('/settings')
def settings():
    return render_template('settings.html')