#!/usr/bin/env bash
# Kunlik zaxira nusxa: maʼlumotlar bazasi + yuklangan fayllar (audio, xaritalar). Oxirgi 14 kun saqlanadi.
# Cron:  0 3 * * * /srv/levi/app/deploy/backup.sh >> /srv/levi/backup.log 2>&1
# Zaxirani BOSHQA serverga ham koʻchiring (DEPLOY.md, 8-qadam): bitta server buzilsa, zaxira ham yoʻqolmasin.
set -euo pipefail

APP_DIR="${APP_DIR:-/srv/levi/app}"
BACKUP_DIR="${BACKUP_DIR:-/srv/levi/backups}"
KEEP_DAYS="${KEEP_DAYS:-14}"
STAMP="$(date +%Y-%m-%d_%H%M)"

mkdir -p "$BACKUP_DIR"
cd "$APP_DIR"

# .env ni "source" qilmaymiz (qiymatlarda boʻsh joy boʻlishi mumkin): faqat DATABASE_URL ni olamiz
DATABASE_URL="${DATABASE_URL:-$(grep -E '^DATABASE_URL=' .env 2>/dev/null | head -1 | cut -d= -f2- || true)}"

if [[ "$DATABASE_URL" == postgres* ]]; then
    pg_dump "$DATABASE_URL" | gzip > "$BACKUP_DIR/db_$STAMP.sql.gz"
else
    DB_FILE="instance/cefr.db"
    [ -f "$DB_FILE" ] || { echo "SQLite fayl topilmadi: $DB_FILE" >&2; exit 1; }
    python3 - "$DB_FILE" "$BACKUP_DIR/db_$STAMP.sqlite" <<'PY'        # Python'ning oʻz zaxira usuli: ish paytida ham xavfsiz, qoʻshimcha dastur kerak emas
import sqlite3, sys
src, dst = sqlite3.connect(sys.argv[1]), sqlite3.connect(sys.argv[2])
src.backup(dst)
dst.close(); src.close()
PY
    gzip -f "$BACKUP_DIR/db_$STAMP.sqlite"
fi

DIRS=()
for d in static/audio static/maps; do [ -d "$d" ] && DIRS+=("$d"); done
if [ ${#DIRS[@]} -gt 0 ]; then
    tar -czf "$BACKUP_DIR/files_$STAMP.tar.gz" "${DIRS[@]}"
fi

find "$BACKUP_DIR" -type f -mtime +"$KEEP_DAYS" -delete
echo "$(date -Is) zaxira tayyor: $BACKUP_DIR (db_$STAMP)"
