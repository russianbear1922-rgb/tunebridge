from __future__ import annotations

import contextlib
import hmac
import logging
import threading
from urllib.parse import quote

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from . import accounts, ads, billing, credentials, db, legal, stats, telegram
from .config import (
    AD,
    APP_NAME,
    BASE_URL,
    BOT_POLLING,
    FREE_MODE,
    HOSTED,
    HOST,
    LAN_ENABLED,
    MAX_BODY_BYTES,
    MAX_TRACKS,
    PORT,
    RATE_AUTH,
    RATE_GLOBAL,
    RATE_HEAVY,
    RATE_LIMIT_ENABLED,
    SECRET_KEY_FROM_ENV,
    SESSION_COOKIE,
    SPOTIFY_REDIRECT_URI,
    STATIC_DIR,
    TRIAL_TOKENS,
    TWA_PACKAGE,
    TWA_SHA256,
    VERSION,
    WEBHOOK_SECRET,
)
from .network import is_local_client, lan_address
from .jobs import BusyError, manager, start_match_job, start_transfer_job
from .matching import score_candidates
from .models import (
    AdminCreditRequest,
    AdminPromoRequest,
    AdminRefundRequest,
    AdEventRequest,
    Candidate,
    ExportRequest,
    ImportRequest,
    MatchRequest,
    Playlist,
    PromoRedeemRequest,
    ResolveRequest,
    SearchRequest,
    SpotifyClientRequest,
    TelegramAuthRequest,
    TelegramSendRequest,
    TelegramTokenRequest,
    TokenRequest,
    TopupRequest,
    TransferRequest,
    YoutubeBrowserRequest,
    YoutubeHeadersRequest,
)
from .providers import apple, demo, files, soundcloud, spotify, yandex, youtube
from .providers.base import ProviderError
from .providers.registry import get_source, get_target
from .ratelimit import RateLimiter

logger = logging.getLogger("tunebridge")

_PUBLIC_API = {
    "/api/health",
    "/api/session",
    "/api/auth/telegram",
    "/api/auth/logout",
    "/api/billing/telegram/webhook",
    "/api/phone/qr.svg",
    "/api/ads/event",
}
_CSRF_EXEMPT = {"/api/auth/telegram", "/api/billing/telegram/webhook", "/api/ads/event"}


def _poll_updates(stop: threading.Event) -> None:
    offset = int(db.kv_get("telegram_offset", "0") or 0)
    logger.info("Telegram long polling started")
    while not stop.is_set():
        try:
            updates = telegram.get_updates(offset, 25)
        except ProviderError as exc:
            logger.warning("Telegram polling failed: %s", exc.message)
            stop.wait(5)
            continue
        except Exception:  # noqa: BLE001
            logger.exception("Telegram polling crashed")
            stop.wait(5)
            continue
        for update in updates:
            try:
                update_id = int(update.get("update_id") or 0)
            except (TypeError, ValueError):
                update_id = 0
            if update_id:
                offset = max(offset, update_id + 1)
            try:
                billing.handle_update(update)
            except Exception:  # noqa: BLE001
                logger.exception("Telegram update failed")
        if updates:
            try:
                db.kv_set("telegram_offset", str(offset))
            except Exception:  # noqa: BLE001
                logger.warning("Could not persist Telegram offset", exc_info=True)


@contextlib.asynccontextmanager
async def lifespan(_: FastAPI):
    db.init()
    if HOSTED and not SECRET_KEY_FROM_ENV:
        logger.warning(
            "TUNEBRIDGE_SECRET_KEY is not set: user credentials are encrypted with a key "
            "derived from the bot token. Set a dedicated key before rotating the token."
        )
    stop = threading.Event()
    poller: threading.Thread | None = None
    if BOT_POLLING and telegram.bot_token():
        poller = threading.Thread(target=_poll_updates, args=(stop,), name="telegram-poll", daemon=True)
        poller.start()
    try:
        yield
    finally:
        stop.set()


app = FastAPI(
    title=APP_NAME,
    version=VERSION,
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
    lifespan=lifespan,
)


def _context(request: Request) -> dict:
    return accounts.context_for_request(request)


def _session_payload(context: dict) -> dict:
    return {
        "ok": True,
        "mode": context["mode"],
        "hosted": HOSTED,
        "authenticated": True,
        "user": context["user"],
        "csrf": context["csrf"],
        "bot": {"username": telegram.bot_username()},
        "packages": billing.packages(),
        "trial_tokens": TRIAL_TOKENS,
        "free_mode": FREE_MODE,
    }


