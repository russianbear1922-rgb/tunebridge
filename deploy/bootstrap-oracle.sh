#!/usr/bin/env bash
# Первичная настройка виртуальной машины Oracle Cloud Always Free (Ubuntu, ARM).
# Готовит сервер к запуску TuneBridge через docker compose: Docker, фаервол,
# каталог /opt/tunebridge, репозиторий и .env. Сам сервис НЕ поднимает —
# сначала заполните .env (домен, токен бота), затем docker compose up -d --build.
#
# Запуск на сервере (под root или через sudo):
#   curl -fsSL https://raw.githubusercontent.com/<you>/<repo>/main/deploy/bootstrap-oracle.sh -o bootstrap.sh
#   sudo REPO_URL=https://github.com/<you>/<repo>.git bash bootstrap.sh
#   # или из уже склонированного репозитория:
#   sudo REPO_URL=https://github.com/<you>/<repo>.git bash deploy/bootstrap-oracle.sh
#
# Переменные:
#   REPO_URL     git-адрес репозитория (обязательно, если каталог ещё не склонирован)
#   DEPLOY_PATH  каталог установки (по умолчанию /opt/tunebridge)
#   DEPLOY_USER  пользователь, которому добавить права docker (по умолчанию ubuntu)
#
# Что скрипт НЕ делает (нужно вручную):
#   * Ingress-правила в OCI Console (Security List / NSG): TCP 80 и 443 с 0.0.0.0/0.
#     Без них фаервол VM не поможет — трафик режется на уровне облака.
#   * DNS A-запись домена на публичный IP машины.
#   * Токен бота и секреты в .env.

set -euo pipefail

DEPLOY_PATH="${DEPLOY_PATH:-/opt/tunebridge}"
DEPLOY_USER="${DEPLOY_USER:-ubuntu}"
REPO_URL="${REPO_URL:-}"

if [ "$(id -u)" -ne 0 ]; then
  echo "Запустите с правами root: sudo bash deploy/bootstrap-oracle.sh" >&2
  exit 1
fi
if ! command -v apt-get >/dev/null 2>&1; then
  echo "Скрипт рассчитан на Ubuntu/Debian (apt-get не найден)." >&2
  exit 1
fi

echo "==> Пакеты: git, curl, фаервол, утилиты"
export DEBIAN_FRONTEND=noninteractive
apt-get update -y
apt-get install -y ca-certificates curl gnupg git iptables-persistent netfilter-persistent

echo "==> Docker (официальный репозиторий) + compose plugin"
if ! command -v docker >/dev/null 2>&1; then
  install -m 0755 -d /etc/apt/keyrings
  curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
  chmod a+r /etc/apt/keyrings/docker.asc
  . /etc/os-release
  echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] \
https://download.docker.com/linux/ubuntu ${VERSION_CODENAME} stable" > /etc/apt/sources.list.d/docker.list
  apt-get update -y
  apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
fi
systemctl enable --now docker
if id "$DEPLOY_USER" >/dev/null 2>&1; then
  usermod -aG docker "$DEPLOY_USER"
  echo "    пользователь $DEPLOY_USER добавлен в группу docker (перелогиньтесь)"
fi

echo "==> Фаервол: открываю 80/443 в iptables (образы Oracle игнорируют ufw)"
# В образах Oracle Ubuntu цепочка INPUT заканчивается правилом REJECT,
# которое оценивается раньше правил ufw. Вставляем ACCEPT перед REJECT.
open_port() {
  local port="$1"
  if iptables -C INPUT -p tcp --dport "$port" -j ACCEPT 2>/dev/null; then
    return 0
  fi
  local reject_pos
  reject_pos="$(iptables -L INPUT --line-numbers -n | awk '/REJECT/{print $1; exit}')"
  if [ -n "$reject_pos" ]; then
    iptables -I INPUT "$reject_pos" -p tcp --dport "$port" -j ACCEPT
  else
    iptables -A INPUT -p tcp --dport "$port" -j ACCEPT
  fi
}
open_port 80
open_port 443
# SSH оставляем доступным; ufw на всякий случай тоже настроен (не конфликтует).
if command -v ufw >/dev/null 2>&1; then
  ufw allow OpenSSH >/dev/null 2>&1 || true
  ufw allow 80/tcp >/dev/null 2>&1 || true
  ufw allow 443/tcp >/dev/null 2>&1 || true
fi
netfilter-persistent save
echo "    правила сохранены (переживут перезагрузку)"

echo "==> Каталог и репозиторий: $DEPLOY_PATH"
mkdir -p "$DEPLOY_PATH"
if [ ! -d "$DEPLOY_PATH/.git" ]; then
  if [ -z "$REPO_URL" ]; then
    echo "Каталог пуст и REPO_URL не задан. Укажите: sudo REPO_URL=https://github.com/<you>/<repo>.git bash ..." >&2
    exit 1
  fi
  git clone "$REPO_URL" "$DEPLOY_PATH"
else
  echo "    репозиторий уже на месте, пропускаю клонирование"
fi
cd "$DEPLOY_PATH"
git config --global --add safe.directory "$DEPLOY_PATH" || true

echo "==> .env"
if [ ! -f .env ]; then
  cp .env.example .env
  # Секрет шифрования подключений генерируем сразу — его не нужно придумывать.
  if command -v python3 >/dev/null 2>&1; then
    SECRET="$(python3 -c 'import secrets; print(secrets.token_urlsafe(48))')"
    sed -i "s|^TUNEBRIDGE_SECRET_KEY=.*|TUNEBRIDGE_SECRET_KEY=$SECRET|" .env
  fi
  chmod 600 .env
  echo "    создан .env из .env.example (SECRET_KEY сгенерирован)"
else
  echo "    .env уже существует, не трогаю"
fi
chown -R "$DEPLOY_USER":"$DEPLOY_USER" "$DEPLOY_PATH" 2>/dev/null || true
chmod +x deploy/*.sh deploy/twa/*.sh 2>/dev/null || true

cat <<EOF

==> Готово. Дальше вручную:

1. OCI Console → Networking → Subnet → Security List → Add Ingress Rules:
   TCP, источник 0.0.0.0/0, порты 80 и 443. (Без этого сайт недоступен извне.)

2. DNS: A-запись вашего домена → публичный IP этой машины.

3. Заполните .env:
   sudo nano $DEPLOY_PATH/.env
   Обязательные: TUNEBRIDGE_DOMAIN, TUNEBRIDGE_BASE_URL (https://домен),
   TUNEBRIDGE_BOT_TOKEN, TUNEBRIDGE_BOT_USERNAME, TUNEBRIDGE_ADMIN_IDS.
   Бесплатный режим уже включён (TUNEBRIDGE_FREE_MODE=1).

4. Поднимите сервис:
   cd $DEPLOY_PATH && docker compose up -d --build
   docker compose ps        # tunebridge healthy, caddy up
   docker compose logs -f caddy   # видно выдачу сертификата Let's Encrypt

5. Telegram-вебхук (подставьте токен и секрет из .env):
   curl "https://api.telegram.org/bot<TOKEN>/setWebhook?url=https://<DOMAIN>/api/billing/telegram/webhook&secret_token=<WEBHOOK_SECRET>"

6. Бэкапы (cron):
   17 3 * * * $DEPLOY_PATH/deploy/backup.sh >> /var/log/tunebridge-backup.log 2>&1

Подробный пошаговый разбор — в DEPLOY.md.
EOF