from __future__ import annotations

import unittest
from unittest import mock

from fastapi import HTTPException
from starlette.requests import Request
from ytmusicapi.exceptions import YTMusicUserError

from app import main, network
from app.providers import youtube


def client_factory(by_cookie=None, *, requested=None):
    by_cookie = by_cookie or {}

    def build(auth=None, language="ru"):
        auth = auth or {}
        cookie = str(auth.get("cookie") or "")
        index = str(auth.get("x-goog-authuser") or "0")
        if requested is not None:
            requested.append((cookie, index))
        client = mock.Mock()
        for marker, profiles in by_cookie.items():
            if marker in cookie:
                profile = profiles.get(index)
                if profile is None:
                    client.get_account_info.side_effect = YTMusicUserError("no account")
                else:
                    client.get_account_info.return_value = profile
                return client
        client.get_account_info.side_effect = YTMusicUserError("no account")
        return client

    return build


def cookie(marker: str) -> str:
    return f"SAPISID=abc; __Secure-3PAPISID=XYZ123; marker={marker}"


class ConnectWithHeadersTest(unittest.TestCase):
    def setUp(self) -> None:
        patches = [
            mock.patch.object(youtube, "write_json"),
            mock.patch.object(youtube, "set_service_credentials"),
        ]
        self.write_json, self.save_credentials = [patcher.start() for patcher in patches]
        self.patches = patches

    def tearDown(self) -> None:
        for patcher in reversed(self.patches):
            patcher.stop()

    def test_asks_to_choose_when_browser_has_two_accounts(self) -> None:
        factory = client_factory(
            {
                "SAPISID=abc": {
                    "0": {"name": "Владелец", "channelId": "u1"},
                    "1": {"name": "Друг", "channelId": "u2"},
                }
            }
        )
        with mock.patch.object(youtube, "YTMusic", side_effect=factory):
            with self.assertRaises(youtube.AccountChoiceRequired) as ctx:
                youtube.connect_with_headers(cookie(""))
        names = [account["name"] for account in ctx.exception.accounts]
        self.assertEqual(names, ["Владелец", "Друг"])
        self.assertEqual([account["authuser"] for account in ctx.exception.accounts], [0, 1])
        self.write_json.assert_not_called()
        self.save_credentials.assert_not_called()

    def test_explicit_authuser_connects_that_account(self) -> None:
        factory = client_factory(
            {
                "SAPISID=abc": {
                    "0": {"name": "Владелец", "channelId": "u1"},
                    "1": {"name": "Друг", "channelId": "u2"},
                }
            }
        )
        with mock.patch.object(youtube, "YTMusic", side_effect=factory):
            profile = youtube.connect_with_headers(cookie(""), authuser=1)
        self.assertEqual(profile["name"], "Друг")
        headers = self.write_json.call_args[0][1]
        self.assertEqual(headers["x-goog-authuser"], "1")

    def test_header_block_authuser_is_not_ignored(self) -> None:
        requested: list[tuple[str, str]] = []
        factory = client_factory(
            {
                "SAPISID=abc": {
                    "0": {"name": "Владелец", "channelId": "u1"},
                    "1": {"name": "Друг", "channelId": "u2"},
                }
            },
            requested=requested,
        )
        raw = "cookie: SAPISID=abc; __Secure-3PAPISID=XYZ123\nx-goog-authuser: 1"
        with mock.patch.object(youtube, "YTMusic", side_effect=factory):
            profile = youtube.connect_with_headers(raw)
        self.assertEqual(profile["name"], "Друг")
        self.assertEqual([index for _cookie, index in requested], ["1"])


