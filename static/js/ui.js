import { icon, SERVICE_META } from "./icons.js";
import { t, getLang, locale } from "./i18n.js";

export function esc(value) {
  return String(value ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

export function safeUrl(value) {
  if (!value) return null;
  const raw = String(value).trim();
  if (!raw) return null;
  if (raw.startsWith("/") && !raw.startsWith("//")) return raw;
  try {
    const url = new URL(raw);
    if (url.protocol === "http:" || url.protocol === "https:") return url.href;
  } catch {
    return null;
  }
  return null;
}

export function coverMarkup(track, className = "cover-sm", service = null) {
  const svc = service || track?.source || "file";
  const name = SERVICE_META[svc]?.icon || "music";
  const url = safeUrl(track?.cover_url);
  return `<div class="cover ${className}">${
    url ? `<img src="${esc(url)}" alt="" loading="lazy" referrerpolicy="no-referrer">` : ""
  }${icon(name)}</div>`;
}

export function fmtDuration(ms) {
  const value = Number(ms);
  if (!Number.isFinite(value) || value <= 0) return "—";
  const total = Math.round(value / 1000);
  const hours = Math.floor(total / 3600);
  const minutes = Math.floor((total % 3600) / 60);
  const seconds = total % 60;
  if (hours > 0) {
    return `${hours}:${String(minutes).padStart(2, "0")}:${String(seconds).padStart(2, "0")}`;
  }
  return `${minutes}:${String(seconds).padStart(2, "0")}`;
}

export function fmtElapsed(seconds) {
  const value = Math.max(0, Math.round(Number(seconds) || 0));
  const minutes = Math.floor(value / 60);
  const rest = value % 60;
  return `${minutes}:${String(rest).padStart(2, "0")}`;
}

export function fmtNumber(value) {
  return new Intl.NumberFormat(locale()).format(Number(value) || 0);
}

export function plural(count, one, few, many) {
  const n = Math.abs(Number(count) || 0);
  if (getLang() === "en") return n === 1 ? one : many;
  const mod100 = n % 100;
  const last = n % 10;
  if (mod100 > 10 && mod100 < 20) return many;
  if (last === 1) return one;
  if (last >= 2 && last <= 4) return few;
  return many;
}

export function fmtTracks(count) {
  return `${fmtNumber(count)} ${plural(count, t("трек"), t("трека"), t("треков"))}`;
}

export function fmtDateTime(timestamp) {
  if (!timestamp) return "—";
  try {
    return new Intl.DateTimeFormat(locale(), {
      day: "numeric",
      month: "long",
      hour: "2-digit",
      minute: "2-digit",
    }).format(new Date(timestamp));
  } catch {
    return "—";
  }
}

export function artistsLine(artists) {
  if (!Array.isArray(artists) || !artists.length) return t("Неизвестный исполнитель");
  return artists.filter(Boolean).join(", ") || t("Неизвестный исполнитель");
}

export function toast(message, { kind = "info", title = "", detail = "", timeout = 4800 } = {}) {
  const root = document.getElementById("toast-root");
  if (!root) return;
  const glyph = kind === "error" ? "alert" : kind === "ok" ? "check" : kind === "warn" ? "alert" : "info";
  const element = document.createElement("div");
  element.className = `toast is-${kind}`;
  element.innerHTML = `${icon(glyph, "toast-icon")}<div class="toast-msg">${
    title ? `<b>${esc(title)}</b>` : ""
  }<span>${esc(message)}</span>${
    detail ? `<span style="display:block;margin-top:2px">${esc(detail)}</span>` : ""
  }</div>`;
  root.appendChild(element);
  const remove = () => {
    element.classList.add("is-out");
    setTimeout(() => element.remove(), 240);
  };
  setTimeout(remove, timeout);
}

let activeModal = null;

export function openModal({ title = "", subtitle = "", body = "", footer = "", size = "", onMount, onClose } = {}) {
  closeModal();
  const root = document.getElementById("modal-root");
  if (!root) return null;

  const backdrop = document.createElement("div");
  backdrop.className = "modal-backdrop";
  backdrop.setAttribute("data-modal-backdrop", "");
  backdrop.innerHTML = `<div class="modal ${size}" role="dialog" aria-modal="true" aria-label="${esc(
    title || t("Окно")
  )}">
    <div class="modal-head">
      <div class="modal-head-text">
        <h2 class="modal-title">${esc(title)}</h2>
        ${subtitle ? `<p class="modal-sub">${esc(subtitle)}</p>` : ""}
      </div>
      <button class="icon-btn modal-close" type="button" data-modal-close aria-label="${t("Закрыть")}">${icon("close")}</button>
    </div>
    <div class="modal-body">${body}</div>
    ${footer ? `<div class="modal-foot">${footer}</div>` : ""}
  </div>`;

  const modal = backdrop.querySelector(".modal");
  root.replaceChildren(backdrop);
  document.body.style.overflow = "hidden";

  const close = (reason = "dismiss") => {
    if (!activeModal || activeModal.backdrop !== backdrop) return;
    activeModal = null;
    root.replaceChildren();
    document.body.style.overflow = "";
    if (typeof onClose === "function") onClose(reason);
  };

  activeModal = { backdrop, modal, close };

  backdrop.addEventListener("click", (event) => {
    if (event.target === backdrop) close("backdrop");
  });
  modal.addEventListener("click", (event) => {
    if (event.target.closest("[data-modal-close]")) close("button");
  });

  if (typeof onMount === "function") {
    queueMicrotask(() => onMount(modal, close));
  }
  return { modal, close };
}

export function closeModal(reason = "programmatic") {
  if (activeModal) activeModal.close(reason);
}

export function isModalOpen() {
  return Boolean(activeModal);
}

document.addEventListener("keydown", (event) => {
  if (event.key === "Escape" && activeModal) activeModal.close("escape");
});

export function confirmDialog({
  title,
  message,
  detail = "",
  confirmText = t("Продолжить"),
  cancelText = t("Отмена"),
  danger = false,
}) {
  return new Promise((resolve) => {
    let settled = false;
    const settle = (value) => {
      if (settled) return;
      settled = true;
      resolve(value);
    };
    openModal({
      title,
      subtitle: message,
      size: "is-sm",
      body: detail ? `<p class="modal-sub" style="margin:0">${esc(detail)}</p>` : "",
      footer: `<button class="btn btn-ghost" type="button" data-confirm-cancel>${esc(cancelText)}</button>
        <button class="btn ${danger ? "btn-danger" : "btn-primary"}" type="button" data-confirm-ok>${esc(
        confirmText
      )}</button>`,
      onMount(modal) {
        modal.querySelector("[data-confirm-ok]")?.addEventListener("click", () => {
          settle(true);
          closeModal();
        });
        modal.querySelector("[data-confirm-cancel]")?.addEventListener("click", () => {
          settle(false);
          closeModal();
        });
      },
      onClose() {
        settle(false);
      },
    });
  });
}

export async function copyText(text) {
  const value = String(text ?? "");
  try {
    await navigator.clipboard.writeText(value);
    toast(t("Скопировано"), { kind: "ok", timeout: 1800 });
    return true;
  } catch {
    const area = document.createElement("textarea");
    area.value = value;
    area.style.position = "fixed";
    area.style.opacity = "0";
    document.body.appendChild(area);
    area.select();
    try {
      document.execCommand("copy");
      toast(t("Скопировано"), { kind: "ok", timeout: 1800 });
      return true;
    } catch {
      toast(t("Не удалось скопировать"), { kind: "error" });
      return false;
    } finally {
      area.remove();
    }
  }
}

export function downloadBlob(blob, filename) {
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  setTimeout(() => URL.revokeObjectURL(url), 5000);
}
