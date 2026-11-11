from __future__ import annotations

import base64
import ctypes
import json
import os
import shutil
import sqlite3
import sys
import tempfile
from ctypes import wintypes
from pathlib import Path
from typing import Any

from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

_COOKIE_HOST = "%youtube.com"


class CookieImportError(Exception):
    pass


class _Blob(ctypes.Structure):
    _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]


def _dpapi_unprotect(payload: bytes) -> bytes:
    if sys.platform != "win32":
        raise CookieImportError("Импорт из браузера поддерживается только на Windows")
    buffer = ctypes.create_string_buffer(payload, len(payload))
    source = _Blob(len(payload), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_char)))
    result = _Blob()
    ok = ctypes.windll.crypt32.CryptUnprotectData(
        ctypes.byref(source), None, None, None, None, 0, ctypes.byref(result)
    )
    if not ok:
        raise CookieImportError("Windows не смогла расшифровать ключ браузера")
    try:
        return ctypes.string_at(result.pbData, result.cbData)
    finally:
        ctypes.windll.kernel32.LocalFree(result.pbData)


def _chrome_key(profile_root: Path) -> bytes:
    state_path = profile_root / "Local State"
    if not state_path.exists():
        raise CookieImportError("Браузер ещё не создавал профиль")
    try:
        state = json.loads(state_path.read_text(encoding="utf-8"))
        encrypted = base64.b64decode(state["os_crypt"]["encrypted_key"])
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise CookieImportError("Не удалось прочитать ключ браузера") from exc
    if not encrypted.startswith(b"DPAPI"):
        raise CookieImportError("Браузер хранит cookie в неизвестном формате")
    return _dpapi_unprotect(encrypted[5:])


def _as_cookie_text(data: bytes) -> str:
    for candidate in (data, data[32:] if len(data) > 32 else b""):
        if not candidate:
            continue
        try:
            text = candidate.decode("utf-8")
        except UnicodeDecodeError:
            continue
        if text and all(character.isprintable() for character in text):
            return text
    raise CookieImportError("cookie расшифровались в неизвестном виде")


def _decrypt_cbc(key: bytes, payload: bytes) -> str:
    decryptor = Cipher(algorithms.AES(key), modes.CBC(b" " * 16)).decryptor()
    data = decryptor.update(payload) + decryptor.finalize()
    padding = data[-1] if data else 0
    if 1 <= padding <= 16 and data.endswith(bytes([padding]) * padding):
        data = data[:-padding]
    return _as_cookie_text(data)


def _decrypt_chrome_value(encrypted: bytes, key: bytes) -> str:
    if not encrypted:
        return ""
    prefix = encrypted[:3]
    if prefix in (b"v10", b"v11"):
        nonce, payload = encrypted[3:15], encrypted[15:]
        try:
            return _as_cookie_text(AESGCM(key).decrypt(nonce, payload, None))
        except Exception:  # noqa: BLE001
            try:
                return _decrypt_cbc(key, payload)
            except CookieImportError:
                raise
            except Exception as exc:  # noqa: BLE001
                raise CookieImportError(
                    f"cookie в формате {prefix.decode(errors='replace')} не расшифровались"
                ) from exc
    if prefix == b"v20":
        raise CookieImportError("браузер перешёл на новое шифрование cookie")
    return _as_cookie_text(encrypted)


def _copy_database(path: Path, folder: Path) -> Path:
    target = folder / "cookies.sqlite"
    shutil.copy2(path, target)
    for suffix in ("-wal", "-shm"):
        extra = path.with_name(path.name + suffix)
        if extra.exists():
            shutil.copy2(extra, target.with_name(target.name + suffix))
    return target


def _read_sqlite(path: Path, query: str, params: tuple[Any, ...]) -> list[tuple[Any, ...]]:
    with tempfile.TemporaryDirectory(prefix="tunebridge-cookies-") as raw:
        database = _copy_database(path, Path(raw))
        connection = sqlite3.connect(f"file:{database}?mode=ro", uri=True)
        try:
            return list(connection.execute(query, params).fetchall())
        finally:
            connection.close()


def _header(pairs: list[tuple[str, str]]) -> str:
    seen: dict[str, str] = {}
    for name, value in pairs:
        if not name or name in seen:
            continue
        seen[name] = value
    return "; ".join(f"{name}={value}" for name, value in seen.items())


def _chromium_cookie_file(profile: Path) -> Path | None:
    for candidate in (profile / "Network" / "Cookies", profile / "Cookies"):
        if candidate.exists():
            return candidate
    return None


def _chromium_profiles(root: Path) -> list[Path]:
    if not root.is_dir():
        return []
    profiles: list[Path] = []
    if _chromium_cookie_file(root):
        profiles.append(root)
    default = root / "Default"
    if default.is_dir():
        profiles.append(default)
    try:
        children = sorted(root.iterdir())
    except OSError:
        children = []
    for child in children:
        if child.is_dir() and child.name.startswith("Profile "):
            profiles.append(child)
    return profiles


