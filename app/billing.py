from __future__ import annotations

import json
import logging
import re
import secrets
import time
from collections import defaultdict, deque
from typing import Any

from . import accounts, config, db, telegram
from .providers.base import ProviderError

logger = logging.getLogger("tunebridge.billing")

_CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
_CODE_RE = re.compile(r"^[A-Z0-9]{4,24}$")
_PROMO_WINDOW = 10 * 60
_PROMO_ATTEMPTS = 12
_promo_attempts: dict[int, deque[float]] = defaultdict(deque)


class BillingError(Exception):
    def __init__(self, message: str, hint: str | None = None, status: int = 400):
        super().__init__(message)
        self.message = message
        self.hint = hint
        self.status = status


class InsufficientBalance(BillingError):
    def __init__(self, needed: int, balance: int):
        super().__init__(
            "Недостаточно треков на балансе",
            "Пополните баланс или уменьшите плейлист: списывается по одному треку за добавленный.",
            status=402,
        )
        self.needed = int(needed)
        self.balance = int(balance)


def charge_transfer(user_id: int, tracks: int, ref: str, target_name: str) -> dict[str, Any]:
    tokens = 0 if config.FREE_MODE else max(0, int(tracks)) * config.TOKENS_PER_TRACK
    user = accounts.find_user(user_id=user_id)
    if tokens <= 0:
        return {"charged": 0, "balance": int(user["balance"]) if user else 0}
    try:
        result = accounts.credit(
            user_id,
            -tokens,
            "spend",
            f"Перенос в {target_name}",
            ref=ref,
        )
    except ValueError as exc:
        fresh = accounts.find_user(user_id=user_id)
        raise InsufficientBalance(tokens, int(fresh["balance"]) if fresh else 0) from exc
    return {"charged": tokens, "balance": int(result["balance"])}


def refund_unused(user_id: int, tracks: int, ref: str) -> dict[str, Any] | None:
    if config.FREE_MODE:
        return None
    tokens = max(0, int(tracks)) * config.TOKENS_PER_TRACK
    if tokens <= 0:
        return None
    return accounts.credit(
        user_id,
        tokens,
        "refund",
        "Возврат за неперенесённые треки",
        ref=ref,
    )


def packages() -> list[dict[str, Any]]:
    result = []
    for package in config.PACKAGES:
        stars = int(package["stars"])
        rub = int(round(stars * config.STARS_RUB_RATE))
        result.append(
            {
                "id": package["id"],
                "title": package["title"],
                "title_en": package.get("title_en", package["title"]),
                "tokens": int(package["tokens"]),
                "stars": stars,
                "rub": rub,
                "per_track": round(rub / max(1, int(package["tokens"])), 2),
                "best": bool(package.get("best")),
            }
        )
    return result


def get_package(package_id: str) -> dict[str, Any] | None:
    for package in packages():
        if package["id"] == package_id:
            return package
    return None


def _order_payload(order: Any) -> dict[str, Any]:
    package = get_package(order["package_id"]) or {}
    return {
        "id": order["id"],
        "package_id": order["package_id"],
        "title": package.get("title") or order["package_id"],
        "tokens": int(order["tokens"]),
        "stars": int(order["stars"]),
        "status": order["status"],
        "invoice_url": order["invoice_url"],
        "created_at": accounts.iso(order["created_at"]),
        "paid_at": accounts.iso(order["paid_at"]),
        "refunded_at": accounts.iso(order["refunded_at"]),
    }


def orders_for(user_id: int, limit: int = 20) -> list[dict[str, Any]]:
    limit = max(1, min(int(limit), 100))
    found = db.rows(
        "SELECT * FROM orders WHERE user_id = ? ORDER BY created_at DESC LIMIT ?",
        (int(user_id), limit),
    )
    return [_order_payload(item) for item in found]


def wallet_snapshot(user_id: int) -> dict[str, Any]:
    user = accounts.find_user(user_id=user_id)
    return {
        "balance": int(user["balance"]) if user else 0,
        "trial_tokens": config.TRIAL_TOKENS,
        "packages": packages(),
        "transactions": accounts.wallet_transactions(user_id),
        "orders": orders_for(user_id),
        "transfers": accounts.transfers_for(user_id),
    }


