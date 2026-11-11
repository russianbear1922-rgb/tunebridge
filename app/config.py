from __future__ import annotations

import hashlib
import os
from pathlib import Path

from .network import lan_address

APP_NAME = "TuneBridge"
VERSION = "1.4.0"

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
STATIC_DIR = BASE_DIR / "static"
EXPORT_DIR = DATA_DIR / "exports"

for _path in (DATA_DIR, EXPORT_DIR, DATA_DIR / "tmp"):
    _path.mkdir(parents=True, exist_ok=True)

HOST = os.environ.get("TUNEBRIDGE_HOST", "127.0.0.1")
PORT = int(os.environ.get("TUNEBRIDGE_PORT", "8787"))
LAN_ENABLED = HOST not in {"127.0.0.1", "localhost", "::1"}
if os.environ.get("TUNEBRIDGE_BASE_URL"):
    BASE_URL = os.environ["TUNEBRIDGE_BASE_URL"]
elif LAN_ENABLED:
    BASE_URL = f"http://{lan_address() or HOST}:{PORT}"
else:
    BASE_URL = f"http://{HOST}:{PORT}"
SPOTIFY_REDIRECT_URI = f"{BASE_URL}/api/auth/spotify/callback"

CREDENTIALS_PATH = DATA_DIR / "credentials.json"
SPOTIFY_CACHE_PATH = DATA_DIR / "spotify_token.json"
YOUTUBE_AUTH_PATH = DATA_DIR / "ytmusic_headers.json"
YANDEX_DEVICE_PATH = DATA_DIR / "yandex_device.json"
MATCH_CACHE_PATH = DATA_DIR / "match_cache.json"

MAX_TRACKS = 2000
MAX_IMPORT_BYTES = 5 * 1024 * 1024

SPOTIFY_SCOPES = " ".join(
    [
        "playlist-read-private",
        "playlist-read-collaborative",
        "playlist-modify-public",
        "playlist-modify-private",
        "user-read-private",
    ]
)

SERVICE_NAMES = {
    "yandex": "Яндекс Музыка",
    "spotify": "Spotify",
    "youtube": "YouTube Music",
    "soundcloud": "SoundCloud",
    "apple": "Apple Music",
    "file": "Файл",
    "demo": "Демо",
}

# --------------------------------------------------------------- hosted mode

BOT_TOKEN = os.environ.get("TUNEBRIDGE_BOT_TOKEN", "").strip()
HOSTED = bool(BOT_TOKEN)
BOT_USERNAME = os.environ.get("TUNEBRIDGE_BOT_USERNAME", "").strip().lstrip("@")
WEBHOOK_SECRET = os.environ.get("TUNEBRIDGE_WEBHOOK_SECRET", "").strip()
BOT_POLLING = os.environ.get("TUNEBRIDGE_BOT_POLLING", "").strip().lower() in {"1", "true", "yes"}

# Key for encrypting per-user credentials at rest. A dedicated value is strongly
# recommended: rotating the bot token must not make saved connections unreadable.
SECRET_KEY = os.environ.get("TUNEBRIDGE_SECRET_KEY", "").strip()
SECRET_KEY_FROM_ENV = bool(SECRET_KEY)
if not SECRET_KEY and BOT_TOKEN:
    SECRET_KEY = hashlib.sha256(f"tunebridge-bot:{BOT_TOKEN}".encode("utf-8")).hexdigest()

ADMIN_TELEGRAM_IDS = {
    int(part)
    for part in os.environ.get("TUNEBRIDGE_ADMIN_IDS", "").replace(";", ",").split(",")
    if part.strip().isdigit()
}

DB_PATH = Path(os.environ.get("TUNEBRIDGE_DB_PATH") or (DATA_DIR / "tunebridge.db"))

