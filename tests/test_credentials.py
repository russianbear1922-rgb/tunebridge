from __future__ import annotations

import json
import os
import shutil
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest import mock

from app import accounts, config, credentials, db, storage, telegram
from app.providers import spotify, yandex, youtube


class CredentialsTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.old_path = os.environ.get("TUNEBRIDGE_DB_PATH")
        self.old_secret = config.SECRET_KEY
        self.tempdir = tempfile.mkdtemp(prefix="tunebridge-credentials-")
        db.use_path(os.path.join(self.tempdir, "test.db"))
        config.SECRET_KEY = "unit-test-secret"
        self.legacy_path = Path(self.tempdir) / "credentials.json"
        self.patchers = [
            mock.patch.object(storage, "CREDENTIALS_PATH", self.legacy_path),
            mock.patch.object(telegram, "TELEGRAM_PATH", Path(self.tempdir) / "telegram.json"),
            mock.patch.object(youtube, "YOUTUBE_AUTH_PATH", Path(self.tempdir) / "ytmusic_headers.json"),
        ]
        for patcher in self.patchers:
            patcher.start()
        self.user_a = int(accounts.upsert_telegram_user({"id": 801, "first_name": "A"})["id"])
        self.user_b = int(accounts.upsert_telegram_user({"id": 802, "first_name": "B"})["id"])

    def tearDown(self) -> None:
        for patcher in reversed(self.patchers):
            patcher.stop()
        db.close_current()
        config.SECRET_KEY = self.old_secret
        if self.old_path is None:
            os.environ.pop("TUNEBRIDGE_DB_PATH", None)
        else:
            os.environ["TUNEBRIDGE_DB_PATH"] = self.old_path
        shutil.rmtree(self.tempdir, ignore_errors=True)

    def payload(self, service: str) -> dict[str, str]:
        return {"secret": f"{service}-super-secret-cookie", "profile": {"name": "Тест"}}


class SecretStoreTest(CredentialsTestCase):
    def test_ciphertext_is_not_plaintext(self) -> None:
        credentials.save(self.user_a, "youtube", self.payload("youtube"))
        raw = db.scalar(
            "SELECT ciphertext FROM service_credentials WHERE user_id = ? AND service = ?",
            (self.user_a, "youtube"),
        )
        self.assertIsInstance(raw, str)
        self.assertNotIn("super-secret-cookie", raw)
        self.assertEqual(credentials.load(self.user_a, "youtube"), self.payload("youtube"))

    def test_users_are_isolated(self) -> None:
        credentials.save(self.user_a, "youtube", self.payload("youtube"))
        self.assertIsNone(credentials.load(self.user_b, "youtube"))
        credentials.delete(self.user_a, "youtube")
        self.assertIsNone(credentials.load(self.user_a, "youtube"))

    def test_record_is_bound_to_service(self) -> None:
        credentials.save(self.user_a, "youtube", self.payload("youtube"))
        raw = db.scalar(
            "SELECT ciphertext FROM service_credentials WHERE user_id = ? AND service = ?",
            (self.user_a, "youtube"),
        )
        with self.assertLogs("tunebridge.credentials", level="WARNING"):
            self.assertIsNone(credentials.decrypt(raw, user_id=self.user_a, service="spotify"))
            self.assertIsNone(credentials.decrypt(raw, user_id=self.user_b, service="youtube"))
        self.assertIsNotNone(credentials.decrypt(raw, user_id=self.user_a, service="youtube"))

    def test_tampered_ciphertext_is_rejected(self) -> None:
        credentials.save(self.user_a, "yandex", self.payload("yandex"))
        raw = db.scalar(
            "SELECT ciphertext FROM service_credentials WHERE user_id = ? AND service = ?",
            (self.user_a, "yandex"),
        )
        tampered = ("A" if raw[0] != "A" else "B") + raw[1:]
        with db.write_tx() as conn:
            conn.execute(
                "UPDATE service_credentials SET ciphertext = ? WHERE user_id = ? AND service = ?",
                (tampered, self.user_a, "yandex"),
            )
        with self.assertLogs("tunebridge.credentials", level="WARNING"):
            self.assertIsNone(credentials.load(self.user_a, "yandex"))

    def test_missing_key_refuses_to_encrypt(self) -> None:
        config.SECRET_KEY = ""
        with self.assertRaises(RuntimeError):
            credentials.save(self.user_a, "yandex", self.payload("yandex"))

    def test_delete_keeps_other_services(self) -> None:
        credentials.save(self.user_a, "yandex", self.payload("yandex"))
        credentials.save(self.user_a, "spotify", self.payload("spotify"))
        credentials.delete(self.user_a, "yandex")
        self.assertIsNone(credentials.load(self.user_a, "yandex"))
        self.assertEqual(credentials.load(self.user_a, "spotify"), self.payload("spotify"))


