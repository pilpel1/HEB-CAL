#!/bin/sh
# הפעלה מחדש בלי systemd ובלי sudo.
# מעתיקים לקובץ משלכם (לא את הדוגמה עצמה), ורושמים את הנתיב המלא ב-.env:
#   HEB_CAL_RESTART_COMMAND=/נתיב/מלא/scripts/restart.sh
# הסקריפט חייב לצאת אחרי שהתהליכים עלו. הוא לא נשאר בחזית.
# HEB_CAL_UPDATE_ACTION=stop  — רק עוצר (העדכון משתמש בזה לפני שחזור גיבוי).
set -eu
ROOT="$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
mkdir -p data logs
ACTION="${HEB_CAL_UPDATE_ACTION:-restart}"

stop_pid() {
    pidfile="$1"
    if [ ! -f "$pidfile" ]; then
        return 0
    fi
    pid="$(cat "$pidfile" 2>/dev/null || true)"
    if [ -n "${pid}" ]; then
        kill "$pid" 2>/dev/null || true
    fi
    rm -f "$pidfile"
}

stop_pid data/flask.pid
stop_pid data/worker.pid

if [ "$ACTION" = "stop" ]; then
    exit 0
fi

if [ -f .venv/bin/activate ]; then
    # shellcheck disable=SC1091
    . .venv/bin/activate
fi

# FLASK_DEBUG כבוי: רילודר של פיתוח מתבלבל בזמן עדכון קבצים.
nohup python -m flask --app app run --host 127.0.0.1 --port 5000 >> logs/flask.log 2>&1 &
echo $! > data/flask.pid
nohup python scripts/reminder_worker.py >> logs/worker.log 2>&1 &
echo $! > data/worker.pid
exit 0
