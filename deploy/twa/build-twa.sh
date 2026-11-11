#!/usr/bin/env bash
# Сборка Android TWA (обёртки сайта) через Bubblewrap и генерация assetlinks.
#
# Что делает:
#   1. рендерит deploy/twa/twa-manifest.template.json в рабочий каталог;
#   2. создаёт android.keystore (если его ещё нет) — ключ подписи приложения;
#   3. собирает подписанные APK и AAB через `bubblewrap build`;
#   4. достаёт SHA-256 отпечаток, добавляет его в проект и генерирует assetlinks.json;
#   5. печатает строки для .env сервера (TUNEBRIDGE_TWA_PACKAGE / TUNEBRIDGE_TWA_SHA256).
#
# Запуск (из любого каталога):
#   TWA_DOMAIN=tunebridge.example.com bash deploy/twa/build-twa.sh
#   # или: bash deploy/twa/build-twa.sh tunebridge.example.com
#
# Необязательные переменные:
#   TWA_PACKAGE       package id (по умолчанию app.tunebridge)
#   TWA_VERSION_NAME  версия для людей (по умолчанию 1.4.0)
#   TWA_VERSION_CODE  целое число версии для Play (по умолчанию 1; увеличивайте при каждом релизе)
#   TWA_BUILD_DIR     рабочий каталог (по умолчанию deploy/twa/build)
#   BUBBLEWRAP_KEYSTORE_PASSWORD / BUBBLEWRAP_KEY_PASSWORD — пароли ключа.
#     Если не заданы, скрипт спросит их скрытым вводом. В git и в логи они не попадают.
#
# Требования: Node.js 18+, JDK (keytool), Android SDK, @bubblewrap/cli.
#   npm i -g @bubblewrap/cli
#   При первом `bubblewrap build` CLI спросит пути к JDK и Android SDK и скачает Build Tools.
#
# ВАЖНО: android.keystore и пароли — единственный ключ подписи. Потеряете ключ —
# не сможете обновлять приложение в Play. Храните каталог сборки в надёжном месте,
# в репозиторий он не попадает (см. .gitignore).

set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
TEMPLATE="$ROOT/deploy/twa/twa-manifest.template.json"

# --- конфигурация -------------------------------------------------------------
DOMAIN="${1:-${TWA_DOMAIN:-}}"
if [ -z "$DOMAIN" ] && [ -f "$ROOT/.env" ]; then
  DOMAIN="$(sed -n 's/^TUNEBRIDGE_DOMAIN=//p' "$ROOT/.env" | head -1)"
fi
# принимаем и голый домен, и полный URL — оставляем только хост
DOMAIN="${DOMAIN#http://}"; DOMAIN="${DOMAIN#https://}"; DOMAIN="${DOMAIN%%/*}"
if [ -z "$DOMAIN" ]; then
  echo "Не задан домен. Запустите: TWA_DOMAIN=example.com bash deploy/twa/build-twa.sh" >&2
  exit 1
fi

PACKAGE="${TWA_PACKAGE:-app.tunebridge}"
VERSION_NAME="${TWA_VERSION_NAME:-1.4.0}"
VERSION_CODE="${TWA_VERSION_CODE:-1}"
BUILD_DIR="${TWA_BUILD_DIR:-$ROOT/deploy/twa/build}"
BASE_URL="https://$DOMAIN"

case "$VERSION_CODE" in
  ''|*[!0-9]*) echo "TWA_VERSION_CODE должен быть целым числом, получено: $VERSION_CODE" >&2; exit 1 ;;
esac

# --- требования ---------------------------------------------------------------
for tool in node keytool; do
  command -v "$tool" >/dev/null 2>&1 || { echo "Не найдено: $tool. Установите Node.js 18+ и JDK." >&2; exit 1; }
done
if ! command -v bubblewrap >/dev/null 2>&1; then
  echo "Не найдено: bubblewrap. Установите: npm i -g @bubblewrap/cli" >&2
  exit 1
fi
[ -f "$TEMPLATE" ] || { echo "Нет шаблона: $TEMPLATE" >&2; exit 1; }

mkdir -p "$BUILD_DIR"
BUILD_DIR="$(cd "$BUILD_DIR" && pwd)"

