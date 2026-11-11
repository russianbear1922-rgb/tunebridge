import { api, ApiError, setCsrf } from "./api.js";
import {
  state,
  isConnected,
  profileName,
  addHistoryEntry,
  clearHistoryStorage,
  resetPlaylistState,
} from "./store.js";
import * as views from "./views.js";
import {
  openModal,
  closeModal,
  isModalOpen,
  confirmDialog,
  toast,
  copyText,
  downloadBlob,
  esc,
  fmtTracks,
  fmtNumber,
} from "./ui.js";
import { icon, SERVICE_META } from "./icons.js";
import { t, toggleLang, applyDocumentLang } from "./i18n.js";
import { localize } from "./server-i18n.js";

let pollTimer = null;
let yandexTimer = null;
let connectIntent = null;
let exportFormats = [];
let telegramArchive = true;

const CONNECT_SERVICES = ["yandex", "spotify", "youtube"];
const INTENT_KEY = "tunebridge.connect-intent";
const FLOW_KEY = "tunebridge.flow-snapshot";
const INTENT_TTL = 20 * 60 * 1000;

function stashIntent(intent) {
  if (!intent) return;
  try {
    sessionStorage.setItem(INTENT_KEY, JSON.stringify({ ...intent, at: Date.now() }));
  } catch {
    /* sessionStorage может быть недоступен */
  }
}

function takeStashedIntent() {
  try {
    const raw = sessionStorage.getItem(INTENT_KEY);
    sessionStorage.removeItem(INTENT_KEY);
    if (!raw) return null;
    const data = JSON.parse(raw);
    if (!data || Date.now() - (Number(data.at) || 0) > INTENT_TTL) return null;
    delete data.at;
    return data;
  } catch {
    return null;
  }
}

function stashFlow() {
  if (!state.playlist) return;
  try {
    sessionStorage.setItem(
      FLOW_KEY,
      JSON.stringify({
        at: Date.now(),
        action: connectIntent?.action || null,
        playlist: state.playlist,
        playlistService: state.playlistService,
        playlistTitle: state.playlistTitle,
        target: connectIntent?.target || state.target,
        targetOptions: state.targetOptions,
        matches:
          connectIntent?.action === "transfer"
            ? state.matches.map((match) => ({ ...match, candidates: [] }))
            : null,
        matchMeta: connectIntent?.action === "transfer" ? state.matchMeta : null,
        stats: connectIntent?.action === "transfer" ? state.stats : null,
        reviewFilter: state.reviewFilter,
      })
    );
  } catch {
    /* снимок необязателен — продолжим без него */
  }
}

function takeFlow() {
  try {
    const raw = sessionStorage.getItem(FLOW_KEY);
    sessionStorage.removeItem(FLOW_KEY);
    if (!raw) return null;
    const data = JSON.parse(raw);
    if (!data || Date.now() - (Number(data.at) || 0) > INTENT_TTL) return null;
    return data.playlist ? data : null;
  } catch {
    return null;
  }
}

function prepareSpotifyRedirect() {
  stashIntent(connectIntent);
  if (connectIntent?.thenSelect) stashFlow();
  window.location.href = "/api/auth/spotify/start";
}

/* --------------------------------------------------------------- helpers */

const screenEl = () => document.getElementById("screen");

function scrollTop() {
  window.scrollTo(0, 0);
}

function setBusy(button, busy, label = t("Подождите…")) {
  if (!button) return;
  if (busy) {
    if (!button.dataset.originalHtml) button.dataset.originalHtml = button.innerHTML;
    button.disabled = true;
    button.innerHTML = `<span class="spinner"></span> ${esc(label)}`;
  } else if (button.dataset.originalHtml) {
    button.disabled = false;
    button.innerHTML = button.dataset.originalHtml;
    delete button.dataset.originalHtml;
  }
}

function isJobRunning() {
  return Boolean(state.job && (state.job.status === "running" || state.job.status === "cancelling"));
}

function targetMeta(id) {
  return state.targets.find((item) => item.id === id) || { id, requires_auth: id === "spotify" || id === "youtube" };
}

function handleActionError(error) {
  if (error instanceof ApiError && error.auth === "required") {
    state.authenticated = false;
    state.account = null;
    state.screen = "auth";
    render();
    return;
  }
  if (error instanceof ApiError && error.activeJob) {
    state.activeJob = error.activeJob;
    const config = views.busyModal(error.activeJob);
    openModal(config);
    return;
  }
  if (error instanceof ApiError && error.payload?.code === "insufficient_balance") {
    openModal(views.insufficientModal(error.payload));
    return;
  }
  toast(localize(error?.message) || t("Не удалось выполнить действие"), {
    kind: "error",
    title: t("Не получилось"),
    detail: localize(error?.hint) || "",
  });
}

function showSourceFeedback() {
  const host = document.getElementById("source-feedback");
  if (host) host.innerHTML = views.sourceFeedback(state);
}

/* ---------------------------------------------------------------- render */

let adViewKey = null;

function reportAdView() {
  if (!state.ads || !document.querySelector(".ad-slot")) return;
  const key = `${state.screen}:${state.playlist?.id || state.playlist?.url || ""}:${state.result?.job || ""}`;
  if (key === adViewKey) return;
  adViewKey = key;
  api.adEvent("view");
}

function render() {
  document.getElementById("sidebar").innerHTML = views.sidebar(state);
  document.getElementById("topbar").innerHTML = views.topbar(state);
  const screen = screenEl();
  if (screen) screen.innerHTML = views.screenMarkup(state);
  syncSidebar();
  reportAdView();
  syncNetBanner();
}

function renderScreenOnly() {
  const screen = screenEl();
  if (screen) screen.innerHTML = views.screenMarkup(state);
  reportAdView();
}

function syncSidebar() {
  const sidebar = document.getElementById("sidebar");
  if (sidebar) sidebar.classList.toggle("is-open", state.sidebarOpen);
  let scrim = document.getElementById("sidebar-scrim");
  if (!scrim) {
    scrim = document.createElement("div");
    scrim.id = "sidebar-scrim";
    scrim.className = "sidebar-scrim";
    scrim.dataset.action = "toggle-sidebar";
    document.body.appendChild(scrim);
  }
  scrim.classList.toggle("is-open", state.sidebarOpen);
}

async function refreshState() {
  const data = await api.state();
  state.services = data.services || {};
  state.targets = data.targets || [];
  state.telegram = data.telegram || { connected: false, profile: null, chat: "" };
  state.phone = data.phone || { enabled: false, url: null };
  state.limits = data.limits || state.limits;
  state.activeJob = data.active_job || null;
  state.freeMode = Boolean(data.free_mode);
  state.ads = data.ads || null;
  if (data.account) {
    state.account = data.account;
    state.mode = data.account.mode || state.mode;
    state.hosted = Boolean(data.account.hosted);
    state.packages = state.packages?.length ? state.packages : state.wallet?.packages || [];
  }
}

/* --------------------------------------------------------------- account */

function telegramWebApp() {
  return window.Telegram?.WebApp || null;
}

function applySession(session) {
  state.mode = session.mode || "local";
  state.hosted = Boolean(session.hosted);
  state.freeMode = Boolean(session.free_mode);
  state.authenticated = Boolean(session.authenticated);
  state.account = session.user || null;
  state.botUsername = session.bot?.username || null;
  if (Array.isArray(session.packages)) state.packages = session.packages;
  setCsrf(session.csrf);
}

async function loadSession() {
  const session = await api.session();
  applySession(session);
  return session;
}