@app.middleware("http")
async def disable_static_cache(request: Request, call_next):
    response = await call_next(request)
    path = request.url.path
    if path == "/" or path.startswith("/static/") or path.endswith(".webmanifest"):
        response.headers["Cache-Control"] = "no-store"
    return response


@app.middleware("http")
async def guard_api(request: Request, call_next):
    path = request.url.path
    if not (HOSTED and path.startswith("/api/")) or path in _PUBLIC_API:
        return await call_next(request)

    raw = request.cookies.get(SESSION_COOKIE)
    session = accounts.session_from_cookie(raw)
    if session is None:
        return JSONResponse(
            status_code=401,
            content={
                "message": "Нужен вход через Telegram",
                "hint": "Откройте TuneBridge как Mini App в Telegram и обновите страницу.",
                "auth": "required",
            },
        )
    if (
        request.method in {"POST", "PUT", "PATCH", "DELETE"}
        and path not in _CSRF_EXEMPT
        and request.headers.get("x-tb-csrf") != session["csrf"]
    ):
        return JSONResponse(
            status_code=403,
            content={
                "message": "Проверка безопасности не пройдена",
                "hint": "Обновите страницу и повторите действие.",
            },
        )
    token = credentials.activate(int(session["user_row"]["id"]))
    try:
        return await call_next(request)
    finally:
        credentials.reset(token)


def _service_state(service_id: str) -> dict:
    if service_id == "yandex":
        provider = yandex.get_provider()
        return {
            "id": "yandex",
            "name": provider.name,
            "connected": provider.is_connected(),
            "profile": provider.profile(),
            "auth": "device",
            "public_source": True,
        }
    if service_id == "spotify":
        provider = spotify.get_provider()
        client_id = provider.client_id()
        masked = f"{client_id[:4]}…{client_id[-4:]}" if client_id and len(client_id) > 10 else None
        return {
            "id": "spotify",
            "name": provider.name,
            "connected": provider.is_connected(),
            "profile": provider.profile(),
            "auth": "oauth",
            "public_source": True,
            "client_id_set": bool(client_id),
            "client_id_masked": masked,
            "redirect_uri": SPOTIFY_REDIRECT_URI,
        }
    if service_id == "youtube":
        provider = youtube.get_provider()
        return {
            "id": "youtube",
            "name": provider.name,
            "connected": provider.is_connected(),
            "profile": provider.profile(),
            "auth": "headers",
            "public_source": True,
        }
    if service_id == "soundcloud":
        provider = soundcloud.get_provider()
        return {
            "id": "soundcloud",
            "name": provider.name,
            "connected": False,
            "profile": None,
            "auth": "public",
            "public_source": True,
        }
    if service_id == "apple":
        provider = apple.get_provider()
        return {
            "id": "apple",
            "name": provider.name,
            "connected": False,
            "profile": None,
            "auth": "public",
            "public_source": True,
        }
    return {"id": service_id, "name": service_id, "connected": False, "profile": None}


def _phone_state() -> dict:
    if not LAN_ENABLED:
        return {"enabled": False, "url": None}
    host = lan_address() or (HOST if HOST not in {"0.0.0.0", "::"} else None)
    if not host:
        return {"enabled": True, "url": None}
    return {"enabled": True, "url": f"http://{host}:{PORT}"}


@app.get("/api/health")
def health() -> dict:
    return {
        "ok": True,
        "name": APP_NAME,
        "version": VERSION,
        "mode": "hosted" if HOSTED else "local",
        "free": FREE_MODE,
    }


@app.get("/api/phone/qr.svg")
def phone_qr() -> Response:
    phone = _phone_state()
    if not phone.get("url"):
        raise HTTPException(
            404,
            detail={
                "message": "Адрес для телефона недоступен",
                "hint": "Запустите TuneBridge через start-lan.bat (Windows) или start-lan.sh — приложение откроется для устройств в этой Wi-Fi сети.",
            },
        )
    try:
        import qrcode.image.svg

        image = qrcode.make(phone["url"], image_factory=qrcode.image.svg.SvgPathImage, box_size=12, border=2)
        svg = image.to_string().decode("utf-8")
    except ImportError as exc:
        raise HTTPException(
            503,
            detail={"message": "Нет модуля qrcode", "hint": "Запустите start.bat — он доустановит зависимости."},
        ) from exc
    return Response(
        content=svg,
        media_type="image/svg+xml",
        headers={"Cache-Control": "no-store"},
    )


