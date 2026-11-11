from __future__ import annotations

import hashlib
import hmac
import json
import os
import shutil
import tempfile
import threading
import time
import unittest
from urllib.parse import parse_qsl, urlencode
from unittest import mock

from app import accounts, auth, billing, db, jobs

BOT_TOKEN = "123456:TEST-TOKEN"


def init_data(user: dict, auth_date: int | None = None, *, token: str = BOT_TOKEN) -> str:
    data = {
        "auth_date": str(int(time.time()) if auth_date is None else auth_date),
        "query_id": "AAH-test",
        "user": json.dumps(user, ensure_ascii=False, separators=(",", ":")),
    }
    check_string = "\n".join(f"{key}={data[key]}" for key in sorted(data))
    secret = hmac.new(b"WebAppData", token.encode("utf-8"), hashlib.sha256).digest()
    data["hash"] = hmac.new(secret, check_string.encode("utf-8"), hashlib.sha256).hexdigest()
    return urlencode(data)


class InitDataTest(unittest.TestCase):
    def test_valid_signature_returns_user(self) -> None:
        result = auth.validate_init_data(init_data({"id": 42, "first_name": "Аня"}), BOT_TOKEN)
        self.assertEqual(result["user"]["id"], 42)
        self.assertEqual(result["query_id"], "AAH-test")
        self.assertGreater(result["auth_date"], 0)

    def test_tampered_user_is_rejected(self) -> None:
        pairs = dict(parse_qsl(init_data({"id": 42, "first_name": "Аня"})))
        pairs["user"] = pairs["user"].replace('"id":42', '"id":43')
        with self.assertRaises(auth.AuthError) as ctx:
            auth.validate_init_data(urlencode(pairs), BOT_TOKEN)
        self.assertEqual(ctx.exception.message, "Telegram не подтвердил вход")

    def test_other_bot_token_is_rejected(self) -> None:
        raw = init_data({"id": 42}, token="999:OTHER")
        with self.assertRaises(auth.AuthError):
            auth.validate_init_data(raw, BOT_TOKEN)

    def test_expired_and_future_dates(self) -> None:
        old = init_data({"id": 42}, auth_date=int(time.time()) - 90000)
        with self.assertRaises(auth.AuthError) as ctx:
            auth.validate_init_data(old, BOT_TOKEN, max_age=86400)
        self.assertEqual(ctx.exception.message, "Вход в Telegram устарел")

        future = init_data({"id": 42}, auth_date=int(time.time()) + 3600)
        with self.assertRaises(auth.AuthError) as ctx:
            auth.validate_init_data(future, BOT_TOKEN, max_age=86400)
        self.assertEqual(ctx.exception.message, "Часы устройства расходятся с сервером")

    def test_missing_and_duplicate_fields(self) -> None:
        with self.assertRaises(auth.AuthError) as ctx:
            auth.validate_init_data("", BOT_TOKEN)
        self.assertEqual(ctx.exception.message, "Не пришло подтверждение Telegram")

        with self.assertRaises(auth.AuthError) as ctx:
            auth.validate_init_data("auth_date=1&auth_date=2&hash=abc", BOT_TOKEN)
        self.assertEqual(ctx.exception.message, "Подпись Telegram повреждена")

        with self.assertRaises(auth.AuthError) as ctx:
            auth.validate_init_data("auth_date=1&user=%7B%7D", BOT_TOKEN)
        self.assertEqual(ctx.exception.message, "В подписи Telegram нет hash")

    def test_missing_bot_token(self) -> None:
        with self.assertRaises(auth.AuthError) as ctx:
            auth.validate_init_data("auth_date=1&hash=abc", "")
        self.assertEqual(ctx.exception.message, "Вход через Telegram не настроен")


class DatabaseTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.old_path = os.environ.get("TUNEBRIDGE_DB_PATH")
        self.tempdir = tempfile.mkdtemp(prefix="tunebridge-test-")
        db.use_path(os.path.join(self.tempdir, "test.db"))
        billing._promo_attempts.clear()

    def tearDown(self) -> None:
        db.close_current()
        if self.old_path is None:
            os.environ.pop("TUNEBRIDGE_DB_PATH", None)
        else:
            os.environ["TUNEBRIDGE_DB_PATH"] = self.old_path
        shutil.rmtree(self.tempdir, ignore_errors=True)


class LocalAccountTest(DatabaseTestCase):
    def test_local_user_gets_trial_once(self) -> None:
        user = accounts.ensure_local_user()
        self.assertEqual(int(user["balance"]), 50)
        self.assertTrue(user["trial_granted"])
        self.assertTrue(accounts.user_payload(user)["is_admin"])

        again = accounts.ensure_local_user()
        self.assertEqual(int(again["id"]), int(user["id"]))
        self.assertEqual(int(again["balance"]), 50)
        trial_rows = db.rows("SELECT * FROM wallet_tx WHERE kind = 'trial'")
        self.assertEqual(len(trial_rows), 1)

    def test_credit_is_idempotent_by_ref(self) -> None:
        user = accounts.ensure_local_user()
        first = accounts.credit(int(user["id"]), 100, "topup", "Тест", ref="charge-1")
        second = accounts.credit(int(user["id"]), 100, "topup", "Тест", ref="charge-1")
        self.assertEqual(first["balance"], 150)
        self.assertTrue(second["duplicate"])
        self.assertEqual(second["balance"], 150)
        self.assertEqual(int(accounts.find_user(user_id=int(user["id"]))["balance"]), 150)
        self.assertEqual(len(accounts.wallet_transactions(int(user["id"]))), 2)

    def test_negative_balance_is_refused(self) -> None:
        user = accounts.ensure_local_user()
        with self.assertRaises(ValueError):
            accounts.credit(int(user["id"]), -500, "admin", "Списание")

    def test_session_roundtrip_and_tamper(self) -> None:
        user = accounts.ensure_local_user()
        raw, csrf = accounts.create_session(int(user["id"]), "test-agent")
        found = accounts.session_from_cookie(raw)
        self.assertIsNotNone(found)
        self.assertEqual(found["csrf"], csrf)
        self.assertIsNone(accounts.session_from_cookie("tampered-token"))

    def test_sandbox_topup_credits_and_creates_order(self) -> None:
        user = accounts.ensure_local_user()
        with mock.patch.object(billing.config, "HOSTED", False):
            result = billing.create_topup(accounts.user_payload(user), "start")
        self.assertEqual(result["mode"], "sandbox")
        self.assertEqual(result["tokens"], 100)
        self.assertEqual(result["balance"], 150)
        order = db.row("SELECT * FROM orders WHERE id = ?", (result["order_id"],))
        self.assertEqual(order["status"], "sandbox")