def _invoice_copy(package: dict[str, Any], lang: str | None) -> tuple[str, str, str]:
    tokens = int(package["tokens"])
    if lang == "en":
        return (
            f"{package['title_en']} · {tokens} tracks",
            f"TuneBridge balance top-up: {tokens} tracks.",
            f"{tokens} tracks",
        )
    return (
        f"{package['title']} · {tokens} треков",
        f"Пополнение баланса TuneBridge: {tokens} треков.",
        f"{tokens} треков",
    )


def create_topup(user: dict[str, Any], package_id: str, lang: str | None = None) -> dict[str, Any]:
    package = get_package(package_id)
    if package is None:
        raise BillingError("Такого пакета нет", "Обновите страницу и выберите пакет заново.")

    order_id = "ord_" + secrets.token_hex(8)
    now = time.time()
    tokens = int(package["tokens"])
    stars = int(package["stars"])

    if not config.HOSTED:
        with db.write_tx() as conn:
            conn.execute(
                "INSERT INTO orders(id, user_id, package_id, tokens, stars, status, created_at, paid_at) "
                "VALUES(?, ?, ?, ?, ?, 'sandbox', ?, ?)",
                (order_id, int(user["id"]), package["id"], tokens, stars, now, now),
            )
            credited = accounts.credit_in_conn(
                conn,
                int(user["id"]),
                tokens,
                "topup",
                f"Тестовое пополнение «{package['title']}»",
                ref=f"sandbox:{order_id}",
                meta=json.dumps({"order_id": order_id, "sandbox": True}),
            )
        return {
            "mode": "sandbox",
            "order_id": order_id,
            "tokens": tokens,
            "stars": stars,
            "balance": credited["balance"],
        }

    if not telegram.bot_token():
        raise BillingError(
            "Оплата пока недоступна",
            "На сервере не настроен бот Telegram. Попробуйте позже.",
            status=503,
        )

    title, description, price_label = _invoice_copy(package, lang)
    try:
        invoice_url = telegram.create_invoice_link(
            title=title,
            description=description,
            payload=order_id,
            prices=[{"label": price_label, "amount": stars}],
        )
    except ProviderError as exc:
        raise BillingError(exc.message, exc.hint, status=502) from exc

    with db.write_tx() as conn:
        conn.execute(
            "INSERT INTO orders(id, user_id, package_id, tokens, stars, status, invoice_url, created_at) "
            "VALUES(?, ?, ?, ?, ?, 'pending', ?, ?)",
            (order_id, int(user["id"]), package["id"], tokens, stars, invoice_url, now),
        )

    return {
        "mode": "stars",
        "order_id": order_id,
        "tokens": tokens,
        "stars": stars,
        "invoice_url": invoice_url,
    }


def _order_for_update(conn: Any, order_id: str) -> Any:
    return conn.execute("SELECT * FROM orders WHERE id = ?", (order_id,)).fetchone()


