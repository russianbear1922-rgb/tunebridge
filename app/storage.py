from __future__ import annotations

import json
import os
import threading
from pathlib import Path
from typing import Any

from . import credentials
from .config import CREDENTIALS_PATH, DATA_DIR

_lock = threading.RLock()


def read_json(path: Path, default: Any = None) -> Any:
    with _lock:
        try:
            with path.open("r", encoding="utf-8") as handle:
                return json.load(handle)
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            return default


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with _lock:
        with tmp.open("w", encoding="utf-8") as handle:
            json.dump(data, handle, ensure_ascii=False, indent=2)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, path)


def load_credentials() -> dict[str, Any]:
    data = read_json(CREDENTIALS_PATH, {})
    return data if isinstance(data, dict) else {}


def save_credentials(data: dict[str, Any]) -> None:
    write_json(CREDENTIALS_PATH, data)


def scoped_user_id() -> int | None:
    """User id when credentials must be isolated; None keeps the legacy files."""
    return credentials.current_user_id()


def get_service_credentials(service: str) -> dict[str, Any]:
    user_id = scoped_user_id()
    if user_id is not None:
        return credentials.load(user_id, service) or {}
    value = load_credentials().get(service)
    return value if isinstance(value, dict) else {}


def set_service_credentials(service: str, value: dict[str, Any]) -> None:
    user_id = scoped_user_id()
    if user_id is not None:
        credentials.save(user_id, service, value)
        return
    data = load_credentials()
    data[service] = value
    save_credentials(data)


def remove_service_credentials(service: str) -> None:
    user_id = scoped_user_id()
    if user_id is not None:
        credentials.delete(user_id, service)
        return
    data = load_credentials()
    data.pop(service, None)
    save_credentials(data)


def remove_file(path: Path) -> None:
    with _lock:
        try:
            path.unlink()
        except FileNotFoundError:
            pass


def data_file(name: str) -> Path:
    return DATA_DIR / name