async function tryTelegramLogin() {
  const tg = telegramWebApp();
  const initData = tg?.initData;
  if (!initData) return false;
  state.authBusy = true;
  try {
    const session = await api.telegramAuth(initData);
    applySession(session);
    state.authError = null;
    try {
      tg.ready?.();
      tg.expand?.();
    } catch {
      /* Mini App API может быть ограничен */
    }
    return true;
  } catch (error) {
    state.authError = error?.message || t("Не удалось войти через Telegram");
    return false;
  } finally {
    state.authBusy = false;
  }
}

async function openCabinet() {
  if (!state.authenticated) {
    state.screen = "auth";
    render();
    return;
  }
  state.screen = "cabinet";
  state.sidebarOpen = false;
  render();
  scrollTop();
  if (state.account?.is_admin && !state.freeMode && !state.admin) loadAdmin();
  if (state.account?.is_admin && state.freeMode && !state.adminStats) loadAdminStats();
  await loadWallet();
}

async function loadWallet() {
  state.walletLoading = true;
  render();
  try {
    const data = await api.wallet();
    state.wallet = data;
    state.cabinetError = null;
    if (state.account) state.account.balance = data.balance;
  } catch (error) {
    if (error instanceof ApiError && error.auth === "required") {
      handleActionError(error);
      return;
    }
    state.cabinetError = error?.message || t("Не удалось загрузить кабинет");
  } finally {
    state.walletLoading = false;
    if (state.screen === "cabinet" || state.screen === "auth") render();
  }
}

async function loadAdmin(button = null) {
  setBusy(button, true, t("Загружаем…"));
  try {
    const [overview, promos] = await Promise.all([api.adminOverview(), api.adminPromos()]);
    state.admin = { ...overview, promos: promos.promos || [] };
    state.adminError = null;
  } catch (error) {
    state.adminError = error?.message || t("Не удалось загрузить админ-панель");
  } finally {
    setBusy(button, false);
    if (state.screen === "cabinet") render();
  }
}

async function loadAdminStats(button = null) {
  setBusy(button, true, t("Загружаем…"));
  try {
    state.adminStats = await api.adminStats();
    state.adminStatsError = null;
  } catch (error) {
    state.adminStatsError = error?.message || t("Не удалось загрузить статистику");
  } finally {
    setBusy(button, false);
    if (state.screen === "cabinet") render();
  }
}

async function startTopup(packageId, button) {
  if (!packageId) return;
  setBusy(button, true, t("Создаём счёт…"));
  try {
    const result = await api.topup(packageId);
    if (result.mode === "sandbox") {
      toast(`+${fmtNumber(result.tokens)} ${t("токенов")}`, {
        kind: "ok",
        title: t("Тестовое пополнение"),
        detail: t("В локальном режиме звёзды не списываются."),
      });
      await loadSession();
      await loadWallet();
      return;
    }
    const tg = telegramWebApp();
    if (tg?.openInvoice) {
      tg.openInvoice(result.invoice_url, async (status) => {
        if (status === "paid") {
          toast(t("Оплата прошла, баланс обновлён"), { kind: "ok", title: t("Готово") });
          await loadSession();
          await loadWallet();
        } else if (status === "cancelled") {
          toast(t("Оплата отменена"), { kind: "warn" });
        } else if (status === "failed") {
          toast(t("Оплата не прошла"), { kind: "error" });
        }
      });
    } else {
      state.pendingPayment = result;
      openPaymentModal(result);
    }
  } catch (error) {
    handleActionError(error);
  } finally {
    setBusy(button, false);
  }
}

function openPaymentModal(result) {
  openModal({
    title: t("Оплата звёздами"),
    subtitle: `${fmtNumber(result.tokens)} ${t("токенов")} · ${fmtNumber(result.stars)} ${t("звёзд")}`,
    size: "is-sm",
    body: `<p class="modal-sub" style="margin:0 0 16px">${t(
      "Счёт откроется в Telegram. После оплаты вернитесь сюда и нажмите «Проверить оплату»."
    )}</p>
      <a class="btn btn-primary btn-block" href="${esc(result.invoice_url)}" target="_blank" rel="noreferrer">
        ${icon("external")} ${t("Открыть счёт в Telegram")}
      </a>`,
    footer: `<button class="btn btn-ghost" type="button" data-modal-close>${t("Закрыть")}</button>
      <button class="btn btn-primary" type="button" data-action="check-payment">${t("Проверить оплату")}</button>`,
  });
}

async function checkPayment(button) {
  setBusy(button, true, t("Проверяем…"));
  try {
    await loadSession();
    await loadWallet();
    closeModal();
    toast(t("Баланс обновлён"), { kind: "ok", title: t("Готово") });
  } catch (error) {
    handleActionError(error);
  } finally {
    setBusy(button, false);
  }
}

async function redeemPromo(form, button) {
  const input = form.querySelector('input[name="code"]');
  const code = (input?.value || "").trim();
  if (!code) {
    toast(t("Введите промокод"), { kind: "warn" });
    input?.focus();
    return;
  }
  setBusy(button, true, t("Проверяем…"));
  try {
    const result = await api.redeemPromo(code);
    toast(`+${fmtNumber(result.tokens)} ${t("токенов")} · ${t("баланс")} ${fmtNumber(result.balance)}`, {
      kind: "ok",
      title: t("Промокод активирован"),
    });
    if (input) input.value = "";
    await loadSession();
    await loadWallet();
  } catch (error) {
    handleActionError(error);
  } finally {
    setBusy(button, false);
  }
}

async function logoutAccount() {
  const ok = await confirmDialog({
    title: t("Выйти из аккаунта?"),
    message: t("Кошелёк и история переносов останутся на сервере. Войти снова можно через Telegram."),
    confirmText: t("Выйти"),
    danger: true,
  });
  if (!ok) return;
  try {
    await api.logout();
  } catch {
    /* локальная сессия всё равно очищается */
  }
  applySession({
    mode: "hosted",
    hosted: true,
    authenticated: false,
    user: null,
    csrf: null,
    packages: state.packages,
    bot: { username: state.botUsername },
  });
  state.wallet = null;
  state.admin = null;
  state.screen = "auth";
  render();
  scrollTop();
}

async function authRefresh(button) {
  setBusy(button, true, t("Проверяем…"));
  state.authError = null;
  try {
    await loadSession();
    if (!state.authenticated) await tryTelegramLogin();
    if (state.authenticated) {
      await refreshState();
      state.screen = state.activeJob ? "job" : "home";
      render();
      if (state.activeJob) watchJob(state.activeJob.id);
      return;
    }
    render();
    toast(t("Вход пока не подтверждён"), { kind: "warn", detail: t("Откройте приложение из Telegram и нажмите «Я уже вошёл».") });
  } catch (error) {
    state.authError = error?.message || t("Не удалось войти через Telegram");
    render();
  } finally {
    setBusy(button, false);
  }
}

async function createPromos(form, button) {
  const data = new FormData(form);
  const payload = {
    tokens: Number(data.get("tokens")) || 0,
    count: Number(data.get("count")) || 1,
    max_uses: Number(data.get("max_uses")) || 0,
    days: Number(data.get("days")) || 0,
    note: String(data.get("note") || ""),
  };
  setBusy(button, true, t("Создаём…"));
  try {
    const result = await api.adminCreatePromos(payload);
    const codes = result.codes || [];
    state.adminCodes = [...codes, ...(state.adminCodes || [])].slice(0, 20);
    toast(
      codes.length === 1
        ? `${t("Код")} ${codes[0]?.code}`
        : `${fmtNumber(codes.length)} ${t("новых кодов")}`,
      { kind: "ok", title: t("Промокоды созданы") }
    );
    await loadAdmin();
  } catch (error) {
    handleActionError(error);
  } finally {
    setBusy(button, false);
  }
}

