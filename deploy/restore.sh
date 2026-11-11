#!/usr/bin/env bash
# Восстановление бэкапа в работающий docker compose (том tunebridge_data).
# Обратная операция к deploy/backup.sh.
#
# Запуск из корня репозитория на сервере:
#   ./deploy/restore.sh backups/tunebridge-20261111-031700.db.gz
#   ./deploy/restore.sh backups/tunebridge-20261111-031700.db.gz backups/data-20261111-031700.tar.gz
#
# Первый аргумент — база (.db.gz), второй (необязательный) — файлы data/ (.tar.gz).
# Скрипт останавливает приложение, заменяет базу и файлы, запускает обратно.
#
# ВНИМАНИЕ: текущая база будет перезаписана. Для подтверждения введите yes,
# либо задайте FORCE=1 (для автоматического восстановления без вопроса).

set -euo pipefail
cd "$(dirname "$0")/.."

DB_GZ="${1:-}"
DATA_TGZ="${2:-}"
if [ -z "$DB_GZ" ]; then
  echo "Использование: ./deploy/restore.sh <база.db.gz> [файлы-data.tar.gz]" >&2
  exit 1
fi
[ -f "$DB_GZ" ] || { echo "Нет файла базы: $DB_GZ" >&2; exit 1; }
if [ -n "$DATA_TGZ" ] && [ ! -f "$DATA_TGZ" ]; then
  echo "Нет файла данных: $DATA_TGZ" >&2
  exit 1
fi
command -v docker >/dev/null 2>&1 || { echo "docker не найден." >&2; exit 1; }

if [ "${FORCE:-0}" != "1" ]; then
  echo "Это перезапишет текущую базу TuneBridge данными из:"
  echo "  $DB_GZ"
  [ -n "$DATA_TGZ" ] && echo "  $DATA_TGZ"
  printf "Продолжить? Введите yes: "
  read -r answer
  [ "$answer" = "yes" ] || { echo "Отменено."; exit 1; }
fi

# Кладём файлы в отдельный каталог и монтируем его в контейнер только для чтения.
STAGE="$(mktemp -d)"
trap 'rm -rf "$STAGE"' EXIT
cp "$DB_GZ" "$STAGE/restore.db.gz"
if [ -n "$DATA_TGZ" ]; then cp "$DATA_TGZ" "$STAGE/restore-data.tar.gz"; fi

echo "==> Останавливаю tunebridge"
docker compose stop tunebridge

echo "==> Восстанавливаю базу и файлы в том"
# run создаёт временный контейнер с тем же томом; entrypoint переопределяем на sh.
docker compose run --rm --no-deps \
  -v "$STAGE:/restore:ro" \
  --entrypoint sh tunebridge -c '
    set -e
    # Старые журналы WAL несовместимы с восстановленной базой — убираем.
    rm -f /app/data/tunebridge.db-wal /app/data/tunebridge.db-shm
    gzip -dc /restore/restore.db.gz > /app/data/tunebridge.db
    if [ -f /restore/restore-data.tar.gz ]; then
      tar -xzf /restore/restore-data.tar.gz -C /app/data
    fi
    echo "    база и файлы восстановлены"
  '

echo "==> Запускаю tunebridge"
docker compose up -d tunebridge

echo "==> Жду healthcheck"
for _ in $(seq 1 30); do
  status="$(docker inspect --format '{{.State.Health.Status}}' "$(docker compose ps -q tunebridge)" 2>/dev/null || echo starting)"
  if [ "$status" = "healthy" ]; then
    echo "Готово: tunebridge healthy. Восстановление завершено."
    exit 0
  fi
  sleep 2
done
echo "Контейнер не стал healthy за 60с. Проверьте: docker compose logs tunebridge" >&2
exit 1