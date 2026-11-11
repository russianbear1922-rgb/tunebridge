from __future__ import annotations

import json
import os
import shutil
import tempfile
import threading
import unittest
from unittest import mock

from fastapi import HTTPException

from app import accounts, billing, config, db, jobs, main
from app.models import Match, Playlist, PromoRedeemRequest, TopupRequest, Track
from app.providers.base import TargetProvider

AD_ENV_KEYS = (
    "TUNEBRIDGE_AD_TITLE",
    "TUNEBRIDGE_AD_URL",
    "TUNEBRIDGE_AD_TEXT",
    "TUNEBRIDGE_AD_IMAGE",
    "TUNEBRIDGE_AD_CTA",
    "TUNEBRIDGE_AD_LABEL",
)


class FakeTarget(TargetProvider):
    batch_size = 50
    id = "spotify"
    name = "Spotify"

    def is_connected(self) -> bool:
        return True

    def search(self, track: Track) -> list[Track]:
        return []

    def create_playlist(self, title: str, description: str, options: dict) -> dict:
        return {"id": "pl_test", "url": "https://example.test/pl"}

    def add_batch(self, playlist_id: str, tracks: list[Track]) -> None:
        return None


def make_playlist(count: int) -> Playlist:
    tracks = [
        Track(id=f"t{index + 1}", title=f"Трек {index + 1}", artists=["Исполнитель"])
        for index in range(count)
    ]
    return Playlist(id="src", service="yandex", title="Плейлист", tracks=tracks)


def make_matches(count: int) -> list[Match]:
    result = []
    for index in range(count):
        track = Track(id=f"t{index + 1}", title=f"Трек {index + 1}", artists=["Исполнитель"])
        result.append(Match(source=track, target=track, score=0.95, status="auto"))
    return result


class FreeModeTest(unittest.TestCase):
    def setUp(self) -> None:
        self.old_path = os.environ.get("TUNEBRIDGE_DB_PATH")
        self.tempdir = tempfile.mkdtemp(prefix="tunebridge-free-")
        db.use_path(os.path.join(self.tempdir, "test.db"))
        self.user = accounts.upsert_telegram_user({"id": 801, "first_name": "Слушатель"})

    def tearDown(self) -> None:
        db.close_current()
        if self.old_path is None:
            os.environ.pop("TUNEBRIDGE_DB_PATH", None)
        else:
            os.environ["TUNEBRIDGE_DB_PATH"] = self.old_path
        shutil.rmtree(self.tempdir, ignore_errors=True)

    def wait_job(self, job_id: str) -> dict:
        for _ in range(4000):
            snapshot = jobs.manager.snapshot(job_id)
            if snapshot and snapshot["status"] not in {"running", "cancelling"}:
                return snapshot
            threading.Event().wait(0.01)
        self.fail("Задача не завершилась за отведённое время")

    def balance(self) -> int:
        return int(accounts.find_user(user_id=int(self.user["id"]))["balance"])

    def test_charge_is_skipped(self) -> None:
        with mock.patch.object(config, "FREE_MODE", True):
            result = billing.charge_transfer(int(self.user["id"]), 30, "free-ref", "Spotify")
        self.assertEqual(result["charged"], 0)
        self.assertEqual(self.balance(), 50)
        self.assertEqual(len(db.rows("SELECT * FROM wallet_tx WHERE kind = 'spend'")), 0)

    def test_refund_is_skipped(self) -> None:
        with mock.patch.object(config, "FREE_MODE", True):
            self.assertIsNone(billing.refund_unused(int(self.user["id"]), 5, "free-ref"))

    def test_new_user_gets_no_trial_tokens(self) -> None:
        with mock.patch.object(config, "FREE_MODE", True):
            user = accounts.upsert_telegram_user({"id": 802, "first_name": "Новый"})
        self.assertEqual(int(user["balance"]), 0)
        self.assertEqual(int(user["trial_granted"]), 1)

    def test_transfer_is_not_billed(self) -> None:
        with mock.patch.object(jobs.config, "HOSTED", True), mock.patch.object(
            jobs.config, "FREE_MODE", True
        ), mock.patch.object(jobs, "get_target", return_value=FakeTarget()):
            job = jobs.start_transfer_job(
                make_playlist(3),
                "spotify",
                make_matches(3),
                None,
                None,
                {},
                owner=str(int(self.user["id"])),
            )
            snapshot = self.wait_job(job.id)
        self.assertEqual(snapshot["status"], "done")
        self.assertEqual(snapshot["result"]["added"], 3)
        self.assertIsNone(snapshot["result"]["billing"])
        self.assertEqual(self.balance(), 50)
        self.assertEqual(len(db.rows("SELECT * FROM wallet_tx WHERE kind IN ('spend', 'refund')")), 0)

    def test_topup_and_promo_are_blocked(self) -> None:
        context = {"user": accounts.find_user(user_id=int(self.user["id"])), "row": {"id": self.user["id"], "lang": "ru"}}
        with mock.patch.object(main, "FREE_MODE", True):
            with self.assertRaises(HTTPException) as topup:
                main.wallet_topup(TopupRequest(package_id="start"), context)
            with self.assertRaises(HTTPException) as promo:
                main.promo_redeem(PromoRedeemRequest(code="ABC12345"), context)
        self.assertEqual(topup.exception.status_code, 403)
        self.assertEqual(promo.exception.status_code, 403)
        self.assertEqual(self.balance(), 50)