async function adminCredit(form, button) {
  const data = new FormData(form);
  const payload = {
    telegram_id: Number(data.get("telegram_id")) || null,
    tokens: Number(data.get("tokens")) || 0,
    reason: String(data.get("reason") || ""),
  };
  if (!payload.telegram_id) {
    toast(t("Укажите Telegram ID"), { kind: "warn" });
    return;
  }
  setBusy(button, true, t("Начисляем…"));
  try {
    const result = await api.adminCredit(payload);
    toast(`${t("Баланс")}: ${fmtNumber(result.balance)}`, {
      kind: "ok",
      title: t("Начисление выполнено"),
      detail: esc(result.user?.name || ""),
    });
    if (state.account && result.user?.id === state.account.id) state.account.balance = result.balance;
    form.reset();
    await loadAdmin();
  } catch (error) {
    handleActionError(error);
  } finally {
    setBusy(button, false);
  }
}

async function togglePromo(code, enable, button) {
  if (!code) return;
  setBusy(button, true, t("Сохраняем…"));
  try {
    await api.adminTogglePromo(code, enable);
    toast(enable ? t("Промокод включён") : t("Промокод отключён"), { kind: "ok" });
    await loadAdmin();
  } catch (error) {
    handleActionError(error);
  } finally {
    setBusy(button, false);
  }
}

async function refundOrder(orderId, button) {
  if (!orderId) return;
  const ok = await confirmDialog({
    title: t("Вернуть звёзды?"),
    message: t("Telegram вернёт звёзды покупателю, а токены будут списаны с его баланса."),
    confirmText: t("Вернуть"),
    danger: true,
  });
  if (!ok) return;
  setBusy(button, true, t("Возвращаем…"));
  try {
    const result = await api.adminRefund(orderId, true);
    toast(`${t("Баланс клиента")}: ${fmtNumber(result.balance)}`, { kind: "ok", title: t("Возврат выполнен") });
    await loadAdmin();
    await loadWallet();
  } catch (error) {
    handleActionError(error);
  } finally {
    setBusy(button, false);
  }
}

/* ------------------------------------------------------------- navigation */

async function goHome() {
  if (isJobRunning()) {
    const ok = await confirmDialog({
      title: t("Задача ещё выполняется"),
      message: t("Вернуться на главную? Перенос продолжится в фоне, но вернуться к прогрессу можно будет только попыткой нового запуска."),
      confirmText: t("На главную"),
    });
    if (!ok) return;
    stopPolling();
    state.job = null;
    state.activeJob = null;
  }
  closeModal();
  resetPlaylistState();
  state.target = null;
  state.screen = "home";
  state.sourceFeedback = null;
  state.sidebarOpen = false;
  render();
  scrollTop();
}

function openHistory() {
  state.screen = "history";
  state.sidebarOpen = false;
  render();
  scrollTop();
}

function backToPlaylist() {
  if (!state.playlist) return goHome();
  state.screen = "playlist";
  render();
  scrollTop();
}

/* ---------------------------------------------------------------- resolve */

async function resolvePlaylist(service, url, button = null) {
  state.sourceFeedback = { kind: "info", message: `${t("Открываем плейлист в")} ${SERVICE_META[service]?.name || service}…` };
  showSourceFeedback();
  setBusy(button, true, t("Открываем…"));
  try {
    const data = await api.resolve(service, url);
    openPlaylist(data.playlist, service);
  } catch (error) {
    state.sourceFeedback = { kind: "error", message: error.message || t("Не удалось открыть плейлист"), hint: error.hint };
    showSourceFeedback();
    if (error.status === 401) {
      connectIntent = { thenResolve: true, url, service };
      openConnect(service);
    }
  } finally {
    setBusy(button, false);
  }
}

function chooseDefaultTarget(playlist) {
  const others = ["spotify", "youtube"].filter((id) => id !== playlist.service);
  const connected = others.find((id) => isConnected(id));
  state.target = connected || (playlist.service === "demo" ? "demo" : "file");
}

function openPlaylist(playlist, service) {
  state.playlist = playlist;
  state.playlistService = service || playlist.service;
  state.playlistTitle = playlist.title || t("Перенесённый плейлист");
  state.targetOptions = { public: true, privacy: "PRIVATE", formats: ["m3u", "csv", "json"], description: "" };
  chooseDefaultTarget(playlist);
  state.matches = [];
  state.matchMeta = null;
  state.stats = null;
  state.result = null;
  state.resultJob = null;
  state.reviewFilter = "all";
  state.sourceFeedback = null;
  state.screen = "playlist";
  state.sidebarOpen = false;
  closeModal();
  render();
  scrollTop();
}

async function loadDemo(button) {
  setBusy(button, true, t("Загружаем…"));
  try {
    const data = await api.demo();
    openPlaylist(data.playlist, "demo");
  } catch (error) {
    handleActionError(error);
  } finally {
    setBusy(button, false);
  }
}

async function loadPlaylists(service) {
  if (!isConnected(service)) {
    connectIntent = { thenPlaylists: true };
    openConnect(service);
    return;
  }
  state.sourceService = service;
  state.playlistsLoading = true;
  render();
  try {
    const data = await api.playlists(service);
    state.playlists[service] = data.playlists || [];
  } catch (error) {
    delete state.playlists[service];
    if (error.status === 401) {
      connectIntent = { thenPlaylists: true };
      openConnect(service);
    } else {
      handleActionError(error);
    }
  } finally {
    state.playlistsLoading = false;
    render();
  }
}

async function openFromCache(button) {
  const service = button.dataset.service;
  const index = Number(button.dataset.index);
  const item = state.playlists[service]?.[index];
  if (!item) return;
  if ((item.tracks || []).length) {
    openPlaylist(item, service);
    return;
  }
  if (!item.url) {
    toast(t("У плейлиста нет ссылки — откройте его по URL"), { kind: "warn" });
    return;
  }
  state.sourceService = service;
  await resolvePlaylist(service, item.url);
}

async function handleFile(file) {
  if (!file) return;
  if (file.size > 5 * 1024 * 1024) {
    state.sourceFeedback = { kind: "error", message: t("Файл больше 5 МБ"), hint: t("Загрузите файл поменьше или разбейте плейлист.") };
    showSourceFeedback();
    return;
  }
  state.sourceFeedback = { kind: "info", message: `${t("Читаем «")}${file.name}»…` };
  showSourceFeedback();
  try {
    const text = await file.text();
    const data = await api.importFile(file.name, text);
    openPlaylist(data.playlist, "file");
  } catch (error) {
    state.sourceFeedback = { kind: "error", message: error.message || t("Не удалось прочитать файл"), hint: error.hint };
    showSourceFeedback();
  }
}

/* ------------------------------------------------------------------ jobs */

function stopPolling() {
  if (pollTimer) {
    clearTimeout(pollTimer);
    pollTimer = null;
  }
}

function beginJob(job, { resetMatches = false } = {}) {
  state.job = job;
  state.activeJob = job;
  state.result = null;
  state.resultJob = null;
  if (resetMatches) {
    state.matches = [];
    state.matchMeta = null;
    state.stats = null;
  }
  state.screen = "job";
  render();
  scrollTop();
  watchJob(job.id);
}

function watchJob(id) {
  stopPolling();
  const tick = async () => {
    try {
      const job = await api.job(id);
      state.job = job;
      state.activeJob = job.status === "running" || job.status === "cancelling" ? job : null;
      if (state.screen === "job") patchJob(job);
      if (["done", "error", "cancelled"].includes(job.status)) {
        stopPolling();
        finishJob(job);
        return;
      }
      pollTimer = setTimeout(tick, 850);
    } catch (error) {
      if (error.status === 404) {
        stopPolling();
        state.error = { title: t("Задача не найдена"), message: localize(error.message), hint: localize(error.hint) };
        state.screen = "error";
        render();
        return;
      }
      toast(localize(error.message), { kind: "error", detail: localize(error.hint) || "" });
      pollTimer = setTimeout(tick, 2500);
    }
  };
  tick();
}

