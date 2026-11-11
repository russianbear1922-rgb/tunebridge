from __future__ import annotations

import logging
import secrets
import threading
import time
from collections import deque
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from typing import Any, Callable

from .config import MATCH_CACHE_PATH, SERVICE_NAMES
from . import accounts, billing, config, credentials, db
from .matching import (
    AUTO_THRESHOLD,
    REVIEW_THRESHOLD,
    make_match,
    match_cache_key,
    stats_for,
)
from .models import Candidate, Match, Playlist, Track
from .providers.base import (
    AuthError,
    NotConnectedError,
    ProviderError,
    RateLimitError,
    TargetProvider,
)
from .providers.registry import get_target
from .storage import read_json, write_json

logger = logging.getLogger("tunebridge.jobs")

_CACHE_LIMIT = 8000
_JOB_TTL = 6 * 60 * 60


class BusyError(Exception):
    def __init__(self, active: dict[str, Any]):
        super().__init__("Уже выполняется другая задача")
        self.active = active


class JobCancelled(Exception):
    pass


@dataclass
class Job:
    id: str
    type: str
    title: str
    total: int = 0
    status: str = "running"
    phase: str = "starting"
    done: int = 0
    current: str | None = None
    message: str | None = None
    error: str | None = None
    hint: str | None = None
    result: dict[str, Any] | None = None
    events: deque[dict[str, Any]] = field(default_factory=lambda: deque(maxlen=14))
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    finished_at: float | None = None
    cancel_event: threading.Event = field(default_factory=threading.Event)
    playlist: Playlist | None = None
    target: str | None = None
    owner: str = "local"