def _confirm_payment(update: dict[str, Any]) -> str:
    message = update.get("message") or update.get("edited_message") or {}
    payment = message.get("successful_payment")
    if not isinstance(payment, dict):
        return "ignored"
    payload = str(payment.get("invoice_payload") or "")
    charge_id = str(payment.get("telegram_payment_charge_id") or "")
    provider_charge = str(payment.get("provider_payment_charge_id") or "")
    if not payload or not charge_id:
        logger.warning("Successful payment without payload or charge id")
        return "invalid"

    with db.write_tx() as conn:
        order = _order_for_update(conn, payload)
        if order is None:
            logger.warning("Payment for unknown order %s", payload)
            return "unknown_order"
        if order["status"] in {"paid", "refunded"}:
            return "duplicate"
        if str(payment.get("currency") or "") != "XTR":
            logger.warning("Payment for %s has unexpected currency", payload)
            return "currency"
        if int(payment.get("total_amount") or 0) != int(order["stars"]):
            logger.warning("Payment amount mismatch for %s", payload)
            return "amount"

        now = time.time()
        conn.execute(
            "UPDATE orders SET status = 'paid', paid_at = ?, telegram_payment_charge_id = ?, "
            "provider_payment_charge_id = ? WHERE id = ?",
            (now, charge_id, provider_charge, payload),
        )
        credited = accounts.credit_in_conn(
            conn,
            int(order["user_id"]),
            int(order["tokens"]),
            "topup",
            f"Пополнение через Telegram Stars ({order['tokens']} шт.)",
            ref=charge_id,
            meta=json.dumps({"order_id": payload, "stars": int(order["stars"])}),
        )

    chat_id = (message.get("chat") or {}).get("id")
    if chat_id:
        try:
            telegram.send_message(
                chat_id,
                f"✅ Баланс пополнен на {order['tokens']} треков. Сейчас на счету: {credited['balance']}.",
            )
        except Exception:  # noqa: BLE001
            logger.debug("Could not send payment confirmation", exc_info=True)
    return "paid"


def _check_pre_checkout(update: dict[str, Any]) -> str:
    query = update.get("pre_checkout_query")
    if not isinstance(query, dict):
        return "ignored"
    query_id = str(query.get("id") or "")
    payload = str(query.get("invoice_payload") or "")
    ok = False
    error = "Заказ не найден. Вернитесь в приложение и создайте новый."
    try:
        found = db.row("SELECT * FROM orders WHERE id = ?", (payload,))
        if found is not None:
            if found["status"] == "pending":
                if str(query.get("currency") or "") == "XTR" and int(query.get("total_amount") or 0) == int(found["stars"]):
                    ok = True
                    error = None
                else:
                    error = "Сумма или валюта платежа не совпали."
            elif found["status"] == "paid":
                ok = True
                error = None
    except Exception:  # noqa: BLE001
        logger.exception("Pre-checkout validation failed")
    if query_id:
        try:
            telegram.answer_pre_checkout_query(query_id, ok=ok, error_message=error)
        except Exception:  # noqa: BLE001
            logger.exception("Could not answer pre-checkout query")
    return "pre_checkout_ok" if ok else "pre_checkout_rejected"


def handle_update(update: dict[str, Any]) -> str:
    if "pre_checkout_query" in update:
        return _check_pre_checkout(update)
    if "message" in update or "edited_message" in update:
        result = _confirm_payment(update)
        if result != "ignored":
            return result
    return "ignored"


def refund_order(order_id: str, *, revoke: bool = True) -> dict[str, Any]:
    order = db.row("SELECT * FROM orders WHERE id = ?", (order_id,))
    if order is None:
        raise BillingError("Заказ не найден", "Проверьте номер заказа.")
    if order["status"] != "paid":
        raise BillingError("Вернуть можно только оплаченный заказ", "Этот заказ ещё не оплачен или уже возвращён.")
    if not order["telegram_payment_charge_id"]:
        raise BillingError("Нет идентификатора платежа", "Telegram не передал charge id — возврат невозможен.")
    user = accounts.find_user(user_id=int(order["user_id"]))
    if user is None or not user["telegram_id"]:
        raise BillingError("Пользователь не найден", "Возврат звёзд доступен только Telegram-аккаунтам.")
    if revoke and int(user["balance"]) < int(order["tokens"]):
        raise BillingError(
            "Токены уже потрачены",
            "Верните звёзды без списания баланса или сначала пополните счёт вручную.",
        )

    try:
        telegram.refund_star_payment(int(user["telegram_id"]), str(order["telegram_payment_charge_id"]))
    except ProviderError as exc:
        raise BillingError(exc.message, exc.hint, status=502) from exc

    with db.write_tx() as conn:
        fresh = _order_for_update(conn, order_id)
        if fresh is None or fresh["status"] != "paid":
            raise BillingError("Заказ уже изменился", "Обновите кабинет и повторите.")
        conn.execute(
            "UPDATE orders SET status = 'refunded', refunded_at = ? WHERE id = ?",
            (time.time(), order_id),
        )
        balance = int(accounts.find_user(user_id=int(order["user_id"]))["balance"])
        if revoke:
            credited = accounts.credit_in_conn(
                conn,
                int(order["user_id"]),
                -int(order["tokens"]),
                "refund",
                f"Возврат звёзд за заказ {order_id}",
                ref=f"refund:{order_id}",
            )
            balance = credited["balance"]
    return {"ok": True, "order_id": order_id, "balance": balance, "tokens_revoked": int(order["tokens"]) if revoke else 0}