@app.get("/api/state")
def state(context: dict = Depends(_context)) -> dict:
    services = {
        service_id: _service_state(service_id)
        for service_id in ("yandex", "spotify", "youtube", "soundcloud", "apple")
    }
    return {
        "app": {"name": APP_NAME, "version": VERSION, "port": PORT},
        "account": {
            **context["user"],
            "mode": context["mode"],
            "hosted": HOSTED,
            "bot": {"username": telegram.bot_username()},
        },
        "services": services,
        "targets": [
            {
                "id": "spotify",
                "name": "Spotify",
                "connected": services["spotify"]["connected"],
                "requires_auth": True,
            },
            {
                "id": "youtube",
                "name": "YouTube Music",
                "connected": services["youtube"]["connected"],
                "requires_auth": True,
            },
            {"id": "file", "name": "Файлы", "connected": True, "requires_auth": False},
            {"id": "demo", "name": "Демо-плеер", "connected": True, "requires_auth": False, "demo": True},
        ],
        "active_job": manager.active(context["owner"]),
        "telegram": {
            "connected": telegram.is_connected(),
            "profile": telegram.profile(),
            "chat": telegram.saved_chat(),
        },
        "phone": _phone_state(),
        "limits": {"max_tracks": MAX_TRACKS},
        "free_mode": FREE_MODE,
        "ads": ads.current(),
    }


@app.get("/api/session")
def session_info(request: Request) -> dict:
    context = accounts.peek(request)
    if context is None:
        return {
            "ok": True,
            "mode": "hosted",
            "hosted": True,
            "authenticated": False,
            "user": None,
            "csrf": None,
            "bot": {"username": telegram.bot_username()},
            "packages": billing.packages(),
            "trial_tokens": TRIAL_TOKENS,
            "free_mode": FREE_MODE,
        }
    return _session_payload(context)


@app.post("/api/auth/telegram")
def auth_telegram(payload: TelegramAuthRequest, request: Request, response: Response) -> dict:
    context, raw = accounts.login_with_init_data(request, payload.init_data)
    accounts.set_cookie(response, raw)
    return _session_payload(context)


@app.post("/api/auth/logout")
def auth_logout(request: Request, response: Response) -> dict:
    accounts.logout(request)
    accounts.clear_cookie(response)
    return {"ok": True}


@app.get("/api/wallet")
def wallet(context: dict = Depends(_context)) -> dict:
    return billing.wallet_snapshot(int(context["row"]["id"]))


@app.post("/api/wallet/topup")
def wallet_topup(payload: TopupRequest, context: dict = Depends(_context)) -> dict:
    if FREE_MODE:
        raise HTTPException(
            403,
            detail={
                "message": "Пополнение отключено",
                "hint": "Сервис работает бесплатно: переносы не списывают токены.",
            },
        )
    return billing.create_topup(context["user"], payload.package_id, context["row"]["lang"])


@app.post("/api/promo/redeem")
def promo_redeem(payload: PromoRedeemRequest, context: dict = Depends(_context)) -> dict:
    if FREE_MODE:
        raise HTTPException(
            403,
            detail={
                "message": "Промокоды отключены",
                "hint": "Сервис бесплатный, поэтому промокоды больше не нужны.",
            },
        )
    return billing.redeem_promo(int(context["row"]["id"]), payload.code)


@app.post("/api/ads/event")
def ads_event(payload: AdEventRequest) -> dict:
    return {"ok": ads.record(payload.kind)}


@app.get("/api/history")
def transfer_history(context: dict = Depends(_context)) -> dict:
    return {"transfers": accounts.transfers_for(int(context["row"]["id"]), 50)}


@app.post("/api/billing/telegram/webhook")
async def telegram_webhook(request: Request) -> dict:
    if not HOSTED:
        raise HTTPException(404, detail={"message": "Оплата не настроена"})
    if not WEBHOOK_SECRET:
        logger.error("Telegram webhook called without TUNEBRIDGE_WEBHOOK_SECRET")
        raise HTTPException(503, detail={"message": "Вебхук Telegram не настроен", "hint": "Задайте секрет вебхука."})
    header = request.headers.get("x-telegram-bot-api-secret-token", "")
    if not hmac.compare_digest(header, WEBHOOK_SECRET):
        raise HTTPException(403, detail={"message": "Неверный секрет вебхука"})
    try:
        update = await request.json()
    except ValueError as exc:
        raise HTTPException(400, detail={"message": "Некорректный запрос Telegram"}) from exc
    if not isinstance(update, dict):
        raise HTTPException(400, detail={"message": "Некорректный запрос Telegram"})
    result = billing.handle_update(update)
    return {"ok": True, "result": result}


