#!/bin/bash
# מכין data/ logs/ backups/, יורד למשתמש hebcal, ומשכפל stdout לקובץ לוג.
# הסודות מגיעים מהסביבה (compose env_file). אסור לכתוב אותם ללוג.
set -euo pipefail

export PATH="/opt/venv/bin:${PATH:-/usr/bin:/bin}"

mkdir -p /app/data /app/logs /app/backups

if [[ "$(id -u)" -eq 0 ]]; then
  chown hebcal:hebcal /app/data /app/logs /app/backups
  exec runuser --preserve-environment -u hebcal -- "$0" "$@"
fi

secret="${SECRET_KEY:-}"
if [[ -z "${secret}" || "${secret}" == "change-me-before-production" || "${secret}" == "dev-secret-key-change-me" ]]; then
  echo "הגדירו SECRET_KEY בקובץ .env — לא משאירים את הערך מהדוגמה." >&2
  exit 1
fi

if [[ -n "${HEB_CAL_LOG_NAME:-}" ]]; then
  name="${HEB_CAL_LOG_NAME}"
  if [[ ! "${name}" =~ ^[A-Za-z0-9_-]+$ ]]; then
    echo "HEB_CAL_LOG_NAME לא תקין." >&2
    exit 1
  fi
  log="/app/logs/${name}.log"
  touch "${log}"
  py=0
  tail_pid=0
  stop() {
    if [[ "${py}" -ne 0 ]]; then
      kill -TERM "${py}" 2>/dev/null || true
    fi
  }
  trap stop TERM INT
  # שורות חדשות גם ב-docker logs. הקובץ נשאר ב-volume.
  tail -n 0 -F "${log}" &
  tail_pid=$!
  "$@" >>"${log}" 2>&1 &
  py=$!
  set +e
  wait "${py}"
  status=$?
  set -e
  kill "${tail_pid}" 2>/dev/null || true
  wait "${tail_pid}" 2>/dev/null || true
  exit "${status}"
fi

exec "$@"