# --- рендер манифеста ---------------------------------------------------------
echo "==> Манифест: $PACKAGE @ $DOMAIN (version $VERSION_NAME / code $VERSION_CODE)"
TWA_DOMAIN="$DOMAIN" TWA_BASE_URL="$BASE_URL" TWA_PACKAGE="$PACKAGE" \
TWA_VERSION_NAME="$VERSION_NAME" TWA_VERSION_CODE="$VERSION_CODE" \
node -e '
  const fs = require("fs");
  const [tpl, out] = process.argv.slice(1);
  const e = process.env;
  let s = fs.readFileSync(tpl, "utf8");
  s = s.replaceAll("__DOMAIN__", e.TWA_DOMAIN)
       .replaceAll("__BASE_URL__", e.TWA_BASE_URL)
       .replaceAll("__PACKAGE__", e.TWA_PACKAGE)
       .replaceAll("__VERSION_NAME__", e.TWA_VERSION_NAME)
       .replaceAll("__VERSION_CODE__", e.TWA_VERSION_CODE);
  JSON.parse(s); // проверка, что получился валидный JSON
  fs.writeFileSync(out, s);
' "$TEMPLATE" "$BUILD_DIR/twa-manifest.json"

# --- пароли ключа -------------------------------------------------------------
if [ -z "${BUBBLEWRAP_KEYSTORE_PASSWORD:-}" ]; then
  read -rs -p "Пароль хранилища ключа (придумайте и запомните): " BUBBLEWRAP_KEYSTORE_PASSWORD; echo
fi
if [ -z "${BUBBLEWRAP_KEY_PASSWORD:-}" ]; then
  read -rs -p "Пароль ключа (Enter — тот же, что и хранилище): " BUBBLEWRAP_KEY_PASSWORD; echo
  BUBBLEWRAP_KEY_PASSWORD="${BUBBLEWRAP_KEY_PASSWORD:-$BUBBLEWRAP_KEYSTORE_PASSWORD}"
fi
[ -n "$BUBBLEWRAP_KEYSTORE_PASSWORD" ] || { echo "Пустой пароль хранилища недопустим." >&2; exit 1; }
export BUBBLEWRAP_KEYSTORE_PASSWORD BUBBLEWRAP_KEY_PASSWORD

# --- ключ подписи -------------------------------------------------------------
KEYSTORE="$BUILD_DIR/android.keystore"
if [ ! -f "$KEYSTORE" ]; then
  echo "==> Создаю ключ подписи: $KEYSTORE"
  keytool -genkeypair -v \
    -keystore "$KEYSTORE" -alias android \
    -keyalg RSA -keysize 2048 -validity 10000 \
    -storepass:env BUBBLEWRAP_KEYSTORE_PASSWORD \
    -keypass:env BUBBLEWRAP_KEY_PASSWORD \
    -dname "CN=TuneBridge, OU=Mobile, O=TuneBridge, C=RU"
else
  echo "==> Использую существующий ключ: $KEYSTORE"
fi

# --- сборка -------------------------------------------------------------------
echo "==> bubblewrap build (APK + AAB)"
cd "$BUILD_DIR"
bubblewrap build --skipPwaValidation

# --- отпечаток и assetlinks ---------------------------------------------------
echo "==> SHA-256 отпечаток и assetlinks.json"
SHA256="$(keytool -list -v -keystore "$KEYSTORE" -alias android \
  -storepass:env BUBBLEWRAP_KEYSTORE_PASSWORD 2>/dev/null \
  | sed -n 's/^[[:space:]]*SHA256:[[:space:]]*//p' | head -1)"
[ -n "$SHA256" ] || { echo "Не удалось прочитать SHA-256 из ключа." >&2; exit 1; }

bubblewrap fingerprint add "$SHA256" --name "upload" >/dev/null 2>&1 || \
  bubblewrap fingerprint add "$SHA256" >/dev/null
bubblewrap fingerprint generateAssetLinks --output="$BUILD_DIR/assetlinks.json" >/dev/null

# --- итог ---------------------------------------------------------------------
cat <<EOF

Готово. Артефакты в $BUILD_DIR:
  app-release-signed.apk   — для прямой установки на телефон
  app-release-bundle.aab   — для загрузки в Google Play Console
  assetlinks.json          — файл привязки домена (сервер отдаёт его сам, см. ниже)

Добавьте в .env на сервере и перезапустите (docker compose up -d):
  TUNEBRIDGE_TWA_PACKAGE=$PACKAGE
  TUNEBRIDGE_TWA_SHA256=$SHA256

Сервер сам отдаёт /.well-known/assetlinks.json из этих переменных — отдельная
загрузка файла не нужна. Проверка: curl https://$DOMAIN/.well-known/assetlinks.json

Если приложение подписывается через Google Play App Signing, в Play Console
возьмите SHA-256 из «App integrity» и добавьте его вторым через запятую:
  TUNEBRIDGE_TWA_SHA256=$SHA256,<PLAY_SHA256>
EOF