@app.get("/api/admin/overview")
def admin_overview(context: dict = Depends(_context)) -> dict:
    accounts.require_admin(context)
    return billing.admin_overview()


@app.get("/api/admin/stats")
def admin_stats(context: dict = Depends(_context)) -> dict:
    accounts.require_admin(context)
    return stats.overview()


@app.post("/api/admin/credit")
def admin_credit(payload: AdminCreditRequest, context: dict = Depends(_context)) -> dict:
    accounts.require_admin(context)
    target = accounts.find_user(user_id=payload.user_id, telegram_id=payload.telegram_id)
    if target is None:
        raise HTTPException(404, detail={"message": "Пользователь не найден", "hint": "Проверьте Telegram ID или ID в базе."})
    if payload.tokens == 0 or abs(payload.tokens) > 1_000_000:
        raise HTTPException(400, detail={"message": "Некорректная сумма", "hint": "Укажите от 1 до 1 000 000 токенов."})
    try:
        credited = accounts.credit(
            int(target["id"]),
            int(payload.tokens),
            "admin",
            (payload.reason or "Начисление администратором")[:200],
            ref=None,
        )
    except ValueError as exc:
        raise HTTPException(
            400,
            detail={"message": "Не получилось изменить баланс", "hint": "На счету недостаточно токенов для списания."},
        ) from exc
    fresh = accounts.find_user(user_id=int(target["id"]))
    return {"ok": True, "balance": credited["balance"], "user": accounts.user_payload(fresh)}


@app.get("/api/admin/promos")
def admin_promos(context: dict = Depends(_context)) -> dict:
    accounts.require_admin(context)
    return {"promos": billing.list_promos()}


@app.post("/api/admin/promos")
def admin_promos_create(payload: AdminPromoRequest, context: dict = Depends(_context)) -> dict:
    accounts.require_admin(context)
    codes = billing.create_promo_codes(
        int(context["row"]["id"]),
        count=payload.count,
        tokens=payload.tokens,
        max_uses=payload.max_uses,
        days=payload.days,
        note=payload.note,
    )
    return {"ok": True, "codes": codes}


@app.post("/api/admin/promos/{code}/enable")
def admin_promo_enable(code: str, context: dict = Depends(_context)) -> dict:
    accounts.require_admin(context)
    return billing.toggle_promo(code, True)


@app.post("/api/admin/promos/{code}/disable")
def admin_promo_disable(code: str, context: dict = Depends(_context)) -> dict:
    accounts.require_admin(context)
    return billing.toggle_promo(code, False)


@app.post("/api/admin/refund")
def admin_refund(payload: AdminRefundRequest, context: dict = Depends(_context)) -> dict:
    accounts.require_admin(context)
    return billing.refund_order(payload.order_id, revoke=payload.revoke)


@app.post("/api/resolve")
def resolve(payload: ResolveRequest) -> dict:
    service = (payload.service or "").strip()
    if service == "demo":
        return {"playlist": demo.build_demo_playlist().model_dump()}
    if service == "file":
        raise HTTPException(400, detail={"message": "Для файла используйте импорт", "hint": "Загрузите M3U, CSV или JSON."})
    provider = get_source(service)
    playlist = provider.resolve_url(payload.url)
    if not playlist.tracks and playlist.track_count:
        playlist.warnings.append("Не удалось получить треки плейлиста.")
    return {"playlist": playlist.model_dump()}


@app.get("/api/playlists/{service}")
def list_playlists(service: str) -> dict:
    provider = get_source(service)
    if not provider.is_connected():
        raise HTTPException(401, detail={"message": f"{provider.name}: аккаунт не подключён", "hint": "Подключите аккаунт и повторите."})
    playlists = provider.list_playlists()
    return {"playlists": [playlist.model_dump() for playlist in playlists]}


@app.get("/api/demo")
def demo_playlist() -> dict:
    return {"playlist": demo.build_demo_playlist().model_dump()}


@app.post("/api/import")
def import_file(payload: ImportRequest) -> dict:
    playlist = files.parse_import(payload.filename, payload.content)
    return {"playlist": playlist.model_dump()}