def _normalize_code(code: str) -> str:
    return re.sub(r"\s+", "", (code or "").strip().upper())


def _check_promo_rate(user_id: int) -> None:
    now = time.time()
    bucket = _promo_attempts[int(user_id)]
    while bucket and now - bucket[0] > _PROMO_WINDOW:
        bucket.popleft()
    if len(bucket) >= _PROMO_ATTEMPTS:
        raise BillingError(
            "Слишком много попыток",
            "Подождите несколько минут и попробуйте снова.",
            status=429,
        )
    bucket.append(now)


def redeem_promo(user_id: int, code: str) -> dict[str, Any]:
    normalized = _normalize_code(code)
    if not _CODE_RE.match(normalized):
        raise BillingError("Промокод не похож на настоящий", "Проверьте раскладку и введите код ещё раз.")
    _check_promo_rate(user_id)

    now = time.time()
    with db.write_tx() as conn:
        promo = conn.execute("SELECT * FROM promo_codes WHERE code = ?", (normalized,)).fetchone()
        if promo is None or not promo["active"]:
            raise BillingError("Промокод не найден", "Проверьте код: возможно, в нём опечатка или он отключён.")
        if promo["expires_at"] and float(promo["expires_at"]) < now:
            raise BillingError("Промокод истёк", "Попросите новый код у администратора.")
        if int(promo["max_uses"]) and int(promo["used_count"]) >= int(promo["max_uses"]):
            raise BillingError("Промокод уже использован максимальное число раз", "Промокоды можно активировать один раз.")
        already = conn.execute(
            "SELECT 1 FROM promo_redemptions WHERE code = ? AND user_id = ?", (normalized, int(user_id))
        ).fetchone()
        if already is not None:
            raise BillingError("Вы уже активировали этот промокод", "Каждый промокод срабатывает для аккаунта один раз.")

        conn.execute(
            "INSERT INTO promo_redemptions(code, user_id, tokens, created_at) VALUES(?, ?, ?, ?)",
            (normalized, int(user_id), int(promo["tokens"]), now),
        )
        conn.execute(
            "UPDATE promo_codes SET used_count = used_count + 1 WHERE code = ?", (normalized,)
        )
        credited = accounts.credit_in_conn(
            conn,
            int(user_id),
            int(promo["tokens"]),
            "promo",
            f"Промокод {normalized}",
            ref=f"promo:{normalized}:{int(user_id)}",
            meta=json.dumps({"code": normalized}),
        )
    return {
        "ok": True,
        "code": normalized,
        "tokens": int(promo["tokens"]),
        "balance": credited["balance"],
    }


def _random_code() -> str:
    return "".join(secrets.choice(_CODE_ALPHABET) for _ in range(8))


def create_promo_codes(
    admin_id: int,
    *,
    count: int = 1,
    tokens: int,
    max_uses: int = 1,
    days: int = 30,
    note: str = "",
) -> list[dict[str, Any]]:
    count = int(count)
    tokens = int(tokens)
    max_uses = int(max_uses)
    days = int(days)
    if not 1 <= count <= 50:
        raise BillingError("За один раз можно создать от 1 до 50 кодов")
    if not 1 <= tokens <= 100_000:
        raise BillingError("Начисление по промокоду должно быть от 1 до 100 000")
    if not 0 <= max_uses <= 100_000:
        raise BillingError("Лимит активаций должен быть от 0 до 100 000")
    if not 0 <= days <= 365:
        raise BillingError("Срок действия должен быть от 0 до 365 дней")

    now = time.time()
    expires_at = now + days * 86400 if days else None
    created: list[dict[str, Any]] = []
    with db.write_tx() as conn:
        while len(created) < count:
            code = _random_code()
            if conn.execute("SELECT 1 FROM promo_codes WHERE code = ?", (code,)).fetchone():
                continue
            conn.execute(
                "INSERT INTO promo_codes(code, tokens, max_uses, used_count, active, expires_at, note, created_by, "
                "created_at) VALUES(?, ?, ?, 0, 1, ?, ?, ?, ?)",
                (code, tokens, max_uses, expires_at, (note or "")[:200], int(admin_id), now),
            )
            created.append(
                {
                    "code": code,
                    "tokens": tokens,
                    "max_uses": max_uses,
                    "expires_at": accounts.iso(expires_at),
                }
            )
    return created


