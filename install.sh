#!/usr/bin/env bash
# התקנת HEB-CAL לבית על Linux: בודק Docker, מושך ghcr.io/pilpel1/heb-cal, מעלה compose.
# אחרי אתחול: heb-cal.service (אם יש sudo ו-docker.service), אחרת restart: unless-stopped.
# Tailscale Serve אופציונלי על המארח. אם 443 / תפוס — HTTPS 8443, בלי reset.
set -euo pipefail

IMAGE="${HEB_CAL_IMAGE:-ghcr.io/pilpel1/heb-cal:latest}"
REPO_URL="https://github.com/pilpel1/HEB-CAL.git"
install_dir=""
boot_note=""

say() { printf '%s\n' "$*"; }
die() { printf '%s\n' "$*" >&2; exit 1; }

new_secret() {
  if command -v openssl >/dev/null 2>&1; then
    openssl rand -hex 32
    return
  fi
  if command -v python3 >/dev/null 2>&1; then
    python3 -c 'import secrets; print(secrets.token_hex(32))'
    return
  fi
  od -An -N32 -tx1 /dev/urandom | tr -d ' \n'
}

require_docker() {
  command -v docker >/dev/null 2>&1 || die "Docker לא מותקן. התקינו Docker Engine עם Compose ואז הריצו שוב: https://docs.docker.com/engine/install/"
  docker compose version >/dev/null 2>&1 || die "חסר Docker Compose. צריך את הפקודה docker compose (תוסף v2), לא רק את docker."
  if ! docker info >/dev/null 2>&1; then
    die "Docker לא רץ, או שאין למשתמש הזה הרשאה. נסו: sudo systemctl start docker
אם הפקודה docker עובדת רק עם sudo: sudo usermod -aG docker \"\$USER\" ואז התנתקו והתחברו, והריצו שוב."
  fi
}