@app.post("/api/export")
def export(payload: ExportRequest) -> Response:
    if not payload.playlist.tracks:
        raise HTTPException(400, detail={"message": "В плейлисте нет треков", "hint": "Загрузите плейлист заново."})
    data = files.build_export_zip(payload.playlist, payload.formats)
    return Response(
        content=data,
        media_type="application/zip",
        headers={
            "Content-Disposition": 'attachment; filename="tunebridge-export.zip"',
            "Cache-Control": "no-store",
        },
    )


@app.post("/api/targets/{target}/search")
def search_target(target: str, payload: SearchRequest) -> dict:
    provider = get_target(target)
    if provider.id != "demo" and not provider.is_connected():
        raise HTTPException(401, detail={"message": f"{provider.name}: аккаунт не подключён", "hint": "Подключите аккаунт и повторите."})
    candidates = provider.search_query(payload.query)
    if payload.source is not None:
        scored = score_candidates(payload.source, candidates, limit=10)
    else:
        scored = [Candidate(track=item, score=1.0) for item in candidates[:10]]
    return {"candidates": [candidate.model_dump() for candidate in scored]}


@app.post("/api/connect/yandex/device")
def yandex_device_start() -> dict:
    return yandex.start_device_flow()


@app.post("/api/connect/yandex/poll")
def yandex_device_poll() -> dict:
    return yandex.poll_device_flow()


@app.post("/api/connect/yandex/token")
def yandex_token(payload: TokenRequest) -> dict:
    profile = yandex.connect_with_token(payload.token)
    return {"ok": True, "profile": profile}


@app.post("/api/connect/spotify/client")
def spotify_client_id(payload: SpotifyClientRequest) -> dict:
    value = spotify.set_client_id(payload.client_id)
    return {
        "ok": True,
        "client_id_masked": f"{value[:4]}…{value[-4:]}" if len(value) > 10 else value,
        "redirect_uri": SPOTIFY_REDIRECT_URI,
    }


@app.get("/api/auth/spotify/start")
def spotify_oauth_start() -> RedirectResponse:
    try:
        url = spotify.start_oauth()
    except ProviderError as exc:
        return RedirectResponse(f"/?spotify_error={quote(exc.message)}", status_code=303)
    return RedirectResponse(url, status_code=303)


@app.get("/api/auth/spotify/callback")
def spotify_oauth_callback(request: Request) -> RedirectResponse:
    error = request.query_params.get("error")
    if error:
        message = "Доступ к Spotify отменён" if error == "access_denied" else f"Spotify вернул ошибку: {error}"
        return RedirectResponse(f"/?spotify_error={quote(message)}", status_code=303)
    code = request.query_params.get("code")
    state_value = request.query_params.get("state")
    if not code or not state_value:
        return RedirectResponse(f"/?spotify_error={quote('Spotify не вернул код авторизации')}", status_code=303)
    try:
        spotify.finish_oauth(state_value, code)
    except ProviderError as exc:
        return RedirectResponse(f"/?spotify_error={quote(exc.message)}", status_code=303)
    return RedirectResponse("/?connected=spotify", status_code=303)


@app.post("/api/connect/youtube")
def youtube_connect(payload: YoutubeHeadersRequest) -> dict:
    if len(payload.headers) > 300_000:
        raise HTTPException(400, detail={"message": "Слишком большой блок заголовков", "hint": "Скопируйте заголовки одного запроса browse."})
    try:
        profile = youtube.connect_with_headers(payload.headers, authuser=payload.authuser)
    except youtube.AccountChoiceRequired as exc:
        return {"ok": False, "needs_choice": True, "accounts": exc.accounts}
    return {"ok": True, "profile": profile}


@app.post("/api/connect/youtube/browser")
def youtube_connect_browser(request: Request, payload: YoutubeBrowserRequest | None = None) -> dict:
    if HOSTED:
        raise HTTPException(
            403,
            detail={
                "message": "Импорт из браузера выключен в облачном режиме",
                "hint": "Он ищет вход в браузерах сервера. Вставьте cookie вручную — тогда подключится ваш аккаунт.",
            },
        )
    client = request.client.host if request.client else None
    if not is_local_client(client):
        raise HTTPException(
            403,
            detail={
                "message": "Импорт из браузера доступен только на компьютере с TuneBridge",
                "hint": "На телефоне или другом устройстве вставьте cookie вручную: эта кнопка ищет вход в браузерах компьютера, где запущено приложение.",
            },
        )
    try:
        profile = youtube.connect_from_browser(
            payload.label if payload else None,
            payload.authuser if payload else None,
        )
    except youtube.AccountChoiceRequired as exc:
        return {"ok": False, "needs_choice": True, "accounts": exc.accounts}
    return {"ok": True, "profile": profile}


