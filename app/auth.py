from __future__ import annotations

import hashlib
import hmac
import json
import logging
import time
from urllib.parse import parse_qsl

logger = logging.getLogger("tunebridge.auth")

MAX_INIT_DATA_LENGTH = 16 * 1024


class AuthError(Exception):
    def __init__(self, message: str, hint: str | None = None):
        super().__init__(message)
        self.message = message
        self.hint = hint


def validate_init_data(init_data: str, bot_token: str, *, max_age: int = 86400, now: float | None = None) -> dict:
    """Validate Telegram Mini App initData and return its decoded fields."""
    value = (init_data or "").strip()
    if not value:
        raise AuthError(
            "Не пришло подтверждение Telegram",
            "Откройте TuneBridge как Mini App внутри Telegram и повторите вход.",
        )
    if len(value) > MAX_INIT_DATA_LENGTH:
        raise AuthError("Слишком большой запрос авторизации", "Обновите страницу и попробуйте снова.")
    if not bot_token:
        raise AuthError(
            "Вход через Telegram не настроен",
            "Администратору нужно указать TUNEBRIDGE_BOT_TOKEN на сервере.",
        )

    try:
        pairs = parse_qsl(value, keep_blank_values=True, strict_parsing=False)
    except ValueError as exc:
        raise AuthError("Не удалось прочитать подпись Telegram", "Обновите страницу и попробуйте снова.") from exc

    data: dict[str, str] = {}
    for key, item in pairs:
        if key in data:
            raise AuthError("Подпись Telegram повреждена", "Обновите страницу и попробуйте снова.")
        data[key] = item

    received = data.pop("hash", "")
    if not received:
        raise AuthError("В подписи Telegram нет hash", "Обновите страницу и попробуйте снова.")

    check_string = "\n".join(f"{key}={data[key]}" for key in sorted(data))
    secret = hmac.new(b"WebAppData", bot_token.encode("utf-8"), hashlib.sha256).digest()
    expected = hmac.new(secret, check_string.encode("utf-8"), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, received):
        raise AuthError(
            "Telegram не подтвердил вход",
            "Проверьте, что приложение открыто из нужного бота, и попробуйте снова.",
        )

    try:
        auth_date = int(data.get("auth_date", "0"))
    except (TypeError, ValueError) as exc:
        raise AuthError("В подписи нет времени входа", "Обновите страницу и попробуйте снова.") from exc

    current = time.time() if now is None else now
    if auth_date <= 0:
        raise AuthError("В подписи нет времени входа", "Обновите страницу и попробуйте снова.")
    if current - auth_date > max_age:
        raise AuthError("Вход в Telegram устарел", "Закройте и снова откройте Mini App.")
    if auth_date > current + 300:
        raise AuthError("Часы устройства расходятся с сервером", "Проверьте время на телефоне и повторите вход.")

    try:
        user = json.loads(data.get("user") or "{}")
    except ValueError as exc:
        raise AuthError("Не удалось прочитать профиль Telegram", "Обновите страницу и попробуйте снова.") from exc

    if not isinstance(user, dict) or not user.get("id"):
        raise AuthError("Telegram не передал профиль", "Откройте Mini App из бота и повторите вход.")

    try:
        user_id = int(user["id"])
    except (TypeError, ValueError) as exc:
        raise AuthError("Некорректный профиль Telegram", "Обновите страницу и попробуйте снова.") from exc
    if user_id <= 0:
        raise AuthError("Некорректный профиль Telegram", "Обновите страницу и попробуйте снова.")

    return {
        "user": user,
        "auth_date": auth_date,
        "query_id": data.get("query_id"),
    }