resolve_install_dir() {
  local src dir
  src=${BASH_SOURCE[0]:-}
  case "$src" in
    ""|bash|/dev/stdin|/dev/fd/*) src="" ;;
  esac
  if [[ -n "$src" && -f "$src" ]]; then
    dir=$(CDPATH= cd -- "$(dirname "$src")" && pwd)
    if [[ -f "$dir/docker-compose.yml" ]]; then
      install_dir=$dir
      return
    fi
  fi
  if [[ -z "${HOME:-}" ]]; then
    die "משתנה HOME לא מוגדר, ואין docker-compose.yml ליד הסקריפט."
  fi
  install_dir=${HEB_CAL_HOME:-"$HOME/heb-cal"}
  if [[ -f "$install_dir/docker-compose.yml" ]]; then
    return
  fi
  if [[ -e "$install_dir" ]]; then
    die "התיקייה $install_dir קיימת בלי docker-compose.yml. מחקו אותה, או הריצו את הסקריפט מתוך עותק של HEB-CAL."
  fi
  command -v git >/dev/null 2>&1 || die "אין docker-compose.yml ליד הסקריפט, ואין git כדי להוריד את HEB-CAL."
  say "מוריד את קבצי HEB-CAL אל $install_dir"
  git clone --depth 1 "$REPO_URL" "$install_dir"
}

ensure_env() {
  local secret tmp
  secret=$(new_secret)
  if [[ -z "$secret" || ${#secret} -lt 32 ]]; then
    die "לא הצלחתי ליצור SECRET_KEY."
  fi
  tmp=$(mktemp)
  if [[ ! -f .env ]]; then
    awk -v secret="$secret" '
      { sub(/\r$/, "") }
      $0 == "SECRET_KEY=change-me-before-production" { print "SECRET_KEY=" secret; next }
      $0 == "FLASK_DEBUG=1" { print "FLASK_DEBUG=0"; next }
      { print }
    ' .env.example >"$tmp"
    mv "$tmp" .env
    chmod 600 .env
    say "נוצר .env עם SECRET_KEY אקראי. הערך לא מודפס."
    return
  fi
  rm -f "$tmp"
  if grep -qx 'SECRET_KEY=change-me-before-production' .env; then
    tmp=$(mktemp)
    awk -v secret="$secret" '
      { sub(/\r$/, "") }
      $0 == "SECRET_KEY=change-me-before-production" { print "SECRET_KEY=" secret; next }
      { print }
    ' .env >"$tmp"
    mv "$tmp" .env
    chmod 600 .env
    say "ב-.env היה המפתח מהדוגמה. הוחלף במפתח אקראי. הערך לא מודפס."
    return
  fi
  say "משאיר את קובץ .env הקיים."
}

pull_and_up() {
  say "מושך את התמונה (ברירת מחדל ${IMAGE}, אלא אם HEB_CAL_IMAGE הוגדר בסביבה או ב-.env)."
  if ! docker compose pull; then
    die "משיכת התמונה נכשלה.
אם החבילה ב-GitHub עדיין פרטית, צריך פעם אחת להפוך אותה לציבורית:
GitHub → Packages → heb-cal → Package settings → Change visibility → Public.
אחר כך הריצו שוב את הסקריפט. בינתיים אין בניית תמונה מהקוד."
  fi
  if ! docker compose up -d --no-build --wait; then
    docker compose logs --tail 80 || true
    die "הקונטיינרים לא עלו. בדקו את הלוג למעלה."
  fi
}

run_root() {
  if [[ "$(id -u)" -eq 0 ]]; then
    "$@"
  else
    sudo "$@"
  fi
}

can_sudo() {
  if [[ "$(id -u)" -eq 0 ]]; then
    return 0
  fi
  if ! command -v sudo >/dev/null 2>&1; then
    return 1
  fi
  if sudo -n true >/dev/null 2>&1; then
    return 0
  fi
  if [[ -t 0 ]]; then
    say "צריך סיסמת sudo כדי ש-HEB-CAL יעלה אחרי אתחול."
    if ! sudo -v; then
      return 1
    fi
    return 0
  fi
  return 1
}

enable_boot() {
  local docker_bin rendered tmp
  boot_note="restart: unless-stopped יחזיר קונטיינרים שלא נעצרו ביד, אם Docker עצמו עולה עם המחשב."
  if ! command -v systemctl >/dev/null 2>&1; then
    boot_note="אין systemd. ${boot_note}"
    return 0
  fi
  if ! systemctl cat docker.service >/dev/null 2>&1; then
    boot_note="לא מצאתי docker.service (למשל Docker Desktop). סמנו שהוא עולה עם המחשב. ${boot_note}"
    return 0
  fi
  if docker info --format '{{.SecurityOptions}}' 2>/dev/null | grep -q 'name=rootless'; then
    boot_note="זה Docker rootless. לא התקנתי יחידת system. ${boot_note} לשירות המשתמש: systemctl --user enable docker, וגם loginctl enable-linger \$USER."
    return 0
  fi
  if [[ "$install_dir" == *$'\n'* || "$install_dir" == *'"'* ]]; then
    boot_note="הנתיב לא מתאים ליחידת systemd. ${boot_note}"
    return 0
  fi
  docker_bin=$(command -v docker)
  if [[ "$docker_bin" != /* ]]; then
    boot_note="לא מצאתי נתיב מלא ל-docker. ${boot_note}"
    return 0
  fi
  if ! can_sudo; then
    boot_note="בלי sudo לא התקנתי heb-cal.service. ${boot_note}"
    return 0
  fi
  if [[ ! -f "$install_dir/docker/heb-cal.service" ]]; then
    boot_note="חסרה התבנית docker/heb-cal.service. ${boot_note}"
    return 0
  fi
  rendered=$(cat "$install_dir/docker/heb-cal.service")
  rendered=${rendered//@INSTALL_DIR@/$install_dir}
  rendered=${rendered//@DOCKER_BIN@/$docker_bin}
  if [[ "$rendered" == *"@INSTALL_DIR@"* || "$rendered" == *"@DOCKER_BIN@"* ]]; then
    boot_note="התבנית של systemd לא הוחלפה. ${boot_note}"
    return 0
  fi
  tmp=$(mktemp)
  printf '%s\n' "$rendered" >"$tmp"
  if ! run_root cp "$tmp" /etc/systemd/system/heb-cal.service; then
    rm -f "$tmp"
    boot_note="לא הצלחתי לכתוב את heb-cal.service. ${boot_note}"
    return 0
  fi
  rm -f "$tmp"
  if ! run_root chmod 644 /etc/systemd/system/heb-cal.service; then
    boot_note="heb-cal.service נכתב, אבל לא הצלחתי לקבוע הרשאות. ${boot_note}"
    return 0
  fi
  if ! run_root systemctl daemon-reload; then
    boot_note="heb-cal.service נכתב, אבל systemctl daemon-reload נכשל. ${boot_note}"
    return 0
  fi
  if ! run_root systemctl enable docker.service; then
    boot_note="heb-cal.service נכתב, אבל docker.service לא סומן לעלייה. ${boot_note}"
    return 0
  fi
  if ! run_root systemctl enable heb-cal.service; then
    boot_note="docker.service יעלה, אבל heb-cal.service לא הופעל. ${boot_note}"
    return 0
  fi
  boot_note="heb-cal.service מופעל. אחרי אתחול הוא רץ אחרי docker.service ומריץ docker compose up -d. קונטיינר שנעצר ביד חוזר בהפעלה הבאה. בנוסף, restart: unless-stopped מחזיר קונטיינר שלא נעצר ביד ברגע ש-Docker עלה."
}

# --- Tailscale Serve על המארח. אופציונלי, אף פעם לא נכשל את ההתקנה. ---
# לא מריצים serve reset. אם 443 / תפוס (למשל bt-speaker), היומן עולה על HTTPS 8443.

ts_capture() {
  local errf
  errf=$(mktemp)
  set +e
  _ts_out=$(command tailscale "$@" 2>"$errf")
  _ts_rc=$?
  set -e
  _ts_err=$(cat "$errf" 2>/dev/null || true)
  rm -f "$errf"
  _ts_blob="${_ts_out}"$'\n'"${_ts_err}"
}

ts_lc() {
  printf '%s' "$1" | tr '[:upper:]' '[:lower:]'
}

ts_is_permission_err() {
  local s
  s=$(ts_lc "$1")
  [[ "$s" == *permission* || "$s" == *'access denied'* || "$s" == *operator* || "$s" == *'must be root'* || "$s" == *'operation not permitted'* || "$s" == *'access is denied'* ]]
}

ts_is_offline_err() {
  local s
  s=$(ts_lc "$1")
  [[ "$s" == *'logged out'* || "$s" == *'not logged'* || "$s" == *'needs login'* || "$s" == *'failed to connect'* || "$s" == *tailscaled* || "$s" == *'is stopped'* || "$s" == *'tailscale up'* ]]
}

ts_status_empty() {
  local s
  s=$(printf '%s' "$1" | tr -d '[:space:]')
  [[ -z "$s" || "$s" == "{}" ]] && return 0
  s=$(ts_lc "$1")
  [[ "$s" == *'no serve config'* || "$s" == *'no https'* || "$s" == *'nothing serving'* ]]
}

ts_points_at_local_port() {
  local blob=$1 port=$2
  [[ "$blob" == *"127.0.0.1:${port}"* || "$blob" == *"localhost:${port}"* || "$blob" == *"[::1]:${port}"* ]]
}

# האם HTTPS port הזה כבר מופיע ב-Serve (JSON או טקסט).
# 443 בטקסט הוא https://host בלי :פורט — לא https://host:8443.
ts_https_in_use() {
  local blob=$1 https=$2
  if [[ "$https" == "443" ]]; then
    if [[ "$blob" == *':443"'* || "$blob" == *'"443":'* ]]; then
      return 0
    fi
    printf '%s\n' "$blob" | grep -Eq 'https://[A-Za-z0-9._-]+(/|[[:space:]]|$)'
    return
  fi
  [[ "$blob" == *":${https}\""* || "$blob" == *"\"${https}\":"* || "$blob" == *":${https} "* || "$blob" == *":${https}"$'\n'* ]]
}

print_tailscale_serve_commands() {
  local port=$1
  say "פקודות ידניות. לא מריצים tailscale serve reset — זה מוחק גם שירותים אחרים על המחשב:"
  say "  # 443 תפוס (למשל רמקול על /): היומן על 8443"
  say "  tailscale serve --bg --https=8443 http://127.0.0.1:${port}"
  say "  # 443 פנוי והיומן לבד:"
  say "  tailscale serve --bg --https=443 http://127.0.0.1:${port}"
  say "בלי הרשאה, פעם אחת בלינוקס:"
  say "  sudo tailscale set --operator=${USER:-\$USER}"
  say "ואז חוזרים על פקודת serve."
}

print_tailscale_missing() {
  local port=$1
  say "Tailscale לא מותקן — היומן רץ רק מקומית, וזה בסדר."
  say "להתקין ולהצטרף לרשת: https://tailscale.com/download/linux"
  print_tailscale_serve_commands "$port"
}

print_tailscale_permission() {
  local port=$1 https=${2:-8443}
  say "אין הרשאה להגדיר Tailscale Serve."
  say "פעם אחת (אחר כך בלי sudo):"
  say "  sudo tailscale set --operator=${USER:-\$USER}"
  say "ואז:"
  say "  tailscale serve --bg --https=${https} http://127.0.0.1:${port}"
}

want_tailscale_serve() {
  local prompt=$1 ans
  case "${HEB_CAL_TAILSCALE_SERVE:-}" in
    0|n|no|false|off) return 1 ;;
    1|y|yes|true|on) return 0 ;;
  esac
  if [[ ! -t 0 ]]; then
    return 1
  fi
  say ""
  say "$prompt"
  if ! read -r -p " [כ/ל] " ans; then
    return 1
  fi
  case "$ans" in
    כ|כן|k|K|y|Y|yes|Yes) return 0 ;;
    *) return 1 ;;
  esac
}

run_tailscale_serve() {
  local port=$1 https=$2
  ts_capture serve --bg --https="$https" --yes "http://127.0.0.1:${port}"
  if [[ "$_ts_rc" -ne 0 ]]; then
    local blob
    blob=$(ts_lc "${_ts_blob}")
    if [[ "$blob" == *'unknown flag'* || "$blob" == *'flag provided but not defined'* || "$blob" == *'not defined: -yes'* || "$blob" == *'not defined: --yes'* ]]; then
      ts_capture serve --bg --https="$https" "http://127.0.0.1:${port}"
    fi
  fi
}

maybe_configure_tailscale_serve() {
  local port=$1 https_port="" blob json text
  port=${port:-5000}

  if ! command -v tailscale >/dev/null 2>&1; then
    print_tailscale_missing "$port"
    return 0
  fi

  ts_capture serve status --json
  json="${_ts_out}"
  if [[ "$_ts_rc" -ne 0 ]] && ts_is_permission_err "$_ts_blob"; then
    print_tailscale_permission "$port"
    return 0
  fi
  if [[ "$_ts_rc" -ne 0 ]] && ts_is_offline_err "$_ts_blob"; then
    say "Tailscale מותקן אבל לא מחובר. אחרי tailscale up:"
    print_tailscale_serve_commands "$port"
    return 0
  fi

  ts_capture serve status
  text="${_ts_out}"
  blob="${json}"$'\n'"${text}"

  if ts_points_at_local_port "$blob" "$port"; then
    say "Tailscale Serve כבר מפנה ליומן על פורט ${port}."
    if [[ -n "$text" ]]; then
      say "$text"
    fi
    return 0
  fi

  if [[ -n "${HEB_CAL_TAILSCALE_HTTPS_PORT:-}" ]]; then
    https_port=$HEB_CAL_TAILSCALE_HTTPS_PORT
    if [[ ! "$https_port" =~ ^[0-9]+$ ]] || (( https_port < 1 || https_port > 65535 )); then
      say "HEB_CAL_TAILSCALE_HTTPS_PORT לא תקין. מדלג על Serve."
      print_tailscale_serve_commands "$port"
      return 0
    fi
  elif ts_status_empty "$blob"; then
    https_port=443
  elif ts_https_in_use "$blob" "443"; then
    https_port=8443
  else
    https_port=443
  fi

  if [[ "$https_port" == "443" ]] && ! ts_status_empty "$blob" && ts_https_in_use "$blob" "443"; then
    say "Tailscale Serve על 443 / כבר תפוס. לא דורסים אותו ולא מריצים reset."
    say "אפשר לחבר את היומן בנפרד:"
    say "  tailscale serve --bg --https=8443 http://127.0.0.1:${port}"
    if [[ -n "${HEB_CAL_TAILSCALE_HTTPS_PORT:-}" ]]; then
      return 0
    fi
    https_port=8443
  fi

  if [[ "$https_port" != "443" ]] && ts_https_in_use "$blob" "$https_port"; then
    say "HTTPS ${https_port} כבר בשימוש ב-Serve. לא דורסים ולא מריצים reset."
    say "פורט אחר: HEB_CAL_TAILSCALE_HTTPS_PORT=9443"
    print_tailscale_serve_commands "$port"
    return 0
  fi

  local prompt
  if [[ "$https_port" == "443" ]]; then
    prompt="Tailscale מותקן. להגדיר Serve ליומן על HTTPS 443 (MagicDNS, נתיב /)?"
  else
    prompt="על HTTPS 443 כבר יש שירות — נשאר כמו שהוא. להגדיר את היומן על HTTPS ${https_port}?"
  fi

  if ! want_tailscale_serve "$prompt"; then
    if [[ -z "${HEB_CAL_TAILSCALE_SERVE:-}" && ! -t 0 ]]; then
      say "דילגתי על Tailscale Serve (אין מסוף אינטראקטיבי, וההתקנה לא דורשת אותו)."
    else
      say "דילגתי על Tailscale Serve."
    fi
    print_tailscale_serve_commands "$port"
    return 0
  fi

  run_tailscale_serve "$port" "$https_port"
  if [[ "$_ts_rc" -ne 0 ]]; then
    if ts_is_permission_err "$_ts_blob"; then
      print_tailscale_permission "$port" "$https_port"
      return 0
    fi
    if ts_is_offline_err "$_ts_blob"; then
      say "Tailscale לא מחובר. אחרי tailscale up:"
      print_tailscale_serve_commands "$port"
      return 0
    fi
    say "הגדרת Serve נכשלה:"
    if [[ -n "$_ts_err" ]]; then
      say "$_ts_err"
    elif [[ -n "$_ts_out" ]]; then
      say "$_ts_out"
    fi
    print_tailscale_serve_commands "$port"
    return 0
  fi

  say "Tailscale Serve הוגדר ליומן: HTTPS ${https_port} → http://127.0.0.1:${port}"
  if [[ "$https_port" != "443" ]]; then
    say "הנתיב / על 443 לא השתנה."
  fi
  if [[ -n "$_ts_out" ]]; then
    say "$_ts_out"
  fi
  return 0
}

main() {
  require_docker
  resolve_install_dir
  cd "$install_dir"
  [[ -f .env.example ]] || die "חסר .env.example ב-$install_dir"
  [[ -f docker-compose.yml ]] || die "חסר docker-compose.yml ב-$install_dir"
  mkdir -p data logs backups
  ensure_env
  pull_and_up
  enable_boot
  local port=5000 line
  if line=$(grep -E '^HEB_CAL_PORT=' .env | tail -n 1); then
    port=${line#HEB_CAL_PORT=}
    port=${port//$'\r'/}
  fi
  if [[ ! "$port" =~ ^[0-9]+$ ]]; then
    port=5000
  fi
  say ""
  say "HEB-CAL עלה."
  say "בדפדפן על המחשב הזה: http://127.0.0.1:${port}"
  say "תיקייה: ${install_dir}"
  say "אחרי אתחול: ${boot_note}"
  say "עדכון אחר כך: docker compose pull && docker compose up -d"
  say "טלגרם: ערכו TELEGRAM_BOT_TOKEN ב-.env והריצו docker compose up -d"
  maybe_configure_tailscale_serve "$port"
}

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
  main "$@"
fi
