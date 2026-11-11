from __future__ import annotations

import json
import logging
import re
import time
import uuid
from pathlib import Path
from typing import Any
from urllib import error as urlerror
from urllib import request as urlrequest

from .config import BOT_TOKEN, BOT_USERNAME, DATA_DIR, SERVICE_NAMES
from .models import Playlist
from .providers.base import ProviderError
from .providers.files import build_export_zip
from .storage import get_service_credentials, remove_service_credentials, scoped_user_id, set_service_credentials

logger = logging.getLogger("tunebridge.telegram")

TELEGRAM_PATH = DATA_DIR / "telegram.json"
_API_URL = "https://api.telegram.org/bot{token}/{method}"
_TOKEN_RE = re.compile(r"^\d{5,15}:[A-Za-z0-9_-]{30,80}$")
_MESSAGE_LIMIT = 3800
_TRACK_LIST_LIMIT = 150
_bot_username_cache: str | None = None
_bot_username_checked_at = 0.0


def _load() -> dict[str, Any]:
    try:
        data = json.loads(TELEGRAM_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def _save(data: dict[str, Any]) -> None:
    TELEGRAM_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _token() -> str:
    return BOT_TOKEN or str(_load().get("token") or "")


def bot_token() -> str:
    return _token()


def _multipart(payload: dict[str, str], files: dict[str, tuple[str, bytes, str]]) -> tuple[bytes, str]:
    boundary = uuid.uuid4().hex
    chunks: list[bytes] = []
    for name, value in payload.items():
        chunks.append(
            f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"\r\n\r\n'.encode("utf-8")
            + str(value).encode("utf-8")
            + b"\r\n"
        )
    for name, (filename, content, content_type) in files.items():
        chunks.append(
            (
                f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"; filename="{filename}"\r\n'
                f"Content-Type: {content_type}\r\n\r\n"
            ).encode("utf-8")
            + content
            + b"\r\n"
        )
    chunks.append(f"--{boundary}--\r\n".encode("utf-8"))
    return b"".join(chunks), f"multipart/form-data; boundary={boundary}"


def _call(
    method: str,
    payload: dict[str, Any] | None = None,
    files: dict[str, tuple[str, bytes, str]] | None = None,
    *,
    timeout: int = 25,
) -> dict[str, Any]:
    token = _token()
    if not token:
        raise ProviderError(
            "Telegram: бот не подключён",
            "Добавьте токен бота — кнопка «Подключить Telegram».",
            fatal=True,
        )
    if files:
        body, content_type = _multipart({k: str(v) for k, v in (payload or {}).items()}, files)
    else:
        body = json.dumps(payload or {}).encode("utf-8")
        content_type = "application/json"
    request = urlrequest.Request(
        _API_URL.format(token=token, method=method),
        data=body,
        headers={"Content-Type": content_type},
        method="POST",
    )
    try:
        with urlrequest.urlopen(request, timeout=timeout) as response:
            data = json.loads(response.read().decode("utf-8"))
    except urlerror.HTTPError as exc:
        try:
            detail = json.loads(exc.read().decode("utf-8"))
        except (ValueError, OSError):
            detail = {}
        description = str(detail.get("description") or "")
        if exc.code == 401:
            raise ProviderError(
                "Telegram не принял токен",
                "Токен отозван или скопирован с ошибкой. Создайте нового бота через @BotFather.",
                fatal=True,
            ) from exc
        if "chat not found" in description:
            raise ProviderError(
                "Telegram не нашёл этот чат",
                "Откройте бота в Telegram и отправьте ему /start, либо укажите @канал, где бот администратор.",
            ) from exc
        if "not enough rights" in description or "administrator" in description:
            raise ProviderError(
                "Боту не хватает прав в канале",
                "Добавьте бота администратором канала с правом публикации сообщений.",
            ) from exc
        raise ProviderError(
            "Telegram вернул ошибку",
            description or f"Код ответа {exc.code}. Попробуйте ещё раз.",
        ) from exc
    except (urlerror.URLError, TimeoutError, OSError) as exc:
        raise ProviderError(
            "Нет связи с Telegram",
            "Проверьте интернет. Если Telegram недоступен напрямую, включите VPN и повторите.",
        ) from exc
    if not data.get("ok"):
        raise ProviderError(
            "Telegram отклонил запрос",
            str(data.get("description") or "Проверьте токен и повторите."),
        )
    return data


def get_me() -> dict[str, Any]:
    return _call("getMe")["result"]


def connect(token: str) -> dict[str, Any]:
    if BOT_TOKEN:
        raise ProviderError(
            "Бот уже подключён",
            "В этом режиме используется общий бот TuneBridge — подключение своего бота недоступно.",
        )
    value = (token or "").strip()
    if not _TOKEN_RE.match(value):
        raise ProviderError(
            "Это не похоже на токен бота",
            "Токен выглядит так: 123456789:AAH… — скопируйте его из сообщения @BotFather целиком.",
        )
    saved = _load()
    saved["token"] = value
    _save(saved)
    try:
        me = get_me()
    except ProviderError:
        if not saved.get("bot"):
            try:
                TELEGRAM_PATH.unlink()
            except OSError:
                pass
        raise
    saved = _load()
    saved["token"] = value
    saved["bot"] = {
        "id": me.get("id"),
        "username": me.get("username"),
        "name": me.get("first_name"),
    }
    _save(saved)
    return profile() or {}


def profile() -> dict[str, Any] | None:
    if BOT_TOKEN:
        username = BOT_USERNAME or bot_username()
        return {"name": f"@{username}" if username else "Telegram-бот", "id": None, "bot": True}
    data = _load()
    if not data.get("token"):
        return None
    bot = data.get("bot") or {}
    username = bot.get("username") or BOT_USERNAME or bot_username()
    name = f"@{username}" if username else "Telegram-бот"
    return {"name": name, "id": bot.get("id"), "bot": True}


def bot_username(refresh: bool = False) -> str | None:
    global _bot_username_cache, _bot_username_checked_at
    if _bot_username_cache and not refresh:
        return _bot_username_cache
    saved = "" if BOT_TOKEN else ((_load().get("bot") or {}).get("username") or "").strip()
    if saved:
        _bot_username_cache = saved
        return saved
    if BOT_USERNAME:
        _bot_username_cache = BOT_USERNAME
        return BOT_USERNAME
    if not _token():
        return None
    if not refresh and time.time() - _bot_username_checked_at < 300:
        return None
    _bot_username_checked_at = time.time()
    try:
        me = get_me()
    except ProviderError:
        return None
    username = str(me.get("username") or "").strip()
    if username:
        _bot_username_cache = username
        if not BOT_TOKEN:
            data = _load()
            data["bot"] = {
                "id": me.get("id"),
                "username": username,
                "name": me.get("first_name"),
            }
            try:
                _save(data)
            except OSError:
                pass
    return username or None


def is_connected() -> bool:
    return bool(_token())


def saved_chat() -> str:
    if scoped_user_id() is not None:
        return str(get_service_credentials("telegram").get("chat") or "")
    return str(_load().get("chat") or "")


def _save_chat(chat: str) -> None:
    if scoped_user_id() is not None:
        creds = get_service_credentials("telegram")
        creds["chat"] = chat
        set_service_credentials("telegram", creds)
        return
    saved = _load()
    saved["chat"] = chat
    _save(saved)


def disconnect() -> None:
    if scoped_user_id() is not None:
        remove_service_credentials("telegram")
        return
    try:
        TELEGRAM_PATH.unlink()
    except OSError:
        pass


def chat_label(chat: str) -> str:
    value = (chat or "").strip()
    if not value:
        return "чат с ботом"
    if value.lstrip("-").isdigit():
        return f"чат {value}"
    return value


def discover_chats() -> list[dict[str, Any]]:
    if BOT_TOKEN:
        # The service bot receives messages from every user: its update queue is not
        # a per-user chat list, so exposing it would leak other people's chats.
        return []
    data = _call("getUpdates", {"limit": 100, "timeout": 0, "allowed_updates": ["message"]})
    found: dict[str, dict[str, Any]] = {}
    for update in data.get("result", []):
        message = update.get("message") or update.get("edited_message") or {}
        chat = message.get("chat") or {}
        chat_id = chat.get("id")
        if chat_id is None:
            continue
        kind = chat.get("type") or "private"
        title = (
            chat.get("title")
            or " ".join(part for part in (chat.get("first_name"), chat.get("last_name")) if part)
            or chat.get("username")
            or "Без названия"
        )
        found[str(chat_id)] = {
            "id": chat_id,
            "title": title,
            "type": kind,
            "value": f"@{chat['username']}" if kind == "channel" and chat.get("username") else str(chat_id),
        }
    return list(found.values())[:10]


def _current_telegram_id() -> int | None:
    from . import db

    user_id = scoped_user_id()
    if user_id is None:
        return None
    found = db.row("SELECT telegram_id FROM users WHERE id = ?", (int(user_id),))
    value = found["telegram_id"] if found is not None else None
    return int(value) if value else None


def _resolve_chat(chat: str) -> str:
    value = (chat or "").strip()
    if value:
        if value.startswith("@") or value.lstrip("-").isdigit():
            return value
        raise ProviderError(
            "Непонятный адрес чата",
            "Укажите @username канала или числовой ID из списка найденных чатов.",
        )
    if BOT_TOKEN:
        own = _current_telegram_id()
        if own is not None:
            return str(own)
        raise ProviderError(
            "Укажите, куда отправить",
            "Введите @username канала или числовой ID чата.",
        )
    discovered = discover_chats()
    if not discovered:
        raise ProviderError(
            "Пока не видно, куда отправлять",
            "Откройте бота в Telegram, нажмите Start и отправьте /start. Затем вернитесь и повторите отправку.",
        )
    return discovered[0]["value"]


def _track_lines(playlist: Playlist, limit: int) -> list[str]:
    lines: list[str] = []
    for index, track in enumerate(playlist.tracks[:limit], start=1):
        artists = ", ".join(track.artists)
        title = track.title or "Без названия"
        line = f"{index}. {artists} — {title}" if artists else f"{index}. {title}"
        if track.url:
            line += f"\n{track.url}"
        lines.append(line)
    return lines


def _message_chunks(text: str) -> list[str]:
    chunks: list[str] = []
    current = ""
    for block in text.split("\n\n"):
        candidate = f"{current}\n\n{block}" if current else block
        if len(candidate) > _MESSAGE_LIMIT:
            if current:
                chunks.append(current)
            current = block
        else:
            current = candidate
    if current:
        chunks.append(current)
    return chunks or [text[:_MESSAGE_LIMIT]]


def _slug(title: str) -> str:
    slug = re.sub(r"[^\w\-.]+", "-", title or "playlist", flags=re.UNICODE).strip("-")[:60]
    return slug or "playlist"


def _tracks_word(count: int) -> str:
    tail = abs(count) % 100
    last = tail % 10
    if 11 <= tail <= 14 or last == 0 or last >= 5:
        return "треков"
    return "трек" if last == 1 else "трека"


def build_text(playlist: Playlist) -> str:
    service = SERVICE_NAMES.get(playlist.service, playlist.service)
    total = len(playlist.tracks)
    header = [f"🎵 {playlist.title or 'Плейлист'}", f"{total} {_tracks_word(total)} · источник: {service}"]
    if playlist.url:
        header.append(playlist.url)
    if total > _TRACK_LIST_LIMIT:
        header.append(
            f"Ниже — первые {_TRACK_LIST_LIMIT}. Полный список со ссылками — в приложенном архиве."
        )
    blocks = ["\n".join(header)]
    blocks.extend(_track_lines(playlist, _TRACK_LIST_LIMIT))
    return "\n\n".join(blocks)


def send_playlist(playlist: Playlist, chat: str = "", formats: list[str] | None = None) -> dict[str, Any]:
    if not playlist.tracks:
        raise ProviderError("В плейлисте нет треков", "Загрузите плейлист заново.")
    target = _resolve_chat(chat)
    label = chat_label(target)

    messages = 0
    for index, chunk in enumerate(_message_chunks(build_text(playlist)), start=1):
        _call(
            "sendMessage",
            {
                "chat_id": target,
                "text": chunk,
                "disable_web_page_preview": True,
            },
        )
        messages += 1

    archive_sent = False
    selected = [fmt for fmt in (formats or []) if fmt in {"m3u", "csv", "json"}]
    if selected:
        data = build_export_zip(playlist, selected)
        filename = f"{_slug(playlist.title)}-tunebridge.zip"
        _call(
            "sendDocument",
            {
                "chat_id": target,
                "caption": f"«{playlist.title or 'Плейлист'}» · {len(playlist.tracks)} {_tracks_word(len(playlist.tracks))} · {', '.join(selected).upper()}",
            },
            {"document": (filename, data, "application/zip")},
            timeout=60,
        )
        archive_sent = True

    _save_chat(target)

    return {
        "ok": True,
        "chat": label,
        "messages": messages,
        "archive": archive_sent,
        "tracks": len(playlist.tracks),
    }


def send_message(chat_id: int | str, text: str) -> dict[str, Any]:
    value = str(chat_id or "").strip()
    if not value:
        raise ProviderError("Не указан чат", "Передайте chat_id получателя.")
    return _call("sendMessage", {"chat_id": value, "text": text[:4000], "disable_web_page_preview": True})


def create_invoice_link(
    *,
    title: str,
    description: str,
    payload: str,
    prices: list[dict[str, Any]],
    currency: str = "XTR",
) -> str:
    result = _call(
        "createInvoiceLink",
        {
            "title": title[:32],
            "description": description[:255],
            "payload": payload,
            "provider_token": "",
            "currency": currency,
            "prices": prices,
        },
    ).get("result")
    if not isinstance(result, str) or not result.startswith(("https://", "tg:")):
        raise ProviderError("Telegram не вернул ссылку на оплату", "Попробуйте ещё раз через минуту.")
    return result


def answer_pre_checkout_query(query_id: str, *, ok: bool, error_message: str | None = None) -> dict[str, Any]:
    payload: dict[str, Any] = {"pre_checkout_query_id": query_id, "ok": bool(ok)}
    if not ok and error_message:
        payload["error_message"] = error_message[:200]
    return _call("answerPreCheckoutQuery", payload)


def refund_star_payment(user_id: int, charge_id: str) -> dict[str, Any]:
    return _call(
        "refundStarPayment",
        {"user_id": int(user_id), "telegram_payment_charge_id": charge_id},
    )


def get_updates(offset: int = 0, timeout: int = 25) -> list[dict[str, Any]]:
    data = _call(
        "getUpdates",
        {
            "offset": int(offset),
            "timeout": int(timeout),
            "allowed_updates": ["message", "pre_checkout_query"],
        },
        timeout=int(timeout) + 15,
    )
    updates = data.get("result")
    return updates if isinstance(updates, list) else []
