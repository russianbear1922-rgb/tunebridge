#!/usr/bin/env bash
# Бэкап базы и файлов data/ из работающего docker compose.
# Запуск: ./deploy/backup.sh
# Cron:   17 3 * * * /opt/tunebridge/deploy/backup.sh >> /var/log/tunebridge-backup.log 2>&1

set -euo pipefail

cd "$(dirname "$0")/.."

STAMP="$(date +%Y%m%d-%H%M%S)"
KEEP_DAYS="${BACKUP_KEEP_DAYS:-14}"
mkdir -p backups

docker compose exec -T tunebridge python - <<'PY' > "backups/tunebridge-$STAMP.db"
import os
import sqlite3
import sys

path = os.environ.get("TUNEBRIDGE_DB_PATH") or "/app/data/tunebridge.db"
source = sqlite3.connect(path)
target = sqlite3.connect(":memory:")
source.backup(target)
sys.stdout.buffer.write(target.serialize())
PY

gzip -f "backups/tunebridge-$STAMP.db"

docker compose exec -T tunebridge tar -cz \
  --exclude=./tunebridge.db \
  --exclude=./tunebridge.db-wal \
  --exclude=./tunebridge.db-shm \
  -C /app/data . > "backups/data-$STAMP.tar.gz"

find backups -maxdepth 1 -type f \( -name '*.db.gz' -o -name '*.tar.gz' \) \
  -mtime "+$KEEP_DAYS" -delete

echo "Backup ready: backups/tunebridge-$STAMP.db.gz, backups/data-$STAMP.tar.gz"