class AdSlotConfigTest(unittest.TestCase):
    def _clean_env(self) -> None:
        for key in AD_ENV_KEYS:
            os.environ.pop(key, None)

    def test_no_env_means_no_ad(self) -> None:
        with mock.patch.dict(os.environ, {}, clear=False):
            self._clean_env()
            self.assertIsNone(config._ad_slot())

    def test_slot_reads_env(self) -> None:
        with mock.patch.dict(os.environ, {}, clear=False):
            self._clean_env()
            os.environ.update(
                {
                    "TUNEBRIDGE_AD_TITLE": "Скидка на наушники",
                    "TUNEBRIDGE_AD_TEXT": "Промокод TUNEBRIDGE",
                    "TUNEBRIDGE_AD_URL": "https://shop.example/promo",
                    "TUNEBRIDGE_AD_IMAGE": "/static/img/ads/shop.png",
                    "TUNEBRIDGE_AD_CTA": "Купить",
                }
            )
            slot = config._ad_slot()
        self.assertIsNotNone(slot)
        self.assertEqual(slot["label"], "Реклама")
        self.assertEqual(slot["url"], "https://shop.example/promo")
        self.assertEqual(slot["image"], "/static/img/ads/shop.png")
        self.assertEqual(slot["cta"], "Купить")

    def test_unsafe_values_are_dropped(self) -> None:
        with mock.patch.dict(os.environ, {}, clear=False):
            self._clean_env()
            os.environ.update(
                {
                    "TUNEBRIDGE_AD_TITLE": "Тест",
                    "TUNEBRIDGE_AD_URL": "javascript:alert(1)",
                    "TUNEBRIDGE_AD_IMAGE": "//evil.example/banner.png",
                }
            )
            slot = config._ad_slot()
        self.assertEqual(slot["url"], "")
        self.assertEqual(slot["image"], "")


class StatePayloadTest(unittest.TestCase):
    def setUp(self) -> None:
        self.old_path = os.environ.get("TUNEBRIDGE_DB_PATH")
        self.tempdir = tempfile.mkdtemp(prefix="tunebridge-state-")
        db.use_path(os.path.join(self.tempdir, "test.db"))
        accounts.ensure_local_user()

    def tearDown(self) -> None:
        db.close_current()
        if self.old_path is None:
            os.environ.pop("TUNEBRIDGE_DB_PATH", None)
        else:
            os.environ["TUNEBRIDGE_DB_PATH"] = self.old_path
        shutil.rmtree(self.tempdir, ignore_errors=True)

    def test_state_exposes_free_mode_and_ad(self) -> None:
        ad = {
            "label": "Реклама",
            "title": "Наушники",
            "text": "",
            "cta": "",
            "url": "https://shop.example",
            "image": "",
        }
        context = main.accounts.context_for_request(_request())
        with mock.patch.object(main, "FREE_MODE", True), mock.patch.object(
            config, "AD", ad
        ), mock.patch.object(main, "_service_state", return_value={"connected": False, "profile": None}):
            payload = main.state(context)
        self.assertTrue(payload["free_mode"])
        self.assertEqual(payload["ads"], ad)


def _request():
    from starlette.requests import Request

    return Request({"type": "http", "method": "GET", "path": "/api/state", "headers": [], "client": ("127.0.0.1", 1)})


class TwaAssetLinksTest(unittest.TestCase):
    def test_missing_config_returns_404(self) -> None:
        with mock.patch.object(main, "TWA_PACKAGE", ""), mock.patch.object(main, "TWA_SHA256", []):
            with self.assertRaises(HTTPException) as ctx:
                main.assetlinks()
        self.assertEqual(ctx.exception.status_code, 404)

    def test_payload_lists_fingerprints(self) -> None:
        with mock.patch.object(main, "TWA_PACKAGE", "com.example.tunebridge"), mock.patch.object(
            main, "TWA_SHA256", ["AA:BB:CC"]
        ):
            response = main.assetlinks()
        payload = json.loads(response.body)
        self.assertEqual(payload[0]["target"]["package_name"], "com.example.tunebridge")
        self.assertEqual(payload[0]["target"]["sha256_cert_fingerprints"], ["AA:BB:CC"])


if __name__ == "__main__":
    unittest.main()
