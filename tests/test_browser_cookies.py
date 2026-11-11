from __future__ import annotations

import ctypes
import sys
import tempfile
import unittest
from ctypes import wintypes
from pathlib import Path

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app import browser_cookies as bc


class HeaderTest(unittest.TestCase):
    def test_deduplicates_cookie_names(self) -> None:
        header = bc._header([("SID", "a"), ("SID", "b"), ("__Secure-3PAPISID", "c")])
        self.assertEqual(header, "SID=a; __Secure-3PAPISID=c")

    def test_skips_empty_names(self) -> None:
        self.assertEqual(bc._header([("", "x"), ("SAPISID", "y")]), "SAPISID=y")


class ChromeValueTest(unittest.TestCase):
    def setUp(self) -> None:
        self.key = AESGCM.generate_key(bit_length=256)

    def test_decrypts_v10_gcm(self) -> None:
        nonce = b"0123456789ab"
        blob = b"v10" + nonce + AESGCM(self.key).encrypt(nonce, b"SID=abc", None)
        self.assertEqual(bc._decrypt_chrome_value(blob, self.key), "SID=abc")

    def test_reports_app_bound_encryption(self) -> None:
        with self.assertRaises(bc.CookieImportError):
            bc._decrypt_chrome_value(b"v20abcdef", self.key)

    def test_passes_plain_values(self) -> None:
        self.assertEqual(bc._decrypt_chrome_value(b"plain", self.key), "plain")


class Blob(ctypes.Structure):
    _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]


@unittest.skipUnless(sys.platform == "win32", "DPAPI доступен только на Windows")
class DpapiTest(unittest.TestCase):
    def test_round_trip(self) -> None:
        payload = b"tunebridge-secret"
        buffer = ctypes.create_string_buffer(payload, len(payload))
        source = Blob(len(payload), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_char)))
        result = Blob()
        ok = ctypes.windll.crypt32.CryptProtectData(
            ctypes.byref(source), None, None, None, None, 0, ctypes.byref(result)
        )
        self.assertTrue(ok)
        try:
            sealed = ctypes.string_at(result.pbData, result.cbData)
        finally:
            ctypes.windll.kernel32.LocalFree(result.pbData)
        self.assertNotEqual(sealed, payload)
        self.assertEqual(bc._dpapi_unprotect(sealed), payload)


class ChromiumProfilesTest(unittest.TestCase):
    def test_finds_default_and_numbered_profiles(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            (root / "Default" / "Network").mkdir(parents=True)
            (root / "Default" / "Network" / "Cookies").write_bytes(b"")
            (root / "Profile 1" / "Network").mkdir(parents=True)
            (root / "Profile 1" / "Network" / "Cookies").write_bytes(b"")
            (root / "NotAProfile").mkdir()
            names = [path.name for path in bc._chromium_profiles(root)]
            self.assertEqual(names, ["Default", "Profile 1"])

    def test_opera_style_single_profile(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            (root / "Network").mkdir()
            (root / "Network" / "Cookies").write_bytes(b"")
            self.assertEqual([path.name for path in bc._chromium_profiles(root)], [root.name])


if __name__ == "__main__":
    unittest.main()
