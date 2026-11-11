from __future__ import annotations

import json
import unittest

from app.providers.base import ProviderError
from app.providers.youtube import build_auth_headers


class YouTubeAuthInputTest(unittest.TestCase):
    def test_accepts_bare_cookie_value(self) -> None:
        headers = build_auth_headers("SAPISID=abc; __Secure-3PAPISID=XYZ123; SID=def")
        self.assertEqual(headers["cookie"], "SAPISID=abc; __Secure-3PAPISID=XYZ123; SID=def")
        self.assertEqual(headers["origin"], "https://music.youtube.com")
        self.assertEqual(headers["x-goog-authuser"], "0")
        self.assertTrue(headers["authorization"].startswith("SAPISIDHASH "))

    def test_accepts_cookie_header_prefix_and_quotes(self) -> None:
        headers = build_auth_headers('cookie: "SID=abc; __Secure-3PAPISID=XYZ123"')
        self.assertNotIn('"', headers["cookie"])
        self.assertIn("__Secure-3PAPISID=XYZ123", headers["cookie"])

    def test_extracts_cookie_from_curl(self) -> None:
        curl = (
            "curl 'https://music.youtube.com/youtubei/v1/browse?alt=json' "
            "-H 'authorization: SAPISIDHASH 1_x' "
            "-H 'cookie: SID=abc; __Secure-3PAPISID=XYZ123'"
        )
        headers = build_auth_headers(curl)
        self.assertEqual(headers["cookie"], "SID=abc; __Secure-3PAPISID=XYZ123")
        self.assertIn("SAPISIDHASH", headers["authorization"])

    def test_extracts_cookie_from_request_headers_block(self) -> None:
        block = (
            "authorization: SAPISIDHASH 1_x\n"
            "cookie: SID=abc; __Secure-3PAPISID=XYZ123; HSID=def\n"
            "x-goog-authuser: 1"
        )
        headers = build_auth_headers(block)
        self.assertEqual(headers["x-goog-authuser"], "0")
        self.assertEqual(headers["origin"], "https://music.youtube.com")

    def test_completes_json_without_authorization(self) -> None:
        raw = json.dumps({"cookie": "SID=abc; __Secure-3PAPISID=XYZ123"})
        headers = build_auth_headers(raw)
        self.assertEqual(headers["cookie"], "SID=abc; __Secure-3PAPISID=XYZ123")
        self.assertTrue(headers["authorization"].startswith("SAPISIDHASH "))

    def test_rejects_cookie_without_sapisid(self) -> None:
        with self.assertRaises(ProviderError) as ctx:
            build_auth_headers("SID=abc; HSID=def")
        self.assertIn("__Secure-3PAPISID", ctx.exception.hint)

    def test_rejects_empty_input(self) -> None:
        with self.assertRaises(ProviderError):
            build_auth_headers("   ")


if __name__ == "__main__":
    unittest.main()
