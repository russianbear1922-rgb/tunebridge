from __future__ import annotations

import logging
import os
import sqlite3
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

from . import config

logger = logging.getLogger("tunebridge.db")

_write_lock = threading.RLock()
_local = threading.local()
_schema_ready: set[str] = set()

_SCHEMA_V1 = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    telegram_id INTEGER UNIQUE,
    username TEXT,
    first_name TEXT,
    last_name TEXT,
    lang TEXT,
    balance INTEGER NOT NULL DEFAULT 0,
    trial_granted INTEGER NOT NULL DEFAULT 0,
    is_admin INTEGER NOT NULL DEFAULT 0,
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS sessions (
    id TEXT PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    csrf TEXT NOT NULL,
    created_at REAL NOT NULL,
    expires_at REAL NOT NULL,
    last_seen_at REAL NOT NULL,
    user_agent TEXT
);
CREATE INDEX IF NOT EXISTS sessions_user ON sessions(user_id);

CREATE TABLE IF NOT EXISTS wallet_tx (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    delta INTEGER NOT NULL,
    kind TEXT NOT NULL,
    reason TEXT,
    ref TEXT,
    meta TEXT,
    balance_after INTEGER NOT NULL,
    created_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS wallet_tx_user ON wallet_tx(user_id, id DESC);
CREATE UNIQUE INDEX IF NOT EXISTS wallet_tx_ref ON wallet_tx(kind, ref) WHERE ref IS NOT NULL;

CREATE TABLE IF NOT EXISTS orders (
    id TEXT PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    package_id TEXT NOT NULL,
    tokens INTEGER NOT NULL,
    stars INTEGER NOT NULL,
    status TEXT NOT NULL,
    invoice_url TEXT,
    telegram_payment_charge_id TEXT UNIQUE,
    provider_payment_charge_id TEXT,
    created_at REAL NOT NULL,
    paid_at REAL,
    refunded_at REAL
);
CREATE INDEX IF NOT EXISTS orders_user ON orders(user_id, created_at DESC);

CREATE TABLE IF NOT EXISTS promo_codes (
    code TEXT PRIMARY KEY,
    tokens INTEGER NOT NULL,
    max_uses INTEGER NOT NULL DEFAULT 1,
    used_count INTEGER NOT NULL DEFAULT 0,
    active INTEGER NOT NULL DEFAULT 1,
    expires_at REAL,
    note TEXT,
    created_by INTEGER,
    created_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS promo_redemptions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code TEXT NOT NULL REFERENCES promo_codes(code) ON DELETE CASCADE,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    tokens INTEGER NOT NULL,
    created_at REAL NOT NULL,
    UNIQUE (code, user_id)
);

CREATE TABLE IF NOT EXISTS transfers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    source_service TEXT,
    source_title TEXT,
    source_url TEXT,
    target TEXT,
    target_name TEXT,
    playlist_url TEXT,
    added INTEGER NOT NULL DEFAULT 0,
    total INTEGER NOT NULL DEFAULT 0,
    demo INTEGER NOT NULL DEFAULT 0,
    created_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS transfers_user ON transfers(user_id, id DESC);

CREATE TABLE IF NOT EXISTS kv (
    key TEXT PRIMARY KEY,
    value TEXT
);
"""

_SCHEMA_V2 = """
CREATE TABLE IF NOT EXISTS service_credentials (
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    service TEXT NOT NULL,
    ciphertext TEXT NOT NULL,
    updated_at REAL NOT NULL,
    PRIMARY KEY (user_id, service)
);
"""

_SCHEMA_V3 = """
CREATE TABLE IF NOT EXISTS ad_events (
    day TEXT NOT NULL,
    kind TEXT NOT NULL,
    count INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (day, kind)
);
"""


def _database_path() -> str:
    return os.environ.get("TUNEBRIDGE_DB_PATH") or str(config.DB_PATH)


def _connect_raw(path: str) -> sqlite3.Connection:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, timeout=10, isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA busy_timeout=5000")
    return conn


def _ensure_schema(conn: sqlite3.Connection, path: str) -> None:
    if path in _schema_ready:
        return
    with _write_lock:
        if path in _schema_ready:
            return
        version = int(conn.execute("PRAGMA user_version").fetchone()[0])
        if version < 1:
            conn.executescript(_SCHEMA_V1)
            conn.execute("PRAGMA user_version = 1")
        if version < 2:
            conn.executescript(_SCHEMA_V2)
            conn.execute("PRAGMA user_version = 2")
        if version < 3:
            conn.executescript(_SCHEMA_V3)
            conn.execute("PRAGMA user_version = 3")
        _schema_ready.add(path)


def connect() -> sqlite3.Connection:
    path = _database_path()
    conn = getattr(_local, "conn", None)
    if conn is not None and getattr(_local, "path", None) == path:
        return conn
    if conn is not None:
        try:
            conn.close()
        except sqlite3.Error:
            pass
    conn = _connect_raw(path)
    _local.conn = conn
    _local.path = path
    _ensure_schema(conn, path)
    return conn


def init() -> None:
    connect()


def use_path(path: str | Path) -> None:
    """Point the layer at another database (tests, isolated deployments)."""
    close_current()
    os.environ["TUNEBRIDGE_DB_PATH"] = str(path)
    _schema_ready.discard(str(path))
    connect()


def close_current() -> None:
    conn = getattr(_local, "conn", None)
    if conn is not None:
        try:
            conn.close()
        except sqlite3.Error:
            pass
    _local.conn = None
    _local.path = None


def rows(sql: str, params: tuple[Any, ...] = ()) -> list[sqlite3.Row]:
    return list(connect().execute(sql, params).fetchall())


def row(sql: str, params: tuple[Any, ...] = ()) -> sqlite3.Row | None:
    return connect().execute(sql, params).fetchone()


def scalar(sql: str, params: tuple[Any, ...] = (), default: Any = None) -> Any:
    found = row(sql, params)
    return found[0] if found is not None else default


@contextmanager
def write_tx() -> Iterator[sqlite3.Connection]:
    conn = connect()
    with _write_lock:
        conn.execute("BEGIN IMMEDIATE")
        try:
            yield conn
        except BaseException:
            try:
                conn.execute("ROLLBACK")
            except sqlite3.Error:
                pass
            raise
        else:
            conn.execute("COMMIT")


def kv_get(key: str, default: str = "") -> str:
    value = scalar("SELECT value FROM kv WHERE key = ?", (key,), default)
    return str(value) if value is not None else default


def kv_set(key: str, value: str) -> None:
    with write_tx() as conn:
        conn.execute(
            "INSERT INTO kv(key, value) VALUES(?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, str(value)),
        )
