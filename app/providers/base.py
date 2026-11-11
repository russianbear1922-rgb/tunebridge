from __future__ import annotations

import re
from abc import ABC, abstractmethod
from typing import Any

from ..models import Playlist, Track


class ProviderError(Exception):
    def __init__(self, message: str, hint: str | None = None, *, fatal: bool = False):
        super().__init__(message)
        self.message = message
        self.hint = hint
        self.fatal = fatal


class NotConnectedError(ProviderError):
    def __init__(self, service_name: str, hint: str | None = None):
        super().__init__(
            f"{service_name}: аккаунт не подключён",
            hint or "Подключите аккаунт в разделе сервисов слева.",
            fatal=True,
        )


class AuthError(ProviderError):
    def __init__(self, service_name: str, hint: str | None = None):
        super().__init__(
            f"{service_name} отклонил доступ",
            hint or "Подключите аккаунт заново — срок действия токена истёк.",
            fatal=True,
        )


class RateLimitError(ProviderError):
    def __init__(self, service_name: str, hint: str | None = None):
        super().__init__(
            f"{service_name}: слишком много запросов",
            hint or "Подождите минуту и повторите. Для больших плейлистов сервис может ограничивать частоту.",
        )


def clean_url(value: str | None) -> str | None:
    if not value:
        return None
    if value.startswith("//"):
        value = "https:" + value
    if value.startswith("http://"):
        value = "https://" + value[len("http://") :]
    if not value.startswith("https://") and not value.startswith("/"):
        return None
    return value


def normalize_space(value: str | None) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


class SourceProvider(ABC):
    id: str
    name: str

    def is_connected(self) -> bool:
        return False

    def profile(self) -> dict[str, Any] | None:
        return None

    @abstractmethod
    def list_playlists(self) -> list[Playlist]:
        raise NotImplementedError

    @abstractmethod
    def resolve_url(self, url: str) -> Playlist:
        raise NotImplementedError

    def get_playlist(self, ref: str) -> Playlist:
        return self.resolve_url(ref)


class TargetProvider(ABC):
    id: str
    name: str
    search_workers: int = 3
    batch_size: int = 50
    supports_search: bool = True
    auth_required: bool = True

    def is_connected(self) -> bool:
        return False

    @abstractmethod
    def search(self, track: Track) -> list[Track]:
        raise NotImplementedError

    def search_query(self, query: str) -> list[Track]:
        raise NotImplementedError

    @abstractmethod
    def create_playlist(self, title: str, description: str, options: dict[str, Any]) -> dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    def add_batch(self, playlist_id: str, tracks: list[Track]) -> None:
        raise NotImplementedError
