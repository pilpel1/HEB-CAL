#!/usr/bin/env bash
# התקנת יחידות systemd --user ל-HEB-CAL (Flask + reminder_worker) על Linux.
# אידמפוטנטי. בלי סודות בקבצי היחידה. לא דורש sudo אחרי linger.
# מופע נוסף בתיקייה אחרת: ./scripts/install_services.sh [--name heb-cal2] [--port 5001] [--tailscale-serve]
# בלי --name: אם יש שם שמור ב-data/instance.env משתמשים בו; אחרת heb-cal, או heb-cal2... אם heb-cal תפוס בתיקייה אחרת.
set -euo pipefail

TEMPLATE_WEB=heb-cal-web.service
TEMPLATE_WORKER=heb-cal-worker.service
TEMPLATE_SOCKET=heb-cal-web.socket

say() { printf '%s\n' "$*"; }
die() { printf '%s\n' "$*" >&2; exit 1; }

usage() {
  cat <<'EOF'
התקנת יחידות systemd --user ל-HEB-CAL.

  ./scripts/install_services.sh [--name NAME] [--port PORT] [--tailscale-serve] [--units-only]

  --name NAME          שם המופע (יחידות NAME-web / NAME-worker / NAME-web.socket). ברירת מחדל: heb-cal
  --port PORT          פורט TCP הציבורי של Flask. ברירת מחדל למופע הראשון: 5000
  --tailscale-serve    מיפוי HTTPS ב-Tailscale ל-localhost:PORT בלי לגעת במיפויים קיימים
  --units-only         רק כותב/מפעיל יחידות (כולל socket), בלי עצירה/הפעלה ובלי Tailscale.
                       לעדכון מהממשק: הפורט נשאר זה שב-data/instance.env, בלי פורט שני.

בלי דגלים, אם יש data/instance.env משתמשים בשם ובפורט השמורים.
אם heb-cal כבר מותקן לתיקייה אחרת — נבחר heb-cal2, heb-cal3... ופורט פנוי מ-5001.
EOF
}

ROOT="$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