function patchJob(job) {
  const pct = views.jobPercent(job);
  const ring = document.getElementById("job-ring");
  if (ring) ring.style.setProperty("--p", pct);
  const ringValue = document.getElementById("job-ring-value");
  if (ringValue) ringValue.textContent = `${pct}%`;
  const phase = document.getElementById("job-phase");
  if (phase) phase.textContent = views.jobPhaseLabel(job);
  const current = document.getElementById("job-current");
  if (current) {
    current.innerHTML = job.current
      ? `${icon("music")}<span class="truncate">${esc(job.current)}</span>`
      : `<span class="dim">${t("Готовим задачу…")}</span>`;
  }
  const bar = document.getElementById("job-bar");
  if (bar) bar.style.width = `${pct}%`;
  const metrics = document.getElementById("job-metrics");
  if (metrics) metrics.innerHTML = views.jobMetrics(job);
  const events = document.getElementById("job-events");
  if (events) events.innerHTML = views.eventList(job.events);
  const cancel = document.querySelector('[data-action="cancel-job"]');
  if (cancel) {
    cancel.disabled = job.status === "cancelling";
    cancel.innerHTML =
      job.status === "cancelling" ? `${icon("close")} ${t("Останавливаем…")}` : `${icon("close")} ${t("Остановить")}`;
  }
}

async function finishJob(job) {
  state.activeJob = null;
  state.job = job;

  if (job.type === "match") {
    if (job.status === "done" && job.result) {
      const result = job.result;
      state.matches = (result.matches || []).map((match) => ({ ...match, _excluded: false }));
      state.matchMeta = {
        target: result.target,
        target_name: result.target_name,
        warnings: result.warnings || [],
        cache_hits: result.cache_hits || 0,
      };
      state.stats = result.stats || null;
      state.reviewFilter = "all";
      state.screen = "review";
      render();
      scrollTop();
      return;
    }
    if (job.status === "cancelled") {
      state.screen = "playlist";
      render();
      toast(t("Поиск остановлен"), { kind: "warn" });
      return;
    }
    state.error = {
      title: t("Не удалось подобрать треки"),
      message: localize(job.error) || t("Поиск прерван"),
      hint: localize(job.hint) || t("Проверьте подключение и попробуйте ещё раз."),
    };
    state.screen = "error";
    render();
    return;
  }

  const result = job.result || null;
  state.result = result;
  state.resultJob = job;

  if (result) {
    addHistoryEntry({
      id: job.id,
      at: Date.now(),
      source_title: result.source_title || state.playlist?.title || t("Плейлист"),
      source_service: result.source_service || state.playlistService,
      target: result.target,
      target_name: result.target_name,
      added: result.added || 0,
      total: (result.added || 0) + (result.failed || 0) + (result.skipped || 0),
      url: result.url,
      demo: Boolean(result.demo),
    });
  }

  if (job.status === "error" && !result) {
    state.error = {
      title: t("Перенос не удался"),
      message: localize(job.error) || t("Сервис вернул ошибку"),
      hint: localize(job.hint) || null,
    };
    state.screen = "error";
    render();
    return;
  }

  state.screen = "result";
  render();
  scrollTop();

  if (job.status === "cancelled") {
    toast(t("Перенос остановлен"), { kind: "warn" });
  } else if (job.status === "error") {
    toast(localize(job.error) || t("Перенос прерван"), { kind: "error", detail: localize(job.hint) || "" });
  }
}

async function startMatch(button) {
  const target = state.target;
  if (!target) {
    toast(t("Сначала выберите сервис"), { kind: "warn" });
    return;
  }
  if (target === "file") {
    openExportModal();
    return;
  }
  const meta = targetMeta(target);
  if (meta.requires_auth && !isConnected(target)) {
    connectIntent = { thenSelect: true, action: "match", target };
    openConnect(target);
    return;
  }
  if (!state.playlist?.tracks?.length) {
    toast(t("В плейлисте нет треков"), { kind: "warn" });
    return;
  }
  setBusy(button, true, t("Запускаем…"));
  try {
    const job = await api.startMatch(state.playlist, target);
    beginJob(job, { resetMatches: true });
  } catch (error) {
    handleActionError(error);
  } finally {
    setBusy(button, false);
  }
}

async function startTransfer(button) {
  const target = state.target;
  if (!target) return;
  const meta = targetMeta(target);
  if (meta.requires_auth && !isConnected(target)) {
    connectIntent = { thenSelect: true, action: "transfer", target };
    openConnect(target);
    return;
  }
  const included = state.matches.filter(
    (match) => !match._excluded && match.target && match.status !== "missing"
  );
  if (!included.length) {
    toast(t("Нет треков для переноса"), { kind: "warn" });
    return;
  }
  const matches = included.map((match) => ({
    source: match.source,
    target: match.target,
    score: match.score,
    status: match.status,
    candidates: match.candidates || [],
  }));
  const title = (state.playlistTitle || "").trim() || state.playlist?.title || t("Перенесённый плейлист");
  const description = (state.targetOptions.description || "").trim() || null;
  const options =
    target === "spotify"
      ? { public: Boolean(state.targetOptions.public) }
      : target === "youtube"
      ? { privacy: state.targetOptions.privacy || "PRIVATE" }
      : {};

  setBusy(button, true, t("Запускаем…"));
  try {
    const job = await api.startTransfer(state.playlist, target, matches, title, description, options);
    beginJob(job);
  } catch (error) {
    handleActionError(error);
  } finally {
    setBusy(button, false);
  }
}

async function cancelJob(button) {
  if (!state.job) return;
  setBusy(button, true, t("Останавливаем…"));
  try {
    const job = await api.cancel(state.job.id);
    state.job = job;
    patchJob(job);
  } catch (error) {
    handleActionError(error);
  }
}

/* -------------------------------------------------------------- connections */

function stopYandexPolling() {
  if (yandexTimer) {
    clearInterval(yandexTimer);
    yandexTimer = null;
  }
}

function openConnect(service, options = null) {
  if (!CONNECT_SERVICES.includes(service)) {
    toast(`${SERVICE_META[service]?.name || service} ${t("не требует входа")}`, {
      kind: "info",
      detail: t("Вставьте ссылку на плейлист — этого достаточно."),
    });
    return;
  }
  if (options) connectIntent = { ...options };
  stopYandexPolling();
  const config = views.connectModal(state, service);
  openModal({
    ...config,
    onClose() {
      stopYandexPolling();
      setTimeout(() => {
        if (!isModalOpen()) connectIntent = null;
      }, 0);
    },
  });
  if (service === "yandex" && !isConnected("yandex")) {
    startYandexDevice();
  }
}

function chooseYouTubeAccount(accounts) {
  return new Promise((resolve) => {
    let settled = false;
    const finish = (value) => {
      if (settled) return;
      settled = true;
      resolve(value);
    };
    openModal({
      title: t("Выберите аккаунт"),
      subtitle: t("В браузере несколько аккаунтов Google. Подключится тот, который вы выберете."),
      size: "is-sm",
      body: `<div class="account-list">${(accounts || [])
        .map(
          (account, index) => `<button class="account-card" type="button" data-pick="${index}">
            ${
              account.avatar
                ? `<img class="account-avatar" src="${esc(account.avatar)}" alt="" loading="lazy">`
                : `<span class="account-avatar">${esc((account.name || "Y").trim().charAt(0).toUpperCase())}</span>`
            }
            <span class="account-text">
              <span class="account-name truncate">${esc(account.name || "YouTube Music")}</span>
              <span class="account-sub truncate">${esc(account.label || t("Google-аккаунт"))}</span>
            </span>
          </button>`
        )
        .join("")}</div>`,
      footer: `<button class="btn btn-ghost" type="button" data-modal-close>${t("Отмена")}</button>`,
      onMount(modal) {
        modal.querySelectorAll("[data-pick]").forEach((button) => {
          button.addEventListener("click", () => {
            finish(accounts[Number(button.dataset.pick)] || null);
            closeModal();
          });
        });
      },
      onClose() {
        finish(null);
      },
    });
  });
}