class ScopeTest(CredentialsTestCase):
    def test_scope_helper_works_across_threads(self) -> None:
        self.assertIsNone(credentials.current_user_id())
        with ThreadPoolExecutor(max_workers=2) as executor:
            future = executor.submit(credentials.run_as, self.user_a, credentials.current_user_id)
            self.assertEqual(future.result(), self.user_a)
        with credentials.user_scope(self.user_b):
            self.assertEqual(credentials.current_user_id(), self.user_b)
            with credentials.user_scope(None):
                self.assertIsNone(credentials.current_user_id())
            self.assertEqual(credentials.current_user_id(), self.user_b)
        self.assertIsNone(credentials.current_user_id())

    def test_scoped_storage_does_not_read_legacy_files(self) -> None:
        storage.set_service_credentials("youtube", {"headers": {"cookie": "legacy"}})
        self.assertTrue(self.legacy_path.exists())
        with credentials.user_scope(self.user_a):
            self.assertEqual(storage.get_service_credentials("youtube"), {})
            self.assertEqual(storage.get_service_credentials("yandex"), {})

    def test_scoped_storage_writes_encrypted_rows(self) -> None:
        with credentials.user_scope(self.user_a):
            storage.set_service_credentials("yandex", {"token": "yandex-token"})
        stored = db.row(
            "SELECT ciphertext FROM service_credentials WHERE user_id = ? AND service = ?",
            (self.user_a, "yandex"),
        )
        self.assertIsNotNone(stored)
        self.assertNotIn("yandex-token", stored["ciphertext"])
        self.assertEqual(credentials.load(self.user_a, "yandex"), {"token": "yandex-token"})
        self.assertFalse(self.legacy_path.exists())


class ProviderIsolationTest(CredentialsTestCase):
    def test_youtube_connection_follows_user(self) -> None:
        provider = youtube.get_provider()
        with credentials.user_scope(self.user_a):
            storage.set_service_credentials(
                "youtube", {"headers": {"cookie": "SID=test"}, "profile": {"name": "A"}}
            )
            self.assertTrue(provider.is_connected())
            self.assertEqual(provider.profile(), {"name": "A"})
        with credentials.user_scope(self.user_b):
            self.assertFalse(provider.is_connected())
            self.assertIsNone(provider.profile())
        self.assertFalse(provider.is_connected())

    def test_local_mode_still_reads_youtube_file(self) -> None:
        path = Path(self.tempdir) / "ytmusic_headers.json"
        path.write_text(json.dumps({"cookie": "SID=legacy"}), encoding="utf-8")
        with mock.patch.object(youtube, "YOUTUBE_AUTH_PATH", path):
            self.assertTrue(youtube.get_provider().is_connected())
            with credentials.user_scope(self.user_a):
                self.assertFalse(youtube.get_provider().is_connected())

    def test_spotify_connection_follows_user(self) -> None:
        provider = spotify.get_provider()
        with credentials.user_scope(self.user_a):
            storage.set_service_credentials("spotify", {"client_id": "a" * 20})
            self.assertFalse(provider.is_connected())
            credentials.save(self.user_a, "spotify_token", {"access_token": "token"})
            self.assertTrue(provider.is_connected())
        with credentials.user_scope(self.user_b):
            self.assertFalse(provider.is_connected())

    def test_yandex_connection_follows_user(self) -> None:
        provider = yandex.get_provider()
        with credentials.user_scope(self.user_a):
            storage.set_service_credentials("yandex", {"token": "yandex-token"})
            self.assertTrue(provider.is_connected())
        with credentials.user_scope(self.user_b):
            self.assertFalse(provider.is_connected())

    def test_telegram_chat_follows_user(self) -> None:
        with credentials.user_scope(self.user_a):
            telegram._save_chat("111222333")
            self.assertEqual(telegram.saved_chat(), "111222333")
        with credentials.user_scope(self.user_b):
            self.assertEqual(telegram.saved_chat(), "")
        self.assertEqual(telegram.saved_chat(), "")


class SchemaTest(CredentialsTestCase):
    def test_schema_migrations_are_applied(self) -> None:
        self.assertEqual(int(db.scalar("PRAGMA user_version")), 3)
        for table in ("service_credentials", "ad_events"):
            found = db.row("SELECT name FROM sqlite_master WHERE type = 'table' AND name = ?", (table,))
            self.assertIsNotNone(found, table)


if __name__ == "__main__":
    unittest.main()