class PromoTest(DatabaseTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.user = accounts.upsert_telegram_user({"id": 501, "first_name": "Первый"})
        self.admin = accounts.upsert_telegram_user({"id": 502, "first_name": "Админ"})

    def test_promo_single_use_per_user(self) -> None:
        codes = billing.create_promo_codes(int(self.admin["id"]), count=1, tokens=80, max_uses=2, days=30)
        code = codes[0]["code"]
        first = billing.redeem_promo(int(self.user["id"]), code)
        self.assertEqual(first["tokens"], 80)
        self.assertEqual(first["balance"], 130)
        with self.assertRaises(billing.BillingError) as ctx:
            billing.redeem_promo(int(self.user["id"]), code)
        self.assertEqual(ctx.exception.message, "Вы уже активировали этот промокод")

        other = accounts.upsert_telegram_user({"id": 503, "first_name": "Второй"})
        billing.redeem_promo(int(other["id"]), code)
        third = accounts.upsert_telegram_user({"id": 504, "first_name": "Третий"})
        with self.assertRaises(billing.BillingError) as ctx:
            billing.redeem_promo(int(third["id"]), code)
        self.assertEqual(ctx.exception.message, "Промокод уже использован максимальное число раз")

    def test_disabled_and_expired_promos(self) -> None:
        billing.create_promo_codes(int(self.admin["id"]), count=1, tokens=10, max_uses=1, days=0)
        code = db.scalar("SELECT code FROM promo_codes")
        billing.toggle_promo(code, False)
        with self.assertRaises(billing.BillingError) as ctx:
            billing.redeem_promo(int(self.user["id"]), code)
        self.assertEqual(ctx.exception.message, "Промокод не найден")

        billing.toggle_promo(code, True)
        with db.write_tx() as conn:
            conn.execute("UPDATE promo_codes SET expires_at = ? WHERE code = ?", (time.time() - 10, code))
        with self.assertRaises(billing.BillingError) as ctx:
            billing.redeem_promo(int(self.user["id"]), code)
        self.assertEqual(ctx.exception.message, "Промокод истёк")

    def test_bad_code_shape(self) -> None:
        with self.assertRaises(billing.BillingError) as ctx:
            billing.redeem_promo(int(self.user["id"]), "привет")
        self.assertEqual(ctx.exception.message, "Промокод не похож на настоящий")

    def test_creation_limits(self) -> None:
        with self.assertRaises(billing.BillingError):
            billing.create_promo_codes(int(self.admin["id"]), count=51, tokens=10)
        with self.assertRaises(billing.BillingError):
            billing.create_promo_codes(int(self.admin["id"]), count=1, tokens=0)
        with self.assertRaises(billing.BillingError):
            billing.create_promo_codes(int(self.admin["id"]), count=1, tokens=10, days=400)


class PaymentTest(DatabaseTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.user = accounts.upsert_telegram_user({"id": 601, "first_name": "Покупатель"})
        self.order_id = "ord_test_1"
        with db.write_tx() as conn:
            conn.execute(
                "INSERT INTO orders(id, user_id, package_id, tokens, stars, status, created_at) "
                "VALUES(?, ?, 'start', 100, 60, 'pending', ?)",
                (self.order_id, int(self.user["id"]), time.time()),
            )

    def _payment_update(self, charge: str = "charge-1", amount: int = 60) -> dict:
        return {
            "message": {
                "successful_payment": {
                    "invoice_payload": self.order_id,
                    "telegram_payment_charge_id": charge,
                    "provider_payment_charge_id": "provider-1",
                    "currency": "XTR",
                    "total_amount": amount,
                }
            }
        }

    def test_pre_checkout_answers(self) -> None:
        calls = []
        with mock.patch.object(billing.telegram, "answer_pre_checkout_query", lambda *a, **k: calls.append((a, k))):
            status = billing.handle_update(
                {
                    "pre_checkout_query": {
                        "id": "q1",
                        "invoice_payload": self.order_id,
                        "currency": "XTR",
                        "total_amount": 60,
                    }
                }
            )
        self.assertEqual(status, "pre_checkout_ok")
        self.assertEqual(calls[0][0][0], "q1")
        self.assertTrue(calls[0][1]["ok"])

        with mock.patch.object(billing.telegram, "answer_pre_checkout_query", lambda *a, **k: calls.append((a, k))):
            status = billing.handle_update(
                {
                    "pre_checkout_query": {
                        "id": "q2",
                        "invoice_payload": "ord_unknown",
                        "currency": "XTR",
                        "total_amount": 60,
                    }
                }
            )
        self.assertEqual(status, "pre_checkout_rejected")
        self.assertFalse(calls[-1][1]["ok"])

    def test_payment_confirmation_is_idempotent(self) -> None:
        status = billing.handle_update(self._payment_update())
        self.assertEqual(status, "paid")
        self.assertEqual(int(accounts.find_user(user_id=int(self.user["id"]))["balance"]), 150)
        self.assertEqual(db.row("SELECT status FROM orders WHERE id = ?", (self.order_id,))["status"], "paid")

        again = billing.handle_update(self._payment_update())
        self.assertEqual(again, "duplicate")
        self.assertEqual(int(accounts.find_user(user_id=int(self.user["id"]))["balance"]), 150)
        self.assertEqual(
            len(db.rows("SELECT * FROM wallet_tx WHERE kind = 'topup' AND ref = 'charge-1'")), 1
        )

    def test_payment_amount_mismatch(self) -> None:
        status = billing.handle_update(self._payment_update(amount=10))
        self.assertEqual(status, "amount")
        self.assertEqual(int(accounts.find_user(user_id=int(self.user["id"]))["balance"]), 50)
        self.assertEqual(db.row("SELECT status FROM orders WHERE id = ?", (self.order_id,))["status"], "pending")

    def test_refund_requires_balance_and_revokes_tokens(self) -> None:
        billing.handle_update(self._payment_update(charge="charge-refund"))
        order = db.row("SELECT * FROM orders WHERE id = ?", (self.order_id,))
        self.assertEqual(order["status"], "paid")
        accounts.credit(int(self.user["id"]), -120, "spend", "Списание")
        with self.assertRaises(billing.BillingError) as ctx:
            billing.refund_order(self.order_id)
        self.assertEqual(ctx.exception.message, "Токены уже потрачены")

        accounts.credit(int(self.user["id"]), 100, "admin", "Доначисление")
        refunded = []
        with mock.patch.object(billing.telegram, "refund_star_payment", lambda *a: refunded.append(a)):
            result = billing.refund_order(self.order_id)
        self.assertTrue(result["ok"])
        self.assertEqual(result["tokens_revoked"], 100)
        self.assertEqual(int(accounts.find_user(user_id=int(self.user["id"]))["balance"]), 30)
        self.assertEqual(db.row("SELECT status FROM orders WHERE id = ?", (self.order_id,))["status"], "refunded")
        self.assertEqual(refunded, [(601, "charge-refund")])
        with self.assertRaises(billing.BillingError):
            billing.refund_order(self.order_id)


class JobIsolationTest(unittest.TestCase):
    def test_jobs_are_scoped_to_owner(self) -> None:
        manager = jobs.JobManager()
        gate = threading.Event()

        def blocking_worker(job: jobs.Job) -> dict:
            gate.wait(2)
            return {"ok": True}

        job = manager.start("match", "Чужая задача", 1, blocking_worker, owner="a")
        try:
            with self.assertRaises(jobs.BusyError):
                manager.start("match", "Вторая", 1, blocking_worker, owner="a")
            self.assertIsNone(manager.snapshot(job.id, owner="b"))
            self.assertIsNone(manager.cancel(job.id, owner="b"))
            self.assertIsNone(manager.active("b"))
            self.assertIsNotNone(manager.active("a"))
            self.assertIsNotNone(manager.snapshot(job.id, owner="a"))

            other = manager.start("match", "Своя задача", 1, lambda item: {"ok": True}, owner="b")
            deadline = time.time() + 3
            while time.time() < deadline:
                snapshot = manager.snapshot(other.id, owner="b")
                if snapshot and snapshot["status"] == "done":
                    break
                time.sleep(0.01)
            self.assertEqual(manager.snapshot(other.id, owner="b")["status"], "done")
            self.assertIsNone(manager.snapshot(other.id, owner="a"))
        finally:
            gate.set()
            deadline = time.time() + 3
            while time.time() < deadline:
                snapshot = manager.snapshot(job.id)
                if snapshot and snapshot["status"] != "running":
                    break
                time.sleep(0.01)
            self.assertEqual(manager.snapshot(job.id)["status"], "done")


if __name__ == "__main__":
    unittest.main()
