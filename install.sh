#!/usr/bin/env bash
# התקנת HEB-CAL לבית על Linux: בודק Docker, מושך ghcr.io/pilpel1/heb-cal, מעלה compose.
# אחרי אתחול: heb-cal.service (אם יש sudo ו-docker.service), אחרת restart: unless-stopped.
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
}

main "$@"
