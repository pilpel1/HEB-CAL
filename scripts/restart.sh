#!/bin/sh
# הפעלה מחדש בלי סודות. HEB_CAL_RESTART_COMMAND=scripts/restart.sh
# אם יחידות systemd --user מותקנות: systemctl --user (בלי sudo) רק של המופע הזה.
# שם המופע: HEB_CAL_INSTANCE_NAME או data/instance.env, ברירת מחדל heb-cal.
# אחרת nohup, אחרי הריגת התהליכים הישנים של הריפו הזה (pidfile + pgrep לפי נתיב).
# כתובת ופורט: HEB_CAL_BIND_HOST / HEB_CAL_PORT (ברירת מחדל 127.0.0.1:5000).
# הסקריפט חייב לצאת אחרי שהתהליכים עלו. הוא לא נשאר בחזית.
# HEB_CAL_UPDATE_ACTION=stop  — רק עוצר (העדכון משתמש בזה לפני שחזור גיבוי).
set -eu
ROOT="$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
mkdir -p data logs

UNIT_DIR="${HEB_CAL_UNIT_DIR:-$HOME/.config/systemd/user}"

env_get() {
    name=$1
    default=$2
    eval "current=\${$name-}"
    if [ -n "${current}" ]; then
        printf '%s' "$current"
        return
    fi
    for file in data/instance.env .env; do
        if [ -f "$file" ]; then
            line=$(grep -E "^${name}=" "$file" | tail -n 1 || true)
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
    done
    printf '%s' "$default"
}

unit_working_directory() {
    unit=$1
    if [ ! -f "$unit" ]; then
        return 1
    fi
    line=$(grep -E '^WorkingDirectory=' "$unit" | tail -n 1 || true)
    [ -n "$line" ] || return 1
    value=${line#WorkingDirectory=}
    value=$(printf '%s' "$value" | tr -d '\r')
    case "$value" in
        \"*\") value=${value#\"}; value=${value%\"} ;;
        \'*\') value=${value#\'}; value=${value%\'} ;;
    esac
    printf '%s' "$value"
}

INSTANCE_NAME="$(env_get HEB_CAL_INSTANCE_NAME "")"
case "$INSTANCE_NAME" in
    [a-z]*[a-z0-9-]|[a-z]) ;;
    "") INSTANCE_NAME="" ;;
    *) INSTANCE_NAME="" ;;
esac
if [ -z "$INSTANCE_NAME" ]; then
    # שדרוג בלי instance.env: יחידה שכבר מצביעה לתיקייה הזו.
    for unit in "$UNIT_DIR"/*-web.service; do
        [ -f "$unit" ] || continue
        wd=$(unit_working_directory "$unit" || true)
        if [ "$wd" = "$ROOT" ]; then
            base=$(basename "$unit")
            INSTANCE_NAME=${base%-web.service}
            break
        fi
    done
fi
if [ -z "$INSTANCE_NAME" ]; then
    INSTANCE_NAME=heb-cal
fi
WEB_UNIT="${INSTANCE_NAME}-web.service"
WORKER_UNIT="${INSTANCE_NAME}-worker.service"

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

ensure_runtime_dir() {
    if [ -z "${XDG_RUNTIME_DIR:-}" ]; then
        uid=$(id -u)
        if [ -d "/run/user/$uid" ]; then
            XDG_RUNTIME_DIR="/run/user/$uid"
            export XDG_RUNTIME_DIR
        fi
    fi
}

systemd_user_units() {
    ensure_runtime_dir
    [ -f "$UNIT_DIR/$WEB_UNIT" ] && [ -f "$UNIT_DIR/$WORKER_UNIT" ]
}

kill_pid() {
    pid=$1
    if [ -z "$pid" ] || [ "$pid" = "$$" ]; then
        return 0
    fi
    kill "$pid" 2>/dev/null || return 0
    n=0
    while [ "$n" -lt 20 ]; do
        kill -0 "$pid" 2>/dev/null || return 0
        sleep 0.1
        n=$((n + 1))
    done
    kill -9 "$pid" 2>/dev/null || true
}

pid_is_ours() {
    pid=$1
    [ -n "$pid" ] || return 1
    [ "$pid" = "$$" ] && return 1
    cwd=$(readlink "/proc/$pid/cwd" 2>/dev/null || true)
    cmd=$(tr '\0' ' ' < "/proc/$pid/cmdline" 2>/dev/null || true)
    case "$cwd" in
        "$ROOT"|"$ROOT"/*) ;;
        *)
            case "$cmd" in
                *"$ROOT"*) ;;
                *) return 1 ;;
            esac
            ;;
    esac
    case "$cmd" in
        *flask*"--app"*app*run*|*scripts/reminder_worker.py*|*reminder_worker.py*|*app/main.py*) return 0 ;;
    esac
    return 1
}

stop_pidfile() {
    pidfile=$1
    if [ ! -f "$pidfile" ]; then
        return 0
    fi
    pid="$(cat "$pidfile" 2>/dev/null || true)"
    if [ -n "${pid}" ]; then
        kill_pid "$pid"
    fi
    rm -f "$pidfile"
}

stop_pattern() {
    pattern=$1
    if ! command -v pgrep >/dev/null 2>&1; then
        return 0
    fi
    pgrep -f "$pattern" 2>/dev/null | while IFS= read -r pid; do
        if pid_is_ours "$pid"; then
            kill_pid "$pid"
        fi
    done
}

stop_port() {
    port=$1
    pids=""
    if command -v lsof >/dev/null 2>&1; then
        pids=$(lsof -t -iTCP:"$port" -sTCP:LISTEN 2>/dev/null || true)
    elif command -v fuser >/dev/null 2>&1; then
        pids=$(fuser "${port}/tcp" 2>/dev/null || true)
    fi
    if [ -z "$pids" ]; then
        return 0
    fi
    # shellcheck disable=SC2086
    for pid in $pids; do
        if pid_is_ours "$pid"; then
            kill_pid "$pid"
        fi
    done
}

stop_repo_processes() {
    stop_pidfile data/flask.pid
    stop_pidfile data/worker.pid
    stop_pattern "$ROOT/scripts/reminder_worker.py"
    stop_pattern "scripts/reminder_worker.py"
    stop_pattern "flask --app app run"
    stop_port "$PORT"
}

if systemd_user_units; then
    systemctl --user stop "$WEB_UNIT" "$WORKER_UNIT" >/dev/null 2>&1 || true
    stop_repo_processes
    if [ "$ACTION" = "stop" ]; then
        exit 0
    fi
    if ! systemctl --user start "$WEB_UNIT" "$WORKER_UNIT"; then
        echo "systemctl --user start $WEB_UNIT $WORKER_UNIT failed" >&2
        exit 1
    fi
    exit 0
fi

stop_repo_processes

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
nohup "$PYTHON" -m flask --app app run --host "$HOST" --port "$PORT" --with-threads >> logs/flask.log 2>&1 &
echo $! > data/flask.pid
nohup "$PYTHON" scripts/reminder_worker.py >> logs/worker.log 2>&1 &
echo $! > data/worker.pid
exit 0
