# Деплой TuneBridge — пошаговый runbook

Практическая инструкция «с нуля до работающего сайта и приложения». Рассчитана на
бесплатный режим (без токенов и оплат, доход с рекламы) и хостинг Oracle Cloud Always
Free. Глубокие детали и описание возможностей — в [README.md](README.md); здесь —
конкретные команды по порядку.

Всё, что можно автоматизировать, лежит в скриптах:

| Скрипт | Назначение |
| --- | --- |
| `deploy/bootstrap-oracle.sh` | первичная настройка VM: Docker, фаервол, репозиторий, `.env` |
| `deploy/backup.sh` | бэкап базы и файлов `data/` из работающего compose |
| `deploy/restore.sh` | восстановление бэкапа в том |
| `deploy/twa/build-twa.sh` | сборка Android-приложения (TWA) и генерация assetlinks |

---

## 0. Что понадобится заранее

Это то, что нельзя сделать скриптом — нужны ваши аккаунты:

- **Oracle Cloud** аккаунт (карта для верификации, списаний на Always Free нет).
- **Домен** и доступ к его DNS (например, `tunebridge.example.com`).
- **Telegram-бот**: токен от [@BotFather](https://t.me/BotFather) (`/newbot`).
- **Ваш Telegram ID** (узнать у [@userinfobot](https://t.me/userinfobot)) — для админки.
- Для Android-приложения: **Google Play Console** аккаунт ($25 разово) и компьютер с
  Node.js 18+, JDK и Android SDK.
- Для рекламы: аккаунт рекламной сети или свои прямые рекламодатели.

---

## 1. Виртуальная машина Oracle

1. Console → **Compute → Instances → Create Instance**.
2. Image: **Ubuntu 22.04/24.04**, Shape: **Ampere ARM `VM.Standard.A1.Flex`**
   (Always Free: до 2 OCPU / 12 ГБ — берите 1–2 OCPU / 6–12 ГБ).
3. Скачайте **SSH-ключ** при создании (или добавьте свой публичный ключ).
4. Запомните **публичный IP** машины.

Подключитесь:

```bash
ssh -i ~/path/to/key ubuntu@<PUBLIC_IP>
```

## 2. Первичная настройка (bootstrap)

Скрипт ставит Docker, открывает порты в фаерволе (образы Oracle игнорируют `ufw`,
поэтому правила добавляются прямо в `iptables` и сохраняются), клонирует репозиторий
в `/opt/tunebridge` и создаёт `.env` со сгенерированным `SECRET_KEY`.

```bash
# из склонированного репозитория:
sudo REPO_URL=https://github.com/<you>/<repo>.git bash deploy/bootstrap-oracle.sh

# или одной командой на чистой машине:
curl -fsSL https://raw.githubusercontent.com/<you>/<repo>/main/deploy/bootstrap-oracle.sh -o bootstrap.sh
sudo REPO_URL=https://github.com/<you>/<repo>.git bash bootstrap.sh
```

После завершения перелогиньтесь, чтобы заработали права группы `docker`:

```bash
exit && ssh -i ~/path/to/key ubuntu@<PUBLIC_IP>
```

## 3. Сеть: OCI ingress + DNS

Скрипт открыл порты **внутри** VM. Облачный фаервол Oracle нужно открыть отдельно:

1. Console → Instance → **Primary VNIC → Subnet → Security List** (или NSG).
2. **Add Ingress Rules**: Source `0.0.0.0/0`, IP Protocol **TCP**, Destination Port
   Range `80,443`.
3. DNS: **A-запись** `tunebridge.example.com` → `<PUBLIC_IP>`.

Проверка, что DNS-propagation прошёл: `dig +short tunebridge.example.com`.

## 4. Окружение `.env`

```bash
cd /opt/tunebridge
nano .env
```

Заполните обязательное:

```ini
TUNEBRIDGE_DOMAIN=tunebridge.example.com
TUNEBRIDGE_BASE_URL=https://tunebridge.example.com
TUNEBRIDGE_BOT_TOKEN=123456:ABC...        # от @BotFather
TUNEBRIDGE_BOT_USERNAME=tunebridge_bot
TUNEBRIDGE_WEBHOOK_SECRET=<длинная случайная строка>
TUNEBRIDGE_ADMIN_IDS=<ваш Telegram ID>
TUNEBRIDGE_FREE_MODE=1                     # бесплатно, без токенов
TUNEBRIDGE_COOKIE_SECURE=1
```

`TUNEBRIDGE_SECRET_KEY` уже сгенерирован bootstrap-скриптом — не меняйте его после
запуска, иначе сохранённые подключения пользователей станут нечитаемыми.

Реклама (свой блок; пустые `AD_TITLE`/`AD_URL` — блок не показывается):

```ini
TUNEBRIDGE_AD_TITLE=Заголовок оффера
TUNEBRIDGE_AD_TEXT=Короткое описание
TUNEBRIDGE_AD_CTA=Подробнее
TUNEBRIDGE_AD_URL=https://рекламодатель.example/offer
TUNEBRIDGE_AD_IMAGE=/static/img/ads/banner.png   # только со своего домена
```

Контакт для юридических страниц (необязательно, но желательно):

```ini
TUNEBRIDGE_OPERATOR=ИП Иванов И.И.
TUNEBRIDGE_CONTACT_EMAIL=support@example.com
TUNEBRIDGE_CONTACT_TELEGRAM=tunebridge_support
```

## 5. Запуск

```bash
docker compose up -d --build
docker compose ps                 # tunebridge: healthy, caddy: up
docker compose logs -f caddy      # видно получение сертификата Let's Encrypt
```

Caddy сам получит HTTPS-сертификат, как только DNS указывает на машину и порты
80/443 открыты. Проверка:

```bash
curl -fsS https://tunebridge.example.com/api/health
# {"ok":true,"name":"TuneBridge",...,"mode":"hosted","free":true}
```

Откройте `https://tunebridge.example.com` в браузере — должен загрузиться сайт.

## 6. Telegram: бот, Mini App, вебхук

1. **Mini App**: @BotFather → `/newapp` → выберите бота → название, описание,
   картинка (можно `static/img/og-image.png`) и URL `https://tunebridge.example.com/`.
2. **Вебхук** (принимает обновления бота и оплаты; нужен секрет):

   ```bash
   source <(grep -E '^TUNEBRIDGE_(BOT_TOKEN|WEBHOOK_SECRET)=' .env)
   curl "https://api.telegram.org/bot$TUNEBRIDGE_BOT_TOKEN/setWebhook" \
     -d "url=https://tunebridge.example.com/api/billing/telegram/webhook" \
     -d "secret_token=$TUNEBRIDGE_WEBHOOK_SECRET"
   ```

3. Проверка: `curl "https://api.telegram.org/bot$TUNEBRIDGE_BOT_TOKEN/getWebhookInfo"`
   — `url` заполнен, `last_error_message` пусто.

Вход на сайте — через Telegram (кнопка «Войти через Telegram» / Mini App).

## 7. Бэкапы и восстановление

Бэкап (база через SQLite backup API + файлы `data/`, хранение 14 дней):

```bash
./deploy/backup.sh
ls backups/        # tunebridge-<stamp>.db.gz, data-<stamp>.tar.gz
```

Cron на ежедневный бэкап в 03:17:

```cron
17 3 * * * /opt/tunebridge/deploy/backup.sh >> /var/log/tunebridge-backup.log 2>&1
```

Восстановление (останавливает приложение, заменяет базу и файлы, поднимает обратно):

```bash
./deploy/restore.sh backups/tunebridge-<stamp>.db.gz backups/data-<stamp>.tar.gz
# без вопроса подтверждения: FORCE=1 ./deploy/restore.sh ...
```

Бэкапы стоит копировать и за пределы VM (Oracle может пересоздать бесплатный инстанс).

## 8. Автодеплой из GitHub

`ci.yml` на каждый push/PR гоняет тесты **и собирает Docker-образ** (без публикации) —
ловит регрессии Dockerfile. `deploy.yml` после пуша в `main` заходит по SSH и обновляет
сервис.

Секреты репозитория (Settings → Secrets and variables → Actions):

| Секрет | Значение |
| --- | --- |
| `DEPLOY_HOST` | IP или домен сервера |
| `DEPLOY_USER` | `ubuntu` |
| `DEPLOY_SSH_KEY` | приватный SSH-ключ от VM |
| `DEPLOY_PATH` | `/opt/tunebridge` |

Публичный ключ должен быть в `~/.ssh/authorized_keys` на сервере. После настройки
каждый `git push` в `main` автоматически обновляет продакшен.

## 9. Android-приложение (TWA)

TWA — полноэкранная обёртка того же сайта в Chrome. Отдельный код не нужен.

### Сборка

На компьютере с Node.js 18+, JDK и Android SDK:

```bash
npm i -g @bubblewrap/cli
TWA_DOMAIN=tunebridge.example.com bash deploy/twa/build-twa.sh
```

Скрипт отрендерит `deploy/twa/twa-manifest.template.json`, создаст ключ подписи
`android.keystore` (пароли спросит скрытым вводом или возьмёт из
`BUBBLEWRAP_KEYSTORE_PASSWORD` / `BUBBLEWRAP_KEY_PASSWORD`), соберёт подписанные
`app-release-signed.apk` и `app-release-bundle.aab`, сгенерирует `assetlinks.json`
и напечатает строки для `.env`.

> Ключ подписи — единственный. Потеряете `android.keystore` и пароли — не сможете
> обновлять приложение в Play. Каталог `deploy/twa/build/` в git не попадает.

При первом `bubblewrap build` CLI спросит пути к JDK и Android SDK и скачает Build
Tools (нужно принять лицензию).

### Привязка домена

Добавьте напечатанные строки в `.env` на сервере и перезапустите:

```ini
TUNEBRIDGE_TWA_PACKAGE=app.tunebridge
TUNEBRIDGE_TWA_SHA256=AA:BB:CC:...
```

Сервер сам отдаёт `/.well-known/assetlinks.json` из этих переменных — загружать файл
отдельно не нужно. Проверка:

```bash
curl https://tunebridge.example.com/.well-known/assetlinks.json
```

Если включите **Google Play App Signing**, возьмите SHA-256 из Play Console
(«App integrity») и добавьте вторым через запятую — иначе адресная строка в
установленном из Play приложении не исчезнет.

### Публикация

Play Console → Create app → загрузите `app-release-bundle.aab` → заполните карточку
(иконки `static/img/icon-512.png`, скриншоты, описание) → отправьте на ревью.
Политика конфиденциальности: `https://tunebridge.example.com/privacy`.

## 10. iOS

Отдельного приложения в App Store нет — используется PWA: Safari → «Поделиться» →
«На экран „Домой"». Сайт сам подскажет эти шаги (кнопка установки и справка).
Иконка `apple-touch-icon.png` и манифест уже настроены.

## 11. Обновление и откат

```bash
cd /opt/tunebridge
git pull --ff-only
docker compose up -d --build      # пересоберёт и перезапустит без простоя БД
docker image prune -f
```

Откат на предыдущую версию:

```bash
git log --oneline -5              # найти нужный коммит
git checkout <commit>
docker compose up -d --build
```

База переживает обновления: миграции применяются автоматически (`PRAGMA user_version`).
Перед рискованным обновлением сделайте `./deploy/backup.sh`.

## 12. Диагностика

| Симптом | Причина и решение |
| --- | --- |
| Сайт не открывается извне, `curl` с сервера работает | не добавлены OCI Ingress-правила 80/443 (шаг 3) или фаервол VM |
| Порты закрыты после перезагрузки | не сохранены iptables: `sudo netfilter-persistent save` |
| Caddy не получает сертификат | DNS не указывает на IP, или закрыт порт 80; `docker compose logs caddy` |
| Вебхук отвечает 403 | `secret_token` в `setWebhook` ≠ `TUNEBRIDGE_WEBHOOK_SECRET`; перевызовите `setWebhook` |
| Вебхук 503 | не задан `TUNEBRIDGE_WEBHOOK_SECRET` в `.env` |
| В TWA видна адресная строка | не совпадает SHA-256 в `assetlinks.json`; проверьте отпечаток подписи Play |
| 429 на запросах | сработал rate-limit; настройте `TUNEBRIDGE_RATE_*` (см. README) |
| Подключения пользователей «пропали» после смены ключа | меняли `TUNEBRIDGE_SECRET_KEY` — восстановите прежний или переподключите сервисы |

Логи:

```bash
docker compose logs -f tunebridge
docker compose logs -f caddy
```

---

## Монетизация

В бесплатном режиме доход идёт с рекламного блока (`TUNEBRIDGE_AD_*`). Анонимная
статистика показов/кликов и общая сводка доступны админу в личном кабинете
(«Статистика») и через `GET /api/admin/stats`. Счётчики обезличены: только день,
тип события и количество, без персональных данных. Юридические страницы
(`/privacy`, `/terms`) описывают, что именно собирается и хранится.