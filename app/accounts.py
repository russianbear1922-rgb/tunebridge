from __future__ import annotations

import datetime
import hashlib
import logging
import secrets
import time
from typing import Any

from fastapi import Request, Response

from . import auth, config, db, telegram

logger = logging.getLogger("tunebridge.accounts")

LOCAL_TELEGRAM_ID = 0
LOCAL_NAME = "Локальный пользователь"


class AuthRequired(Exception):
    def __init__(self, message: str = "Нужен вход через Telegram", hint: str | None = None):
        super().__init__(message)
        self.message = message
        self.hint = hint or "Откройте TuneBridge как Mini App в Telegram и вернитесь в кабинет."


class AdminRequired(Exception):
    def __init__(self, message: str = "Недостаточно прав"):
        super().__init__(message)
        self.message = message
        self.hint = "Действие доступно только администратору сервиса."


def iso(ts: float | int | None) -> str | None:
    if not ts:
        return None
    return datetime.datetime.fromtimestamp(float(ts), datetime.timezone.utc).isoformat()


def _now() -> float:
    return time.time()


def _hash_token(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _is_admin_row(row: Any) -> bool:
    if not config.HOSTED:
        return True
    if row["is_admin"]:
        return True
    telegram_id = row["telegram_id"]
    return bool(telegram_id and int(telegram_id) in config.ADMIN_TELEGRAM_IDS)


def _display_name(row: Any) -> str:
    parts = [row["first_name"], row["last_name"]]
    name = " ".join(part for part in parts if part)
    return name or row["username"] or ("Локальный пользователь" if not row["telegram_id"] else "Гость")


def user_payload(row: Any) -> dict[str, Any]:
    return {
        "id": row["id"],
        "telegram_id": row["telegram_id"] if row["telegram_id"] else None,
        "name": _display_name(row),
        "username": row["username"],
        "lang": row["lang"],
        "balance": int(row["balance"]),
        "trial_granted": bool(row["trial_granted"]),
        "is_admin": _is_admin_row(row),
        "created_at": iso(row["created_at"]),
    }


def _get_user(user_id: int) -> Any:
    return db.row("SELECT * FROM users WHERE id = ?", (int(user_id),))


def _credit_locked(
    conn: Any,
    user_id: int,
    tokens: int,
    kind: str,
    reason: str,
    *,
    ref: str | None = None,
    meta: str | None = None,
) -> dict[str, Any]:
    if ref is not None:
        existing = conn.execute(
            "SELECT * FROM wallet_tx WHERE kind = ? AND ref = ?", (kind, ref)
        ).fetchone()
        if existing is not None:
            return {
                "delta": int(existing["delta"]),
                "balance": int(existing["balance_after"]),
                "kind": kind,
                "created_at": iso(existing["created_at"]),
                "duplicate": True,
            }

    found = conn.execute("SELECT balance FROM users WHERE id = ?", (int(user_id),)).fetchone()
    if found is None:
        raise ValueError("Пользователь не найден")
    new_balance = int(found["balance"]) + int(tokens)
    if new_balance < 0:
        raise ValueError("Недостаточно токенов на балансе")

    now = _now()
    conn.execute(
        "UPDATE users SET balance = ?, updated_at = ? WHERE id = ?",
        (new_balance, now, int(user_id)),
    )
    conn.execute(
        "INSERT INTO wallet_tx(user_id, delta, kind, reason, ref, meta, balance_after, created_at) "
        "VALUES(?, ?, ?, ?, ?, ?, ?, ?)",
        (int(user_id), int(tokens), kind, reason, ref, meta, new_balance, now),
    )
    return {
        "delta": int(tokens),
        "balance": new_balance,
        "kind": kind,
        "created_at": iso(now),
        "duplicate": False,
    }


def credit(
    user_id: int,
    tokens: int,
    kind: str,
    reason: str,
    *,
    ref: str | None = None,
    meta: str | None = None,
) -> dict[str, Any]:
    with db.write_tx() as conn:
        return _credit_locked(conn, user_id, tokens, kind, reason, ref=ref, meta=meta)


def credit_in_conn(
    conn: Any,
    user_id: int,
    tokens: int,
    kind: str,
    reason: str,
    *,
    ref: str | None = None,
    meta: str | None = None,
) -> dict[str, Any]:
    return _credit_locked(conn, user_id, tokens, kind, reason, ref=ref, meta=meta)


def _grant_trial(conn: Any, user_id: int) -> None:
    found = conn.execute("SELECT trial_granted FROM users WHERE id = ?", (int(user_id),)).fetchone()
    if found is None or found["trial_granted"]:
        return
    if config.TRIAL_TOKENS > 0 and not config.FREE_MODE:
        _credit_locked(
            conn,
            user_id,
            config.TRIAL_TOKENS,
            "trial",
            "Приветственные треки",
            ref=f"trial:{user_id}",
        )
    conn.execute("UPDATE users SET trial_granted = 1, updated_at = ? WHERE id = ?", (_now(), int(user_id)))


def ensure_local_user() -> Any:
    found = db.row("SELECT * FROM users WHERE telegram_id = ?", (LOCAL_TELEGRAM_ID,))
    if found is not None:
        return found
    with db.write_tx() as conn:
        found = conn.execute("SELECT * FROM users WHERE telegram_id = ?", (LOCAL_TELEGRAM_ID,)).fetchone()
        if found is None:
            now = _now()
            cursor = conn.execute(
                "INSERT INTO users(telegram_id, username, first_name, lang, balance, trial_granted, is_admin, "
                "created_at, updated_at) VALUES(?, ?, ?, ?, 0, 0, 1, ?, ?)",
                (LOCAL_TELEGRAM_ID, "local", LOCAL_NAME, "ru", now, now),
            )
            user_id = int(cursor.lastrowid)
            _grant_trial(conn, user_id)
            found = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    return found


def upsert_telegram_user(tg_user: dict[str, Any], lang: str | None = None) -> Any:
    telegram_id = int(tg_user["id"])
    username = str(tg_user.get("username") or "")[:64] or None
    first_name = str(tg_user.get("first_name") or "")[:128] or None
    last_name = str(tg_user.get("last_name") or "")[:128] or None
    language = str(tg_user.get("language_code") or lang or "")[:8] or None
    now = _now()

    with db.write_tx() as conn:
        found = conn.execute("SELECT * FROM users WHERE telegram_id = ?", (telegram_id,)).fetchone()
        if found is None:
            cursor = conn.execute(
                "INSERT INTO users(telegram_id, username, first_name, last_name, lang, balance, trial_granted, "
                "is_admin, created_at, updated_at) VALUES(?, ?, ?, ?, ?, 0, 0, ?, ?, ?)",
                (
                    telegram_id,
                    username,
                    first_name,
                    last_name,
                    language,
                    int(telegram_id in config.ADMIN_TELEGRAM_IDS),
                    now,
                    now,
                ),
            )
            user_id = int(cursor.lastrowid)
            _grant_trial(conn, user_id)
        else:
            user_id = int(found["id"])
            conn.execute(
                "UPDATE users SET username = ?, first_name = ?, last_name = ?, lang = COALESCE(?, lang), "
                "is_admin = CASE WHEN ? = 1 THEN 1 ELSE is_admin END, updated_at = ? WHERE id = ?",
                (
                    username,
                    first_name,
                    last_name,
                    language,
                    int(telegram_id in config.ADMIN_TELEGRAM_IDS),
                    now,
                    user_id,
                ),
            )
        return conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()


def create_session(user_id: int, user_agent: str = "") -> tuple[str, str]:
    raw = secrets.token_urlsafe(32)
    session_id = _hash_token(raw)
    csrf = secrets.token_urlsafe(24)
    now = _now()
    with db.write_tx() as conn:
        conn.execute("DELETE FROM sessions WHERE expires_at < ?", (now,))
        conn.execute(
            "INSERT INTO sessions(id, user_id, csrf, created_at, expires_at, last_seen_at, user_agent) "
            "VALUES(?, ?, ?, ?, ?, ?, ?)",
            (session_id, int(user_id), csrf, now, now + config.SESSION_TTL, now, (user_agent or "")[:240]),
        )
    return raw, csrf


def session_from_cookie(raw: str | None) -> dict[str, Any] | None:
    if not raw:
        return None
    found = db.row(
        "SELECT s.id AS session_id, s.csrf, s.expires_at, s.last_seen_at, u.* "
        "FROM sessions s JOIN users u ON u.id = s.user_id WHERE s.id = ?",
        (_hash_token(raw),),
    )
    if found is None:
        return None
    now = _now()
    if float(found["expires_at"]) <= now:
        with db.write_tx() as conn:
            conn.execute("DELETE FROM sessions WHERE id = ?", (found["session_id"],))
        return None
    if now - float(found["last_seen_at"]) > 600:
        try:
            with db.write_tx() as conn:
                conn.execute(
                    "UPDATE sessions SET last_seen_at = ? WHERE id = ?", (now, found["session_id"])
                )
        except Exception:  # noqa: BLE001
            logger.debug("Could not touch session", exc_info=True)
    return {"session_id": found["session_id"], "csrf": found["csrf"], "user_row": found}


def context_for_request(request: Request) -> dict[str, Any]:
    if not config.HOSTED:
        row = ensure_local_user()
        return {
            "mode": "local",
            "user": user_payload(row),
            "row": row,
            "csrf": None,
            "session_id": None,
            "owner": str(row["id"]),
        }

    raw = request.cookies.get(config.SESSION_COOKIE)
    session = session_from_cookie(raw)
    if session is None:
        raise AuthRequired()
    row = session["user_row"]
    return {
        "mode": "hosted",
        "user": user_payload(row),
        "row": row,
        "csrf": session["csrf"],
        "session_id": session["session_id"],
        "owner": str(row["id"]),
    }


def peek(request: Request) -> dict[str, Any] | None:
    if not config.HOSTED:
        return context_for_request(request)
    session = session_from_cookie(request.cookies.get(config.SESSION_COOKIE))
    if session is None:
        return None
    row = session["user_row"]
    return {
        "mode": "hosted",
        "user": user_payload(row),
        "row": row,
        "csrf": session["csrf"],
        "session_id": session["session_id"],
        "owner": str(row["id"]),
    }


def login_with_init_data(request: Request, init_data: str) -> tuple[dict[str, Any], str]:
    token = telegram.bot_token()
    if not token:
        raise AuthRequired(
            "Вход через Telegram не настроен",
            "На сервере нужен TUNEBRIDGE_BOT_TOKEN — без него Mini App не может подтвердить вход.",
        )
    validated = auth.validate_init_data(init_data, token, max_age=config.INIT_DATA_TTL)
    row = upsert_telegram_user(validated["user"])
    raw, csrf = create_session(int(row["id"]), request.headers.get("user-agent", ""))
    fresh = _get_user(int(row["id"])) or row
    context = {
        "mode": "hosted",
        "user": user_payload(fresh),
        "row": fresh,
        "csrf": csrf,
        "session_id": _hash_token(raw),
        "owner": str(fresh["id"]),
    }
    return context, raw


def logout(request: Request) -> None:
    raw = request.cookies.get(config.SESSION_COOKIE)
    if not raw:
        return
    with db.write_tx() as conn:
        conn.execute("DELETE FROM sessions WHERE id = ?", (_hash_token(raw),))


def set_cookie(response: Response, raw: str) -> None:
    response.set_cookie(
        config.SESSION_COOKIE,
        raw,
        max_age=config.SESSION_TTL,
        httponly=True,
        secure=config.COOKIE_SECURE,
        samesite="lax",
        path="/",
    )


def clear_cookie(response: Response) -> None:
    response.delete_cookie(config.SESSION_COOKIE, path="/")


def require_admin(context: dict[str, Any]) -> None:
    if not context["user"]["is_admin"]:
        raise AdminRequired()


def wallet_transactions(user_id: int, limit: int = 30) -> list[dict[str, Any]]:
    limit = max(1, min(int(limit), 100))
    found = db.rows(
        "SELECT id, delta, kind, reason, balance_after, created_at FROM wallet_tx "
        "WHERE user_id = ? ORDER BY id DESC LIMIT ?",
        (int(user_id), limit),
    )
    return [
        {
            "id": item["id"],
            "delta": int(item["delta"]),
            "kind": item["kind"],
            "reason": item["reason"],
            "balance_after": int(item["balance_after"]),
            "created_at": iso(item["created_at"]),
        }
        for item in found
    ]


def record_transfer(owner: str | int | None, result: dict[str, Any]) -> None:
    try:
        user_id = int(owner) if owner is not None else 0
    except (TypeError, ValueError):
        return
    if user_id <= 0:
        return
    try:
        with db.write_tx() as conn:
            conn.execute(
                "INSERT INTO transfers(user_id, source_service, source_title, source_url, target, target_name, "
                "playlist_url, added, total, demo, created_at) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    user_id,
                    str(result.get("source_service") or "")[:32],
                    str(result.get("source_title") or "")[:200],
                    str(result.get("source_url") or "")[:500],
                    str(result.get("target") or "")[:32],
                    str(result.get("target_name") or "")[:80],
                    str(result.get("url") or "")[:500],
                    int(result.get("added") or 0),
                    int(result.get("added") or 0) + int(result.get("failed") or 0),
                    1 if result.get("demo") else 0,
                    _now(),
                ),
            )
    except Exception:  # noqa: BLE001
        logger.warning("Could not save transfer history", exc_info=True)


def transfers_for(user_id: int, limit: int = 12) -> list[dict[str, Any]]:
    limit = max(1, min(int(limit), 50))
    found = db.rows(
        "SELECT * FROM transfers WHERE user_id = ? ORDER BY id DESC LIMIT ?",
        (int(user_id), limit),
    )
    return [
        {
            "id": item["id"],
            "source_service": item["source_service"],
            "source_title": item["source_title"],
            "source_url": item["source_url"],
            "target": item["target"],
            "target_name": item["target_name"],
            "url": item["playlist_url"],
            "added": int(item["added"]),
            "total": int(item["total"]),
            "demo": bool(item["demo"]),
            "created_at": iso(item["created_at"]),
        }
        for item in found
    ]


def find_user(*, user_id: int | None = None, telegram_id: int | None = None) -> Any:
    if user_id:
        return _get_user(int(user_id))
    if telegram_id is not None:
        return db.row("SELECT * FROM users WHERE telegram_id = ?", (int(telegram_id),))
    return None
