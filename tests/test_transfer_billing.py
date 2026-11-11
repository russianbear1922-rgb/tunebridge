from __future__ import annotations

import asyncio
import json
import os
import shutil
import tempfile
import threading
import unittest
from unittest import mock

from app import accounts, billing, db, jobs
from app.models import Match, Playlist, Track
from app.providers.base import ProviderError, TargetProvider


class FakeTarget(TargetProvider):
    batch_size = 50

    def __init__(self, target_id: str = "spotify", fail_ids: set[str] | None = None,
                 fatal_ids: set[str] | None = None):
        self.id = target_id
        self.name = "Spotify" if target_id == "spotify" else "Демо"
        self.fail_ids = fail_ids or set()
        self.fatal_ids = fatal_ids or set()

    def is_connected(self) -> bool:
        return True

    def search(self, track: Track) -> list[Track]:
        return []

    def create_playlist(self, title: str, description: str, options: dict) -> dict:
        return {"id": "pl_test", "url": "https://example.test/pl"}

    def add_batch(self, playlist_id: str, tracks: list[Track]) -> None:
        if any(track.id in self.fatal_ids for track in tracks):
            raise ProviderError("Сервис отклонил доступ", "Подключите аккаунт заново.", fatal=True)
        if any(track.id in self.fail_ids for track in tracks):
            raise ProviderError("Не удалось добавить треки", "Повторите позже.")


def make_playlist(count: int) -> Playlist:
    tracks = [
        Track(id=f"t{index + 1}", title=f"Трек {index + 1}", artists=["Исполнитель"])
        for index in range(count)
    ]
    return Playlist(id="src", service="yandex", title="Плейлист", tracks=tracks)


def make_matches(count: int) -> list[Match]:
    matches = []
    for index in range(count):
        track = Track(id=f"t{index + 1}", title=f"Трек {index + 1}", artists=["Исполнитель"])
        matches.append(Match(source=track, target=track, score=0.95, status="auto"))
    return matches


class DatabaseTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.old_path = os.environ.get("TUNEBRIDGE_DB_PATH")
        self.tempdir = tempfile.mkdtemp(prefix="tunebridge-metering-")
        db.use_path(os.path.join(self.tempdir, "test.db"))
        self.user = accounts.upsert_telegram_user({"id": 701, "first_name": "Слушатель"})

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


class ChargeTest(DatabaseTestCase):
    def test_charge_and_refuse_when_short(self) -> None:
        self.assertEqual(self.balance(), 50)
        result = billing.charge_transfer(int(self.user["id"]), 30, "test-ref", "Spotify")
        self.assertEqual(result["charged"], 30)
        self.assertEqual(result["balance"], 20)

        with self.assertRaises(billing.InsufficientBalance) as ctx:
            billing.charge_transfer(int(self.user["id"]), 30, "test-ref-2", "Spotify")
        self.assertEqual(ctx.exception.status, 402)
        self.assertEqual(ctx.exception.needed, 30)
        self.assertEqual(ctx.exception.balance, 20)
        self.assertEqual(self.balance(), 20)

    def test_refund_is_idempotent(self) -> None:
        billing.charge_transfer(int(self.user["id"]), 10, "job-ref", "Spotify")
        first = billing.refund_unused(int(self.user["id"]), 4, "job-ref")
        self.assertIsNotNone(first)
        self.assertEqual(first["balance"], 44)
        second = billing.refund_unused(int(self.user["id"]), 4, "job-ref")
        self.assertTrue(second["duplicate"])
        self.assertEqual(self.balance(), 44)
        self.assertIsNone(billing.refund_unused(int(self.user["id"]), 0, "job-ref"))

    def test_zero_tracks_cost_nothing(self) -> None:
        result = billing.charge_transfer(int(self.user["id"]), 0, "empty", "Spotify")
        self.assertEqual(result["charged"], 0)
        self.assertEqual(self.balance(), 50)