@app.post("/api/connect/telegram")
def telegram_connect(payload: TelegramTokenRequest) -> dict:
    profile = telegram.connect(payload.token)
    return {"ok": True, "profile": profile}


@app.get("/api/telegram/chats")
def telegram_chats() -> dict:
    return {"chats": telegram.discover_chats()}


@app.post("/api/telegram/send")
def telegram_send(payload: TelegramSendRequest) -> dict:
    if len(payload.playlist.tracks) > MAX_TRACKS:
        raise HTTPException(400, detail={"message": "Слишком большой плейлист", "hint": "Отправьте архив из «Скачать плейлист»."})
    return telegram.send_playlist(payload.playlist, payload.chat, payload.formats)


@app.delete("/api/connect/{service}")
def disconnect(service: str) -> dict:
    if service == "yandex":
        yandex.disconnect()
    elif service == "spotify":
        spotify.disconnect()
    elif service == "youtube":
        youtube.disconnect()
    elif service == "telegram":
        telegram.disconnect()
    else:
        raise HTTPException(404, detail={"message": "Неизвестный сервис"})
    return {"ok": True}


@app.post("/api/jobs/match")
def start_match(payload: MatchRequest, context: dict = Depends(_context)) -> dict:
    job = start_match_job(payload.playlist, payload.target, owner=context["owner"])
    return manager.snapshot(job.id, context["owner"]) or {}


@app.post("/api/jobs/transfer")
def start_transfer(payload: TransferRequest, context: dict = Depends(_context)) -> dict:
    job = start_transfer_job(
        payload.playlist,
        payload.target,
        payload.matches,
        payload.title,
        payload.description,
        payload.options,
        owner=context["owner"],
    )
    return manager.snapshot(job.id, context["owner"]) or {}


@app.get("/api/jobs/active")
def active_job(context: dict = Depends(_context)) -> dict:
    return {"job": manager.active(context["owner"])}


@app.get("/api/jobs/{job_id}")
def job_status(job_id: str, context: dict = Depends(_context)) -> dict:
    snapshot = manager.snapshot(job_id, context["owner"])
    if not snapshot:
        raise HTTPException(404, detail={"message": "Задача не найдена", "hint": "Возможно, она устарела. Запустите перенос заново."})
    return snapshot


@app.post("/api/jobs/{job_id}/cancel")
def cancel_job(job_id: str, context: dict = Depends(_context)) -> dict:
    snapshot = manager.cancel(job_id, context["owner"])
    if not snapshot:
        raise HTTPException(404, detail={"message": "Задача не найдена"})
    return snapshot


@app.exception_handler(ProviderError)
async def provider_error_handler(request: Request, exc: ProviderError) -> JSONResponse:
    status = 401 if getattr(exc, "fatal", False) else 400
    return JSONResponse(status_code=status, content={"message": exc.message, "hint": exc.hint})


@app.exception_handler(BusyError)
async def busy_error_handler(request: Request, exc: BusyError) -> JSONResponse:
    return JSONResponse(
        status_code=409,
        content={
            "message": "Сейчас выполняется другая задача",
            "hint": "Дождитесь её завершения или остановите.",
            "active_job": exc.active,
        },
    )


@app.exception_handler(accounts.AuthRequired)
async def auth_required_handler(request: Request, exc: accounts.AuthRequired) -> JSONResponse:
    return JSONResponse(
        status_code=401,
        content={"message": exc.message, "hint": exc.hint, "auth": "required"},
    )


@app.exception_handler(accounts.AdminRequired)
async def admin_required_handler(request: Request, exc: accounts.AdminRequired) -> JSONResponse:
    return JSONResponse(status_code=403, content={"message": exc.message, "hint": exc.hint})


@app.exception_handler(billing.BillingError)
async def billing_error_handler(request: Request, exc: billing.BillingError) -> JSONResponse:
    content: dict[str, object] = {"message": exc.message, "hint": exc.hint}
    if isinstance(exc, billing.InsufficientBalance):
        content.update({"code": "insufficient_balance", "needed": exc.needed, "balance": exc.balance})
    return JSONResponse(status_code=exc.status, content=content)