NAME_FLAG=""
PORT_FLAG=""
TAILSCALE_SERVE=0
UNITS_ONLY=0
while [[ $# -gt 0 ]]; do
  case "$1" in
    -h|--help)
      usage
      exit 0
      ;;
    --units-only)
      UNITS_ONLY=1
      shift
      ;;
    --name)
      [[ $# -ge 2 ]] || die "חסר ערך ל--name"
      NAME_FLAG=$2
      shift 2
      ;;
    --name=*)
      NAME_FLAG=${1#*=}
      shift
      ;;
    --port)
      [[ $# -ge 2 ]] || die "חסר ערך ל--port"
      PORT_FLAG=$2
      shift 2
      ;;
    --port=*)
      PORT_FLAG=${1#*=}
      shift
      ;;
    --tailscale-serve)
      TAILSCALE_SERVE=1
      shift
      ;;
    *)
      die "ארגומנט לא מוכר: $1 (ראו --help)"
      ;;
  esac
done

if [[ -f /.dockerenv ]]; then
  die "רצים בתוך Docker. היחידות האלה מיועדות להרצה עם venv על המארח, לא בקונטיינר."
fi

command -v systemctl >/dev/null 2>&1 || die "אין systemctl. צריך systemd."

USER_NAME=$(id -un)
UNIT_DIR="${HEB_CAL_UNIT_DIR:-$HOME/.config/systemd/user}"
TEMPLATE_DIR="$ROOT/deploy/systemd"
SELECT_PY="$ROOT/scripts/instance_select.py"

[[ -f "$TEMPLATE_DIR/$TEMPLATE_WEB" ]] || die "חסרה התבנית $TEMPLATE_DIR/$TEMPLATE_WEB"
[[ -f "$TEMPLATE_DIR/$TEMPLATE_WORKER" ]] || die "חסרה התבנית $TEMPLATE_DIR/$TEMPLATE_WORKER"
[[ -f "$TEMPLATE_DIR/$TEMPLATE_SOCKET" ]] || die "חסרה התבנית $TEMPLATE_DIR/$TEMPLATE_SOCKET"
[[ -f "$SELECT_PY" ]] || die "חסר $SELECT_PY"

if [[ "$ROOT" == *$'\n'* || "$ROOT" == *'"'* || "$ROOT" == *'@'* ]]; then
  die "נתיב הריפו לא מתאים ליחידת systemd."
fi

env_get() {
  local name=$1 default=$2 current line value
  eval "current=\${$name-}"
  if [[ -n "${current}" ]]; then
    printf '%s' "$current"
    return
  fi
  for file in data/instance.env .env; do
    if [[ -f "$file" ]]; then
      line=$(grep -E "^${name}=" "$file" | tail -n 1 || true)
      if [[ -n "$line" ]]; then
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

env_set() {
  local file=$1 key=$2 value=$3 tmp
  if [[ ! -f "$file" ]]; then
    return 0
  fi
  tmp=$(mktemp)
  awk -v k="$key" -v v="$value" '
    { sub(/\r$/, "") }
    index($0, k "=") == 1 { print k "=" v; seen=1; next }
    { print }
    END { if (!seen) print k "=" v }
  ' "$file" >"$tmp"
  mv "$tmp" "$file"
  if [[ "$file" == ".env" ]]; then
    chmod 600 "$file" 2>/dev/null || true
  fi
}

if [[ -x "$ROOT/.venv/bin/python" ]]; then
  PYTHON="$ROOT/.venv/bin/python"
elif command -v python3 >/dev/null 2>&1; then
  PYTHON=$(command -v python3)
else
  die "אין Python. צריך .venv ב-$ROOT או python3 ב-PATH."
fi

HOST="$(env_get HEB_CAL_BIND_HOST 127.0.0.1)"
case "$HOST" in
  *[!\.A-Za-z0-9:_\[\]-]*) HOST=127.0.0.1 ;;
  "") HOST=127.0.0.1 ;;
esac

resolve_args=("$PYTHON" "$SELECT_PY" resolve --root "$ROOT" --unit-dir "$UNIT_DIR")
if [[ -n "$NAME_FLAG" ]]; then
  resolve_args+=(--name "$NAME_FLAG")
fi
if [[ -n "$PORT_FLAG" ]]; then
  resolve_args+=(--port "$PORT_FLAG")
fi

set +e
resolve_out=$("${resolve_args[@]}")
resolve_rc=$?
set -e
if [[ "$resolve_rc" -ne 0 ]]; then
  exit "$resolve_rc"
fi

INSTANCE_NAME=""
PORT=""
WEB_UNIT=""
WORKER_UNIT=""
SOCKET_UNIT=""
while IFS='=' read -r key value; do
  case "$key" in
    INSTANCE_NAME) INSTANCE_NAME=$value ;;
    PORT) PORT=$value ;;
    WEB_UNIT) WEB_UNIT=$value ;;
    WORKER_UNIT) WORKER_UNIT=$value ;;
    SOCKET_UNIT) SOCKET_UNIT=$value ;;
  esac
done <<<"$resolve_out"

[[ -n "$INSTANCE_NAME" && -n "$PORT" && -n "$WEB_UNIT" && -n "$WORKER_UNIT" ]] || die "בחירת שם/פורט נכשלה."
case "$INSTANCE_NAME" in
  *[!\.a-z0-9-]*) die "שם מופע לא תקין: $INSTANCE_NAME" ;;
esac
case "$PORT" in
  ''|*[!0-9]*) die "פורט לא תקין: $PORT" ;;
esac
case "$WEB_UNIT" in
  *.service) ;;
  *) die "שם יחידה לא תקין: $WEB_UNIT" ;;
esac
if [[ -z "$SOCKET_UNIT" ]]; then
  SOCKET_UNIT="${INSTANCE_NAME}-web.socket"