async function startYandexDevice() {
  const modal = document.querySelector("#modal-root .modal");
  if (!modal) return;
  stopYandexPolling();
  const codeEl = modal.querySelector("[data-yandex-code]");
  const hintEl = modal.querySelector("[data-yandex-hint]");
  const statusEl = modal.querySelector("[data-yandex-status]");
  if (codeEl) codeEl.textContent = "•••• ••••";
  if (hintEl) hintEl.textContent = t("Получаем код у Яндекса…");
  if (statusEl) {
    statusEl.style.color = "";
    statusEl.innerHTML = `<span class="spinner"></span> ${t("Ожидаем подтверждение…")}`;
  }

  let data;
  try {
    data = await api.yandexDevice();
  } catch (error) {
    if (codeEl) codeEl.textContent = "—";
    if (hintEl) hintEl.textContent = t("Не удалось получить код");
    if (statusEl) {
      statusEl.style.color = "#ffb3be";
      statusEl.innerHTML = `${icon("alert")} <span>${esc(localize(error.message))}</span>
        <button class="link-btn" type="button" data-action="retry-yandex">${t("Повторить")}</button>`;
    }
    return;
  }

  if (codeEl) codeEl.textContent = data.user_code || "—";
  if (hintEl) {
    hintEl.textContent = `${t("Код действует")} ${Math.max(1, Math.round((data.expires_in || 300) / 60))} ${t("мин ·")} ya.ru/device`;
  }

  const interval = Math.max(2, Number(data.interval) || 3) * 1000;
  let busy = false;
  yandexTimer = setInterval(async () => {
    if (busy) return;
    if (!document.body.contains(modal)) {
      stopYandexPolling();
      return;
    }
    busy = true;
    try {
      const result = await api.yandexPoll();
      if (result.status === "connected") {
        stopYandexPolling();
        await onConnected("yandex");
      }
    } catch (error) {
      stopYandexPolling();
      if (statusEl) {
        statusEl.style.color = "#ffb3be";
        statusEl.innerHTML = `${icon("alert")} <span>${esc(localize(error.message))}</span>
          <button class="link-btn" type="button" data-action="retry-yandex">${t("Получить новый код")}</button>`;
      }
    } finally {
      busy = false;
    }
  }, interval);
}

async function resumeIntent(intent, service) {
  if (!intent) return false;
  if (intent.thenResolve && intent.url) {
    state.sourceService = service;
    state.sourceUrl = intent.url;
    state.screen = "home";
    render();
    await resolvePlaylist(service, intent.url);
    return true;
  }
  if (intent.thenPlaylists) {
    await loadPlaylists(service);
    return true;
  }
  if (intent.thenSelect) {
    if (state.screen === "playlist" || state.screen === "review") state.target = intent.target || service;
    if (intent.action === "match") {
      await startMatch(null);
      return true;
    }
    if (intent.action === "transfer") {
      await startTransfer(null);
      return true;
    }
    render();
    return true;
  }
  return false;
}

async function restoreFlow(flow) {
  if (!flow?.playlist) return false;
  openPlaylist(flow.playlist, flow.playlistService || flow.playlist.service);
  state.playlistTitle = flow.playlistTitle || state.playlistTitle;
  state.targetOptions = flow.targetOptions || state.targetOptions;
  if (flow.target) state.target = flow.target;
  state.reviewFilter = flow.reviewFilter || "all";
  if (flow.action === "transfer" && Array.isArray(flow.matches) && flow.matches.length) {
    state.matches = flow.matches.map((match) => ({ ...match, _excluded: Boolean(match._excluded) }));
    state.matchMeta = flow.matchMeta || null;
    state.stats = flow.stats || null;
    state.screen = "review";
  }
  render();
  scrollTop();
  if (flow.action === "match") await startMatch(null);
  if (flow.action === "transfer") await startTransfer(null);
  return true;
}

async function onConnected(service) {
  const intent = connectIntent || {};
  connectIntent = null;
  stopYandexPolling();
  try {
    await refreshState();
  } catch {
    /* состояние обновим при следующем действии */
  }
  closeModal();
  toast(`${SERVICE_META[service]?.name || service} ${t("подключён")}`, { kind: "ok", title: t("Готово"), timeout: 3200 });

  if (await resumeIntent(intent, service)) return;
  render();
}

async function disconnectService(service) {
  const ok = await confirmDialog({
    title: `${t("Отключить")} ${SERVICE_META[service]?.name || service}?`,
    message: t("Токен будет удалён с этого компьютера. Плейлисты в сервисе останутся на месте."),
    confirmText: t("Отключить"),
    danger: true,
  });
  if (!ok) return;
  try {
    await api.disconnect(service);
    await refreshState();
    if (state.target === service) {
      state.target = state.playlist?.service === "demo" ? "demo" : "file";
    }
    closeModal();
    render();
    toast(t("Аккаунт отключён"), { kind: "ok" });
  } catch (error) {
    handleActionError(error);
  }
}

/* ---------------------------------------------------------------- review */

async function toggleBusyModal(job) {
  state.activeJob = job;
  const config = views.busyModal(job);
  openModal(config);
}

function openSearch(index) {
  const match = state.matches[index];
  if (!match) return;
  const target = state.target;
  state.searchIndex = index;
  const config = views.searchModalMarkup(match.source, target);
  openModal({
    title: `${t("Найти трек в")} ${SERVICE_META[target]?.name || target}`,
    subtitle: t("Выберите подходящий вариант — он заменит текущее совпадение."),
    body: config.body,
    footer: config.footer,
    size: "is-lg",
    onMount(modal) {
      const input = modal.querySelector('input[name="query"]');
      input?.focus();
      input?.select();
      input?.addEventListener("keydown", (event) => {
        if (event.key === "Enter") {
          event.preventDefault();
          runSearch(modal, index);
        }
      });
      runSearch(modal, index);
    },
  });
}

async function runSearch(modal, index) {
  if (!modal) return;
  const input = modal.querySelector('input[name="query"]');
  const list = modal.querySelector("[data-search-list]");
  if (!list) return;
  const query = (input?.value || "").trim();
  if (!query) {
    toast(t("Введите запрос"), { kind: "warn" });
    return;
  }
  list.innerHTML = `<div class="auth-status"><span class="spinner"></span> ${t("Ищем…")}</div>`;
  try {
    const data = await api.search(state.target, query, state.matches[index]?.source);
    state.searchCandidates = data.candidates || [];
    state.searchIndex = index;
    list.innerHTML = views.searchResults(state.searchCandidates);
  } catch (error) {
    list.innerHTML = `<div class="warn-box">${icon("alert")}<span>${esc(localize(error.message))}${
      error.hint ? `<br><span class="dim">${esc(localize(error.hint))}</span>` : ""
    }</span></div>`;
  }
}

function pickCandidate(button) {
  const candidate = state.searchCandidates[Number(button.dataset.index)];
  const index = state.searchIndex;
  if (!candidate || index == null) return;
  const match = state.matches[index];
  if (!match) return;
  match.target = candidate.track;
  match.score = candidate.score;
  match.status = "manual";
  match.candidates = [candidate];
  match._excluded = false;
  if (!["all", "manual"].includes(state.reviewFilter)) state.reviewFilter = "manual";
  closeModal();
  renderScreenOnly();
  toast(t("Совпадение заменено"), { kind: "ok", timeout: 2400 });
}

/* ---------------------------------------------------------------- export */

