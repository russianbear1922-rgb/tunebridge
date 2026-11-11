import { t } from "./i18n.js";

const BRAND = {
  yandex: `<rect width="24" height="24" rx="7.5" fill="#ffdb4d"/><path d="M9.1 16.6V8.4l6.9-1.4v8.1" fill="none" stroke="#141414" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/><circle cx="7.5" cy="16.8" r="2.1" fill="#141414"/><circle cx="14.4" cy="15.4" r="2.1" fill="#141414"/>`,
  spotify: `<circle cx="12" cy="12" r="11" fill="#1ed760"/><path d="M6.6 9.3c3.9-.9 7.9-.6 11.1 1.1M7.3 12.5c3.2-.7 6.5-.4 9.3 1M8.1 15.5c2.5-.5 4.9-.3 7 .8" fill="none" stroke="#07130b" stroke-width="1.7" stroke-linecap="round"/>`,
  youtube: `<circle cx="12" cy="12" r="11" fill="#ff4e45"/><circle cx="12" cy="12" r="6.3" fill="none" stroke="#fff" stroke-width="1.5"/><path d="M10.5 9.3 14.6 12l-4.1 2.7V9.3Z" fill="#fff"/>`,
  soundcloud: `<rect width="24" height="24" rx="7.5" fill="#ff5500"/><path d="M7 16.6h9.3a2.9 2.9 0 0 0 .4-5.7 4.6 4.6 0 0 0-8.6-1.4A3.6 3.6 0 0 0 7 16.6Z" fill="#fff"/>`,
  apple: `<rect width="24" height="24" rx="7.5" fill="#fa243c"/><path d="M15.1 6.7v7.2a2.6 2.6 0 1 1-1.5-2.4V9l-4.1.9v5.2a2.6 2.6 0 1 1-1.5-2.4V8.4l7.1-1.7Z" fill="#fff"/>`,
  file: `<rect x="2" y="2" width="20" height="20" rx="6" fill="#8b7cff" opacity=".18"/><path d="M7.5 7.5h4.2l1.6 1.8h3.2a1.5 1.5 0 0 1 1.5 1.5v5.2a1.5 1.5 0 0 1-1.5 1.5H7.5A1.5 1.5 0 0 1 6 16V9a1.5 1.5 0 0 1 1.5-1.5Z" fill="none" stroke="#c9c1ff" stroke-width="1.4"/><path d="M9 13.2c1.1-2.2 2.2-2.2 3.3 0s2.2 2.2 3.3 0" fill="none" stroke="#b8f36b" stroke-width="1.4" stroke-linecap="round"/>`,
  demo: `<rect x="2" y="2" width="20" height="20" rx="6" fill="#b8f36b" opacity=".14"/><path d="M12 5.6l1.5 4.1 4.1 1.5-4.1 1.5L12 16.8l-1.5-4.1-4.1-1.5 4.1-1.5L12 5.6Z" fill="none" stroke="#b8f36b" stroke-width="1.4" stroke-linejoin="round"/><circle cx="18" cy="6" r="1.2" fill="#b8f36b"/>`,
  telegram: `<rect x="1.5" y="1.5" width="21" height="21" rx="7" fill="#229ed9"/><path d="M5.6 11.9 17.2 7.2c.6-.2 1.1.2.9.9l-1.9 8.9c-.1.5-.5.7-1 .4l-2.7-2-1.3 1.3c-.2.2-.5.3-.7.1l.2-2.9 5.3-4.8c.2-.2 0-.4-.3-.2l-6.4 3.9-2.7-.8c-.6-.2-.6-.9 0-1.1Z" fill="#fff"/>`,
};

