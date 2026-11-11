import { EN } from "./locale-en.js";

const LANG_KEY = "tunebridge.lang";
const LANGS = ["ru", "en"];
const TITLE_KEY = "TuneBridge — перенос плейлистов";
const DESCRIPTION_KEY =
  "TuneBridge — перенос плейлистов между Яндекс Музыкой, Spotify, YouTube Music, SoundCloud и Apple Music с умным сопоставлением треков.";

function detectLang() {
  try {
    const saved = localStorage.getItem(LANG_KEY);
    if (LANGS.includes(saved)) return saved;
  } catch {
    /* localStorage может быть отключён */
  }
  const nav = String(navigator.language || "ru").toLowerCase();
  return nav.startsWith("ru") ? "ru" : "en";
}

let lang = detectLang();

export function getLang() {
  return lang;
}

export function setLang(next, { persist = true } = {}) {
  if (!LANGS.includes(next)) return lang;
  lang = next;
  if (persist) {
    try {
      localStorage.setItem(LANG_KEY, next);
    } catch {
      /* ignore */
    }
  }
  applyDocumentLang();
  return lang;
}

export function toggleLang() {
  return setLang(lang === "en" ? "ru" : "en");
}

export function locale() {
  return lang === "en" ? "en-US" : "ru-RU";
}

export function t(key, params = null) {
  if (key == null) return "";
  let text = lang === "en" ? EN[key] ?? key : key;
  if (params) {
    text = text.replace(/\{(\w+)\}/g, (match, name) =>
      params[name] == null ? match : String(params[name])
    );
  }
  return text;
}

export function applyDocumentLang() {
  if (typeof document === "undefined") return;
  const html = document.documentElement;
  if (html) html.lang = lang;
  document.title = t(TITLE_KEY);
  document
    .querySelector('meta[name="description"]')
    ?.setAttribute("content", t(DESCRIPTION_KEY));
  document.getElementById("sidebar")?.setAttribute("aria-label", t("Навигация"));
}