SESSION_COOKIE = "tb_session"
SESSION_TTL = int(os.environ.get("TUNEBRIDGE_SESSION_TTL", str(30 * 24 * 3600)))
INIT_DATA_TTL = int(os.environ.get("TUNEBRIDGE_INIT_DATA_TTL", "86400"))
COOKIE_SECURE = (
    os.environ.get("TUNEBRIDGE_COOKIE_SECURE", "1" if BASE_URL.startswith("https") else "0").strip()
    in {"1", "true", "yes"}
)

# Free mode keeps every feature unlocked and drops the token economy: nothing is
# charged, wallets and top-ups disappear from the UI. Revenue comes from ads.
FREE_MODE = os.environ.get("TUNEBRIDGE_FREE_MODE", "0").strip().lower() in {"1", "true", "yes"}

TRIAL_TOKENS = int(os.environ.get("TUNEBRIDGE_TRIAL_TOKENS", "50"))
TOKENS_PER_TRACK = 1
STARS_RUB_RATE = float(os.environ.get("TUNEBRIDGE_STARS_RATE", "2.0"))

# Stars amounts are rounded up from the desired ruble price; the difference covers
# Telegram/platform fees. Adjust after checking the actual payout rate.
PACKAGES = (
    {"id": "start", "title": "Старт", "title_en": "Start", "tokens": 100, "stars": 60},
    {"id": "pro", "title": "Про", "title_en": "Pro", "tokens": 500, "stars": 260, "best": True},
    {"id": "max", "title": "Максимум", "title_en": "Max", "tokens": 1000, "stars": 480},
)

# --------------------------------------------------------------------- ads


def _ad_slot() -> dict[str, str] | None:
    """Собственный рекламный блок. Без заголовка и ссылки блок не показывается."""
    title = os.environ.get("TUNEBRIDGE_AD_TITLE", "").strip()
    url = os.environ.get("TUNEBRIDGE_AD_URL", "").strip()
    if not title and not url:
        return None
    if url and not url.startswith(("http://", "https://")):
        url = ""
    image = os.environ.get("TUNEBRIDGE_AD_IMAGE", "").strip()
    if image.startswith("//") or (image and not image.startswith("/")):
        image = ""
    return {
        "label": (os.environ.get("TUNEBRIDGE_AD_LABEL", "").strip() or "Реклама")[:32],
        "title": title[:80],
        "text": os.environ.get("TUNEBRIDGE_AD_TEXT", "").strip()[:200],
        "cta": os.environ.get("TUNEBRIDGE_AD_CTA", "").strip()[:40],
        "url": url,
        "image": image,
    }


AD = _ad_slot()

# ------------------------------------------------------------------- legal

OPERATOR_NAME = os.environ.get("TUNEBRIDGE_OPERATOR", "").strip() or APP_NAME
CONTACT_EMAIL = os.environ.get("TUNEBRIDGE_CONTACT_EMAIL", "").strip()
CONTACT_TELEGRAM = os.environ.get("TUNEBRIDGE_CONTACT_TELEGRAM", "").strip().lstrip("@")

# ------------------------------------------------------ public server guard

RATE_LIMIT_ENABLED = os.environ.get("TUNEBRIDGE_RATE_LIMIT", "1" if HOSTED else "0").strip().lower() in {
    "1",
    "true",
    "yes",
}
RATE_GLOBAL = int(os.environ.get("TUNEBRIDGE_RATE_GLOBAL", "240"))
RATE_HEAVY = int(os.environ.get("TUNEBRIDGE_RATE_HEAVY", "30"))
RATE_AUTH = int(os.environ.get("TUNEBRIDGE_RATE_AUTH", "12"))
MAX_BODY_BYTES = int(os.environ.get("TUNEBRIDGE_MAX_BODY", str(8 * 1024 * 1024)))

# ------------------------------------------------------------- android TWA

TWA_PACKAGE = os.environ.get("TUNEBRIDGE_TWA_PACKAGE", "").strip()
TWA_SHA256 = [
    part.strip().upper()
    for part in os.environ.get("TUNEBRIDGE_TWA_SHA256", "").replace(";", ",").split(",")
    if part.strip()
]