const UI = {
  "arrow-right": `<path d="M5 12h13.5M13 6.5l5.5 5.5L13 17.5" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/>`,
  "arrow-left": `<path d="M19 12H5.5M11 6.5 5.5 12l5.5 5.5" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/>`,
  "arrow-up-right": `<path d="M7 17 17 7M8 7h9v9" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/>`,
  "chevron-right": `<path d="m9 5 7 7-7 7" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/>`,
  "chevron-down": `<path d="m5 9 7 7 7-7" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/>`,
  check: `<path d="m4.5 12.5 5 5L19.5 7" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>`,
  close: `<path d="m6 6 12 12M18 6 6 18" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round"/>`,
  search: `<circle cx="10.8" cy="10.8" r="6.3" fill="none" stroke="currentColor" stroke-width="1.8"/><path d="m15.6 15.6 4 4" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/>`,
  swap: `<path d="M4 8h13.5M14 4.5 17.5 8 14 11.5M20 16H6.5M10 12.5 6.5 16l3.5 3.5" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"/>`,
  link: `<path d="M10 13.8a4 4 0 0 0 5.7 0l2.2-2.2a4 4 0 0 0-5.7-5.7l-1.1 1.1" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round"/><path d="M14 10.2a4 4 0 0 0-5.7 0l-2.2 2.2a4 4 0 0 0 5.7 5.7l1.1-1.1" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round"/>`,
  clipboard: `<rect x="6" y="4.5" width="12" height="16" rx="2.5" fill="none" stroke="currentColor" stroke-width="1.7"/><path d="M9.5 4.5V3.8A1.3 1.3 0 0 1 10.8 2.5h2.4a1.3 1.3 0 0 1 1.3 1.3v.7M9 10h6M9 13.5h6M9 17h3.5" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round"/>`,
  upload: `<path d="M12 16V4.5M7.5 9 12 4.5 16.5 9M4.5 15.5v2.8A2.2 2.2 0 0 0 6.7 20.5h10.6a2.2 2.2 0 0 0 2.2-2.2v-2.8" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"/>`,
  download: `<path d="M12 4.5v11.3M7.5 11.5 12 16l4.5-4.5M4.5 15.8v2.5a2.2 2.2 0 0 0 2.2 2.2h10.6a2.2 2.2 0 0 0 2.2-2.2v-2.5" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"/>`,
  play: `<path d="M8.4 5.8v12.4L18.6 12 8.4 5.8Z" fill="currentColor"/>`,
  refresh: `<path d="M20 12a8 8 0 1 1-2.3-5.7M20 4.5V12h-7.3" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/>`,
  trash: `<path d="M4.5 7h15M9 7V5.2c0-.9.7-1.7 1.7-1.7h2.6c1 0 1.7.8 1.7 1.7V7M6.5 7l.8 12.1c.1 1 .9 1.9 2 1.9h5.4c1.1 0 1.9-.9 2-1.9L17.5 7M10 11v6M14 11v6" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round"/>`,
  external: `<path d="M13 5h6v6M19 5l-8 8M17 13.5V18a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V9a2 2 0 0 1 2-2h4.5" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"/>`,
  plug: `<path d="M9 3v5M15 3v5M6.5 8h11v3.2a5.5 5.5 0 0 1-11 0V8ZM12 16.7V21" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"/>`,
  history: `<path d="M4.5 12a7.5 7.5 0 1 0 2.2-5.3M4.5 5.5V11H10" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/><path d="M12 8.2V12l2.8 1.7" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round"/>`,
  transfer: `<path d="M4 8.5h14M14.5 5 18 8.5 14.5 12M20 15.5H6M9.5 12 6 15.5 9.5 19" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"/>`,
  shield: `<path d="M12 3.2 19 6v5.4c0 4.5-2.8 7.7-7 9.4-4.2-1.7-7-4.9-7-9.4V6l7-2.8Z" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linejoin="round"/><path d="m9 12 2.1 2.1L15.3 10" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"/>`,
  spark: `<path d="M12 3.5l1.8 4.9 4.9 1.8-4.9 1.8L12 16.9l-1.8-4.9-4.9-1.8 4.9-1.8L12 3.5ZM18.5 16l.8 2.1 2.2.8-2.2.8-.8 2.1-.8-2.1-2.2-.8 2.2-.8.8-2.1Z" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linejoin="round"/>`,
  wallet: `<rect x="3.2" y="6.2" width="17.6" height="13" rx="3" fill="none" stroke="currentColor" stroke-width="1.7"/><path d="M6.4 6.2V5.4a1.8 1.8 0 0 1 1.8-1.8h8.6M3.6 10.2h17M16.2 14.8h2" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round"/>`,
  star: `<path d="m12 3.6 2.6 5.3 5.8.8-4.2 4.1 1 5.8-5.2-2.8-5.2 2.8 1-5.8-4.2-4.1 5.8-.8L12 3.6Z" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linejoin="round"/>`,
  promo: `<path d="M4 8.2V6.5A1.5 1.5 0 0 1 5.5 5h13A1.5 1.5 0 0 1 20 6.5v1.7a2.3 2.3 0 0 0 0 4.6v3.7a1.5 1.5 0 0 1-1.5 1.5h-13A1.5 1.5 0 0 1 4 16.5v-3.7a2.3 2.3 0 0 0 0-4.6Z" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linejoin="round"/><path d="M9 8.6v6.8" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-dasharray="1.6 2.6"/>`,
  user: `<circle cx="12" cy="8" r="3.4" fill="none" stroke="currentColor" stroke-width="1.7"/><path d="M5.6 19.3c.8-3.1 3.3-5 6.4-5s5.6 1.9 6.4 5" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round"/>`,
  logout: `<path d="M14 5h3.3A1.7 1.7 0 0 1 19 6.7v10.6a1.7 1.7 0 0 1-1.7 1.7H14M10 8l-4 4 4 4M6 12h9" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"/>`,
  music: `<path d="M9 18V6.2l10-1.8v11.2" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"/><circle cx="6.6" cy="18.2" r="2.6" fill="none" stroke="currentColor" stroke-width="1.7"/><circle cx="16.6" cy="16.4" r="2.6" fill="none" stroke="currentColor" stroke-width="1.7"/>`,
  headphones: `<path d="M4.5 14v-2a7.5 7.5 0 0 1 15 0v2" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/><rect x="3.2" y="13.2" width="4.3" height="7" rx="2.1" fill="none" stroke="currentColor" stroke-width="1.7"/><rect x="16.5" y="13.2" width="4.3" height="7" rx="2.1" fill="none" stroke="currentColor" stroke-width="1.7"/>`,
  alert: `<path d="M12 4.2 21 20H3L12 4.2Z" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linejoin="round"/><path d="M12 9.5v4.7" stroke="currentColor" stroke-width="1.9" stroke-linecap="round"/><circle cx="12" cy="17.2" r="1.1" fill="currentColor"/>`,
  info: `<circle cx="12" cy="12" r="9" fill="none" stroke="currentColor" stroke-width="1.8"/><path d="M12 10.7v5.2" stroke="currentColor" stroke-width="1.9" stroke-linecap="round"/><circle cx="12" cy="7.7" r="1.1" fill="currentColor"/>`,
  clock: `<circle cx="12" cy="12" r="8.5" fill="none" stroke="currentColor" stroke-width="1.7"/><path d="M12 7.5V12l3 1.9" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round"/>`,
  eye: `<path d="M2.8 12s3.4-6.2 9.2-6.2S21.2 12 21.2 12s-3.4 6.2-9.2 6.2S2.8 12 2.8 12Z" fill="none" stroke="currentColor" stroke-width="1.7"/><circle cx="12" cy="12" r="2.8" fill="none" stroke="currentColor" stroke-width="1.7"/>`,
  "eye-off": `<path d="M4 4.5 20 20M9.9 6.1A9.9 9.9 0 0 1 12 5.8c5.8 0 9.2 6.2 9.2 6.2a16 16 0 0 1-2.4 3.2M6.3 7.7A16.7 16.7 0 0 0 2.8 12S6.2 18.2 12 18.2c1.3 0 2.5-.3 3.6-.8M10 10a2.8 2.8 0 0 0 4 4" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round"/>`,
  settings: `<circle cx="12" cy="12" r="3.2" fill="none" stroke="currentColor" stroke-width="1.7"/><path d="M19.3 14.6a7.8 7.8 0 0 0 0-5.2l1.4-1.9-2.2-2.2-1.9 1.4a7.8 7.8 0 0 0-5.2 0L9.5 5.3 7.3 7.5l1.4 1.9a7.8 7.8 0 0 0 0 5.2l-1.4 1.9 2.2 2.2 1.9-1.4a7.8 7.8 0 0 0 5.2 0l1.9 1.4 2.2-2.2-1.4-1.9Z" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linejoin="round"/>`,
  menu: `<path d="M4 7h16M4 12h16M4 17h16" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/>`,
  disc: `<circle cx="12" cy="12" r="9" fill="none" stroke="currentColor" stroke-width="1.7"/><circle cx="12" cy="12" r="2.4" fill="none" stroke="currentColor" stroke-width="1.7"/><path d="M12 3v2.2M12 18.8V21M3 12h2.2M18.8 12H21" stroke="currentColor" stroke-width="1.4"/>`,
  wave: `<path d="M3 12c2.2 0 2.2-5 4.4-5s2.2 10 4.4 10 2.2-10 4.4-10 2.2 5 4.4 5" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round"/>`,
  "more-horizontal": `<circle cx="5" cy="12" r="1.4" fill="currentColor"/><circle cx="12" cy="12" r="1.4" fill="currentColor"/><circle cx="19" cy="12" r="1.4" fill="currentColor"/>`,
  "file-text": `<path d="M7 3.5h6.5L18 8v12.5H7V3.5Z" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linejoin="round"/><path d="M13 3.5V8h4.5M10 12h5M10 15.5h5" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round"/>`,
  copy: `<rect x="8" y="8" width="12" height="12" rx="2.5" fill="none" stroke="currentColor" stroke-width="1.7"/><path d="M16 8V5.5A1.5 1.5 0 0 0 14.5 4H5.5A1.5 1.5 0 0 0 4 5.5v9A1.5 1.5 0 0 0 5.5 16H8" fill="none" stroke="currentColor" stroke-width="1.7"/>`,
  send: `<path d="M20.6 3.4 3.8 10.1c-.8.3-.8 1.4 0 1.7l4.1 1.5 1.6 4.8c.2.7 1.1.9 1.6.3l2.4-2.6 4.2 3.1c.6.4 1.5.1 1.6-.6l2.6-13.1c.2-.8-.5-1.4-1.3-1.8Z" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linejoin="round"/><path d="m7.9 13.3 9-6.6-6.8 7.6" fill="none" stroke="currentColor" stroke-width="1.4" stroke-linejoin="round"/>`,
  phone: `<rect x="6.8" y="2.5" width="10.4" height="19" rx="2.6" fill="none" stroke="currentColor" stroke-width="1.7"/><path d="M10.6 18.5h2.8" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round"/>`,
  wifi: `<path d="M3.2 8.7a13.4 13.4 0 0 1 17.6 0M6.1 12a9.2 9.2 0 0 1 11.8 0M9 15.3a4.9 4.9 0 0 1 6 0" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/><circle cx="12" cy="18.6" r="1.2" fill="currentColor"/>`,
  qr: `<rect x="3.5" y="3.5" width="7" height="7" rx="1.4" fill="none" stroke="currentColor" stroke-width="1.6"/><rect x="13.5" y="3.5" width="7" height="7" rx="1.4" fill="none" stroke="currentColor" stroke-width="1.6"/><rect x="3.5" y="13.5" width="7" height="7" rx="1.4" fill="none" stroke="currentColor" stroke-width="1.6"/><path d="M13.5 13.5h3v3h-3zM17.5 17.5h3v3h-3zM13.5 20.5h1.5M20.5 13.5h-1.5" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linejoin="round"/>`,
};