@app.exception_handler(HTTPException)
@app.exception_handler(StarletteHTTPException)
async def http_error_handler(request: Request, exc: HTTPException) -> Response:
    detail = exc.detail
    if isinstance(detail, dict):
        content = detail
    else:
        content = {"message": str(detail)}
    if exc.status_code == 404 and not request.url.path.startswith("/api/"):
        return _error_page(
            404,
            "Страница не найдена",
            "Возможно, ссылка устарела. Вернитесь на главную и продолжите перенос.",
        )
    return JSONResponse(status_code=exc.status_code, content=content)


@app.exception_handler(Exception)
async def unhandled_error_handler(request: Request, exc: Exception) -> Response:
    logger.exception("Unhandled error on %s", request.url.path)
    if request.url.path.startswith("/api/"):
        return JSONResponse(
            status_code=500,
            content={
                "message": "Внутренняя ошибка сервера",
                "hint": "Попробуйте ещё раз через минуту. Если повторяется — напишите в поддержку.",
            },
        )
    return _error_page(
        500,
        "Что-то сломалось",
        "Ошибка уже записана. Обновите страницу или вернитесь на главную.",
    )


@app.exception_handler(RequestValidationError)
async def validation_error_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    details = [(error.get("loc"), error.get("type")) for error in exc.errors()[:3]]
    logger.info("Validation error on %s: %s", request.url.path, details)
    return JSONResponse(
        status_code=422,
        content={
            "message": "Некорректные данные запроса",
            "hint": "Обновите страницу и попробуйте снова.",
        },
    )


def _error_page(status: int, title: str, hint: str) -> HTMLResponse:
    return HTMLResponse(
        f"""<!doctype html>
<html lang="ru">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="color-scheme" content="dark">
<meta name="theme-color" content="#08090f">
<meta name="robots" content="noindex">
<title>{status} — TuneBridge</title>
<link rel="icon" href="/static/img/favicon.svg" type="image/svg+xml">
<link rel="stylesheet" href="/static/css/legal.css">
</head>
<body>
<main class="legal">
  <header class="legal-head">
    <a class="legal-brand" href="/"><img src="/static/img/logo.svg" alt=""><span>TuneBridge</span></a>
  </header>
  <h1>{status} · {title}</h1>
  <p class="legal-lead">{hint}</p>
  <p class="legal-lead dim">Page not found or a server error occurred. Go back to the home page and try again.</p>
  <p><a class="legal-contact" href="/">Вернуться на главную / Back to home</a></p>
</main>
</body>
</html>
""",
        status_code=status,
        headers={"Cache-Control": "no-store"},
    )


_HEAVY_PREFIXES = (
    "/api/resolve",
    "/api/jobs/match",
    "/api/jobs/transfer",
    "/api/targets/",
    "/api/import",
    "/api/export",
    "/api/connect/",
    "/api/telegram/send",
)
_limiter_global = RateLimiter(RATE_GLOBAL, 60)
_limiter_heavy = RateLimiter(RATE_HEAVY, 60)
_limiter_auth = RateLimiter(RATE_AUTH, 60)


@app.middleware("http")
async def public_guard(request: Request, call_next):
    if not RATE_LIMIT_ENABLED:
        return await call_next(request)
    length = request.headers.get("content-length")
    if length and length.isdigit() and int(length) > MAX_BODY_BYTES:
        return JSONResponse(
            status_code=413,
            content={
                "message": "Слишком большой запрос",
                "hint": "Уменьшите файл или разделите плейлист на части.",
            },
        )
    path = request.url.path
    if path.startswith("/api/"):
        ip = request.client.host if request.client else "unknown"
        if path == "/api/auth/telegram":
            allowed, retry = _limiter_auth.check(ip)
        elif path.startswith(_HEAVY_PREFIXES):
            allowed, retry = _limiter_heavy.check(f"{ip}:heavy")
        else:
            allowed, retry = _limiter_global.check(ip)
        if not allowed:
            return JSONResponse(
                status_code=429,
                content={
                    "message": "Слишком много запросов",
                    "hint": "Подождите немного и повторите действие.",
                },
                headers={"Retry-After": str(int(retry) + 1)},
            )
    return await call_next(request)


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("Referrer-Policy", "no-referrer")
    if not HOSTED:
        response.headers.setdefault("X-Frame-Options", "DENY")
    if request.url.path.startswith("/api/"):
        response.headers["Cache-Control"] = "no-store"
    if not request.url.path.startswith("/static/"):
        frame_ancestors = (
            "frame-ancestors 'self' https://web.telegram.org https://*.telegram.org"
            if HOSTED
            else "frame-ancestors 'none'"
        )
        script_src = "'self' https://telegram.org" if HOSTED else "'self'"
        response.headers.setdefault(
            "Content-Security-Policy",
            "default-src 'self'; img-src 'self' data: https:; "
            f"style-src 'self' 'unsafe-inline'; script-src {script_src}; "
            "connect-src 'self'; font-src 'self'; base-uri 'none'; "
            f"form-action 'self'; {frame_ancestors}",
        )
    return response


