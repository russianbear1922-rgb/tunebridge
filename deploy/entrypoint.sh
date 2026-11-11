#!/bin/sh
set -eu

# Доверяем X-Forwarded-For только прокси внутри docker-сети и loopback,
# иначе клиент сможет подменить IP и обойти ограничение частоты запросов.
exec uvicorn app.main:app \
  --host "${TUNEBRIDGE_HOST:-0.0.0.0}" \
  --port "${TUNEBRIDGE_PORT:-8787}" \
  --proxy-headers \
  --forwarded-allow-ips="${TUNEBRIDGE_TRUSTED_PROXIES:-172.16.0.0/12,127.0.0.1}"
