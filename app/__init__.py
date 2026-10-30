import mimetypes
import os

from flask import Flask, redirect, render_template, send_from_directory, url_for

mimetypes.add_type("application/manifest+json", ".webmanifest")

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover - optional dependency during bootstrap
    load_dotenv = None

from app.database import init_db, close_db

if load_dotenv is not None:
    load_dotenv()

app = Flask(__name__)
app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", "dev-secret-key-change-me")
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"

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
    from app.updates.version import installed_version

    return render_template('settings.html', app_version=installed_version())


@app.route("/favicon.ico")
def favicon():
    return send_from_directory(
        os.path.join(app.static_folder, "icons"),
        "favicon-32.png",
        mimetype="image/png",
    )


@app.route("/sw.js")
def service_worker():
    # מהשורש כדי ש-scope של ה-worker יהיה `/` (לא `/static/`).
    response = send_from_directory(app.static_folder, "sw.js")
    response.headers["Content-Type"] = "application/javascript; charset=utf-8"
    response.headers["Cache-Control"] = "no-cache"
    response.headers["Service-Worker-Allowed"] = "/"
    return response