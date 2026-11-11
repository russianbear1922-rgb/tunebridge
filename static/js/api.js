import { t } from "./i18n.js";

export class ApiError extends Error {
  constructor(message, { hint = null, status = 0, activeJob = null, auth = null, payload = null } = {}) {
    super(message);
    this.name = "ApiError";
    this.hint = hint;
    this.status = status;
    this.activeJob = activeJob;
    this.auth = auth;
    this.payload = payload;
  }
}

let csrfToken = null;

export function setCsrf(token) {
  csrfToken = token || null;
}

async function request(path, { method = "GET", body, signal } = {}) {
  const headers = {};
  if (body !== undefined) headers["Content-Type"] = "application/json";
  if (csrfToken && method !== "GET") headers["X-TB-CSRF"] = csrfToken;
  let response;
  try {
    response = await fetch(path, {
      method,
      headers,
      body: body !== undefined ? JSON.stringify(body) : undefined,
      signal,
      credentials: "same-origin",
      cache: "no-store",
    });
  } catch (error) {
    if (error?.name === "AbortError") throw error;
    throw new ApiError(t("Нет связи с TuneBridge"), {
      hint: t("Проверьте, что приложение запущено, и обновите страницу."),
    });
  }

  const type = response.headers.get("content-type") || "";
  let data = null;
  if (type.includes("application/json")) {
    try {
      data = await response.json();
    } catch {
      data = null;
    }
  }

  if (!response.ok) {
    throw new ApiError(data?.message || `${t("Ошибка")} ${response.status}`, {
      hint: data?.hint || null,
      status: response.status,
      activeJob: data?.active_job || null,
      auth: data?.auth || null,
      payload: data || null,
    });
  }
  return data ?? {};
}

export const api = {
  state: () => request("/api/state"),
  session: () => request("/api/session"),
  telegramAuth: (initData) => request("/api/auth/telegram", { method: "POST", body: { init_data: initData } }),
  logout: () => request("/api/auth/logout", { method: "POST", body: {} }),
  wallet: () => request("/api/wallet"),
  topup: (packageId) => request("/api/wallet/topup", { method: "POST", body: { package_id: packageId } }),
  redeemPromo: (code) => request("/api/promo/redeem", { method: "POST", body: { code } }),
  history: () => request("/api/history"),
  adminOverview: () => request("/api/admin/overview"),
  adminStats: () => request("/api/admin/stats"),
  adEvent: (kind) =>
    fetch("/api/ads/event", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ kind }),
      keepalive: true,
      credentials: "same-origin",
    }).catch(() => {}),
  adminCredit: (payload) => request("/api/admin/credit", { method: "POST", body: payload }),
  adminPromos: () => request("/api/admin/promos"),
  adminCreatePromos: (payload) => request("/api/admin/promos", { method: "POST", body: payload }),
  adminTogglePromo: (code, enable) =>
    request(`/api/admin/promos/${encodeURIComponent(code)}/${enable ? "enable" : "disable"}`, {
      method: "POST",
      body: {},
    }),
  adminRefund: (orderId, revoke = true) =>
    request("/api/admin/refund", { method: "POST", body: { order_id: orderId, revoke } }),
  resolve: (service, url) => request("/api/resolve", { method: "POST", body: { service, url } }),
  demo: () => request("/api/demo"),
  importFile: (filename, content) => request("/api/import", { method: "POST", body: { filename, content } }),
  playlists: (service) => request(`/api/playlists/${encodeURIComponent(service)}`),
  search: (target, query, source) =>
    request(`/api/targets/${encodeURIComponent(target)}/search`, {
      method: "POST",
      body: { query, source: source ?? null },
    }),
  startMatch: (playlist, target) =>
    request("/api/jobs/match", { method: "POST", body: { playlist, target } }),
  startTransfer: (playlist, target, matches, title, description, options) =>
    request("/api/jobs/transfer", {
      method: "POST",
      body: { playlist, target, matches, title, description, options },
    }),
  job: (id) => request(`/api/jobs/${encodeURIComponent(id)}`),
  activeJob: () => request("/api/jobs/active"),
  cancel: (id) => request(`/api/jobs/${encodeURIComponent(id)}/cancel`, { method: "POST" }),
  yandexDevice: () => request("/api/connect/yandex/device", { method: "POST" }),
  yandexPoll: () => request("/api/connect/yandex/poll", { method: "POST" }),
  yandexToken: (token) => request("/api/connect/yandex/token", { method: "POST", body: { token } }),
  spotifyClient: (clientId) =>
    request("/api/connect/spotify/client", { method: "POST", body: { client_id: clientId } }),
  youtubeConnect: (headers, authuser = null) =>
    request("/api/connect/youtube", { method: "POST", body: { headers, authuser } }),
  youtubeConnectBrowser: (label = null, authuser = null) =>
    request("/api/connect/youtube/browser", { method: "POST", body: { label, authuser } }),
  telegramConnect: (token) =>
    request("/api/connect/telegram", { method: "POST", body: { token } }),
  telegramChats: () => request("/api/telegram/chats"),
  telegramSend: (playlist, chat, formats) =>
    request("/api/telegram/send", { method: "POST", body: { playlist, chat, formats } }),
  disconnect: (service) => request(`/api/connect/${encodeURIComponent(service)}`, { method: "DELETE" }),
  exportZip: async (playlist, formats) => {
    let response;
    try {
      response = await fetch("/api/export", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ playlist, formats }),
      });
    } catch {
      throw new ApiError(t("Нет связи с TuneBridge"), { hint: t("Проверьте, что приложение запущено.") });
    }
    if (!response.ok) {
      let data = null;
      try {
        data = await response.json();
      } catch {
        data = null;
      }
      throw new ApiError(data?.message || t("Не удалось создать архив"), {
        hint: data?.hint || null,
        status: response.status,
      });
    }
    return response.blob();
  },
};
