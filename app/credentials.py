from __future__ import annotations

import base64
import hashlib
import json
import logging
import time
from contextlib import contextmanager
from contextvars import ContextVar, Token
from typing import Any, Callable, Iterator, TypeVar

from cryptography.fernet import Fernet, InvalidToken

from . import config, db

logger = logging.getLogger("tunebridge.credentials")

_current_user: ContextVar[int | None] = ContextVar("tunebridge_user", default=None)
T = TypeVar("T")


def current_user_id() -> int | None:
    return _current_user.get()


def activate(user_id: int | None) -> Token[int | None]:
    return _current_user.set(int(user_id) if user_id is not None else None)


def reset(token: Token[int | None]) -> None:
    _current_user.reset(token)


@contextmanager
def user_scope(user_id: int | None) -> Iterator[None]:
    token = activate(user_id)
    try:
        yield
    finally:
        reset(token)


def run_as(user_id: int | None, func: Callable[..., T], *args: Any, **kwargs: Any) -> T:
    with user_scope(user_id):
        return func(*args, **kwargs)


def _secret() -> str:
    secret = config.SECRET_KEY
    if not secret:
        raise RuntimeError("TUNEBRIDGE_SECRET_KEY не задан — шифрование недоступно")
    return secret


def _cipher() -> Fernet:
    digest = hashlib.sha256(f"tunebridge:v1:{_secret()}".encode("utf-8")).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def encrypt(payload: dict[str, Any]) -> str:
    raw = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return _cipher().encrypt(raw).decode("ascii")


def decrypt(token: str, *, user_id: int | None = None, service: str | None = None) -> dict[str, Any] | None:
    try:
        raw = _cipher().decrypt(str(token).encode("ascii"))
        value = json.loads(raw.decode("utf-8"))
    except (InvalidToken, ValueError, UnicodeError):
        logger.warning("Could not decrypt stored credentials")
        return None
    if not isinstance(value, dict):
        return None
    envelope = value.get("d")
    if not isinstance(envelope, dict):
        return None
    if user_id is not None and value.get("u") != int(user_id):
        logger.warning("Stored credentials belong to another user")
        return None
    if service is not None and value.get("s") != service:
        logger.warning("Stored credentials belong to another service")
        return None
    return envelope


def load(user_id: int, service: str) -> dict[str, Any] | None:
    found = db.row(
        "SELECT ciphertext FROM service_credentials WHERE user_id = ? AND service = ?",
        (int(user_id), service),
    )
    if found is None:
        return None
    return decrypt(found["ciphertext"], user_id=user_id, service=service)


def save(user_id: int, service: str, payload: dict[str, Any]) -> None:
    ciphertext = encrypt({"u": int(user_id), "s": service, "d": payload})
    with db.write_tx() as conn:
        conn.execute(
            "INSERT INTO service_credentials(user_id, service, ciphertext, updated_at) "
            "VALUES(?, ?, ?, ?) ON CONFLICT(user_id, service) DO UPDATE SET "
            "ciphertext = excluded.ciphertext, updated_at = excluded.updated_at",
            (int(user_id), service, ciphertext, time.time()),
        )


def delete(user_id: int, service: str) -> None:
    with db.write_tx() as conn:
        conn.execute(
            "DELETE FROM service_credentials WHERE user_id = ? AND service = ?",
            (int(user_id), service),
        )