@app.get("/")
def index() -> HTMLResponse:
    html = (STATIC_DIR / "index.html").read_text(encoding="utf-8")
    marker = "<!-- TELEGRAM_WEB_APP -->"
    if HOSTED:
        html = html.replace(
            marker,
            '<script src="https://telegram.org/js/telegram-web-app.js"></script>',
        )
    else:
        html = html.replace(marker, "")
    base = BASE_URL.rstrip("/")
    html = html.replace('content="/static/img/og-image.png"', f'content="{base}/static/img/og-image.png"')
    html = html.replace('<link rel="canonical" href="/">', f'<link rel="canonical" href="{base}/">')
    html = html.replace('<meta property="og:url" content="/">', f'<meta property="og:url" content="{base}/">')
    return HTMLResponse(
        html,
        headers={
            "Cache-Control": "no-store",
            "Content-Security-Policy": (
                "default-src 'self'; img-src 'self' data: https:; style-src 'self' 'unsafe-inline'; "
                "script-src 'self'"
                + (" https://telegram.org" if HOSTED else "")
                + "; connect-src 'self'; font-src 'self'; base-uri 'none'; form-action 'self'; "
                "frame-ancestors "
                + ("'self' https://web.telegram.org https://*.telegram.org" if HOSTED else "'none'")
            ),
        },
    )


@app.get("/robots.txt")
def robots() -> Response:
    base = BASE_URL.rstrip("/")
    body = f"User-agent: *\nAllow: /\nDisallow: /api/\nDisallow: /data/\n\nSitemap: {base}/sitemap.xml\n"
    return Response(body, media_type="text/plain", headers={"Cache-Control": "public, max-age=3600"})


@app.get("/sitemap.xml")
def sitemap() -> Response:
    base = BASE_URL.rstrip("/")
    items = "".join(
        f"<url><loc>{base}{path}</loc><changefreq>weekly</changefreq></url>"
        for path in ("/", "/privacy", "/terms")
    )
    body = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
        f"{items}</urlset>"
    )
    return Response(body, media_type="application/xml", headers={"Cache-Control": "public, max-age=3600"})


def _page_lang(request: Request) -> str:
    query = (request.query_params.get("lang") or "").strip().lower()
    if query in {"ru", "en"}:
        return query
    accept = (request.headers.get("accept-language") or "").lower()
    if not accept:
        return "ru"
    return "ru" if accept.split(",")[0].strip().startswith("ru") else "en"


@app.get("/privacy")
def privacy_page(request: Request) -> HTMLResponse:
    return HTMLResponse(
        legal.render("privacy", _page_lang(request)),
        headers={"Cache-Control": "public, max-age=300"},
    )


@app.get("/terms")
def terms_page(request: Request) -> HTMLResponse:
    return HTMLResponse(
        legal.render("terms", _page_lang(request)),
        headers={"Cache-Control": "public, max-age=300"},
    )


@app.get("/manifest.webmanifest")
def manifest() -> FileResponse:
    return FileResponse(
        STATIC_DIR / "manifest.webmanifest",
        media_type="application/manifest+json",
        headers={"Cache-Control": "no-store"},
    )


@app.get("/.well-known/assetlinks.json")
def assetlinks() -> JSONResponse:
    if not TWA_PACKAGE or not TWA_SHA256:
        raise HTTPException(404, detail={"message": "Android-приложение не настроено"})
    return JSONResponse(
        [
            {
                "relation": ["delegate_permission/common.handle_all_urls"],
                "target": {
                    "namespace": "android_app",
                    "package_name": TWA_PACKAGE,
                    "sha256_cert_fingerprints": TWA_SHA256,
                },
            }
        ],
        headers={"Cache-Control": "public, max-age=3600"},
    )


@app.get("/sw.js")
def service_worker() -> FileResponse:
    return FileResponse(
        STATIC_DIR / "sw.js",
        media_type="text/javascript",
        headers={"Cache-Control": "no-store"},
    )


@app.get("/favicon.ico")
def favicon() -> FileResponse:
    return FileResponse(STATIC_DIR / "img" / "favicon.svg", media_type="image/svg+xml")


app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