def _chromium_cookies(root: Path) -> list[tuple[str, list[tuple[str, str]]]]:
    """Возвращает наборы cookie для каждого профиля браузера."""
    result: list[tuple[str, list[tuple[str, str]]]] = []
    key: bytes | None = None
    for profile in _chromium_profiles(root):
        database = _chromium_cookie_file(profile)
        if not database:
            continue
        if key is None:
            try:
                key = _chrome_key(root)
            except CookieImportError:
                raise
        try:
            rows = _read_sqlite(
                database,
                "SELECT host_key, name, value, encrypted_value FROM cookies WHERE host_key LIKE ?",
                (_COOKIE_HOST,),
            )
        except (sqlite3.DatabaseError, OSError):
            continue
        pairs: list[tuple[str, str]] = []
        failed: CookieImportError | None = None
        for _host, name, value, encrypted in rows:
            if not name:
                continue
            if value:
                pairs.append((str(name), str(value)))
                continue
            try:
                decrypted = _decrypt_chrome_value(bytes(encrypted), key)
            except CookieImportError as exc:
                failed = failed or exc
                continue
            if decrypted:
                pairs.append((str(name), decrypted))
        if pairs:
            result.append((profile.name, pairs))
        elif failed is not None:
            raise failed
    return result


def _firefox_profiles(root: Path) -> list[Path]:
    if not root.is_dir():
        return []
    return [child for child in sorted(root.iterdir()) if (child / "cookies.sqlite").exists()]


def _firefox_cookies(root: Path) -> list[tuple[str, list[tuple[str, str]]]]:
    result: list[tuple[str, list[tuple[str, str]]]] = []
    for profile in _firefox_profiles(root):
        try:
            rows = _read_sqlite(
                profile / "cookies.sqlite",
                "SELECT host, name, value FROM moz_cookies WHERE host LIKE ?",
                (_COOKIE_HOST,),
            )
        except (sqlite3.DatabaseError, OSError):
            continue
        pairs = [(str(name), str(value)) for _host, name, value in rows if name and value]
        if pairs:
            result.append((profile.name, pairs))
    return result


def _candidates() -> list[tuple[str, Path, str]]:
    local = Path(os.environ.get("LOCALAPPDATA") or "")
    roaming = Path(os.environ.get("APPDATA") or "")
    return [
        ("Яндекс Браузер", local / "Yandex" / "YandexBrowser" / "User Data", "chromium"),
        ("Opera", roaming / "Opera Software" / "Opera Stable", "chromium"),
        ("Opera GX", roaming / "Opera Software" / "Opera GX Stable", "chromium"),
        ("Chrome", local / "Google" / "Chrome" / "User Data", "chromium"),
        ("Edge", local / "Microsoft" / "Edge" / "User Data", "chromium"),
        ("Brave", local / "BraveSoftware" / "Brave-Browser" / "User Data", "chromium"),
        ("Vivaldi", local / "Vivaldi" / "User Data", "chromium"),
        ("Firefox", roaming / "Mozilla" / "Firefox" / "Profiles", "firefox"),
    ]


def collect_youtube_cookies() -> list[tuple[str, str]]:
    """Собирает cookie youtube.com из локальных профилей браузеров.

    Возвращает список (название браузера, значение заголовка cookie).
    Ничего не отправляет по сети и не пишет cookie в журналы.
    """
    if sys.platform != "win32":
        raise CookieImportError("Импорт из браузера поддерживается только на Windows")
    found: list[tuple[str, str]] = []
    for name, root, kind in _candidates():
        try:
            profiles = _chromium_cookies(root) if kind == "chromium" else _firefox_cookies(root)
        except CookieImportError:
            continue
        except OSError:
            continue
        for profile_name, pairs in profiles:
            header = _header(pairs)
            if header:
                label = name if profile_name in {"Default", "Opera Stable"} else f"{name} · {profile_name}"
                found.append((label, header))
    return found


def scan() -> list[dict[str, str]]:
    """Короткий отчёт по браузерам без самих cookie — для подсказок в интерфейсе."""
    if sys.platform != "win32":
        return []
    report: list[dict[str, str]] = []
    for name, root, kind in _candidates():
        if not root.is_dir():
            report.append({"label": name, "status": "missing"})
            continue
        try:
            profiles = _chromium_cookies(root) if kind == "chromium" else _firefox_cookies(root)
        except CookieImportError as exc:
            report.append({"label": name, "status": "error", "detail": str(exc)})
            continue
        except OSError:
            report.append({"label": name, "status": "error", "detail": "Нет доступа к профилю браузера"})
            continue
        if not profiles:
            report.append({"label": name, "status": "no_login"})
            continue
        for profile_name, pairs in profiles:
            names = {cookie_name for cookie_name, _value in pairs}
            report.append(
                {
                    "label": name,
                    "status": "login" if "__Secure-3PAPISID" in names else "no_youtube",
                    "profile": profile_name,
                }
            )
    return report

