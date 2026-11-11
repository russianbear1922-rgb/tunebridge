from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest import mock

from app import telegram
from app.models import Playlist, Track
from app.providers.base import ProviderError


def make_playlist(count: int = 3, with_urls: bool = True) -> Playlist:
    tracks = [
        Track(
            id=str(index),
            title=f"Трек {index}",
            artists=["Артист"],
            url=f"https://music.yandex.ru/track/{index}" if with_urls else None,
        )
        for index in range(1, count + 1)
    ]
    return Playlist(
        id="p1",
        service="yandex",
        title="Дорожка",
        track_count=count,
        tracks=tracks,
        url="https://music.yandex.ru/playlists/1",
    )


class TelegramTextTests(unittest.TestCase):
    def test_build_text_contains_links_and_numbers(self):
        text = telegram.build_text(make_playlist(2))
        self.assertIn("Дорожка", text)
        self.assertIn("2 трека", text)
        self.assertIn("Яндекс Музыка", text)
        self.assertIn("1. Артист — Трек 1", text)
        self.assertIn("https://music.yandex.ru/track/2", text)

    def test_long_playlist_is_truncated_with_note(self):
        text = telegram.build_text(make_playlist(200))
        self.assertIn("первые 150", text)
        self.assertNotIn("151. Артист", text)

    def test_chunks_respect_limit(self):
        text = "\n\n".join("x" * 400 for _ in range(40))
        chunks = telegram._message_chunks(text)
        self.assertGreater(len(chunks), 1)
        for chunk in chunks:
            self.assertLessEqual(len(chunk), telegram._MESSAGE_LIMIT)

    def test_chunks_keep_short_text_whole(self):
        self.assertEqual(telegram._message_chunks("привет"), ["привет"])


class TelegramConnectTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.path = Path(self.folder.name) / "telegram.json"
        self.patch = mock.patch.object(telegram, "TELEGRAM_PATH", self.path)
        self.patch.start()

    def tearDown(self):
        self.patch.stop()
        self.folder.cleanup()

    def test_rejects_wrong_token_shape(self):
        with mock.patch.object(telegram, "_call") as call:
            with self.assertRaises(ProviderError):
                telegram.connect("not-a-token")
            call.assert_not_called()

    def test_connect_saves_bot_and_profile(self):
        with mock.patch.object(
            telegram, "get_me", return_value={"id": 42, "username": "tune_bot", "first_name": "Tune"}
        ):
            profile = telegram.connect("123456789:AAH-abcdefghijklmnopqrstuvwxyz0123456789")
        self.assertTrue(telegram.is_connected())
        self.assertEqual(profile["name"], "@tune_bot")
        self.assertEqual(telegram.saved_chat(), "")

    def test_disconnect_removes_file(self):
        with mock.patch.object(telegram, "get_me", return_value={"id": 1, "username": "bot"}):
            telegram.connect("123456789:AAH-abcdefghijklmnopqrstuvwxyz0123456789")
        telegram.disconnect()
        self.assertFalse(telegram.is_connected())
        self.assertFalse(self.path.exists())


class TelegramSendTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.path = Path(self.folder.name) / "telegram.json"
        self.path.write_text(
            '{"token": "123456789:AAH-abcdefghijklmnopqrstuvwxyz0123456789", "bot": {"username": "bot"}}',
            encoding="utf-8",
        )
        self.patch = mock.patch.object(telegram, "TELEGRAM_PATH", self.path)
        self.patch.start()

    def tearDown(self):
        self.patch.stop()
        self.folder.cleanup()

    def test_send_requires_token(self):
        self.path.unlink()
        with self.assertRaises(ProviderError):
            telegram.send_playlist(make_playlist(), "@channel")

    def test_resolve_chat_values(self):
        self.assertEqual(telegram._resolve_chat("@my_channel"), "@my_channel")
        self.assertEqual(telegram._resolve_chat("-1001234567890"), "-1001234567890")
        with self.assertRaises(ProviderError):
            telegram._resolve_chat("просто текст")

    def test_send_uses_discovered_chat_and_archive(self):
        calls = []

        def fake_call(method, payload=None, files=None, *, timeout=25):
            calls.append((method, payload or {}, files))
            return {"ok": True, "result": {}}

        with mock.patch.object(telegram, "_call", side_effect=fake_call), mock.patch.object(
            telegram, "discover_chats", return_value=[{"value": "777", "title": "Я", "type": "private"}]
        ):
            result = telegram.send_playlist(make_playlist(3), "", ["m3u", "csv"])

        methods = [method for method, _payload, _files in calls]
        self.assertEqual(methods, ["sendMessage", "sendDocument"])
        self.assertEqual(result["messages"], 1)
        self.assertTrue(result["archive"])
        self.assertIn("777", result["chat"])
        document = calls[1][2]["document"]
        self.assertTrue(document[0].endswith(".zip"))
        self.assertTrue(document[1].startswith(b"PK"))
        self.assertEqual(telegram.saved_chat(), "777")

    def test_send_without_archive(self):
        with mock.patch.object(telegram, "_call", return_value={"ok": True}) as call:
            result = telegram.send_playlist(make_playlist(2), "@channel", [])
        self.assertFalse(result["archive"])
        self.assertEqual(result["messages"], 1)
        self.assertEqual(call.call_count, 1)

    def test_empty_playlist_is_rejected(self):
        with self.assertRaises(ProviderError):
            telegram.send_playlist(make_playlist(0), "@channel")


if __name__ == "__main__":
    unittest.main()