class ConnectFromBrowserTest(unittest.TestCase):
    def setUp(self) -> None:
        patches = [
            mock.patch.object(youtube, "write_json"),
            mock.patch.object(youtube, "set_service_credentials"),
            mock.patch.object(youtube.browser_cookies, "collect_youtube_cookies"),
        ]
        self.write_json, self.save_credentials, self.collect = [patcher.start() for patcher in patches]
        self.patches = patches

    def tearDown(self) -> None:
        for patcher in reversed(self.patches):
            patcher.stop()

    def test_two_browsers_offer_both_accounts(self) -> None:
        self.collect.return_value = [("Chrome", cookie("chrome")), ("Firefox", cookie("firefox"))]
        factory = client_factory(
            {
                "chrome": {"0": {"name": "Владелец", "channelId": "u1"}},
                "firefox": {"0": {"name": "Друг", "channelId": "u2"}},
            }
        )
        with mock.patch.object(youtube, "YTMusic", side_effect=factory):
            with self.assertRaises(youtube.AccountChoiceRequired) as ctx:
                youtube.connect_from_browser()
        self.assertEqual(
            [(account["label"], account["name"]) for account in ctx.exception.accounts],
            [("Chrome", "Владелец"), ("Firefox", "Друг")],
        )
        self.write_json.assert_not_called()

    def test_chosen_browser_account_is_saved(self) -> None:
        self.collect.return_value = [("Chrome", cookie("chrome")), ("Firefox", cookie("firefox"))]
        factory = client_factory(
            {
                "chrome": {"0": {"name": "Владелец", "channelId": "u1"}},
                "firefox": {"0": {"name": "Друг", "channelId": "u2"}},
            }
        )
        with mock.patch.object(youtube, "YTMusic", side_effect=factory):
            profile = youtube.connect_from_browser("Firefox", 0)
        self.assertEqual(profile["name"], "Друг")
        self.assertEqual(profile["browser"], "Firefox")
        headers = self.write_json.call_args[0][1]
        self.assertIn("firefox", headers["cookie"])

    def test_single_account_connects_without_questions(self) -> None:
        self.collect.return_value = [("Chrome", cookie("chrome"))]
        factory = client_factory({"chrome": {"0": {"name": "Друг", "channelId": "u2"}}})
        with mock.patch.object(youtube, "YTMusic", side_effect=factory):
            profile = youtube.connect_from_browser()
        self.assertEqual(profile["name"], "Друг")
        self.write_json.assert_called_once()


def request_from(host: str) -> Request:
    return Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/api/connect/youtube/browser",
            "headers": [],
            "client": (host, 50000),
        }
    )


class BrowserEndpointGuardTest(unittest.TestCase):
    def test_hosted_mode_disables_browser_import(self) -> None:
        with mock.patch.object(main, "HOSTED", True):
            with self.assertRaises(HTTPException) as ctx:
                main.youtube_connect_browser(request_from("127.0.0.1"))
        self.assertEqual(ctx.exception.status_code, 403)

    def test_remote_device_cannot_read_server_browsers(self) -> None:
        with mock.patch.object(main, "HOSTED", False), mock.patch.object(
            main, "is_local_client", return_value=False
        ):
            with self.assertRaises(HTTPException) as ctx:
                main.youtube_connect_browser(request_from("192.168.1.20"))
        self.assertEqual(ctx.exception.status_code, 403)

    def test_local_request_still_connects(self) -> None:
        with mock.patch.object(main, "HOSTED", False), mock.patch.object(
            main, "is_local_client", return_value=True
        ), mock.patch.object(
            main.youtube, "connect_from_browser", return_value={"name": "Друг"}
        ) as connect:
            result = main.youtube_connect_browser(request_from("127.0.0.1"))
        self.assertTrue(result["ok"])
        self.assertEqual(result["profile"]["name"], "Друг")
        connect.assert_called_once()


class LocalClientTest(unittest.TestCase):
    def test_loopback_and_unknown_addresses(self) -> None:
        self.assertTrue(network.is_local_client("127.0.0.1"))
        self.assertTrue(network.is_local_client("::1"))
        self.assertFalse(network.is_local_client("192.0.2.10"))
        self.assertFalse(network.is_local_client(None))


if __name__ == "__main__":
    unittest.main()
