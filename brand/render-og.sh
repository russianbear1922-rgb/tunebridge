#!/usr/bin/env bash
# Пересобирает static/img/og-image.png (1200x630) из brand/og-card.html.
# Нужен Chrome или Chromium; путь можно задать через CHROME=/path/to/chrome.
set -euo pipefail
cd "$(dirname "$0")/.."

CHROME="${CHROME:-}"
if [ -z "$CHROME" ]; then
  for candidate in \
    "/c/Program Files/Google/Chrome/Application/chrome.exe" \
    "/c/Program Files (x86)/Google/Chrome/Application/chrome.exe" \
    "/usr/bin/google-chrome" "/usr/bin/chromium" "/usr/bin/chromium-browser"; do
    if [ -x "$candidate" ]; then CHROME="$candidate"; break; fi
  done
fi
if [ -z "$CHROME" ]; then
  echo "Chrome/Chromium не найден. Запустите: CHROME=/path/to/chrome bash brand/render-og.sh" >&2
  exit 1
fi

ROOT="$PWD"
OUT="$ROOT/static/img/og-image.png"
if command -v cygpath >/dev/null 2>&1; then
  ROOT="$(cygpath -m "$ROOT")"
  OUT="$(cygpath -m "$OUT")"
fi

"$CHROME" --headless=new --disable-gpu --hide-scrollbars --allow-file-access-from-files \
  --window-size=1200,630 --virtual-time-budget=15000 \
  --screenshot="$OUT" "file://$ROOT/brand/og-card.html"
echo "OK: $OUT"