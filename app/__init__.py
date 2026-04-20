import os

from flask import Flask, render_template

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
    return render_template('add_event.html')

@app.route('/events_list')
def events_list():
    return render_template('events_list.html')