class JobManager:
    def __init__(self) -> None:
        self._jobs: dict[str, Job] = {}
        self._lock = threading.RLock()
        self._active: dict[str, str] = {}

    def _cleanup(self) -> None:
        cutoff = time.time() - _JOB_TTL
        active_ids = set(self._active.values())
        for job_id, job in list(self._jobs.items()):
            if job.id in active_ids:
                continue
            if job.created_at < cutoff:
                self._jobs.pop(job_id, None)

    def start(self, job_type: str, title: str, total: int, worker: Callable[[Job], dict[str, Any]],
              playlist: Playlist | None = None, target: str | None = None,
              owner: str = "local") -> Job:
        owner_key = str(owner or "local")
        with self._lock:
            self._cleanup()
            active_id = self._active.get(owner_key)
            if active_id:
                active = self._jobs.get(active_id)
                if active and active.status in {"running", "cancelling"}:
                    raise BusyError(self._snapshot_locked(active))
            job = Job(
                id=secrets.token_hex(8),
                type=job_type,
                title=title,
                total=total,
                playlist=playlist,
                target=target,
                owner=owner_key,
            )
            self._jobs[job.id] = job
            self._active[owner_key] = job.id
            thread = threading.Thread(
                target=self._run,
                args=(job, worker),
                name=f"tunebridge-job-{job.id}",
                daemon=True,
            )
            thread.start()
            return job

    def _run(self, job: Job, worker: Callable[[Job], dict[str, Any]]) -> None:
        try:
            result = worker(job)
            with self._lock:
                job.result = result
                if job.cancel_event.is_set():
                    job.status = "cancelled"
                    job.phase = "cancelled"
                    job.message = "Задача остановлена"
                else:
                    job.status = "done"
                    job.phase = "done"
                    job.message = "Готово"
                job.updated_at = time.time()
                job.finished_at = job.updated_at
        except JobCancelled:
            with self._lock:
                job.status = "cancelled"
                job.phase = "cancelled"
                job.message = "Задача остановлена"
                job.updated_at = time.time()
                job.finished_at = job.updated_at
        except ProviderError as exc:
            logger.warning("Job %s failed: %s", job.id, exc.message)
            with self._lock:
                job.status = "error"
                job.error = exc.message
                job.hint = exc.hint
                job.updated_at = time.time()
                job.finished_at = job.updated_at
                job.events.append({"t": time.time(), "text": exc.message, "kind": "error"})
        except Exception as exc:  # noqa: BLE001
            logger.exception("Job %s crashed", job.id)
            with self._lock:
                job.status = "error"
                job.error = "Внутренняя ошибка"
                job.hint = f"Попробуйте ещё раз. Техническая информация: {type(exc).__name__}"
                job.updated_at = time.time()
                job.finished_at = job.updated_at
                job.events.append({"t": time.time(), "text": "Внутренняя ошибка", "kind": "error"})
        finally:
            with self._lock:
                if self._active.get(job.owner) == job.id:
                    self._active.pop(job.owner, None)

    def _snapshot_locked(self, job: Job) -> dict[str, Any]:
        end = job.finished_at or time.time()
        return {
            "id": job.id,
            "type": job.type,
            "status": job.status,
            "phase": job.phase,
            "title": job.title,
            "total": job.total,
            "done": job.done,
            "current": job.current,
            "message": job.message,
            "error": job.error,
            "hint": job.hint,
            "events": list(job.events),
            "created_at": job.created_at,
            "updated_at": job.updated_at,
            "elapsed": max(0.0, end - job.created_at),
            "result": job.result if job.status in {"done", "error", "cancelled"} else None,
            "target": job.target,
        }

    def snapshot(self, job_id: str, owner: str | None = None) -> dict[str, Any] | None:
        with self._lock:
            self._cleanup()
            job = self._jobs.get(job_id)
            if job is None:
                return None
            if owner is not None and job.owner != str(owner):
                return None
            return self._snapshot_locked(job)

    def active(self, owner: str = "local") -> dict[str, Any] | None:
        with self._lock:
            job_id = self._active.get(str(owner or "local"))
            job = self._jobs.get(job_id) if job_id else None
            if job and job.status in {"running", "cancelling"}:
                return self._snapshot_locked(job)
            return None

    def cancel(self, job_id: str, owner: str | None = None) -> dict[str, Any] | None:
        with self._lock:
            job = self._jobs.get(job_id)
            if not job:
                return None
            if owner is not None and job.owner != str(owner):
                return None
            if job.status in {"running"}:
                job.cancel_event.set()
                job.status = "cancelling"
                job.message = "Останавливаем…"
                job.updated_at = time.time()
                job.events.append({"t": time.time(), "text": "Запрошена остановка", "kind": "warn"})
            return self._snapshot_locked(job)

    def set_phase(self, job: Job, phase: str, message: str | None = None) -> None:
        with self._lock:
            job.phase = phase
            if message is not None:
                job.message = message
            job.updated_at = time.time()

    def advance(self, job: Job, count: int = 1, current: str | None = None) -> None:
        with self._lock:
            job.done = min(job.total, job.done + count)
            if current is not None:
                job.current = current
            job.updated_at = time.time()

    def event(self, job: Job, text: str, kind: str = "info") -> None:
        with self._lock:
            job.events.append({"t": time.time(), "text": text, "kind": kind})
            job.updated_at = time.time()

    def set_message(self, job: Job, message: str) -> None:
        with self._lock:
            job.message = message
            job.updated_at = time.time()


manager = JobManager()


def _search_with_retry(provider: TargetProvider, track: Track) -> list[Track]:
    last_error: Exception | None = None
    for attempt in range(3):
        try:
            return provider.search(track)
        except RateLimitError as exc:
            last_error = exc
            time.sleep(2.0 + attempt * 2.5)
        except ProviderError as exc:
            if exc.fatal:
                raise
            last_error = exc
            time.sleep(0.5 + attempt * 1.0)
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            time.sleep(0.5 + attempt * 1.0)
    if isinstance(last_error, ProviderError):
        raise last_error
    raise ProviderError(
        "Не удалось выполнить поиск",
        "Повторите попытку. Если ошибка повторяется, проверьте подключение сервиса.",
    )


def _load_cache() -> dict[str, Any]:
    data = read_json(MATCH_CACHE_PATH, {})
    return data if isinstance(data, dict) else {}


