from __future__ import annotations

from . import apple, demo, soundcloud, spotify, yandex, youtube
from .base import ProviderError, SourceProvider, TargetProvider

SOURCES: dict[str, SourceProvider] = {
    "yandex": yandex.get_provider(),
    "spotify": spotify.get_provider(),
    "youtube": youtube.get_provider(),
    "soundcloud": soundcloud.get_provider(),
    "apple": apple.get_provider(),
    "demo": demo.get_provider(),
}

TARGETS: dict[str, TargetProvider] = {
    "spotify": spotify.get_provider(),
    "youtube": youtube.get_provider(),
    "demo": demo.get_provider(),
}


def get_source(service: str) -> SourceProvider:
    provider = SOURCES.get(service)
    if provider is None:
        raise ProviderError("Неизвестный источник", f"Сервис «{service}» пока не поддерживается.")
    return provider


def get_target(service: str) -> TargetProvider:
    provider = TARGETS.get(service)
    if provider is None:
        raise ProviderError("Неизвестный сервис переноса", f"Сервис «{service}» пока не поддерживается.")
    return provider