fi
case "$SOCKET_UNIT" in
  *.socket) ;;
  *) die "שם יחידת socket לא תקין: $SOCKET_UNIT" ;;
esac

LISTEN_STREAM="${HOST}:${PORT}"
case "$HOST" in
  *:*) LISTEN_STREAM="[${HOST}]:${PORT}" ;;
esac

render_unit() {
  local src=$1 dest=$2 text
  text=$(cat "$src")
  text=${text//@INSTALL_DIR@/$ROOT}
  text=${text//@PYTHON@/$PYTHON}
  text=${text//@BIND_HOST@/$HOST}
  text=${text//@PORT@/$PORT}
  text=${text//@USER@/$USER_NAME}
  text=${text//@INSTANCE@/$INSTANCE_NAME}
  text=${text//@LISTEN_STREAM@/$LISTEN_STREAM}
  if [[ "$text" == *"@INSTALL_DIR@"* || "$text" == *"@PYTHON@"* || "$text" == *"@BIND_HOST@"* || "$text" == *"@PORT@"* || "$text" == *"@USER@"* || "$text" == *"@INSTANCE@"* || "$text" == *"@LISTEN_STREAM@"* ]]; then
    die "התבנית $src לא הוחלפה במלואה."
  fi
  printf '%s\n' "$text" >"$dest"
}

ensure_runtime_dir() {
  local uid n
  uid=$(id -u)
  n=0
  while [[ -z "${XDG_RUNTIME_DIR:-}" || ! -d "${XDG_RUNTIME_DIR}" ]]; do
    if [[ -d "/run/user/$uid" ]]; then
      export XDG_RUNTIME_DIR="/run/user/$uid"
      break
    fi
    if [[ "$n" -ge 8 ]]; then
      break
    fi
    sleep 1
    n=$((n + 1))
  done
  if [[ -z "${XDG_RUNTIME_DIR:-}" || ! -S "${XDG_RUNTIME_DIR}/bus" && ! -S "${XDG_RUNTIME_DIR}/systemd/private" ]]; then
    if [[ -d "/run/user/$uid" ]]; then
      export XDG_RUNTIME_DIR="/run/user/$uid"
    fi
  fi
}

enable_linger() {
  if [[ "${HEB_CAL_SKIP_LINGER:-}" == "1" ]]; then
    return 0
  fi
  if ! command -v loginctl >/dev/null 2>&1; then
    say "אין loginctl. היחידות ירוצו אחרי כניסה למשתמש, לא בהכרח אחרי אתחול."
    return 0
  fi
  if loginctl show-user "$USER_NAME" -p Linger 2>/dev/null | grep -qx 'Linger=yes'; then
    return 0
  fi
  if loginctl enable-linger "$USER_NAME" >/dev/null 2>&1; then
    say "הופעל linger למשתמש $USER_NAME (עלייה אחרי אתחול בלי התחברות)."
    return 0
  fi
  if command -v sudo >/dev/null 2>&1 && sudo -n loginctl enable-linger "$USER_NAME" >/dev/null 2>&1; then
    say "הופעל linger למשתמש $USER_NAME (עלייה אחרי אתחול בלי התחברות)."
    return 0
  fi
  if [[ -t 0 ]] && command -v sudo >/dev/null 2>&1; then
    say "צריך sudo פעם אחת ל-loginctl enable-linger (אחרי זה העדכון מהממשק בלי סיסמה)."
    if sudo loginctl enable-linger "$USER_NAME"; then
      say "הופעל linger למשתמש $USER_NAME."
      return 0
    fi
  fi
  say "לא הופעל linger. אחרי אתחול היחידות עולות רק אחרי כניסה למשתמש. אחר כך: sudo loginctl enable-linger $USER_NAME"
}

ensure_restart_command() {
  if [[ ! -f .env ]]; then
    return 0
  fi
  if grep -qE '^HEB_CAL_RESTART_COMMAND=scripts/restart.sh[[:space:]]*$' .env; then
    return 0
  fi
  if grep -qE '^HEB_CAL_RESTART_COMMAND=$' .env || ! grep -qE '^HEB_CAL_RESTART_COMMAND=' .env; then
    env_set .env HEB_CAL_RESTART_COMMAND scripts/restart.sh
    say "ב-.env הוגדר HEB_CAL_RESTART_COMMAND=scripts/restart.sh"
  fi
}

print_tailscale_manual() {
  local port=$1 https=${2:-10000}
  say "פקודה ידנית (לא רצים reset — זה מוחק מיפויים אחרים):"
  say "  tailscale serve --bg --https=${https} http://127.0.0.1:${port}"
  say "בלי הרשאה, פעם אחת:"
  say "  sudo tailscale set --operator=${USER_NAME}"
}

run_tailscale() {
  local errf out rc
  errf=$(mktemp)
  set +e
  out=$(command tailscale "$@" 2>"$errf")
  rc=$?
  set -e
  TAILSCALE_OUT=$out
  TAILSCALE_ERR=$(cat "$errf" 2>/dev/null || true)
  TAILSCALE_RC=$rc
  rm -f "$errf"
}

maybe_configure_tailscale_serve() {
  local port=$1 https_port existing status_file json_file status_json dns url
  port=$1
  if [[ "$TAILSCALE_SERVE" -ne 1 ]]; then
    return 0
  fi
  if ! command -v tailscale >/dev/null 2>&1; then
    say "אין את פקודת tailscale. ההתקנה המשיכה בלי Serve."
    print_tailscale_manual "$port"
    return 0
  fi
  status_file=$(mktemp)
  json_file=$(mktemp)
  run_tailscale serve status
  printf '%s\n' "$TAILSCALE_OUT$TAILSCALE_ERR" >"$status_file"
  run_tailscale serve status --json
  printf '%s\n' "$TAILSCALE_OUT" >"$json_file"
  set +e
  https_out=$("$PYTHON" "$SELECT_PY" pick-https --status-file "$status_file" --json-file "$json_file" --proxy-port "$port")
  https_rc=$?
  set -e
  rm -f "$status_file" "$json_file"
  if [[ "$https_rc" -ne 0 ]]; then
    say "לא הצלחתי לבחור פורט HTTPS ל-Tailscale Serve. ההתקנה המשיכה."
    print_tailscale_manual "$port"
    return 0
  fi
  https_port=""
  existing="0"
  while IFS='=' read -r key value; do
    case "$key" in
      HTTPS_PORT) https_port=$value ;;
      EXISTING) existing=$value ;;
    esac
  done <<<"$https_out"
  if [[ -z "$https_port" ]]; then
    print_tailscale_manual "$port"
    return 0
  fi
  if [[ "$existing" != "1" ]]; then
    run_tailscale serve --bg --https="$https_port" --yes "http://127.0.0.1:${port}"
    if [[ "$TAILSCALE_RC" -ne 0 ]]; then
      blob=$(printf '%s' "$TAILSCALE_OUT $TAILSCALE_ERR" | tr '[:upper:]' '[:lower:]')
      if [[ "$blob" == *'unknown flag'* || "$blob" == *'not defined: --yes'* || "$blob" == *'not defined: -yes'* ]]; then
        run_tailscale serve --bg --https="$https_port" "http://127.0.0.1:${port}"
      fi
    fi
    if [[ "$TAILSCALE_RC" -ne 0 ]]; then
      say "Tailscale Serve נכשל. ההתקנה של היחידות הצליחה."
      print_tailscale_manual "$port" "$https_port"
      return 0
    fi
  fi
  if [[ -f data/instance.env ]]; then
    env_set data/instance.env HEB_CAL_TAILSCALE_HTTPS_PORT "$https_port"
    chmod 644 data/instance.env 2>/dev/null || true
  fi
  dns=""
  run_tailscale status --json
  status_json=$TAILSCALE_OUT
  if [[ "$TAILSCALE_RC" -eq 0 && -n "$status_json" ]]; then
    json_file=$(mktemp)
    printf '%s\n' "$status_json" >"$json_file"
    set +e
    dns=$("$PYTHON" "$SELECT_PY" magic-dns --json-file "$json_file")
    set -e
    rm -f "$json_file"
  fi
  if [[ -z "$dns" ]]; then
    dns="<magicdns-name>"
  fi
  url="https://${dns}:${https_port}"
  say ""
  say "Tailscale Serve: $url"
  say "  (מיפוי ל-http://127.0.0.1:${port}, בלי לגעת במיפויים אחרים)"
}

mkdir -p "$UNIT_DIR" data logs
enable_linger
ensure_runtime_dir

tmp_web=$(mktemp)
tmp_worker=$(mktemp)
tmp_socket=$(mktemp)
trap 'rm -f "$tmp_web" "$tmp_worker" "$tmp_socket"' EXIT
render_unit "$TEMPLATE_DIR/$TEMPLATE_WEB" "$tmp_web"
render_unit "$TEMPLATE_DIR/$TEMPLATE_WORKER" "$tmp_worker"
render_unit "$TEMPLATE_DIR/$TEMPLATE_SOCKET" "$tmp_socket"
cp "$tmp_web" "$UNIT_DIR/$WEB_UNIT"
cp "$tmp_worker" "$UNIT_DIR/$WORKER_UNIT"
cp "$tmp_socket" "$UNIT_DIR/$SOCKET_UNIT"
chmod 644 "$UNIT_DIR/$WEB_UNIT" "$UNIT_DIR/$WORKER_UNIT" "$UNIT_DIR/$SOCKET_UNIT"

if [[ -f .env ]]; then
  env_set .env HEB_CAL_PORT "$PORT"
  env_set .env HEB_CAL_HEALTH_URL "http://127.0.0.1:${PORT}/api/updates/health"
fi

systemctl --user daemon-reload
systemctl --user enable "$SOCKET_UNIT" "$WEB_UNIT" "$WORKER_UNIT"

if [[ "$UNITS_ONLY" -eq 1 ]]; then
  ensure_restart_command
  say "עודכנו יחידות systemd --user (מופע ${INSTANCE_NAME}, בלי הפעלה מחדש)."
  exit 0
fi

# עוצר רק את היחידות של המופע הזה, ואז תהליכים ידניים של הריפו הזה, ואז מעלה מחדש.
# ה-socket עולה אחרי שהפורט השתחרר — בלי פורט TCP נוסף.
export HEB_CAL_UNIT_DIR="$UNIT_DIR"
export HEB_CAL_INSTANCE_NAME="$INSTANCE_NAME"
export HEB_CAL_PORT="$PORT"
HEB_CAL_UPDATE_ACTION=stop "$ROOT/scripts/restart.sh"
systemctl --user reset-failed "$SOCKET_UNIT" "$WEB_UNIT" "$WORKER_UNIT" >/dev/null 2>&1 || true
systemctl --user start "$SOCKET_UNIT" "$WEB_UNIT" "$WORKER_UNIT"

ensure_restart_command
maybe_configure_tailscale_serve "$PORT"

say ""
say "יחידות systemd --user מותקנות ופעילות (מופע ${INSTANCE_NAME})."
say "סטטוס:  systemctl --user status $SOCKET_UNIT $WEB_UNIT $WORKER_UNIT"
say "לוגים:  journalctl --user -u $WEB_UNIT -u $WORKER_UNIT -f"
say "עצירה:  systemctl --user stop $WEB_UNIT $WORKER_UNIT"
say "ביטול עלייה באתחול: systemctl --user disable --now $SOCKET_UNIT $WEB_UNIT $WORKER_UNIT"
say "תיקייה: $ROOT"
say "משתמש: $USER_NAME"
say "כתובת: ${HOST}:${PORT}"
say "שם מופע: $INSTANCE_NAME (נשמר ב-data/instance.env)"