def _save_cache(cache: dict[str, Any], updates: dict[str, Any]) -> None:
    if not updates:
        return
    merged = dict(cache)
    merged.update(updates)
    if len(merged) > _CACHE_LIMIT:
        merged = dict(list(merged.items())[-_CACHE_LIMIT:])
    try:
        write_json(MATCH_CACHE_PATH, merged)
    except OSError:
        logger.warning("Could not save match cache", exc_info=True)


def start_match_job(playlist: Playlist, target_id: str, owner: str = "local") -> Job:
    provider = get_target(target_id)
    if provider.id != "demo" and not provider.is_connected():
        raise NotConnectedError(provider.name)
    if not playlist.tracks:
        raise ProviderError("В плейлисте нет треков", "Загрузите другой плейлист.")

    total = len(playlist.tracks)
    cache = _load_cache()
    cache_updates: dict[str, Any] = {}
    cache_lock = threading.Lock()
    scope_user = int(owner) if config.HOSTED and str(owner).isdigit() else None

    def _run(job: Job) -> dict[str, Any]:
        matches: list[Match | None] = [None] * total
        warnings: list[str] = []
        errors = 0
        successes = 0
        cache_hits = 0
        fatal_error: ProviderError | None = None
        error_lock = threading.Lock()
        abort_event = threading.Event()

        manager.set_phase(job, "searching", f"Ищем совпадения в {provider.name}")
        manager.event(job, f"Начинаем поиск в {provider.name}", "info")

        def work(index: int, track: Track) -> tuple[int, Match | None, str, Exception | None]:
            if job.cancel_event.is_set() or abort_event.is_set():
                return index, None, "skipped", None
            key = match_cache_key(track, provider.id)
            cached = cache.get(key)
            if isinstance(cached, dict) and cached.get("track"):
                try:
                    target_track = Track(**cached["track"])
                    score = float(cached.get("score", 0))
                except Exception:  # noqa: BLE001
                    target_track = None
                    score = 0.0
                if target_track and score >= REVIEW_THRESHOLD:
                    status = "auto" if score >= AUTO_THRESHOLD else "review"
                    match = Match(
                        source=track,
                        target=target_track,
                        score=round(score, 4),
                        status=status,
                        candidates=[Candidate(track=target_track, score=round(score, 4))],
                    )
                    return index, match, "cache", None
            try:
                candidates = _search_with_retry(provider, track)
                match = make_match(track, candidates)
                if match.target is not None:
                    with cache_lock:
                        cache_updates[key] = {
                            "track": match.target.model_dump(),
                            "score": match.score,
                        }
                return index, match, "search", None
            except ProviderError as exc:
                return index, Match(source=track, status="missing"), "error", exc
            except Exception as exc:  # noqa: BLE001
                return index, Match(source=track, status="missing"), "error", exc

        workers = max(1, int(provider.search_workers))
        with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="match") as executor:
            futures = [
                executor.submit(credentials.run_as, scope_user, work, index, track)
                for index, track in enumerate(playlist.tracks)
            ]
            for future in as_completed(futures):
                index, match, kind, exc = future.result()
                if kind == "skipped":
                    continue
                if kind == "error":
                    with error_lock:
                        errors += 1
                        if errors <= 8:
                            text = exc.message if isinstance(exc, ProviderError) else type(exc).__name__
                            warnings.append(f"«{playlist.tracks[index].title}»: {text}")
                        if isinstance(exc, ProviderError) and exc.fatal and fatal_error is None:
                            fatal_error = exc
                            abort_event.set()
                        elif errors >= 3 and successes == 0:
                            abort_event.set()
                else:
                    with error_lock:
                        successes += 1
                    if kind == "cache":
                        cache_hits += 1
                if match is not None:
                    matches[index] = match
                manager.advance(job, 1, playlist.tracks[index].title)
                if job.done % max(1, total // 10) == 0:
                    manager.set_message(job, f"Сопоставлено {job.done} из {total}")
                if job.cancel_event.is_set():
                    for pending in futures:
                        pending.cancel()
                    break

        if fatal_error is not None:
            logger.warning("Fatal search error: %s", fatal_error.message)
            raise fatal_error
        if abort_event.is_set() and successes == 0 and errors:
            raise ProviderError(
                "Не удалось найти совпадения",
                warnings[-1] if warnings else "Проверьте подключение сервиса и повторите.",
            )

        final_matches = [match for match in matches if match is not None]
        if not final_matches:
            if job.cancel_event.is_set():
                return {"matches": [], "stats": stats_for([]).model_dump(), "cancelled": True}
            raise ProviderError(
                "Не удалось сопоставить треки",
                "Попробуйте ещё раз или проверьте подключение сервиса.",
            )
        if errors:
            warnings.append(
                f"Не удалось проверить {errors} из {total} треков. Они отмечены как «не найдены» — их можно найти вручную."
            )
        stats = stats_for(final_matches)
        _save_cache(cache, cache_updates)
        manager.event(
            job,
            f"Готово: {stats.found} из {stats.total} совпадений",
            "success",
        )
        return {
            "target": provider.id,
            "target_name": provider.name,
            "matches": [match.model_dump() for match in final_matches],
            "stats": stats.model_dump(),
            "warnings": warnings,
            "errors": errors,
            "cache_hits": cache_hits,
            "playlist": playlist.model_dump(),
        }

    def worker(job: Job) -> dict[str, Any]:
        with credentials.user_scope(scope_user):
            return _run(job)

    return manager.start(
        "match",
        title=f"Поиск в {provider.name}",
        total=total,
        worker=worker,
        playlist=playlist,
        target=provider.id,
        owner=owner,
    )


def _default_description(playlist: Playlist) -> str:
    source_name = SERVICE_NAMES.get(playlist.service, playlist.service)
    parts = [f"Перенесено из {source_name}"]
    if playlist.url:
        parts.append(playlist.url)
    parts.append("TuneBridge")
    return " • ".join(parts)


def start_transfer_job(playlist: Playlist, target_id: str, matches: list[Match],
                       title: str | None, description: str | None,
                       options: dict[str, Any], owner: str = "local") -> Job:
    provider = get_target(target_id)
    if provider.id != "demo" and not provider.is_connected():
        raise NotConnectedError(provider.name)

    selected: list[Match] = []
    seen: set[str] = set()
    missing = 0
    duplicates = 0
    for match in matches:
        if match.target is None or match.status not in {"auto", "review", "manual"}:
            missing += 1
            continue
        target_key = match.target.id
        if target_key in seen:
            duplicates += 1
            continue
        seen.add(target_key)
        selected.append(match)
    if not selected:
        raise ProviderError(
            "Нет треков для переноса",
            "Вернитесь к сопоставлению и выберите хотя бы один найденный трек.",
        )

    final_title = (title or "").strip() or playlist.title
    title_limit = 100 if provider.id == "spotify" else 150 if provider.id == "youtube" else 200
    final_title = final_title[:title_limit]
    final_description = (description or "").strip() or _default_description(playlist)
    total = len(selected)

    billable = config.HOSTED and not config.FREE_MODE and provider.id != "demo" and str(owner).isdigit()
    billing_user_id = int(owner) if billable else None
    scope_user = int(owner) if config.HOSTED and str(owner).isdigit() else None
    reservation = f"transfer:{secrets.token_hex(8)}"
    if billable:
        billing.charge_transfer(billing_user_id, total, reservation, provider.name)

    def _run(job: Job) -> dict[str, Any]:
        added = 0
        try:
            manager.set_phase(job, "creating", f"Создаём плейлист в {provider.name}")
            manager.event(job, f"Создаём плейлист «{final_title}»", "info")
            created = provider.create_playlist(final_title, final_description, options)
            playlist_id = str(created.get("id") or "")
            if not playlist_id:
                raise ProviderError("Сервис не вернул идентификатор плейлиста", "Попробуйте ещё раз.")
            target_url = created.get("url")
            manager.set_phase(job, "adding", f"Добавляем треки в {provider.name}")
            manager.event(job, "Плейлист создан, добавляем треки", "success")

            failed: list[Track] = []
            fatal_error: ProviderError | None = None

            def add_slice(batch: list[Track], depth: int = 0) -> None:
                nonlocal added, fatal_error
                if not batch or job.cancel_event.is_set():
                    return
                last_error: Exception | None = None
                for attempt in range(3):
                    try:
                        provider.add_batch(playlist_id, batch)
                        added += len(batch)
                        manager.advance(job, len(batch), batch[-1].title)
                        manager.set_message(job, f"Добавлено {added} из {total}")
                        return
                    except ProviderError as exc:
                        last_error = exc
                        if exc.fatal:
                            fatal_error = exc
                            return
                        time.sleep(min(5.0, 0.8 + attempt * 1.8))
                    except Exception as exc:  # noqa: BLE001
                        last_error = exc
                        time.sleep(min(5.0, 0.8 + attempt * 1.8))
                if len(batch) > 2 and depth < 3:
                    middle = len(batch) // 2
                    add_slice(batch[:middle], depth + 1)
                    add_slice(batch[middle:], depth + 1)
                    return
                failed.extend(batch)
                manager.advance(job, len(batch), batch[-1].title)
                label = batch[0].title if len(batch) == 1 else f"{len(batch)} треков"
                detail = last_error.message if isinstance(last_error, ProviderError) else "ошибка сервиса"
                manager.event(job, f"Не удалось добавить {label}: {detail}", "error")

            tracks = [match.target for match in selected if match.target is not None]
            batch_size = max(1, int(provider.batch_size))
            for index in range(0, len(tracks), batch_size):
                if job.cancel_event.is_set():
                    break
                if fatal_error is not None:
                    break
                add_slice(tracks[index : index + batch_size])
                if index + batch_size < len(tracks) and not job.cancel_event.is_set():
                    if provider.id == "youtube":
                        time.sleep(0.3)
                    elif provider.id == "spotify":
                        time.sleep(0.12)
                    else:
                        time.sleep(0.15)

            result = {
                "target": provider.id,
                "target_name": provider.name,
                "playlist_id": playlist_id,
                "url": target_url,
                "title": final_title,
                "added": added,
                "failed": len(failed),
                "skipped": missing + duplicates,
                "duplicates": duplicates,
                "missing": missing,
                "failed_tracks": [
                    {"title": track.title, "artists": track.artists} for track in failed[:80]
                ],
                "demo": bool(created.get("demo")),
                "source_service": playlist.service,
                "source_title": playlist.title,
                "source_url": playlist.url,
                "billing": (
                    {
                        "cost": total * config.TOKENS_PER_TRACK,
                        "charged": added * config.TOKENS_PER_TRACK,
                        "refunded": max(0, total - added) * config.TOKENS_PER_TRACK,
                    }
                    if billable
                    else None
                ),
            }
            accounts.record_transfer(owner, result)
            if fatal_error is not None:
                job.result = result
                raise fatal_error
            if job.cancel_event.is_set():
                manager.event(job, f"Остановлено. Добавлено {added} из {total}", "warn")
                return result
            if failed:
                manager.event(job, f"Готово с ошибками: добавлено {added} из {total}", "warn")
            else:
                manager.event(job, f"Все {added} треков добавлены", "success")
            return result
        finally:
            if billable:
                unused = max(0, total - added)
                try:
                    billing.refund_unused(billing_user_id, unused, reservation)
                except Exception:  # noqa: BLE001
                    logger.exception("Could not refund unused transfer tokens")
            db.close_current()

    def worker(job: Job) -> dict[str, Any]:
        with credentials.user_scope(scope_user):
            return _run(job)

    try:
        return manager.start(
            "transfer",
            title=f"Перенос в {provider.name}",
            total=total,
            worker=worker,
            playlist=playlist,
            target=provider.id,
            owner=owner,
        )
    except BusyError:
        if billable:
            billing.refund_unused(billing_user_id, total, reservation)
        raise