function openExportModal() {
  if (!state.playlist) {
    toast(t("Сначала загрузите плейлист"), { kind: "warn" });
    return;
  }
  exportFormats = [...(state.targetOptions.formats?.length ? state.targetOptions.formats : ["m3u", "csv", "json"])];
  const config = views.exportModal(state, exportFormats);
  openModal(config);
}

async function downloadExport(button) {
  if (!state.playlist) return;
  if (!exportFormats.length) {
    toast(t("Выберите хотя бы один формат"), { kind: "warn" });
    return;
  }
  setBusy(button, true, t("Создаём…"));
  try {
    const blob = await api.exportZip(state.playlist, exportFormats);
    const slug =
      (state.playlist.title || "playlist")
        .replace(/[^\p{L}\p{N}]+/gu, "-")
        .replace(/^-+|-+$/g, "")
        .slice(0, 60) || "playlist";
    downloadBlob(blob, `${slug}-tunebridge.zip`);
    toast(t("Архив скачан"), { kind: "ok" });
  } catch (error) {
    handleActionError(error);
  } finally {
    setBusy(button, false);
  }
}

function openTelegram() {
  openModal(views.telegramModal(state, telegramArchive));
}

async function connectTelegram(button) {
  const token = document.querySelector("[data-telegram-token]")?.value?.trim();
  if (!token) {
    toast(t("Вставьте токен бота"), { kind: "warn" });
    return;
  }
  setBusy(button, true, t("Проверяем…"));
  try {
    await api.telegramConnect(token);
    await refreshState();
    openTelegram();
    toast(t("Telegram подключён"), { kind: "ok", detail: t("Откройте бота и нажмите Start, чтобы получить сообщения.") });
  } catch (error) {
    handleActionError(error);
  } finally {
    setBusy(button, false);
  }
}

async function loadTelegramChats(button) {
  const list = document.querySelector("[data-telegram-chats]");
  if (!list) return;
  setBusy(button, true, t("Ищем…"));
  list.innerHTML = "";
  try {
    const data = await api.telegramChats();
    list.innerHTML = views.telegramChatsMarkup(data.chats || []);
  } catch (error) {
    list.innerHTML = `<div class="warn-box">${icon("alert")}<span>${esc(localize(error.message))}${
      error.hint ? `<br><span class="dim">${esc(localize(error.hint))}</span>` : ""
    }</span></div>`;
  } finally {
    setBusy(button, false);
  }
}

async function sendTelegram(button) {
  if (!state.playlist) return;
  const chat = document.querySelector("[data-telegram-chat]")?.value?.trim() || "";
  const formats = telegramArchive ? ["m3u", "csv", "json"] : [];
  setBusy(button, true, t("Отправляем…"));
  try {
    const result = await api.telegramSend(state.playlist, chat, formats);
    closeModal();
    toast(`${t("Отправлено в")} ${result.chat}`, {
      kind: "ok",
      title: "Telegram",
      detail: `${result.messages} ${result.messages === 1 ? t("сообщение") : t("сообщений")}${
        result.archive ? t(" + архив") : ""
      }`,
      timeout: 6000,
    });
  } catch (error) {
    handleActionError(error);
  } finally {
    setBusy(button, false);
  }
}

async function disconnectTelegram() {
  const ok = await confirmDialog({
    title: t("Отключить Telegram?"),
    message: t("Токен бота будет удалён с этого компьютера. Бот и его чаты останутся в Telegram."),
    confirmText: t("Отключить"),
    danger: true,
  });
  if (!ok) return;
  try {
    await api.disconnect("telegram");
    await refreshState();
    openTelegram();
    toast(t("Telegram отключён"), { kind: "ok" });
  } catch (error) {
    handleActionError(error);
  }
}

function openSpotifyEditor() {
  openModal({
    title: t("Изменить Client ID"),
    subtitle: t("Возьмите Client ID приложения из Spotify Developer Dashboard."),
    size: "is-sm",
    body: `<div class="field">
        <label class="field-label">Client ID</label>
        <input class="input mono" data-spotify-client autocomplete="off" spellcheck="false" placeholder="${t("Например, 1")}a2b3c4d…">
      </div>
      <div class="notice">${icon("shield")}<span>${t("После смены")} Client ID ${t("текущий токен будет удалён — потребуется войти заново.")}</span></div>`,
    footer: `<button class="btn btn-ghost" type="button" data-modal-close>${t("Отмена")}</button>
      <button class="btn btn-primary" type="button" data-action="spotify-client">${t("Сохранить")}</button>`,
  });
}

/* ---------------------------------------------------------------- actions */