def list_promos(limit: int = 100) -> list[dict[str, Any]]:
    limit = max(1, min(int(limit), 500))
    found = db.rows("SELECT * FROM promo_codes ORDER BY created_at DESC LIMIT ?", (limit,))
    now = time.time()
    result = []
    for item in found:
        expired = bool(item["expires_at"] and float(item["expires_at"]) < now)
        exhausted = bool(int(item["max_uses"]) and int(item["used_count"]) >= int(item["max_uses"]))
        result.append(
            {
                "code": item["code"],
                "tokens": int(item["tokens"]),
                "max_uses": int(item["max_uses"]),
                "used_count": int(item["used_count"]),
                "active": bool(item["active"]),
                "expired": expired,
                "exhausted": exhausted,
                "expires_at": accounts.iso(item["expires_at"]),
                "note": item["note"],
                "created_at": accounts.iso(item["created_at"]),
            }
        )
    return result


def toggle_promo(code: str, active: bool) -> dict[str, Any]:
    normalized = _normalize_code(code)
    with db.write_tx() as conn:
        found = conn.execute("SELECT * FROM promo_codes WHERE code = ?", (normalized,)).fetchone()
        if found is None:
            raise BillingError("Промокод не найден", "Обновите список кодов.")
        conn.execute("UPDATE promo_codes SET active = ? WHERE code = ?", (1 if active else 0, normalized))
    return {"ok": True, "code": normalized, "active": bool(active)}


def admin_overview(limit: int = 12) -> dict[str, Any]:
    now = time.time()
    users = int(db.scalar("SELECT COUNT(*) FROM users WHERE telegram_id IS NOT NULL AND telegram_id != 0", default=0) or 0)
    local_users = int(db.scalar("SELECT COUNT(*) FROM users WHERE telegram_id = 0", default=0) or 0)
    balances = int(db.scalar("SELECT COALESCE(SUM(balance), 0) FROM users", default=0) or 0)
    paid_orders = int(db.scalar("SELECT COUNT(*) FROM orders WHERE status = 'paid'", default=0) or 0)
    paid_stars = int(db.scalar("SELECT COALESCE(SUM(stars), 0) FROM orders WHERE status = 'paid'", default=0) or 0)
    paid_tokens = int(db.scalar("SELECT COALESCE(SUM(tokens), 0) FROM orders WHERE status = 'paid'", default=0) or 0)
    active_promos = int(
        db.scalar(
            "SELECT COUNT(*) FROM promo_codes WHERE active = 1 AND (expires_at IS NULL OR expires_at > ?) "
            "AND (max_uses = 0 OR used_count < max_uses)",
            (now,),
            default=0,
        )
        or 0
    )
    recent_orders = db.rows(
        "SELECT o.*, u.first_name, u.username FROM orders o JOIN users u ON u.id = o.user_id "
        "ORDER BY o.created_at DESC LIMIT ?",
        (max(1, min(int(limit), 50)),),
    )
    return {
        "users": users,
        "local_users": local_users,
        "balances": balances,
        "paid_orders": paid_orders,
        "paid_stars": paid_stars,
        "paid_tokens": paid_tokens,
        "active_promos": active_promos,
        "orders": [
            {
                **_order_payload(item),
                "user": item["first_name"] or item["username"] or "Гость",
            }
            for item in recent_orders
        ],
    }
