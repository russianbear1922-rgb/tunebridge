from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import patch

from app.providers import yandex
from app.providers.yandex import _profile_from_client


def account_status(**account) -> SimpleNamespace:
    return SimpleNamespace(account=SimpleNamespace(**account))


class ProfileFromClientTest(unittest.TestCase):
    def test_initialized_client_exposes_account_status_object(self) -> None:
        client = SimpleNamespace(me=account_status(display_name="Мира", login="mira.vale", uid=42))
        self.assertEqual(
            _profile_from_client(client),
            {"name": "Мира", "login": "mira.vale", "uid": 42},
        )

    def test_uninitialized_client_me_is_callable(self) -> None:
        client = SimpleNamespace(me=lambda: account_status(display_name=None, full_name="Мира Вейл", login="mira"))
        self.assertEqual(_profile_from_client(client)["name"], "Мира Вейл")

    def test_falls_back_to_login(self) -> None:
        client = SimpleNamespace(me=account_status(display_name=None, full_name=None, login="mira"))
        self.assertEqual(_profile_from_client(client)["name"], "mira")

    def test_missing_status_or_account(self) -> None:
        self.assertEqual(_profile_from_client(SimpleNamespace(me=None)), {})
        self.assertEqual(_profile_from_client(SimpleNamespace(me=SimpleNamespace(account=None))), {})


class DeviceFlowTest(unittest.TestCase):
    def test_approval_completes_login_and_saves_token(self) -> None:
        status = account_status(display_name="Мира", login="mira", uid=1)

        class FakePollClient:
            def poll_device_token(self, device_code: str) -> SimpleNamespace:
                return SimpleNamespace(access_token="token-123")

        class FakeAuthorizedClient:
            def __init__(self, token: str) -> None:
                self.me = status

            def init(self) -> "FakeAuthorizedClient":
                return self

        def fake_client(*args: str):
            return FakeAuthorizedClient(args[0]) if args else FakePollClient()

        with patch.object(yandex, "Client", fake_client), patch.object(
            yandex, "read_json", return_value={"device_code": "dev", "expires_at": 10**12}
        ), patch.object(yandex, "remove_file", return_value=True), patch.object(
            yandex, "set_service_credentials"
        ) as save:
            result = yandex.poll_device_flow()

        self.assertEqual(result, {"status": "connected", "profile": {"name": "Мира", "login": "mira", "uid": 1}})
        save.assert_called_once_with(
            "yandex",
            {"token": "token-123", "profile": {"name": "Мира", "login": "mira", "uid": 1}},
        )

    def test_pending_approval_keeps_polling(self) -> None:
        class FakePollClient:
            def poll_device_token(self, device_code: str) -> None:
                return None

        with patch.object(yandex, "Client", lambda *args: FakePollClient()), patch.object(
            yandex, "read_json", return_value={"device_code": "dev", "expires_at": 10**12}
        ):
            self.assertEqual(yandex.poll_device_flow(), {"status": "pending"})


class ConnectWithTokenTest(unittest.TestCase):
    def test_strips_oauth_prefix_and_saves_credentials(self) -> None:
        status = account_status(display_name="Мира", login="mira", uid=1)
        created: list[str] = []

        class FakeClient:
            def __init__(self, token: str) -> None:
                created.append(token)
                self.me = status

            def init(self) -> "FakeClient":
                return self

        with patch.object(yandex, "Client", FakeClient), patch.object(
            yandex, "set_service_credentials"
        ) as save:
            profile = yandex.connect_with_token("OAuth abc123")

        self.assertEqual(created, ["abc123"])
        save.assert_called_once_with(
            "yandex",
            {"token": "abc123", "profile": {"name": "Мира", "login": "mira", "uid": 1}},
        )
        self.assertEqual(profile["login"], "mira")

    def test_empty_token_rejected(self) -> None:
        with self.assertRaises(yandex.ProviderError):
            yandex.connect_with_token("   ")


if __name__ == "__main__":
    unittest.main()