class TransferMeteringTest(DatabaseTestCase):
    def start(self, provider: FakeTarget, count: int) -> dict:
        with mock.patch.object(jobs.config, "HOSTED", True), mock.patch.object(
            jobs, "get_target", return_value=provider
        ), mock.patch("app.jobs.time.sleep", return_value=None):
            job = jobs.start_transfer_job(
                make_playlist(count),
                provider.id,
                make_matches(count),
                None,
                None,
                {},
                owner=str(int(self.user["id"])),
            )
            return self.wait_job(job.id)

    def test_partial_failure_refunds_unadded_tracks(self) -> None:
        snapshot = self.start(FakeTarget(fail_ids={"t4"}), 4)
        self.assertEqual(snapshot["status"], "done")
        self.assertEqual(snapshot["result"]["added"], 2)
        self.assertEqual(snapshot["result"]["failed"], 2)
        self.assertEqual(snapshot["result"]["billing"], {"cost": 4, "charged": 2, "refunded": 2})
        self.assertEqual(self.balance(), 48)
        spends = db.rows("SELECT * FROM wallet_tx WHERE kind = 'spend'")
        refunds = db.rows("SELECT * FROM wallet_tx WHERE kind = 'refund'")
        self.assertEqual([int(row["delta"]) for row in spends], [-4])
        self.assertEqual([int(row["delta"]) for row in refunds], [2])

    def test_fatal_error_refunds_everything(self) -> None:
        snapshot = self.start(FakeTarget(fatal_ids={"t2"}), 3)
        self.assertEqual(snapshot["status"], "error")
        self.assertEqual(snapshot["result"]["billing"]["charged"], 0)
        self.assertEqual(snapshot["result"]["billing"]["refunded"], 3)
        self.assertEqual(self.balance(), 50)

    def test_insufficient_balance_blocks_start(self) -> None:
        matches = make_matches(60)
        with mock.patch.object(jobs.config, "HOSTED", True), mock.patch.object(
            jobs, "get_target", return_value=FakeTarget()
        ):
            with self.assertRaises(billing.InsufficientBalance) as ctx:
                jobs.start_transfer_job(
                    make_playlist(60),
                    "spotify",
                    matches,
                    None,
                    None,
                    {},
                    owner=str(int(self.user["id"])),
                )
        self.assertEqual(ctx.exception.needed, 60)
        self.assertIsNone(jobs.manager.active(str(int(self.user["id"]))))
        self.assertEqual(self.balance(), 50)
        self.assertEqual(len(db.rows("SELECT * FROM wallet_tx WHERE kind = 'spend'")), 0)

    def test_demo_target_is_free(self) -> None:
        snapshot = self.start(FakeTarget(target_id="demo"), 3)
        self.assertEqual(snapshot["status"], "done")
        self.assertIsNone(snapshot["result"]["billing"])
        self.assertEqual(self.balance(), 50)
        self.assertEqual(len(db.rows("SELECT * FROM wallet_tx WHERE kind IN ('spend', 'refund')")), 0)

    def test_local_mode_is_free(self) -> None:
        with mock.patch.object(jobs.config, "HOSTED", False), mock.patch.object(
            jobs, "get_target", return_value=FakeTarget()
        ), mock.patch("app.jobs.time.sleep", return_value=None):
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
        self.assertIsNone(snapshot["result"]["billing"])
        self.assertEqual(self.balance(), 50)


class ErrorPayloadTest(unittest.TestCase):
    def test_insufficient_balance_response_contract(self) -> None:
        from app import main

        response = asyncio.run(main.billing_error_handler(None, billing.InsufficientBalance(120, 40)))
        self.assertEqual(response.status_code, 402)
        body = json.loads(response.body)
        self.assertEqual(body["code"], "insufficient_balance")
        self.assertEqual(body["needed"], 120)
        self.assertEqual(body["balance"], 40)
        self.assertEqual(body["message"], "Недостаточно треков на балансе")


if __name__ == "__main__":
    unittest.main()