async function handleAction(action, element) {
  switch (action) {
    case "go-home":
      await goHome();
      break;
    case "open-history":
      openHistory();
      break;
    case "help":
      state.sidebarOpen = false;
      syncSidebar();
      openModal(views.helpModal(state));
      break;
    case "toggle-sidebar":
      state.sidebarOpen = !state.sidebarOpen;
      syncSidebar();
      break;
    case "toggle-lang":
      toggleLang();
      render();
      break;
    case "select-source": {
      const id = element.dataset.service;
      if (state.sourceService !== id) {
        state.sourceService = id;
        state.sourceFeedback = null;
        state.sourceUrl = "";
      }
      render();
      break;
    }
    case "load-playlists":
      await loadPlaylists(element.dataset.service);
      break;
    case "open-playlist":
      await openFromCache(element);
      break;
    case "close-playlists":
      delete state.playlists[state.sourceService];
      render();
      break;
    case "load-demo":
      await loadDemo(element);
      break;
    case "pick-file":
      document.getElementById("file-input")?.click();
      break;
    case "connect":
      state.sidebarOpen = false;
      syncSidebar();
      connectIntent = null;
      openConnect(element.dataset.service);
      break;
    case "disconnect":
      await disconnectService(element.dataset.service);
      break;
    case "retry-yandex":
      await startYandexDevice();
      break;
    case "copy-yandex-code": {
      const code = document.querySelector("[data-yandex-code]")?.textContent?.trim() || "";
      if (!code || code.includes("•") || code === "—") {
        toast(t("Код ещё не получен"), { kind: "warn" });
      } else {
        await copyText(code);
      }
      break;
    }
    case "copy-text":
      await copyText(element.dataset.copy || "");
      break;
    case "yandex-token": {
      const token = document.querySelector("[data-yandex-token]")?.value?.trim();
      if (!token) {
        toast(t("Вставьте токен"), { kind: "warn" });
        return;
      }
      setBusy(element, true, t("Проверяем…"));
      try {
        await api.yandexToken(token);
        await onConnected("yandex");
      } catch (error) {
        handleActionError(error);
      } finally {
        setBusy(element, false);
      }
      break;
    }
    case "spotify-client": {
      const input = document.querySelector("[data-spotify-client]");
      const value = input?.value?.trim();
      if (!value) {
        toast(t("Вставьте Client ID"), { kind: "warn" });
        return;
      }
      setBusy(element, true, t("Сохраняем…"));
      try {
        await api.spotifyClient(value);
        await refreshState();
        toast(t("Client ID сохранён — открываем Spotify"), { kind: "ok" });
        prepareSpotifyRedirect();
      } catch (error) {
        handleActionError(error);
        setBusy(element, false);
      }
      break;
    }
    case "spotify-start":
      prepareSpotifyRedirect();
      break;
    case "spotify-reset":
      openSpotifyEditor();
      break;
    case "youtube-browser": {
      setBusy(element, true, t("Ищем вход…"));
      try {
        let result = await api.youtubeConnectBrowser();
        if (result?.needs_choice) {
          setBusy(element, false);
          const account = await chooseYouTubeAccount(result.accounts);
          if (!account) return;
          setBusy(element, true, t("Подключаем…"));
          result = await api.youtubeConnectBrowser(account.label, account.authuser);
        }
        await onConnected("youtube");
      } catch (error) {
        handleActionError(error);
      } finally {
        setBusy(element, false);
      }
      break;
    }
    case "youtube-connect": {
      const headers = document.querySelector("[data-youtube-headers]")?.value?.trim();
      if (!headers) {
        toast(t("Вставьте значение cookie"), { kind: "warn" });
        return;
      }
      setBusy(element, true, t("Проверяем…"));
      try {
        let result = await api.youtubeConnect(headers);
        if (result?.needs_choice) {
          setBusy(element, false);
          const account = await chooseYouTubeAccount(result.accounts);
          if (!account) return;
          setBusy(element, true, t("Подключаем…"));
          result = await api.youtubeConnect(headers, account.authuser);
        }
        await onConnected("youtube");
      } catch (error) {
        handleActionError(error);
      } finally {
        setBusy(element, false);
      }
      break;
    }
    case "select-target": {
      const id = element.dataset.target;
      const meta = targetMeta(id);
      if (meta.requires_auth && !isConnected(id)) {
        connectIntent = { thenSelect: true, target: id };
        openConnect(id);
        return;
      }
      state.target = id;
      render();
      break;
    }
    case "toggle-public":
      state.targetOptions.public = !state.targetOptions.public;
      element.setAttribute("aria-checked", state.targetOptions.public ? "true" : "false");
      break;
    case "set-privacy":
      state.targetOptions.privacy = element.dataset.privacy;
      element.closest("[data-privacy-group]")
        ?.querySelectorAll("[data-privacy]")
        .forEach((button) => button.classList.toggle("is-active", button === element));
      break;
    case "toggle-target-format": {
      const value = element.dataset.format;
      const formats = state.targetOptions.formats;
      const index = formats.indexOf(value);
      if (index >= 0) {
        if (formats.length === 1) {
          toast(t("Нужен хотя бы один формат"), { kind: "warn" });
          return;
        }
        formats.splice(index, 1);
      } else {
        formats.push(value);
      }
      element.classList.toggle("is-active", formats.includes(value));
      break;
    }
    case "start-match":
      await startMatch(element);
      break;
    case "rematch":
      await startMatch(element);
      break;
    case "transfer":
      await startTransfer(element);
      break;
    case "set-filter":
      state.reviewFilter = element.dataset.filter;
      renderScreenOnly();
      break;
    case "toggle-exclude": {
      const index = Number(element.dataset.index);
      const match = state.matches[index];
      if (!match) return;
      match._excluded = !match._excluded;
      renderScreenOnly();
      break;
    }
    case "search-track":
      openSearch(Number(element.dataset.index));
      break;
    case "run-search": {
      const modal = element.closest(".modal");
      await runSearch(modal, state.searchIndex);
      break;
    }
    case "pick-candidate":
      pickCandidate(element);
      break;
    case "export":
      openExportModal();
      break;
    case "toggle-format": {
      const value = element.dataset.format;
      const index = exportFormats.indexOf(value);
      if (index >= 0) exportFormats.splice(index, 1);
      else exportFormats.push(value);
      element.classList.toggle("is-on", exportFormats.includes(value));
      element.setAttribute("aria-checked", exportFormats.includes(value) ? "true" : "false");
      break;
    }
    case "download-export":
      await downloadExport(element);
      break;
    case "telegram":
      openTelegram();
      break;
    case "telegram-connect":
      await connectTelegram(element);
      break;
    case "telegram-chats":
      await loadTelegramChats(element);
      break;
    case "pick-telegram-chat": {
      const input = document.querySelector("[data-telegram-chat]");
      if (input) {
        input.value = element.dataset.chat || "";
        input.focus();
      }
      break;
    }
    case "toggle-telegram-archive": {
      telegramArchive = !telegramArchive;
      element.classList.toggle("is-on", telegramArchive);
      element.setAttribute("aria-checked", telegramArchive ? "true" : "false");
      const summary = document.querySelector("[data-telegram-summary]");
      if (summary) {
        const count = state.playlist?.track_count || state.playlist?.tracks?.length || 0;
        summary.textContent = `${t("Уйдёт")} ${fmtTracks(count)} ${t("списком")}${
          telegramArchive ? t(" плюс архив") : ""
        }. ${t("При первом сообщении")} Telegram ${t("попросит нажать")} Start ${t("у бота.")}`;
      }
      break;
    }
    case "telegram-send":
      await sendTelegram(element);
      break;
    case "telegram-disconnect":
      await disconnectTelegram();
      break;
    case "phone":
      state.sidebarOpen = false;
      syncSidebar();
      openModal(views.phoneModal(state));
      break;
    case "cancel-job":
      await cancelJob(element);
      break;
    case "back-to-playlist":
      backToPlaylist();
      break;
    case "open-active-job": {
      const job = state.activeJob;
      if (!job?.id) {
        toast(t("Задача уже завершилась"), { kind: "warn" });
        closeModal();
        return;
      }
      closeModal();
      state.job = job;
      state.screen = "job";
      render();
      scrollTop();
      watchJob(job.id);
      break;
    }
    case "clear-history": {
      const ok = await confirmDialog({
        title: t("Очистить историю?"),
        message: t("Записи о переносах будут удалены из этого браузера. Плейлисты в сервисах не изменятся."),
        confirmText: t("Очистить"),
        danger: true,
      });
      if (!ok) return;
      clearHistoryStorage();
      render();
      toast(t("История очищена"), { kind: "ok" });
      break;
    }
    case "open-cabinet":
      await openCabinet();
      break;
    case "go-topup":
      closeModal();
      await openCabinet();
      break;
    case "refresh-cabinet":
      await openCabinet();
      break;
    case "topup":
      await startTopup(element.dataset.package, element);
      break;
    case "check-payment":
      await checkPayment(element);
      break;
    case "logout":
      await logoutAccount();
      break;
    case "auth-refresh":
      await authRefresh(element);
      break;
    case "admin-load":
      await loadAdmin(element);
      break;
    case "admin-stats-load":
      await loadAdminStats(element);
      break;
    case "install-app":
      await installApp();
      break;
    case "net-retry":
      state.offline = !navigator.onLine;
      syncNetBanner();
      if (!state.offline) {
        await refreshState().catch(() => {});
        render();
      }
      break;
    case "admin-toggle-promo":
      await togglePromo(element.dataset.code, element.dataset.active !== "1", element);
      break;
    case "admin-refund":
      await refundOrder(element.dataset.order, element);
      break;
    default:
      break;
  }
}

/* ------------------------------------------------------------- bootstrap */

function registerServiceWorker() {
  if (!("serviceWorker" in navigator)) return;
  if (!window.isSecureContext) return;
  navigator.serviceWorker.register("/sw.js").catch(() => {
    /* офлайн-режим необязателен */
  });
}

function handleQueryParams() {
  const url = new URL(window.location.href);
  const connected = url.searchParams.get("connected");
  const error = url.searchParams.get("spotify_error");
  if (connected) {
    toast(t("Аккаунт Spotify подключён"), { kind: "ok", title: t("Готово") });
    url.searchParams.delete("connected");
  }
  if (error) {
    toast(localize(error), { kind: "error", title: "Spotify" });
    url.searchParams.delete("spotify_error");
  }
  if (connected || error) {
    window.history.replaceState({}, "", url.pathname + (url.search || ""));
  }
  return connected;
}

function openExternal(url) {
  const tg = telegramWebApp();
  if (/^https?:\/\//i.test(url || "") && tg?.openLink) {
    try {
      tg.openLink(url);
      return;
    } catch {
      /* fallback ниже */
    }
  }
  window.open(url, "_blank", "noopener");
}

/* ------------------------------------------------------ install & network */

let installPromptEvent = null;

function isStandalone() {
  return Boolean(window.matchMedia?.("(display-mode: standalone)")?.matches || navigator.standalone);
}