export const SERVICE_META = {
  yandex: {
    get name() {
      return t("Яндекс Музыка");
    },
    get short() {
      return t("Яндекс");
    },
    color: "#ffdb4d",
    tint: "rgba(255, 219, 77, .12)",
    icon: "yandex",
    get hint() {
      return t("ссылка или аккаунт");
    },
    placeholder: "https://music.yandex.ru/playlists/…",
  },
  spotify: {
    name: "Spotify",
    short: "Spotify",
    color: "#1ed760",
    tint: "rgba(30, 215, 96, .12)",
    icon: "spotify",
    get hint() {
      return t("ссылка без входа");
    },
    placeholder: "https://open.spotify.com/playlist/…",
  },
  youtube: {
    name: "YouTube Music",
    short: "YouTube",
    color: "#ff4e45",
    tint: "rgba(255, 78, 69, .12)",
    icon: "youtube",
    get hint() {
      return t("ссылка без входа");
    },
    placeholder: "https://music.youtube.com/playlist?list=…",
  },
  soundcloud: {
    name: "SoundCloud",
    short: "SoundCloud",
    color: "#ff5500",
    tint: "rgba(255, 85, 0, .12)",
    icon: "soundcloud",
    get hint() {
      return t("ссылка на сет");
    },
    placeholder: "https://soundcloud.com/…/sets/…",
  },
  apple: {
    name: "Apple Music",
    short: "Apple Music",
    color: "#fa243c",
    tint: "rgba(250, 36, 60, .12)",
    icon: "apple",
    get hint() {
      return t("ссылка на плейлист");
    },
    placeholder: "https://music.apple.com/…/playlist/…",
  },
  file: {
    get name() {
      return t("Файл");
    },
    get short() {
      return t("Файл");
    },
    color: "#b7a4ff",
    tint: "rgba(183, 164, 255, .12)",
    icon: "file",
    hint: "M3U, CSV, JSON",
    placeholder: "",
  },
  demo: {
    get name() {
      return t("Демо-плеер");
    },
    get short() {
      return t("Демо");
    },
    color: "#b8f36b",
    tint: "rgba(184, 243, 107, .12)",
    icon: "demo",
    get hint() {
      return t("без аккаунтов");
    },
    placeholder: "",
  },
  telegram: {
    name: "Telegram",
    short: "Telegram",
    color: "#229ed9",
    tint: "rgba(34, 158, 217, .14)",
    icon: "telegram",
    get hint() {
      return t("бот и архив");
    },
    placeholder: "",
  },
};

export const TARGET_META = {
  spotify: {
    get description() {
      return t("Плейлист в Spotify. Публичный или приватный.");
    },
    icon: "spotify",
  },
  youtube: {
    get description() {
      return t("Плейлист в YouTube Music с настройкой доступа.");
    },
    icon: "youtube",
  },
  file: {
    get description() {
      return t("M3U8, CSV и JSON одним архивом. Работает без входа.");
    },
    icon: "file",
  },
  demo: {
    get description() {
      return t("Симуляция переноса — чтобы посмотреть весь процесс.");
    },
    icon: "demo",
  },
};

export function icon(name, className = "") {
  const body = UI[name] || BRAND[name] || UI.music;
  return `<svg class="icon ${className}" viewBox="0 0 24 24" aria-hidden="true" focusable="false">${body}</svg>`;
}

export function brandIcon(service, className = "") {
  return icon(SERVICE_META[service]?.icon || "file", `brand-icon ${className}`);
}
