#!/bin/sh
# הפעלה מחדש בלי systemd ובלי sudo. בריפו, בלי סודות.
# HEB_CAL_RESTART_COMMAND=scripts/restart.sh
# כתובת ופורט: HEB_CAL_BIND_HOST (ברירת מחדל 127.0.0.1) ו-HEB_CAL_PORT (ברירת מחדל 5000).
# הסקריפט חייב לצאת אחרי שהתהליכים עלו. הוא לא נשאר בחזית.
# HEB_CAL_UPDATE_ACTION=stop  — רק עוצר (העדכון משתמש בזה לפני שחזור גיבוי).
set -eu
ROOT="$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
mkdir -p data logs

env_get() {
    name=$1
    default=$2
    eval "current=\${$name-}"
    if [ -n "${current}" ]; then
        printf '%s' "$current"
        return
    fi
    if [ -f .env ]; then
        line=$(grep -E "^${name}=" .env | tail -n 1 || true)
        if [ -n "$line" ]; then
            value=${line#*=}
            value=$(printf '%s' "$value" | tr -d '\r')
            case "$value" in
                \"*\") value=${value#\"}; value=${value%\"} ;;
                \'*\') value=${value#\'}; value=${value%\'} ;;
            esac
            printf '%s' "$value"
            return
        fi
    fi
    printf '%s' "$default"
}

HOST="$(env_get HEB_CAL_BIND_HOST 127.0.0.1)"
PORT="$(env_get HEB_CAL_PORT 5000)"
ACTION="${HEB_CAL_UPDATE_ACTION:-restart}"

case "$HOST" in
    *[!\.A-Za-z0-9:_\[\]-]*) HOST=127.0.0.1 ;;
    "") HOST=127.0.0.1 ;;
esac
case "$PORT" in
    ''|*[!0-9]*) PORT=5000 ;;
esac
if [ "$PORT" -lt 1 ] || [ "$PORT" -gt 65535 ]; then
    PORT=5000
fi

stop_pid() {
    pidfile=$1
    if [ ! -f "$pidfile" ]; then
        return 0
    fi
    pid="$(cat "$pidfile" 2>/dev/null || true)"
    if [ -n "${pid}" ]; then
        kill "$pid" 2>/dev/null || true
    fi
    rm -f "$pidfile"
}

stop_pattern() {
    pattern=$1
    if ! command -v pgrep >/dev/null 2>&1; then
        return 0
    fi
    pgrep -f "$pattern" 2>/dev/null | while IFS= read -r pid; do
        if [ -n "$pid" ] && [ "$pid" != "$$" ]; then
            kill "$pid" 2>/dev/null || true
        fi
    done
}

stop_port() {
    port=$1
    if command -v fuser >/dev/null 2>&1; then
        fuser -k "${port}/tcp" >/dev/null 2>&1 || true
        return
    fi
    if command -v lsof >/dev/null 2>&1; then
        pids=$(lsof -t -iTCP:"$port" -sTCP:LISTEN 2>/dev/null || true)
        if [ -n "$pids" ]; then
            # shellcheck disable=SC2086
            kill $pids 2>/dev/null || true
        fi
    fi
}

stop_pid data/flask.pid
stop_pid data/worker.pid
stop_pattern "$ROOT/scripts/reminder_worker.py"
stop_pattern "flask --app app run"
stop_port "$PORT"

if [ "$ACTION" = "stop" ]; then
    exit 0
fi

if [ -f .venv/bin/python ]; then
    PYTHON="$ROOT/.venv/bin/python"
elif command -v python3 >/dev/null 2>&1; then
    PYTHON=python3
else
    PYTHON=python
fi

# FLASK_DEBUG כבוי: רילודר של פיתוח מתבלבל בזמן עדכון קבצים.
export FLASK_DEBUG=0
nohup "$PYTHON" -m flask --app app run --host "$HOST" --port "$PORT" >> logs/flask.log 2>&1 &
echo $! > data/flask.pid
nohup "$PYTHON" scripts/reminder_worker.py >> logs/worker.log 2>&1 &
echo $! > data/worker.pid
exit 0
