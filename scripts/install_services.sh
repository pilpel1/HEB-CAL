#!/usr/bin/env bash
# התקנת יחידות systemd --user ל-HEB-CAL (Flask + reminder_worker) על Linux.
# אידמפוטנטי. בלי סודות בקבצי היחידה. לא דורש sudo אחרי linger.
# לוגים: journalctl --user -u heb-cal-web -u heb-cal-worker
set -euo pipefail

WEB_UNIT=heb-cal-web.service
WORKER_UNIT=heb-cal-worker.service

say() { printf '%s\n' "$*"; }
die() { printf '%s\n' "$*" >&2; exit 1; }

ROOT="$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

if [[ -f /.dockerenv ]]; then
  die "רצים בתוך Docker. היחידות האלה מיועדות להרצה עם venv על המארח, לא בקונטיינר."
fi

command -v systemctl >/dev/null 2>&1 || die "אין systemctl. צריך systemd."

USER_NAME=$(id -un)
UNIT_DIR="${HEB_CAL_UNIT_DIR:-$HOME/.config/systemd/user}"
TEMPLATE_DIR="$ROOT/deploy/systemd"

[[ -f "$TEMPLATE_DIR/$WEB_UNIT" ]] || die "חסרה התבנית $TEMPLATE_DIR/$WEB_UNIT"
[[ -f "$TEMPLATE_DIR/$WORKER_UNIT" ]] || die "חסרה התבנית $TEMPLATE_DIR/$WORKER_UNIT"

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
  if [[ -f .env ]]; then
    line=$(grep -E "^${name}=" .env | tail -n 1 || true)
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
  printf '%s' "$default"
}

if [[ -x "$ROOT/.venv/bin/python" ]]; then
  PYTHON="$ROOT/.venv/bin/python"
elif command -v python3 >/dev/null 2>&1; then
  PYTHON=$(command -v python3)
else
  die "אין Python. צריך .venv ב-$ROOT או python3 ב-PATH."
fi

HOST="$(env_get HEB_CAL_BIND_HOST 127.0.0.1)"
PORT="$(env_get HEB_CAL_PORT 5000)"
case "$HOST" in
  *[!\.A-Za-z0-9:_\[\]-]*) HOST=127.0.0.1 ;;
  "") HOST=127.0.0.1 ;;
esac
case "$PORT" in
  ''|*[!0-9]*) PORT=5000 ;;
esac
if [[ "$PORT" -lt 1 || "$PORT" -gt 65535 ]]; then
  PORT=5000
fi

render_unit() {
  local src=$1 dest=$2 text
  text=$(cat "$src")
  text=${text//@INSTALL_DIR@/$ROOT}
  text=${text//@PYTHON@/$PYTHON}
  text=${text//@BIND_HOST@/$HOST}
  text=${text//@PORT@/$PORT}
  text=${text//@USER@/$USER_NAME}
  if [[ "$text" == *"@INSTALL_DIR@"* || "$text" == *"@PYTHON@"* || "$text" == *"@BIND_HOST@"* || "$text" == *"@PORT@"* || "$text" == *"@USER@"* ]]; then
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
  local tmp
  if [[ ! -f .env ]]; then
    return 0
  fi
  if grep -qE '^HEB_CAL_RESTART_COMMAND=scripts/restart.sh[[:space:]]*$' .env; then
    return 0
  fi
  if grep -qE '^HEB_CAL_RESTART_COMMAND=$' .env; then
    tmp=$(mktemp)
    awk '
      { sub(/\r$/, "") }
      $0 == "HEB_CAL_RESTART_COMMAND=" { print "HEB_CAL_RESTART_COMMAND=scripts/restart.sh"; next }
      { print }
    ' .env >"$tmp"
    mv "$tmp" .env
    chmod 600 .env 2>/dev/null || true
    say "ב-.env הוגדר HEB_CAL_RESTART_COMMAND=scripts/restart.sh"
    return 0
  fi
  if ! grep -qE '^HEB_CAL_RESTART_COMMAND=' .env; then
    printf '\nHEB_CAL_RESTART_COMMAND=scripts/restart.sh\n' >>.env
    say "נוסף HEB_CAL_RESTART_COMMAND=scripts/restart.sh ל-.env"
  fi
}

mkdir -p "$UNIT_DIR" data logs
enable_linger
ensure_runtime_dir

tmp_web=$(mktemp)
tmp_worker=$(mktemp)
trap 'rm -f "$tmp_web" "$tmp_worker"' EXIT
render_unit "$TEMPLATE_DIR/$WEB_UNIT" "$tmp_web"
render_unit "$TEMPLATE_DIR/$WORKER_UNIT" "$tmp_worker"
cp "$tmp_web" "$UNIT_DIR/$WEB_UNIT"
cp "$tmp_worker" "$UNIT_DIR/$WORKER_UNIT"
chmod 644 "$UNIT_DIR/$WEB_UNIT" "$UNIT_DIR/$WORKER_UNIT"

systemctl --user daemon-reload
systemctl --user enable "$WEB_UNIT" "$WORKER_UNIT"

# עוצר יחידות אם רצות, ואז תהליכים ידניים של הריפו הזה, ואז מעלה מחדש.
export HEB_CAL_UNIT_DIR="$UNIT_DIR"
HEB_CAL_UPDATE_ACTION=stop "$ROOT/scripts/restart.sh"
systemctl --user reset-failed "$WEB_UNIT" "$WORKER_UNIT" >/dev/null 2>&1 || true
systemctl --user start "$WEB_UNIT" "$WORKER_UNIT"

ensure_restart_command

say ""
say "יחידות systemd --user מותקנות ופעילות."
say "סטטוס:  systemctl --user status $WEB_UNIT $WORKER_UNIT"
say "לוגים:  journalctl --user -u $WEB_UNIT -u $WORKER_UNIT -f"
say "עצירה:  systemctl --user stop $WEB_UNIT $WORKER_UNIT"
say "ביטול עלייה באתחול: systemctl --user disable --now $WEB_UNIT $WORKER_UNIT"
say "תיקייה: $ROOT"
say "משתמש: $USER_NAME"
say "כתובת: ${HOST}:${PORT}"