function isIos() {
  return (
    /iphone|ipad|ipod/i.test(navigator.userAgent) ||
    (navigator.platform === "MacIntel" && navigator.maxTouchPoints > 1)
  );
}

function setupInstall() {
  if (isStandalone()) return;
  window.addEventListener("beforeinstallprompt", (event) => {
    event.preventDefault();
    installPromptEvent = event;
    state.installReady = true;
    render();
  });
  window.addEventListener("appinstalled", () => {
    installPromptEvent = null;
    state.installReady = false;
    render();
    toast(t("TuneBridge установлен"), { kind: "ok" });
  });
  if (isIos()) state.installReady = true;
}

async function installApp() {
  if (installPromptEvent) {
    const prompt = installPromptEvent;
    installPromptEvent = null;
    prompt.prompt();
    const choice = await prompt.userChoice.catch(() => null);
    state.installReady = choice?.outcome === "accepted" ? false : isIos();
    render();
    return;
  }
  openModal(views.installModal(state));
}

function syncNetBanner() {
  let bar = document.getElementById("net-banner");
  if (!state.offline) {
    bar?.remove();
    return;
  }
  if (!bar) {
    bar = document.createElement("div");
    bar.id = "net-banner";
    bar.className = "net-banner";
    bar.setAttribute("role", "status");
    bar.innerHTML = `${icon("alert")}<span>${t(
      "Нет сети. Переносы приостановлены — проверьте подключение."
    )}</span><button class="btn btn-ghost btn-sm" type="button" data-action="net-retry">${t("Повторить")}</button>`;
    document.body.appendChild(bar);
  }
}

function setupNetwork() {
  state.offline = !navigator.onLine;
  window.addEventListener("online", () => {
    state.offline = false;
    syncNetBanner();
    refreshState()
      .then(render)
      .catch(() => {});
  });
  window.addEventListener("offline", () => {
    state.offline = true;
    syncNetBanner();
  });
}

function bindEvents() {
  document.addEventListener("click", (event) => {
    const adLink = event.target.closest("a[data-ad-link]");
    if (adLink) {
      event.preventDefault();
      api.adEvent("click");
      openExternal(adLink.dataset.adLink);
      return;
    }
    const external = event.target.closest("a[data-external]");
    if (external) {
      event.preventDefault();
      openExternal(new URL(external.getAttribute("href"), window.location.origin).href);
      return;
    }
    const element = event.target.closest("[data-action]");
    if (!element) return;
    const action = element.dataset.action;
    if (!action) return;
    Promise.resolve(handleAction(action, element)).catch((error) => {
      console.error(error);
      toast(localize(error?.message) || t("Непредвиденная ошибка"), { kind: "error", detail: localize(error?.hint) || "" });
    });
  });

  document.addEventListener("submit", (event) => {
    const promoForm = event.target.closest('form[data-form="promo"]');
    if (promoForm) {
      event.preventDefault();
      redeemPromo(promoForm, promoForm.querySelector('button[type="submit"]'));
      return;
    }
    const adminPromoForm = event.target.closest('form[data-form="admin-promo"]');
    if (adminPromoForm) {
      event.preventDefault();
      createPromos(adminPromoForm, adminPromoForm.querySelector('button[type="submit"]'));
      return;
    }
    const adminCreditForm = event.target.closest('form[data-form="admin-credit"]');
    if (adminCreditForm) {
      event.preventDefault();
      adminCredit(adminCreditForm, adminCreditForm.querySelector('button[type="submit"]'));
      return;
    }
    const form = event.target.closest('form[data-form="resolve"]');
    if (!form) return;
    event.preventDefault();
    const service = state.sourceService;
    const input = form.querySelector('input[name="url"]');
    const url = (input?.value || "").trim();
    state.sourceUrl = url;
    if (service === "demo") {
      loadDemo(form.querySelector('button[type="submit"]'));
      return;
    }
    if (service === "file") {
      document.getElementById("file-input")?.click();
      return;
    }
    if (!url) {
      state.sourceFeedback = { kind: "error", message: t("Вставьте ссылку на плейлист"), hint: t("Ссылку можно скопировать из адресной строки сервиса.") };
      showSourceFeedback();
      input?.focus();
      return;
    }
    resolvePlaylist(service, url, form.querySelector('button[type="submit"]'));
  });

  document.addEventListener("input", (event) => {
    const field = event.target.closest("[data-field]");
    if (field) {
      if (field.dataset.field === "title") state.playlistTitle = field.value;
      if (field.dataset.field === "description") state.targetOptions.description = field.value;
      return;
    }
    if (event.target.name === "url") state.sourceUrl = event.target.value;
  });

  document.addEventListener("change", (event) => {
    if (event.target.matches("[data-file-input]")) {
      handleFile(event.target.files?.[0]);
    }
  });

  ["dragenter", "dragover"].forEach((type) => {
    document.addEventListener(type, (event) => {
      const zone = event.target.closest?.(".dropzone");
      if (!zone) return;
      event.preventDefault();
      zone.classList.add("is-over");
    });
  });
  ["dragleave", "drop"].forEach((type) => {
    document.addEventListener(type, (event) => {
      const zone = event.target.closest?.(".dropzone");
      if (!zone) return;
      event.preventDefault();
      zone.classList.remove("is-over");
      if (type === "drop") {
        const file = event.dataTransfer?.files?.[0];
        if (file) handleFile(file);
      }
    });
  });

  document.addEventListener("keydown", (event) => {
    if ((event.key === "Enter" || event.key === " ") && event.target.matches?.('[data-action][role="button"]')) {
      event.preventDefault();
      event.target.click();
    }
    if (event.key === "Escape" && !isModalOpen() && state.sidebarOpen) {
      state.sidebarOpen = false;
      syncSidebar();
    }
  });

  document.addEventListener(
    "error",
    (event) => {
      const target = event.target;
      if (target?.tagName === "IMG") target.remove();
    },
    true
  );
}

async function boot() {
  applyDocumentLang();
  bindEvents();
  registerServiceWorker();
  setupInstall();
  setupNetwork();

  const tg = telegramWebApp();
  if (tg) {
    try {
      tg.ready?.();
      tg.expand?.();
    } catch {
      /* Mini App API может быть ограничен */
    }
  }

  try {
    await loadSession();
  } catch (error) {
    state.error = {
      title: t("TuneBridge не отвечает"),
      message: localize(error.message) || t("Не удалось получить состояние приложения."),
      hint: localize(error.hint) || t("Убедитесь, что сервер запущен, и обновите страницу."),
    };
    state.screen = "error";
    render();
    return;
  }

  if (state.hosted && !state.authenticated) {
    await tryTelegramLogin();
  }
  if (state.hosted && !state.authenticated) {
    state.screen = "auth";
    render();
    return;
  }

  try {
    await refreshState();
  } catch (error) {
    if (error instanceof ApiError && error.auth === "required") {
      state.authenticated = false;
      state.screen = "auth";
      render();
      return;
    }
    state.error = {
      title: t("TuneBridge не отвечает"),
      message: localize(error.message) || t("Не удалось получить состояние приложения."),
      hint: localize(error.hint) || t("Убедитесь, что сервер запущен, и обновите страницу."),
    };
    state.screen = "error";
    render();
    return;
  }

  const connected = handleQueryParams();

  if (connected) {
    const intent = takeStashedIntent();
    if (intent) {
      if (intent.thenSelect) {
        const flow = takeFlow();
        if (flow && (await restoreFlow(flow))) return;
      }
      await resumeIntent(intent, connected);
      return;
    }
  }

  if (state.activeJob) {
    state.job = state.activeJob;
    state.screen = "job";
    render();
    watchJob(state.activeJob.id);
    return;
  }

  state.screen = "home";
  render();
}

boot();
