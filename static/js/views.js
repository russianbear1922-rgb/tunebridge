import { icon, brandIcon, SERVICE_META, TARGET_META } from "./icons.js";
import {
  esc,
  safeUrl,
  coverMarkup,
  fmtDuration,
  fmtElapsed,
  fmtNumber,
  fmtTracks,
  fmtDateTime,
  artistsLine,
  plural,
} from "./ui.js";
import { isConnected, profileName } from "./store.js";
import { t, getLang, locale } from "./i18n.js";
import { localize } from "./server-i18n.js";

const SOURCE_ORDER = ["yandex", "spotify", "youtube", "soundcloud", "apple", "demo", "file"];
const CONNECT_ORDER = ["yandex", "spotify", "youtube"];

function serviceName(id) {
  return SERVICE_META[id]?.name || id;
}

function targetName(id) {
  return SERVICE_META[id]?.name || id;
}

function totalDuration(playlist) {
  return (playlist?.tracks || []).reduce((sum, track) => sum + (Number(track.duration_ms) || 0), 0);
}

function adSlot(state) {
  const ad = state.ads;
  if (!ad || (!ad.title && !ad.url)) return "";
  const url = ad.url ? safeUrl(ad.url) : null;
  const image = ad.image && ad.image.startsWith("/") ? ad.image : null;
  const body = `
    ${image ? `<img class="ad-image" src="${esc(image)}" alt="" loading="lazy">` : ""}
    <span class="ad-copy">
      <span class="ad-title">${esc(ad.title || "TuneBridge")}</span>
      ${ad.text ? `<span class="ad-text">${esc(ad.text)}</span>` : ""}
    </span>
    ${url ? `<span class="ad-cta">${esc(ad.cta || t("Подробнее"))}${icon("arrow-right")}</span>` : ""}`;
  const tag = `<span class="ad-tag">${esc(t(ad.label) || t("Реклама"))}</span>`;
  if (!url) return `<aside class="ad-slot" aria-label="${esc(t("Реклама"))}">${tag}<div class="ad-body">${body}</div></aside>`;
  return `<aside class="ad-slot" aria-label="${esc(t("Реклама"))}">${tag}
    <a class="ad-body" href="${esc(url)}" target="_blank" rel="noreferrer noopener" data-ad-link="${esc(url)}">${body}</a>
  </aside>`;
}

export function reviewStats(matches) {
  const stats = { total: matches.length, auto: 0, review: 0, manual: 0, missing: 0, found: 0, included: 0 };
  for (const match of matches) {
    if (match.status === "auto") stats.auto += 1;
    else if (match.status === "review") stats.review += 1;
    else if (match.status === "manual") stats.manual += 1;
    else stats.missing += 1;

    const hasTarget = Boolean(match.target) && match.status !== "missing";
    if (hasTarget) stats.found += 1;
    if (hasTarget && !match._excluded) stats.included += 1;
  }
  return stats;
}

function filteredMatches(matches, filter) {
  if (filter === "all") return matches;
  return matches.filter((match) => (match.status || "missing") === filter);
}

function scoreClass(score) {
  const pct = Math.round((Number(score) || 0) * 100);
  if (pct >= 84) return "score-high";
  if (pct >= 58) return "score-mid";
  return "score-low";
}

function stepsMarkup(state) {
  if (state.screen === "history") {
    return `<span class="crumb-now topbar-history">${t("История переносов")}</span>`;
  }
  const map = { home: 1, playlist: 2, review: 2, job: state.job?.type === "transfer" ? 3 : 2, result: 3 };
  const current = map[state.screen] || 1;
  const items = [
    [t("Источник"), 1],
    [t("Сопоставление"), 2],
    [t("Перенос"), 3],
  ];
  return `<div class="steps">${items
    .map(([label, number], index) => {
      const cls = number < current ? "is-done" : number === current ? "is-current" : "";
      const inner = number < current ? icon("check") : String(number);
      const line = index < items.length - 1 ? `<span class="step-line"></span>` : "";
      return `<div class="step ${cls}"><span class="step-num">${inner}</span><span class="step-label">${label}</span></div>${line}`;
    })
    .join("")}</div>`;
}

/* ------------------------------------------------------------------ shell */

function legalLinks() {
  const lang = getLang();
  return `<span class="legal-links">
    <a href="/privacy?lang=${lang}" data-external>${t("Политика конфиденциальности")}</a>
    <a href="/terms?lang=${lang}" data-external>${t("Условия использования")}</a>
  </span>`;
}

export function sidebar(state) {
  const historyCount = state.history.length;
  const navActive =
    state.screen === "history"
      ? "history"
      : state.screen === "cabinet"
      ? "cabinet"
      : state.screen === "home"
      ? "home"
      : "";
  const account = state.account;
  return `
    <div class="brand" role="button" tabindex="0" data-action="go-home" aria-label="TuneBridge — ${t("на главную")}">
      <img class="brand-mark" src="/static/img/logo.svg" alt="">
      <span class="brand-text">
        <span class="brand-name">TuneBridge</span>
        <span class="brand-sub">${t("перенос плейлистов")}</span>
      </span>
    </div>

    <nav class="nav" aria-label="${t("Разделы")}">
      <button class="nav-item ${navActive === "home" ? "is-active" : ""}" type="button" data-action="go-home">
        ${icon("wave", "nav-icon")}<span class="nav-label">${t("Главная")}</span>
      </button>
      <button class="nav-item ${navActive === "cabinet" ? "is-active" : ""}" type="button" data-action="open-cabinet">
        ${icon("wallet", "nav-icon")}<span class="nav-label">${t("Кабинет")}</span>
        ${account ? `<span class="nav-count">${fmtNumber(account.balance)}</span>` : ""}
      </button>
      <button class="nav-item ${navActive === "history" ? "is-active" : ""}" type="button" data-action="open-history">
        ${icon("history", "nav-icon")}<span class="nav-label">${t("История")}</span>
        ${historyCount ? `<span class="nav-count">${historyCount}</span>` : ""}
      </button>
      <button class="nav-item" type="button" data-action="help">
        ${icon("info", "nav-icon")}<span class="nav-label">${t("Как это работает")}</span>
      </button>
    </nav>

    <div class="side-block">
      <div class="side-head">
        <span class="side-title">${t("Аккаунты")}</span>
        <span class="dim" style="font-size:10.8px">${t("для своих плейлистов")}</span>
      </div>
      <div class="conn-list">
        ${CONNECT_ORDER.map((id) => {
          const meta = SERVICE_META[id];
          const connected = isConnected(id);
          const name = profileName(id);
          return `<button class="conn ${connected ? "is-on" : ""}" type="button" data-action="connect" data-service="${id}" title="${
            connected ? t("Управление подключением") : t("Подключить")
          }">
            <span class="conn-mark">${brandIcon(id)}</span>
            <span class="conn-text">
              <span class="conn-name">${esc(meta.short)}</span>
              <span class="conn-state">${connected ? esc(name || t("подключено")) : t("не подключено")}</span>
            </span>
            <span class="conn-dot"></span>
          </button>`;
        }).join("")}
      </div>
    </div>

    <div class="side-block">
      <div class="side-head">
        <span class="side-title">${t("Доставка")}</span>
        <span class="dim" style="font-size:10.8px">${t("куда забрать")}</span>
      </div>
      <div class="conn-list">
        <button class="conn ${state.telegram?.connected ? "is-on" : ""}" type="button" data-action="telegram" title="${t("Отправка плейлиста в")} Telegram">
          <span class="conn-mark">${brandIcon("telegram")}</span>
          <span class="conn-text">
            <span class="conn-name">Telegram</span>
            <span class="conn-state">${state.telegram?.connected ? esc(state.telegram.profile?.name || t("бот подключён")) : t("не подключён")}</span>
          </span>
          <span class="conn-dot"></span>
        </button>
        ${
          state.hosted
            ? ""
            : `<button class="conn" type="button" data-action="phone" title="${t("Открыть")} TuneBridge ${t("с телефона")}">
          <span class="conn-mark phone-mark">${icon("phone")}</span>
          <span class="conn-text">
            <span class="conn-name">${t("С телефона")}</span>
            <span class="conn-state">${state.phone?.enabled ? t("адрес и QR") : t("по Wi-Fi")}</span>
          </span>
          <span class="conn-dot"></span>
        </button>`
        }
      </div>
    </div>

    <div class="side-foot">
      ${
        account
          ? `<button class="account-card" type="button" data-action="open-cabinet">
              <span class="account-avatar">${esc((account.name || "T").trim().charAt(0).toUpperCase())}</span>
              <span class="account-text">
                <span class="account-name truncate">${esc(localize(account.name) || t("Гость"))}</span>
                <span class="account-sub truncate">${
                  account.username ? `@${esc(account.username)}` : state.hosted ? "Telegram" : t("Локальный режим")
                }</span>
              </span>
              <span class="account-balance">${
                state.freeMode
                  ? `<span class="account-free">${t("Бесплатно")}</span>`
                  : `${fmtNumber(account.balance)}<small>${tracksWord(account.balance)}</small>`
              }</span>
            </button>`
          : ""
      }
      ${
        state.installReady
          ? `<button class="btn btn-ghost btn-block install-btn" type="button" data-action="install-app">${icon("phone")} ${t("Установить приложение")}</button>`
          : ""
      }
      <div class="privacy-card">
        ${icon("shield")}
        ${
          state.hosted
            ? `<span><b>${t("Данные в аккаунте.")}</b> ${t("Подключения сервисов хранятся зашифрованными и видны только вам.")}</span>`
            : `<span><b>${t("Только локально.")}</b> ${t("Токены хранятся в папке")} <span class="mono">data/</span> ${t("на этом компьютере.")}</span>`
        }
      </div>
      ${legalLinks()}
    </div>`;
}

export function topbar(state) {
  return `
    <div class="topbar-inner">
      <div class="row" style="min-width:0">
        <button class="icon-btn mobile-menu-btn" type="button" data-action="toggle-sidebar" aria-label="${t("Открыть меню")}">
          ${icon("menu")}
        </button>
        <span class="mobile-title brand-name">TuneBridge</span>
        ${stepsMarkup(state)}
      </div>
      <div class="topbar-actions">
        <button class="lang-switch" type="button" data-action="toggle-lang" title="${t("Сменить язык")}" aria-label="${t("Сменить язык")}">
          <span class="${getLang() === "ru" ? "is-on" : ""}">RU</span><span class="${getLang() === "en" ? "is-on" : ""}">EN</span>
        </button>
        ${
          state.account && !state.freeMode
            ? `<button class="balance-pill" type="button" data-action="open-cabinet" title="${t("Кошелёк")}" aria-label="${t("Кошелёк")}">
                ${icon("wallet")}<span>${fmtNumber(state.account.balance)}</span>
              </button>`
            : ""
        }
        <span class="local-pill"><span class="dot"></span> ${state.hosted ? "Telegram" : t("Локальный режим")}</span>
        <button class="icon-btn" type="button" data-action="help" aria-label="${t("Как это работает")}" title="${t("Как это работает")}">
          ${icon("info")}
        </button>
      </div>
    </div>`;
}

/* ------------------------------------------------------------------ home */

function stageVisual() {
  return `
    <div class="stage">
      <svg class="stage-path" viewBox="0 0 480 372" preserveAspectRatio="none" aria-hidden="true">
        <path class="glow" d="M126 100 C 262 100, 238 272, 372 282"/>
        <path d="M126 100 C 262 100, 238 272, 372 282"/>
      </svg>

      <div class="node node-src">
        ${brandIcon("yandex")}
        <span class="node-text"><span class="node-name">${t("Яндекс Музыка")}</span><span class="node-meta">${t("источник")}</span></span>
      </div>

      <div class="node node-dst">
        ${brandIcon("spotify")}
        <span class="node-text"><span class="node-name">Spotify</span><span class="node-meta is-done">${t("готово")}</span></span>
      </div>

      <div class="vinyl" aria-hidden="true"><div class="vinyl-label">TB</div></div>

      <div class="float-chip float-chip-a">
        <span class="chip-icon">${icon("music")}</span> Midnight Drive
      </div>
      <div class="float-chip float-chip-b">
        <span class="chip-icon" style="background:rgba(184,243,107,.14);color:var(--lime)">${icon("check")}</span> 87 ${t("треков готовы")}
      </div>
      <div class="float-chip float-chip-c">
        <span class="chip-icon">${icon("headphones")}</span> 18 ${t("треков")}
      </div>

      <div class="match-badge"><b>96%</b><span>${t("совпадение")}</span></div>
    </div>`;
}

export function sourceFeedback(state) {
  const feedback = state.sourceFeedback;
  if (!feedback) {
    const hints = {
      yandex: t("Публичные плейлисты открываются без входа. Для своих — подключите аккаунт."),
      spotify: t("Публичный плейлист откроется сразу. Вход нужен только для своих плейлистов и сохранения."),
      youtube: t("Публичный плейлист откроется сразу. Вход нужен только для своих плейлистов и сохранения."),
      soundcloud: t("Вставьте ссылку на сет — аккаунт не нужен."),
      apple: t("Вставьте ссылку на плейлист Apple Music — аккаунт не нужен."),
    };
    const hint = hints[state.sourceService];
    return hint
      ? `<div class="hint-line">${icon("info")}<span>${esc(hint)}</span></div>`
      : "";
  }
  const kind = feedback.kind === "error" ? "is-err" : feedback.kind === "warn" ? "is-warn" : "";
  const glyph = feedback.kind === "error" ? "alert" : "info";
  return `<div class="hint-line ${kind}">${icon(glyph)}<span>${esc(localize(feedback.message))}${
    feedback.hint ? `<br><span class="dim">${esc(localize(feedback.hint))}</span>` : ""
  }</span></div>`;
}

function serviceTiles(state) {
  return SOURCE_ORDER.map((id) => {
    const meta = SERVICE_META[id];
    const active = state.sourceService === id;
    return `<button class="service-tile ${active ? "is-active" : ""}" type="button" data-action="select-source" data-service="${id}" aria-pressed="${active}">
      <span class="tile-check">${icon("check")}</span>
      <span class="tile-icon" style="--tint:${meta.tint}">${brandIcon(id)}</span>
      <span class="tile-name">${esc(meta.short)}</span>
      <span class="tile-hint">${esc(meta.hint)}</span>
    </button>`;
  }).join("");
}

function urlForm(state, service) {
  const meta = SERVICE_META[service];
  const connected = isConnected(service);
  const canConnect = CONNECT_ORDER.includes(service);
  return `<form class="source-form" data-form="resolve" novalidate>
    <div class="source-form-head">
      <span>${t("Ссылка на плейлист")}</span>
      ${
        connected
          ? `<span class="badge badge-auto">${icon("check")} ${esc(profileName(service) || t("подключено"))}</span>`
          : `<span class="dim" style="font-size:11.5px">${
              canConnect ? t("вход не обязателен") : t("без аккаунта")
            }</span>`
      }
    </div>
    <div class="field">
      <div class="field-row">
        <div class="input-wrap grow">
          <span class="input-icon">${icon("link")}</span>
          <input class="input" name="url" value="${esc(state.sourceUrl)}" placeholder="${esc(
            meta.placeholder
          )}" autocomplete="off" spellcheck="false" inputmode="url">
        </div>
        <button class="btn btn-primary" type="submit">${t("Открыть")} ${icon("arrow-right")}</button>
      </div>
    </div>
    <div class="source-actions">
      ${
        connected
          ? `<button class="btn btn-ghost btn-sm" type="button" data-action="load-playlists" data-service="${service}">${icon(
              "disc"
            )} ${t("Мои плейлисты")}</button>
             <button class="link-btn is-quiet" type="button" data-action="connect" data-service="${service}">
               ${icon("settings")} ${t("Аккаунт")}
             </button>`
          : canConnect
          ? `<button class="btn btn-ghost btn-sm" type="button" data-action="connect" data-service="${service}">${icon(
              "plug"
            )} ${t("Войти в")} ${esc(meta.short)}</button>
             <span class="dim" style="font-size:11.8px">${t("для своих плейлистов")}</span>`
          : `<span class="dim" style="font-size:11.8px">${t("Аккаунт не нужен — просто вставьте ссылку")}</span>`
      }
    </div>
    <div id="source-feedback">${sourceFeedback(state)}</div>
  </form>`;
}

function demoForm() {
  return `<div class="source-form">
    <div class="source-form-head">
      <span>${t("Демо-плейлист «Ночная поездка»")}</span>
      <span class="dim" style="font-size:11.5px">18 ${t("треков")}</span>
    </div>
    <p class="muted" style="margin:0;font-size:13px;line-height:1.55;max-width:560px">
      ${t("Полный цикл без аккаунтов: подбор совпадений, ручная проверка и создание плейлиста")}
      ${t("в демо-плеере. Занимает около тридцати секунд.")}
    </p>
    <div class="source-actions">
      <button class="btn btn-primary" type="button" data-action="load-demo">${icon("play")} ${t("Загрузить демо")}</button>
      <span class="dim" style="font-size:12px">${t("Ничего не отправляется в сеть")}</span>
    </div>
  </div>`;
}

function fileForm(state) {
  return `<div class="source-form">
    <div class="dropzone" data-action="pick-file" role="button" tabindex="0">
      <span class="drop-icon">${icon("upload")}</span>
      <b>${t("Перетащите файл сюда")}</b>
      <span>M3U, M3U8, CSV, JSON ${t("или простой список «Артист — Название»")}</span>
      <small>${t("До 5 МБ · до 2000 треков")}</small>
    </div>
    <input type="file" id="file-input" class="hidden" accept=".m3u,.m3u8,.csv,.json,.txt" data-file-input>
    <div class="source-actions">
      <button class="btn btn-ghost btn-sm" type="button" data-action="pick-file">${icon("file-text")} ${t("Выбрать файл")}</button>
      <span class="dim" style="font-size:12px">${
        state.hosted
          ? t("Файл читается в браузере и уходит только на сервер TuneBridge.")
          : t("Файл читается в браузере и уходит только локальному серверу.")
      }</span>
    </div>
    <div id="source-feedback">${sourceFeedback(state)}</div>
  </div>`;
}

function playlistCards(state) {
  const service = state.sourceService;
  if (state.playlistsLoading) {
    return `<div class="playlist-grid">${Array.from({ length: 8 })
      .map(
        () => `<div class="playlist-card">
          <div class="skeleton" style="width:100%;aspect-ratio:1;border-radius:14px;margin-bottom:9px"></div>
          <div class="skeleton" style="height:12px;width:72%;margin-bottom:6px"></div>
          <div class="skeleton" style="height:10px;width:44%"></div>
        </div>`
      )
      .join("")}</div>`;
  }
  const list = state.playlists[service];
  if (!list) return "";
  if (!list.length) {
    return `<div class="card empty-state">
      ${icon("disc")}
      <b>${t("Плейлистов пока нет")}</b>
      <span>${t("Создайте плейлист в")} ${esc(serviceName(service))} ${t("или откройте его по ссылке.")}</span>
    </div>`;
  }
  return `<div class="playlist-grid">${list
    .map((item, index) => {
      const count = item.track_count || (item.tracks || []).length;
      return `<button class="playlist-card" type="button" data-action="open-playlist" data-service="${service}" data-index="${index}">
        ${coverMarkup(item, "cover", service)}
        <span class="playlist-meta">
          <span class="playlist-name truncate">${esc(item.title || t("Без названия"))}</span>
          <span class="playlist-sub">${fmtTracks(count)}</span>
        </span>
      </button>`;
    })
    .join("")}</div>`;
}

export function homeScreen(state) {
  const playlistsShown = Boolean(state.playlists[state.sourceService]) || state.playlistsLoading;
  const features = [
    ["spark", t("Умное сопоставление"), t("Название, исполнитель, длительность и версии записи — без слепого поиска.")],
    ["eye", t("Ручная проверка"), t("Спорные совпадения вы решаете сами. Любой трек можно заменить.")],
    ["download", t("Файлы"), t("M3U8, CSV и JSON архивом — для любых плееров и скриптов.")],
    state.hosted
      ? [
          "shield",
          t("Данные в аккаунте."),
          t("Подключения сервисов шифруются и привязаны к вашему Telegram. Другие пользователи их не видят."),
        ]
      : ["shield", t("Приватность"), t("Токены остаются в локальной папке data/. Без облака и аккаунтов TuneBridge.")],
  ];
  return `
  <div class="home">
    <section class="hero rise">
      <div class="hero-copy">
        <span class="eyebrow"><span class="dot"></span> ${t("Перенос без потерь")}</span>
        <h1 class="hero-title">${t("Плейлисты")}<br><span class="grad-text">${t("переезжают")}</span> ${t("без потерь")}</h1>
        <p class="hero-lead">
          TuneBridge ${t("переносит музыку между Яндекс Музыкой,")} Spotify, YouTube Music,
          SoundCloud ${t("и")} Apple Music. ${t("Сам находит совпадения, показывает спорные треки —")}
          ${t("и только потом создаёт плейлист.")}
        </p>
        <ul class="hero-points">
          <li class="hero-point">${icon("check")}<span><b>${t("Точный матчинг")}</b> ${t("по названию, артисту и длительности")}</span></li>
          <li class="hero-point">${icon("check")}<span><b>${t("Вы всё контролируете")}</b> — ${t("проверка до переноса")}</span></li>
          <li class="hero-point">${icon("check")}<span>${
            state.hosted
              ? `<b>${t("В вашем аккаунте")}</b> — ${t("подключения защищены и видны только вам")}`
              : `<b>${t("Только локально")}</b> — ${t("аккаунты остаются у вас")}`
          }</span></li>
        </ul>
      </div>
      <div class="hero-visual rise" style="--i:1">${stageVisual()}</div>
    </section>

    ${adSlot(state)}

    <section class="source-card card rise" style="--i:2">
      <div class="source-head">
        <div>
          <h2>${t("Откуда переносим")}</h2>
          <p>${t("Выберите сервис, откройте плейлист по ссылке или загрузите файл.")}</p>
        </div>
        <span class="pill">${icon("spark")} ${SOURCE_ORDER.length} ${t("источников")}</span>
      </div>
      <div class="service-grid">${serviceTiles(state)}</div>
      ${
        state.sourceService === "file"
          ? fileForm(state)
          : state.sourceService === "demo"
          ? demoForm()
          : urlForm(state, state.sourceService)
      }
    </section>

    ${
      playlistsShown
        ? `<section class="section rise" style="--i:3">
            <div class="section-head">
              <div>
                <h2 class="section-title">${t("Мои плейлисты")}</h2>
                <p class="section-sub">${esc(serviceName(state.sourceService))} · ${t("выберите плейлист")}</p>
              </div>
              <button class="link-btn is-quiet" type="button" data-action="close-playlists">${t("Скрыть")}</button>
            </div>
            ${playlistCards(state)}
          </section>`
        : ""
    }

    <section class="section rise" style="--i:4">
      <div class="section-head">
        <div>
          <h2 class="section-title">${t("Под капотом")}</h2>
          <p class="section-sub">${t("Никакой магии — предсказуемый алгоритм и полный контроль.")}</p>
        </div>
      </div>
      <div class="target-grid">
        ${features
          .map(
            ([glyph, title, text]) => `<div class="target-card" style="cursor:default">
              <span class="target-icon">${icon(glyph)}</span>
              <span class="target-name">${title}</span>
              <span class="target-desc">${text}</span>
            </div>`
          )
          .join("")}
      </div>
    </section>
  </div>`;
}

/* -------------------------------------------------------------- playlist */

function targetCards(state) {
  const targets = state.targets.length
    ? state.targets
    : [
        { id: "spotify", requires_auth: true },
        { id: "youtube", requires_auth: true },
        { id: "file", requires_auth: false },
        { id: "demo", requires_auth: false },
      ];
  return targets
    .map((target) => {
      const meta = TARGET_META[target.id] || {};
      const locked = Boolean(target.requires_auth) && !isConnected(target.id);
      const active = state.target === target.id;
      const description =
        target.id === "file"
          ? t("Скачать M3U8, CSV и JSON архивом. Без сопоставления.")
          : meta.description || "";
      return `<button class="target-card ${active ? "is-active" : ""} ${locked ? "is-locked" : ""}" type="button" data-action="select-target" data-target="${
        target.id
      }" aria-pressed="${active}">
        <span class="target-icon">${brandIcon(target.id)}</span>
        <span class="target-name">${esc(targetName(target.id))}${
        locked ? ` <span class="badge badge-review">${t("вход")}</span>` : ""
      }</span>
        <span class="target-desc">${esc(description)}</span>
        <span class="target-check">${icon("check")}</span>
      </button>`;
    })
    .join("");
}

function optionsPanel(state) {
  const target = state.target;
  const options = state.targetOptions;
  if (!target) return "";

  if (target === "file") {
    return `<div class="options-panel card">
      <div class="option-row">
        <div class="option-label"><b>${t("Форматы файлов")}</b><span>${t("Внутри ZIP будет README с инструкцией по импорту.")}</span></div>
        <div class="chips">
          ${[
            ["m3u", "M3U8"],
            ["csv", "CSV"],
            ["json", "JSON"],
          ]
            .map(
              ([value, label]) => `<button class="chip ${
                options.formats.includes(value) ? "is-active" : ""
              }" type="button" data-action="toggle-target-format" data-format="${value}">${label}</button>`
            )
            .join("")}
        </div>
      </div>
      <div class="notice">${icon("info")}<span>${t("Файлы создаются на этом компьютере. Сопоставление и аккаунты не нужны.")}</span></div>
    </div>`;
  }

  if (target === "demo") {
    return `<div class="options-panel card">
      <div class="field">
        <label class="field-label">${t("Название плейлиста")}</label>
        <input class="input" data-field="title" value="${esc(state.playlistTitle)}" maxlength="200" autocomplete="off">
      </div>
      <div class="notice">${icon("spark")}<span>${t("Демо-плеер имитирует создание плейлиста. Никакие данные не отправляются в сеть.")}</span></div>
    </div>`;
  }

  return `<div class="options-panel card">
    <div class="field">
      <label class="field-label">${t("Название плейлиста")}</label>
      <input class="input" data-field="title" value="${esc(state.playlistTitle)}" maxlength="200" autocomplete="off">
    </div>
    <div class="field">
      <label class="field-label">${t("Описание")}</label>
      <input class="input" data-field="description" value="${esc(options.description || "")}" maxlength="300" autocomplete="off"
             placeholder="${t("Оставьте пустым — подставим ссылку на источник")}">
    </div>
    ${
      target === "spotify"
        ? `<div class="option-row">
            <div class="option-label"><b>${t("Публичный плейлист")}</b><span>${t("Будет виден всем, у кого есть ссылка.")}</span></div>
            <button class="switch" type="button" role="switch" aria-checked="${options.public ? "true" : "false"}"
                    data-action="toggle-public" aria-label="${t("Публичный плейлист")}"></button>
          </div>`
        : target === "youtube"
        ? `<div class="option-row">
            <div class="option-label"><b>${t("Доступ")}</b><span>${t("По умолчанию — приватный плейлист.")}</span></div>
            <div class="segmented" data-privacy-group>
              ${[
                ["PRIVATE", t("Приватный")],
                ["UNLISTED", t("По ссылке")],
                ["PUBLIC", t("Публичный")],
              ]
                .map(
                  ([value, label]) => `<button class="seg ${
                    options.privacy === value ? "is-active" : ""
                  }" type="button" data-action="set-privacy" data-privacy="${value}">${label}</button>`
                )
                .join("")}
            </div>
          </div>`
        : ""
    }
  </div>`;
}

export function playlistScreen(state) {
  const playlist = state.playlist;
  if (!playlist) return homeScreen(state);
  const count = playlist.track_count || (playlist.tracks || []).length;
  const service = playlist.service || state.playlistService;
  const duration = totalDuration(playlist);
  const preview = (playlist.tracks || []).slice(0, 250);
  const hidden = Math.max(0, (playlist.tracks || []).length - preview.length);
  const target = state.target;
  const isFile = target === "file";

  return `
  <div class="rise">
    <div class="crumb">
      <button class="link-btn" type="button" data-action="go-home">${icon("arrow-left")} ${t("Другой плейлист")}</button>
      <span class="crumb-sep">/</span>
      <span class="crumb-now">${esc(serviceName(service))}</span>
    </div>

    <section class="playlist-hero card">
      ${coverMarkup(playlist, "cover-xl", service)}
      <div class="playlist-meta-block">
        <span class="src-tag">${brandIcon(service)} ${esc(serviceName(service))}</span>
        <h1 class="playlist-title">${esc(playlist.title || t("Без названия"))}</h1>
        <div class="playlist-sub">
          ${playlist.owner ? `${esc(playlist.owner)} · ` : ""}${fmtTracks(count)}${
    duration ? ` · ${fmtDuration(duration)}` : ""
  }
        </div>
        <div class="playlist-badges">
          ${playlist.url ? `<span class="pill">${icon("link")} ${t("по ссылке")}</span>` : ""}
          ${playlist.description ? `<span class="pill">${icon("file-text")} ${t("есть описание")}</span>` : ""}
          ${(playlist.warnings || []).length ? `<span class="badge badge-review">${icon("alert")} ${t("с замечаниями")}</span>` : ""}
        </div>
      </div>
      <div class="playlist-hero-actions">
        <button class="btn btn-ghost btn-sm" type="button" data-action="go-home">${icon("swap")} ${t("Сменить")}</button>
      </div>
    </section>

    ${(playlist.warnings || [])
      .slice(0, 3)
      .map((warning) => `<div class="warn-box mt-14">${icon("alert")}<span>${esc(localize(warning))}</span></div>`)
      .join("")}

    <section class="section">
      <div class="section-head">
        <div>
          <h2 class="section-title">${t("Куда переносим")}</h2>
          <p class="section-sub">${
            isFile
              ? t("Файлы создаются сразу, без поиска совпадений.")
              : t("Выберите сервис. Аккаунт можно подключить прямо здесь.")
          }</p>
        </div>
        ${target && !isFile ? `<span class="pill">${icon("spark")} ${esc(targetName(target))}</span>` : ""}
      </div>
      <div class="target-grid">${targetCards(state)}</div>
      ${optionsPanel(state)}
      <div class="cta-bar">
        <div class="cta-copy">
          <b>${isFile ? t("Скачать плейлист файлами") : `${t("Подобрать треки в")} ${esc(targetName(target))}`}</b>
          <span>${
            isFile
              ? `${fmtTracks(count)} · ZIP ${t("с")} M3U8, CSV ${t("и")} JSON`
              : `${fmtTracks(count)} · ${t("обычно 1–3 минуты")}${target === "demo" ? t(" · без аккаунтов") : ""}`
          }</span>
        </div>
        <div class="cta-actions">
          <button class="btn btn-primary btn-lg" type="button" data-action="${isFile ? "export" : "start-match"}">
            ${isFile ? t("Скачать архив") : t("Подобрать треки")} ${icon("arrow-right")}
          </button>
        </div>
      </div>
    </section>

    <details class="track-preview card">
      <summary>
        ${icon("music")} ${t("Треки плейлиста")}
        <span class="pill" style="height:22px;font-size:11px">${fmtNumber(count)}</span>
        <span class="chev">${icon("chevron-right")}</span>
      </summary>
      <div class="track-list">
        ${preview
          .map(
            (track, index) => `<div class="track-row">
              <span class="track-index">${index + 1}</span>
              ${coverMarkup(track, "cover-sm", service)}
              <span class="track-main">
                <span class="track-title truncate">${esc(track.title || t("Без названия"))}</span>
                <span class="track-artists truncate">${esc(artistsLine(track.artists))}</span>
              </span>
              <span class="track-dur">${fmtDuration(track.duration_ms)}</span>
            </div>`
          )
          .join("")}
        ${
          hidden > 0
            ? `<div class="track-row"><span></span><span></span><span class="dim" style="font-size:12px">${t("И ещё")} ${fmtTracks(
                hidden
              )}</span><span></span></div>`
            : ""
        }
      </div>
    </details>
  </div>`;
}

/* ---------------------------------------------------------------- review */

function matchRow(state, match, index, targetId) {
  const source = match.source || {};
  const target = match.target;
  const missing = !target || match.status === "missing";
  const excluded = Boolean(match._excluded);
  const pct = Math.round((Number(match.score) || 0) * 100);
  const token = targetName(targetId);

  const score = missing
    ? `<span class="badge badge-missing">${icon("alert")} ${t("нет")}</span>`
    : `<span class="score ${scoreClass(match.score)}" title="${t("Уверенность")} ${pct}%">${pct}%</span>
       <button class="icon-btn sm" type="button" data-action="toggle-exclude" data-index="${index}"
               title="${excluded ? t("Вернуть в перенос") : t("Не переносить")}"
               aria-label="${excluded ? t("Вернуть в перенос") : t("Не переносить")}">${icon(
        excluded ? "eye" : "eye-off"
      )}</button>
       <button class="icon-btn sm" type="button" data-action="search-track" data-index="${index}"
               title="${t("Заменить трек")}" aria-label="${t("Заменить трек")}">${icon("swap")}</button>`;

  return `<div class="match-row ${missing ? "is-missing" : ""} ${excluded ? "is-excluded" : ""} ${
    match.status === "manual" ? "is-manual" : ""
  }" data-index="${index}">
    <div class="mrow-index">${String(index + 1).padStart(2, "0")}</div>

    <div class="song song-source">
      ${coverMarkup(source, "cover-sm", source.service || state.playlistService)}
      <div class="song-text">
        <span class="song-title truncate">${esc(source.title || t("Без названия"))}</span>
        <span class="song-meta truncate">${esc(artistsLine(source.artists))} · ${fmtDuration(source.duration_ms)}</span>
      </div>
    </div>

    <div class="mrow-arrow">${icon("arrow-right")}</div>

    ${
      missing
        ? `<div class="missing-zone">${icon("alert")}<span>${t("Не найден в")} ${esc(token)}</span>
            <button class="link-btn" type="button" data-action="search-track" data-index="${index}">${t("Найти вручную")}</button>
          </div>`
        : `<div class="song song-target">
            ${coverMarkup(target, "cover-sm", targetId)}
            <div class="song-text">
              <span class="song-title truncate">${esc(target.title || "")}</span>
              <span class="song-meta truncate">${esc(artistsLine(target.artists))} · ${fmtDuration(
            target.duration_ms
          )}${match.status === "manual" ? ` · <span style="color:var(--cyan)">${t("вручную")}</span>` : ""}</span>
            </div>
          </div>`
    }

    <div class="mrow-score">${score}</div>
  </div>`;
}

export function reviewScreen(state) {
  const matches = state.matches || [];
  if (!matches.length) {
    return `<div class="error-screen">
      <div class="error-icon">${icon("search")}</div>
      <h2>${t("Совпадений нет")}</h2>
      <p>${t("Вернитесь к плейлисту и попробуйте другой сервис или повторите поиск.")}</p>
      <button class="btn btn-primary mt-14" type="button" data-action="back-to-playlist">${t("К плейлисту")}</button>
    </div>`;
  }

  const stats = reviewStats(matches);
  const coverage = stats.total
    ? stats.found === stats.total
      ? 100
      : Math.floor((stats.found / stats.total) * 100)
    : 0;
  const targetId = state.target;
  const meta = state.matchMeta || {};
  const list = filteredMatches(matches, state.reviewFilter);
  const originalIndex = new Map(matches.map((match, index) => [match, index]));
  const tabs = [
    ["all", t("Все"), stats.total],
    ["auto", t("Авто"), stats.auto],
    ["review", t("Спорные"), stats.review],
    ["manual", t("Вручную"), stats.manual],
    ["missing", t("Не найдены"), stats.missing],
  ].filter(([key, , count]) => key !== "manual" || count > 0);

  const summaryText =
    stats.found === stats.total
      ? `${t("Все треки нашлись в")} ${targetName(targetId)}. ${t("Можно проверить спорные или сразу переносить.")}`
      : `${t("Не хватает")} ${stats.missing} ${plural(stats.missing, t("трек"), t("трека"), t("треков"))}. ${plural(
          stats.missing,
          t("Его можно найти вручную или перенести без него."),
          t("Их можно найти вручную или перенести без них."),
          t("Их можно найти вручную или перенести без них.")
        )}`;

  return `<div class="review-screen rise">
    <section class="summary-card card">
      <div class="ring" style="--p:${coverage}">
        <div class="ring-inner">
          <span class="ring-value">${coverage}%</span>
          <span class="ring-caption">${t("покрытие")}</span>
        </div>
      </div>
      <div class="summary-main">
        <h2>${stats.found === stats.total ? t("Все треки на месте") : `${t("Нашли")} ${stats.found} ${t("из")} ${stats.total}`}</h2>
        <p>${esc(summaryText)}</p>
        <div class="summary-stats">
          <span class="stat-pill is-auto"><span class="dot"></span>${t("Авто")} <b>${stats.auto}</b></span>
          <span class="stat-pill is-review"><span class="dot"></span>${t("Проверить")} <b>${stats.review}</b></span>
          ${stats.manual ? `<span class="stat-pill is-manual"><span class="dot"></span>${t("Вручную")} <b>${stats.manual}</b></span>` : ""}
          <span class="stat-pill is-missing"><span class="dot"></span>${t("Не найдены")} <b>${stats.missing}</b></span>
        </div>
      </div>
      <div class="summary-action">
        <button class="btn btn-ghost" type="button" data-action="rematch">${icon("refresh")} ${t("Искать заново")}</button>
      </div>
    </section>

    ${(meta.warnings || [])
      .slice(0, 2)
      .map((warning) => `<div class="warn-box mt-14">${icon("alert")}<span>${esc(localize(warning))}</span></div>`)
      .join("")}

    <div class="review-toolbar">
      <div class="tabs" role="tablist" aria-label="${t("Фильтр совпадений")}">
        ${tabs
          .map(
            ([key, label, count]) => `<button class="tab ${
              state.reviewFilter === key ? "is-active" : ""
            }" type="button" data-action="set-filter" data-filter="${key}" role="tab" aria-selected="${
              state.reviewFilter === key
            }">${label} <b>${count}</b></button>`
          )
          .join("")}
      </div>
      <span class="dim" style="font-size:11.8px">${t("Уверенность:")} ${Math.round(
        (stats.found ? matches.filter((m) => m.target).reduce((s, m) => s + (m.score || 0), 0) / stats.found : 0) * 100
      )}% ${t("в среднем")}</span>
    </div>

    <div class="match-list">
      ${
        list.length
          ? list
              .map((match) => matchRow(state, match, originalIndex.get(match), targetId))
              .join("")
          : `<div class="card empty-state">${icon("check")}<b>${t("Здесь пусто")}</b><span>${t("В этой категории нет треков — выберите другой фильтр.")}</span></div>`
      }
    </div>

    <div class="sticky-bar">
      <div class="sticky-inner">
        <div class="sticky-copy">
          <b>${t("К переносу:")} ${fmtTracks(stats.included)}</b>
          <span>${t("из")} ${fmtNumber(stats.total)}${stats.missing ? ` · ${stats.missing} ${t("не найдено")}` : ""} · ${t("в")} ${esc(
    targetName(targetId)
  )}${state.hosted && targetId !== "demo" ? ` · ${t("спишется")} ${fmtTracks(stats.included)}` : ""}</span>
        </div>
        <div class="sticky-actions">
          <button class="btn btn-ghost" type="button" data-action="export" ${
            state.playlist ? "" : "disabled"
          }>${icon("download")} ${t("Файл")}</button>
          <button class="btn btn-primary" type="button" data-action="transfer" ${
            stats.included ? "" : "disabled"
          }>${t("Перенести")} ${icon("arrow-right")}</button>
        </div>
      </div>
    </div>
  </div>`;
}

/* ------------------------------------------------------------------- job */

export function jobPercent(job) {
  if (!job) return 0;
  if (job.status === "done" && job.total > 0) return 100;
  if (!job.total) return job.status === "done" ? 100 : 0;
  return Math.max(0, Math.min(100, Math.round((job.done / job.total) * 100)));
}

export function jobPhaseLabel(job) {
  if (!job) return "";
  if (job.status === "error") return localize(job.error) || t("Ошибка");
  if (job.status === "cancelled") return t("Задача остановлена");
  if (job.status === "done") return t("Готово");
  if (job.status === "cancelling") return t("Останавливаем…");
  const map = {
    starting: t("Подготавливаем задачу"),
    searching: t("Ищем совпадения"),
    creating: t("Создаём плейлист"),
    adding: t("Добавляем треки"),
  };
  return localize(job.message) || map[job.phase] || t("Работаем…");
}

export function jobMetrics(job) {
  return `
    <div class="metric"><span class="metric-value">${fmtNumber(job.done)}</span><span class="metric-label">${t("Обработано")}</span></div>
    <div class="metric"><span class="metric-value">${fmtNumber(job.total)}</span><span class="metric-label">${t("Всего")}</span></div>
    <div class="metric"><span class="metric-value">${fmtElapsed(job.elapsed)}</span><span class="metric-label">${t("Время")}</span></div>`;
}

function timeOf(timestamp) {
  try {
    return new Date(timestamp * 1000).toLocaleTimeString(locale(), {
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
    });
  } catch {
    return "—";
  }
}

export function eventList(events) {
  if (!events || !events.length) {
    return `<div class="event"><span class="event-time">—</span><span class="event-msg dim">${t("Пока без событий")}</span></div>`;
  }
  return events
    .slice()
    .reverse()
    .map(
      (event) => `<div class="event is-${event.kind || "info"}">
        <span class="event-time">${timeOf(event.t)}</span>
        <span class="event-msg">${esc(localize(event.text))}</span>
      </div>`
    )
    .join("");
}

export function jobScreen(state) {
  const job = state.job;
  if (!job) {
    return `<div class="error-screen"><div class="error-icon">${icon("clock")}</div><h2>${t("Нет активной задачи")}</h2><p>${t("Вернитесь на главную и начните перенос.")}</p><button class="btn btn-primary mt-14" type="button" data-action="go-home">${t("На главную")}</button></div>`;
  }
  const pct = jobPercent(job);
  const isTransfer = job.type === "transfer";
  return `<div class="job-screen rise">
    <div class="job-card card">
      <div class="ring" id="job-ring" style="--p:${pct};--size:184px">
        <div class="ring-inner">
          <span class="ring-value" id="job-ring-value">${pct}%</span>
          <span class="ring-caption">${t("готово")}</span>
        </div>
      </div>
      <h2 class="job-title">${esc(localize(job.title) || (isTransfer ? t("Перенос") : t("Поиск")))}</h2>
      <p class="job-phase" id="job-phase">${esc(jobPhaseLabel(job))}</p>
      <div class="job-current" id="job-current">${
        job.current
          ? `${icon("music")}<span class="truncate">${esc(job.current)}</span>`
          : `<span class="dim">${t("Готовим задачу…")}</span>`
      }</div>
      <div class="progress"><div class="progress-bar" id="job-bar" style="width:${pct}%"></div></div>
      <div class="job-metrics" id="job-metrics">${jobMetrics(job)}</div>
      <div class="job-actions">
        <button class="btn btn-danger btn-sm" type="button" data-action="cancel-job" ${
          job.status === "cancelling" ? "disabled" : ""
        }>${icon("close")} ${job.status === "cancelling" ? t("Останавливаем…") : t("Остановить")}</button>
        <span class="dim" style="font-size:11.5px;align-self:center">${t("Окно можно закрыть — задача продолжится.")}</span>
      </div>
    </div>
    <div class="event-log card">
      <h3>${t("Журнал")}</h3>
      <div class="event-list" id="job-events">${eventList(job.events)}</div>
    </div>
  </div>`;
}

/* ---------------------------------------------------------------- result */

export function resultScreen(state) {
  const result = state.result;
  const job = state.resultJob;
  if (!result) {
    return `<div class="error-screen"><div class="error-icon">${icon("alert")}</div><h2>${t("Результат недоступен")}</h2><p>${t("Задача завершилась без данных о переносе.")}</p><button class="btn btn-primary mt-14" type="button" data-action="go-home">${t("На главную")}</button></div>`;
  }

  const cancelled = job?.status === "cancelled";
  const failed = job?.status === "error";
  const issueCount = (result.failed || 0) + (result.skipped || 0);
  const total = (result.added || 0) + (result.failed || 0) + (result.skipped || 0);
  const warn = cancelled || failed || (result.failed || 0) > 0;
  const title = cancelled
    ? t("Перенос остановлен")
    : failed
    ? t("Перенос прерван")
    : warn
    ? t("Плейлист готов с замечаниями")
    : t("Плейлист готов");
  const target = localize(result.target_name) || targetName(result.target);
  const url = safeUrl(result.url);
  const subtitle = cancelled
    ? `${t("Успели добавить")} ${result.added || 0} ${t("из")} ${total} ${t("треков. Остальные можно перенести заново.")}`
    : `${t("Добавлено")} ${result.added || 0} ${t("из")} ${total} ${t("треков в")} ${target}.${
        result.skipped ? ` ${result.skipped} ${t("пропущено.")}` : ""
      }${result.demo ? t(" Это был демо-перенос — данные никуда не отправлялись.") : ""}`;

  return `<div class="result-screen rise">
    <section class="result-hero card">
      <div class="success-mark ${warn ? "is-warn" : ""}">${icon(warn ? "alert" : "check")}</div>
      <h2 class="result-title">«${esc(result.title || t("Плейлист"))}» — ${title.toLowerCase()}</h2>
      <p class="result-sub">${esc(subtitle)}</p>
      <div class="result-actions">
        ${
          url
            ? `<a class="btn btn-primary btn-lg" href="${esc(url)}" target="_blank" rel="noreferrer">${icon(
                "external"
              )} ${t("Открыть в")} ${esc(target)}</a>`
            : `<button class="btn btn-primary btn-lg" type="button" data-action="export" ${
                state.playlist ? "" : "disabled"
              }>${icon("download")} ${t("Скачать архив")}</button>`
        }
        ${
          url && state.playlist
            ? `<button class="btn btn-ghost btn-lg" type="button" data-action="export">${icon("download")} ${t("Скачать архив")}</button>`
            : ""
        }
        ${
          state.playlist
            ? `<button class="btn btn-ghost btn-lg" type="button" data-action="telegram">${icon("telegram")} ${t("В Telegram")}</button>`
            : ""
        }
        <button class="btn btn-quiet" type="button" data-action="go-home">${t("Новый плейлист")}</button>
      </div>
      ${
        result.source_title
          ? `<div class="row" style="justify-content:center;margin-top:14px;flex-wrap:wrap;gap:8px">
              <span class="src-tag">${brandIcon(result.source_service)} ${esc(result.source_title)}</span>
              ${icon("arrow-right", "dim")}
              <span class="src-tag">${brandIcon(result.target)} ${esc(target)}</span>
            </div>`
          : ""
      }
      ${
        failed && job?.hint
          ? `<div class="warn-box mt-14" style="text-align:left;max-width:560px">${icon("alert")}<span>${esc(
              localize(job.error) || t("Ошибка")
            )}${job.hint ? `<br><span class="dim">${esc(localize(job.hint))}</span>` : ""}</span></div>`
          : ""
      }
    </section>

    ${adSlot(state)}

    <div class="result-metrics">
      <div class="rmetric is-ok"><span class="rmetric-value">${fmtNumber(result.added || 0)}</span><span class="rmetric-label">${t("Добавлено")}</span></div>
      <div class="rmetric ${result.skipped ? "is-warn" : ""}"><span class="rmetric-value">${fmtNumber(
    result.skipped || 0
  )}</span><span class="rmetric-label">${t("Пропущено")}</span></div>
      <div class="rmetric ${result.failed ? "is-miss" : ""}"><span class="rmetric-value">${fmtNumber(
    result.failed || 0
  )}</span><span class="rmetric-label">${t("Ошибки")}</span></div>
      <div class="rmetric"><span class="rmetric-value">${fmtElapsed(job?.elapsed || 0)}</span><span class="rmetric-label">${t("Время")}</span></div>
    </div>

    ${
      result.billing
        ? `<p class="cabinet-hint" style="text-align:center">${t("Списано")} ${fmtTracks(result.billing.charged)}${
            result.billing.refunded
              ? ` · ${t("возвращено за неудачные")} ${fmtTracks(result.billing.refunded)}`
              : ""
          }</p>`
        : ""
    }

    ${
      (result.failed_tracks || []).length
        ? `<div class="issue-list card">
            <h3>${t("Не удалось добавить")}</h3>
            ${result.failed_tracks
              .slice(0, 20)
              .map(
                (track) => `<div class="issue-row">
                  <div class="song" style="min-width:0">
                    <div class="song-text">
                      <span class="song-title truncate">${esc(track.title || t("Без названия"))}</span>
                      <span class="song-meta truncate">${esc(artistsLine(track.artists))}</span>
                    </div>
                  </div>
                  <span class="badge badge-missing">${t("ошибка")}</span>
                </div>`
              )
              .join("")}
            ${
              result.failed_tracks.length > 20
                ? `<div class="dim" style="font-size:11.5px">${t("И ещё")} ${result.failed_tracks.length - 20}</div>`
                : ""
            }
          </div>`
        : issueCount
        ? `<div class="notice">${icon("info")}<span>${result.skipped || 0} ${t("треков пропущено: не найдены в")} ${
            esc(target)
          } ${t("или были дублями. Вернитесь к сопоставлению, чтобы найти их вручную.")}</span></div>`
        : ""
    }
  </div>`;
}

/* --------------------------------------------------------------- cabinet */

const TX_KINDS = {
  trial: "Приветственные",
  topup: "Пополнение",
  promo: "Промокод",
  admin: "Начисление",
  refund: "Возврат",
  spend: "Списание",
};

const ORDER_STATUS = {
  pending: "Ждёт оплаты",
  paid: "Оплачен",
  refunded: "Возвращён",
  sandbox: "Тестовый",
};

function tracksWord(count) {
  return plural(count, t("трек"), t("трека"), t("треков"));
}

function starsWord(count) {
  return plural(count, t("звезда"), t("звезды"), t("звёзд"));
}

function packageCard(pkg) {
  return `<button class="package-card ${pkg.best ? "is-best" : ""}" type="button" data-action="topup" data-package="${esc(pkg.id)}">
    ${pkg.best ? `<span class="package-flag">${t("Выгодно")}</span>` : ""}
    <span class="package-tokens">${fmtNumber(pkg.tokens)}</span>
    <span class="package-unit">${tracksWord(pkg.tokens)}</span>
    <span class="package-price">${icon("star")} ${fmtNumber(pkg.stars)}</span>
    <span class="package-rub">${t("≈")} ${fmtNumber(pkg.rub)} ₽</span>
    <span class="package-per">${fmtNumber(pkg.per_track)} ₽ ${t("за трек")}</span>
  </button>`;
}

function transactionRow(item) {
  const positive = item.delta > 0;
  const kind = TX_KINDS[item.kind] ? t(TX_KINDS[item.kind]) : t("Операция");
  return `<div class="tx-row">
    <span class="tx-icon ${positive ? "is-plus" : "is-minus"}">${icon(positive ? "download" : "upload")}</span>
    <span class="tx-main">
      <span class="tx-title">${esc(kind)}</span>
      <span class="tx-sub truncate">${esc(localize(item.reason) || "")} · ${fmtDateTime(item.created_at)}</span>
    </span>
    <span class="tx-amount ${positive ? "is-plus" : "is-minus"}">${positive ? "+" : ""}${fmtNumber(item.delta)}</span>
  </div>`;
}

function orderRow(order, isAdmin) {
  const status = ORDER_STATUS[order.status] ? t(ORDER_STATUS[order.status]) : order.status;
  const badge =
    order.status === "paid" ? "badge-auto" : order.status === "refunded" ? "badge-missing" : "badge-neutral";
  return `<div class="order-row">
    <span class="order-main">
      <span class="order-title">${esc(localize(order.title))} · ${fmtNumber(order.tokens)} ${tracksWord(order.tokens)}</span>
      <span class="order-sub">${fmtNumber(order.stars)} ${starsWord(order.stars)} · ${fmtDateTime(order.created_at)}</span>
    </span>
    <span class="badge ${badge}">${esc(status)}</span>
    ${
      isAdmin && order.status === "paid"
        ? `<button class="icon-btn" type="button" data-action="admin-refund" data-order="${esc(order.id)}" title="${t("Вернуть звёзды")}" aria-label="${t("Вернуть звёзды")}">${icon("refresh")}</button>`
        : ""
    }
  </div>`;
}

function transferRow(item) {
  const url = safeUrl(item.url);
  return `<div class="history-item">
    <span class="history-icon">${icon("transfer")}</span>
    <div class="history-main">
      <span class="history-title truncate">«${esc(item.source_title || t("Плейлист"))}» → ${esc(
    localize(item.target_name) || item.target
  )}</span>
      <span class="history-sub">${fmtDateTime(item.created_at)} · ${fmtNumber(item.added)} ${t("из")} ${fmtNumber(
    item.total
  )} ${plural(item.total, t("трек"), t("трека"), t("треков"))}</span>
    </div>
    ${url ? `<a class="icon-btn" href="${esc(url)}" target="_blank" rel="noreferrer" aria-label="${t("Открыть плейлист")}">${icon("external")}</a>` : ""}
  </div>`;
}

function adminStatsPanel(state) {
  const s = state.adminStats;
  const counters = s
    ? [
        [s.users, t("Пользователи")],
        [s.new_users, t("Новых за 7 дней")],
        [s.transfers, t("Переносов")],
        [s.tracks, t("Добавлено треков")],
        [s.ads?.views ?? 0, t("Показов рекламы")],
        [s.ads?.clicks ?? 0, t("Кликов по рекламе")],
      ]
    : [];
  const mixList = (items, nameFn) =>
    items?.length
      ? `<div class="promo-list">${items
          .map(
            (item) =>
              `<div class="promo-row"><span class="promo-code">${esc(nameFn(item.id))}</span><span class="promo-meta">${fmtNumber(
                item.count
              )}</span></div>`
          )
          .join("")}</div>`
      : `<p class="dim">${t("Пока нет данных.")}</p>`;
  return `<section class="admin-panel">
    <div class="section-head" style="margin-bottom:14px">
      <div>
        <h2 class="section-title" style="font-size:20px">${t("Статистика сервиса")}</h2>
        <p class="section-sub">${t("Пользователи, переносы и реклама. Видно только администратору.")}</p>
      </div>
      <button class="btn btn-ghost btn-sm" type="button" data-action="admin-stats-load">${icon("refresh")} ${t("Обновить")}</button>
    </div>
    ${state.adminStatsError ? `<div class="inline-note is-error">${icon("alert")} ${esc(localize(state.adminStatsError))}</div>` : ""}
    ${
      !s
        ? `<div class="card admin-empty"><b>${t("Статистика пока не загружена")}</b><span>${t("Нажмите «Обновить», чтобы увидеть цифры.")}</span></div>`
        : `<div class="admin-stats">
            ${counters
              .map(([value, label]) => `<div class="admin-stat"><span>${fmtNumber(value)}</span><small>${label}</small></div>`)
              .join("")}
          </div>
          <div class="admin-grid">
            <div class="card admin-card">
              <div class="block-head"><h3>${t("Источники")}</h3>${icon("wave")}</div>
              ${mixList(s.sources, serviceName)}
            </div>
            <div class="card admin-card">
              <div class="block-head"><h3>${t("Цели")}</h3>${icon("transfer")}</div>
              ${mixList(s.targets, targetName)}
            </div>
          </div>
          <div class="card admin-card" style="margin-top:14px">
            <div class="block-head"><h3>${t("Реклама по дням")}</h3><span class="dim">CTR ${s.ads?.ctr ?? 0}%</span></div>
            ${
              s.ads?.days?.length
                ? `<div class="promo-table">${s.ads.days
                    .map(
                      (day) =>
                        `<div class="promo-row"><span class="promo-code mono">${esc(day.day)}</span><span class="promo-meta">${fmtNumber(
                          day.view
                        )} ${t("показов")} · ${fmtNumber(day.click)} ${t("кликов")}</span></div>`
                    )
                    .join("")}</div>`
                : `<p class="dim">${t("Показов рекламы пока не было.")}</p>`
            }
          </div>
          <div class="card admin-card" style="margin-top:14px">
            <div class="block-head"><h3>${t("Последние переносы")}</h3><span class="dim">${fmtNumber(s.recent?.length || 0)}</span></div>
            ${
              s.recent?.length
                ? `<div class="history-list">${s.recent
                    .map(
                      (item) =>
                        `<div class="history-item"><span class="history-icon">${icon("transfer")}</span><div class="history-main"><span class="history-title truncate">«${esc(
                          item.source_title || t("Плейлист")
                        )}» → ${esc(item.target_name || item.target)}</span><span class="history-sub">${esc(
                          item.user
                        )} · ${fmtDateTime(item.created_at)} · ${fmtNumber(item.added)} ${t("из")} ${fmtNumber(item.total)}</span></div></div>`
                    )
                    .join("")}</div>`
                : `<p class="dim">${t("Переносов пока нет.")}</p>`
            }
          </div>`
    }
  </section>`;
}

function adminPanel(state) {
  const admin = state.admin;
  return `<section class="admin-panel">
    <div class="section-head" style="margin-bottom:14px">
      <div>
        <h2 class="section-title" style="font-size:20px">${t("Админ-панель")}</h2>
        <p class="section-sub">${t("Начисления, промокоды и возвраты звёзд.")}</p>
      </div>
      <button class="btn btn-ghost btn-sm" type="button" data-action="admin-load">${icon("refresh")} ${t("Обновить")}</button>
    </div>
    ${state.adminError ? `<div class="inline-note is-error">${icon("alert")} ${esc(localize(state.adminError))}</div>` : ""}
    ${
      !admin
        ? `<div class="card admin-empty"><b>${t("Статистика пока не загружена")}</b><span>${t("Нажмите «Обновить», чтобы увидеть цифры и заказы.")}</span></div>`
        : `<div class="admin-stats">
            ${[
              ["users", t("Пользователи")],
              ["balances", t("Токенов на счетах")],
              ["paid_stars", t("Оплачено звёзд")],
              ["paid_tokens", t("Продано треков")],
              ["active_promos", t("Активных промокодов")],
            ]
              .map(
                ([key, label]) =>
                  `<div class="admin-stat"><span>${fmtNumber(admin[key])}</span><small>${label}</small></div>`
              )
              .join("")}
          </div>
          <div class="admin-grid">
            <div class="card admin-card">
              <div class="block-head"><h3>${t("Новые промокоды")}</h3>${icon("promo")}</div>
              <form class="admin-form" data-form="admin-promo">
                <div class="admin-form-row">
                  <label class="field"><span class="field-label">${t("Токенов на код")}</span><input class="input" name="tokens" type="number" min="1" max="100000" value="100" required></label>
                  <label class="field"><span class="field-label">${t("Количество")}</span><input class="input" name="count" type="number" min="1" max="50" value="1" required></label>
                </div>
                <div class="admin-form-row">
                  <label class="field"><span class="field-label">${t("Активаций на код")}</span><input class="input" name="max_uses" type="number" min="0" max="100000" value="1" required></label>
                  <label class="field"><span class="field-label">${t("Срок, дней")}</span><input class="input" name="days" type="number" min="0" max="365" value="30" required></label>
                </div>
                <label class="field"><span class="field-label">${t("Комментарий")}</span><input class="input" name="note" type="text" maxlength="200" placeholder="${t("Например, для друзей")}"></label>
                <button class="btn btn-primary" type="submit">${icon("spark")} ${t("Создать")}</button>
              </form>
              ${state.adminCodes?.length ? `<div class="promo-list">
                ${state.adminCodes
                  .map(
                    (item) =>
                      `<div class="promo-row"><span class="promo-code mono">${esc(item.code)}</span><span class="promo-meta">${fmtNumber(
                        item.tokens
                      )} ${t("токенов")} · ${fmtNumber(item.max_uses)} ${t("активаций")}</span><button class="icon-btn" type="button" data-action="copy-text" data-copy="${esc(
                        item.code
                      )}" aria-label="${t("Скопировать")}">${icon("copy")}</button></div>`
                  )
                  .join("")}
              </div>` : ""}
            </div>
            <div class="card admin-card">
              <div class="block-head"><h3>${t("Начислить вручную")}</h3>${icon("wallet")}</div>
              <form class="admin-form" data-form="admin-credit">
                <label class="field"><span class="field-label">Telegram ID</span><input class="input" name="telegram_id" type="number" min="1" placeholder="123456789" required></label>
                <label class="field"><span class="field-label">${t("Токены")}</span><input class="input" name="tokens" type="number" min="-100000" max="100000" value="100" required></label>
                <label class="field"><span class="field-label">${t("Комментарий")}</span><input class="input" name="reason" type="text" maxlength="200" placeholder="${t("За что начисление")}"></label>
                <button class="btn btn-primary" type="submit">${icon("user")} ${t("Начислить")}</button>
              </form>
            </div>
          </div>
          <div class="card admin-card" style="margin-top:14px">
            <div class="block-head"><h3>${t("Последние заказы")}</h3><span class="dim">${fmtNumber(admin.orders?.length || 0)}</span></div>
            ${admin.orders?.length ? admin.orders.map((order) => orderRow(order, true)).join("") : `<p class="dim">${t("Заказов пока нет.")}</p>`}
          </div>
          <div class="card admin-card" style="margin-top:14px">
            <div class="block-head"><h3>${t("Промокоды")}</h3><span class="dim">${fmtNumber(admin.promos?.length || 0)}</span></div>
            ${
              admin.promos?.length
                ? `<div class="promo-table">${admin.promos
                    .map(
                      (item) =>
                        `<div class="promo-row">
                          <span class="promo-code mono">${esc(item.code)}</span>
                          <span class="promo-meta">${fmtNumber(item.tokens)} ${t("токенов")} · ${fmtNumber(
                          item.used_count
                        )}/${item.max_uses ? fmtNumber(item.max_uses) : "∞"} · ${
                          item.expires_at ? fmtDateTime(item.expires_at) : t("бессрочно")
                        }</span>
                          <span class="badge ${item.active && !item.expired && !item.exhausted ? "badge-auto" : "badge-neutral"}">${
                          item.expired ? t("Истёк") : item.exhausted ? t("Использован") : item.active ? t("Активен") : t("Отключён")
                        }</span>
                          <button class="btn btn-quiet btn-sm" type="button" data-action="admin-toggle-promo" data-code="${esc(
                            item.code
                          )}" data-active="${item.active ? "1" : "0"}">${item.active ? t("Отключить код") : t("Включить код")}</button>
                        </div>`
                    )
                    .join("")}</div>`
                : `<p class="dim">${t("Промокодов пока нет.")}</p>`
            }
          </div>`
    }
  </section>`;
}

export function cabinetScreen(state) {
  const account = state.account || {};
  const wallet = state.wallet;
  const transactions = wallet?.transactions || [];
  const orders = wallet?.orders || [];
  const transfers = wallet?.transfers || [];
  const packages = wallet?.packages || state.packages || [];
  const balance = account.balance ?? wallet?.balance ?? 0;
  const loading = state.walletLoading;
  return `<div class="cabinet-screen rise">
    <div class="cabinet-head">
      <div class="cabinet-id">
        <span class="cabinet-avatar">${esc((account.name || "T").trim().charAt(0).toUpperCase())}</span>
        <div>
          <h1 class="section-title" style="font-size:26px">${t("Личный кабинет")}</h1>
          <p class="section-sub">${
            account.username ? `@${esc(account.username)}` : state.hosted ? "Telegram" : t("Локальный режим")
          }${state.hosted ? ` · ${t("вход через Mini App")}` : ""}</p>
        </div>
      </div>
      <div class="row" style="gap:8px;flex-wrap:wrap">
        ${
          state.hosted
            ? `<button class="btn btn-ghost btn-sm" type="button" data-action="logout">${icon("logout")} ${t("Выйти")}</button>`
            : ""
        }
        <button class="btn btn-ghost btn-sm" type="button" data-action="refresh-cabinet" ${loading ? "disabled" : ""}>${icon(
    "refresh"
  )} ${t("Обновить")}</button>
      </div>
    </div>
    ${state.cabinetError ? `<div class="inline-note is-error">${icon("alert")} ${esc(localize(state.cabinetError))}</div>` : ""}
    <div class="wallet-panel card">
      <div class="wallet-main">
        ${
          state.freeMode
            ? `<span class="wallet-label">${t("Бесплатный доступ")}</span>
        <div class="wallet-amount"><span>${t("Бесплатно")}</span><small>${t("навсегда")}</small></div>
        <p class="wallet-note">${t("Переносы без токенов и лимитов. Никаких списаний и подписок.")}</p>
        <span class="wallet-trial">${icon("spark")} ${t("Все функции открыты")}</span>`
            : `<span class="wallet-label">${t("Баланс")}</span>
        <div class="wallet-amount"><span>${fmtNumber(balance)}</span><small>${tracksWord(balance)}</small></div>
        <p class="wallet-note">${t("Один токен — один добавленный трек. Неудачные совпадения не списываются.")}</p>
        <form class="promo-form" data-form="promo">
          ${icon("promo", "promo-icon")}
          <input class="input" type="text" name="code" placeholder="${t("Введите промокод")}" autocomplete="off" spellcheck="false" maxlength="24" aria-label="${t("Промокод")}">
          <button class="btn btn-primary" type="submit">${t("Активировать")}</button>
        </form>
        ${
          account.trial_granted
            ? `<span class="wallet-trial">${icon("spark")} ${t("Приветственные треки уже начислены.")}</span>`
            : ""
        }`
        }
      </div>
      <div class="wallet-art" aria-hidden="true">${state.freeMode ? icon("spark") : `${icon("wallet")}<span class="wallet-art-star">${icon("star")}</span>`}</div>
    </div>
    ${
      state.freeMode
        ? ""
        : `<section class="cabinet-section">
      <div class="section-head" style="margin-bottom:14px">
        <div>
          <h2 class="section-title" style="font-size:19px">${t("Пополнить баланс")}</h2>
          <p class="section-sub">${t("Оплата звёздами Telegram. Звёзды покупаются внутри Telegram.")}</p>
        </div>
      </div>
      <div class="package-grid">${packages.map(packageCard).join("")}</div>
      <p class="cabinet-hint">${t("Цена в рублях ориентировочная — итоговая сумма видна в счёте Telegram.")}</p>
    </section>
    <div class="cabinet-columns">
      <section class="card cabinet-block">
        <div class="block-head"><h2>${t("История операций")}</h2><span class="dim">${fmtNumber(transactions.length)}</span></div>
        ${
          transactions.length
            ? `<div class="tx-list">${transactions.map(transactionRow).join("")}</div>`
            : `<p class="dim">${t("Пока нет операций. Пополните баланс или активируйте промокод.")}</p>`
        }
      </section>
      <section class="card cabinet-block">
        <div class="block-head"><h2>${t("Заказы")}</h2><span class="dim">${fmtNumber(orders.length)}</span></div>
        ${
          orders.length
            ? `<div class="order-list">${orders.map((order) => orderRow(order, false)).join("")}</div>`
            : `<p class="dim">${t("Оплаченных заказов пока нет.")}</p>`
        }
      </section>
    </div>`
    }
    <section class="card cabinet-block">
      <div class="block-head"><h2>${t("Переносы в аккаунте")}</h2><span class="dim">${fmtNumber(transfers.length)}</span></div>
      ${
        transfers.length
          ? `<div class="history-list">${transfers.map(transferRow).join("")}</div>`
          : `<p class="dim">${t("Здесь появятся переносы, выполненные в этом аккаунте.")}</p>`
      }
    </section>
    ${account.is_admin && state.freeMode ? adminStatsPanel(state) : ""}
    ${account.is_admin && !state.freeMode ? adminPanel(state) : ""}
    ${
      loading && !wallet
        ? `<div class="cabinet-loading"><span class="spinner"></span> ${t("Загружаем кабинет…")}</div>`
        : ""
    }
  </div>`;
}

export function authScreen(state) {
  const username = state.botUsername;
  const botUrl = username ? `https://t.me/${encodeURIComponent(username)}` : null;
  return `<div class="auth-screen rise">
    <div class="auth-card card">
      <span class="auth-mark">${icon("telegram")}</span>
      <h1>${t("Вход через Telegram")}</h1>
      <p>${t("TuneBridge работает как Mini App внутри Telegram. Вход подтверждает Telegram — пароль вводить не нужно.")}</p>
      <ol class="auth-steps">
        <li>${t("Откройте бота TuneBridge в Telegram.")}</li>
        <li>${t("Нажмите кнопку приложения в меню бота.")}</li>
        <li>${t("Вернитесь сюда — кабинет откроется автоматически.")}</li>
      </ol>
      ${state.authError ? `<div class="inline-note is-error">${icon("alert")} ${esc(localize(state.authError))}</div>` : ""}
      ${
        botUrl
          ? `<a class="btn btn-primary btn-lg btn-block" href="${botUrl}" target="_blank" rel="noreferrer">${icon("telegram")} ${t("Открыть бота")}</a>`
          : `<p class="dim">${t("Ссылка на бота появится, когда администратор настроит TUNEBRIDGE_BOT_USERNAME.")}</p>`
      }
      <button class="btn btn-ghost btn-block mt-14" type="button" data-action="auth-refresh" ${state.authBusy ? "disabled" : ""}>
        ${state.authBusy ? `<span class="spinner"></span> ${t("Проверяем…")}` : `${icon("refresh")} ${t("Я уже вошёл")}`}
      </button>
      <p class="auth-note">${t("Если бот не открывается, попросите ссылку у администратора сервиса.")}</p>
      <p class="auth-note">${t("Входя, вы принимаете условия использования и политику конфиденциальности.")}</p>
      ${legalLinks()}
    </div>
  </div>`;
}

export function insufficientModal(payload) {
  const needed = Math.max(0, Number(payload?.needed) || 0);
  const balance = Math.max(0, Number(payload?.balance) || 0);
  return {
    title: t("Недостаточно треков на балансе"),
    subtitle: t("Списываем только за добавленные треки — за неудачные совпадения возвращаем."),
    size: "is-sm",
    body: `<div class="warn-box">${icon("alert")}<span>${t("Нужно")} <b>${fmtTracks(
      needed
    )}</b>, ${t("на балансе")} <b>${fmtTracks(balance)}</b>.</span></div>
      <p class="dim" style="margin:12px 0 0;font-size:12.5px">${t(
        "Пополните баланс или уменьшите плейлист и повторите перенос."
      )}</p>`,
    footer: `<button class="btn btn-ghost" type="button" data-modal-close>${t("Позже")}</button>
      <button class="btn btn-primary" type="button" data-action="go-topup">${icon("star")} ${t(
      "Пополнить баланс"
    )}</button>`,
  };
}

/* --------------------------------------------------------------- history */

export function historyScreen(state) {
  const list = state.history;
  return `<div class="history-screen rise">
    <div class="section-head" style="margin-bottom:18px">
      <div>
        <h1 class="section-title" style="font-size:26px">${t("История переносов")}</h1>
        <p class="section-sub">${t("Хранится в этом браузере.")} ${fmtNumber(
          list.length
        )} ${plural(list.length, t("запись"), t("записи"), t("записей"))}.</p>
      </div>
      ${
        list.length
          ? `<button class="btn btn-ghost btn-sm" type="button" data-action="clear-history">${icon("trash")} ${t("Очистить")}</button>`
          : ""
      }
    </div>
    ${
      !list.length
        ? `<div class="card empty-state" style="padding:72px 24px">
            ${icon("history")}
            <b>${t("Пока пусто")}</b>
            <span>${t("Здесь появятся завершённые переносы: что перенесли, куда и когда.")}</span>
            <button class="btn btn-primary btn-sm mt-14" type="button" data-action="go-home">${t("Начать перенос")}</button>
          </div>`
        : `<div class="history-list">${list
            .map((entry) => {
              const url = safeUrl(entry.url);
              return `<div class="history-item">
                <span class="history-icon">${icon("transfer")}</span>
                <div class="history-main">
                  <span class="history-title truncate">«${esc(entry.source_title || t("Плейлист"))}» → ${esc(
                localize(entry.target_name) || targetName(entry.target)
              )}</span>
                  <span class="history-sub">${fmtDateTime(entry.at)} · ${fmtNumber(entry.added || 0)} ${t(
                "из"
              )} ${fmtNumber(entry.total || 0)} ${plural(
                entry.added || 0,
                t("трек"),
                t("трека"),
                t("треков")
              )}</span>
                </div>
                <div class="history-side">
                  ${
                    url
                      ? `<a class="icon-btn" href="${esc(url)}" target="_blank" rel="noreferrer" title="${t("Открыть плейлист")}" aria-label="${t("Открыть плейлист")}">${icon(
                          "external"
                        )}</a>`
                      : `<span class="badge badge-neutral">${esc(entry.demo ? t("демо") : t("локально"))}</span>`
                  }
                  <span class="history-date">${fmtDateTime(entry.at)}</span>
                </div>
              </div>`;
            })
            .join("")}</div>`
    }
  </div>`;
}

/* ----------------------------------------------------------------- error */

export function errorScreen(state) {
  const error = state.error || {};
  return `<div class="error-screen rise">
    <div class="error-icon">${icon("alert")}</div>
    <h2>${esc(localize(error.title) || t("Что-то пошло не так"))}</h2>
    <p>${esc(localize(error.message) || t("Попробуйте ещё раз."))}</p>
    ${error.hint ? `<p class="dim" style="font-size:12.5px">${esc(localize(error.hint))}</p>` : ""}
    <div class="row mt-14" style="gap:10px;flex-wrap:wrap;justify-content:center">
      <button class="btn btn-primary" type="button" data-action="go-home">${t("На главную")}</button>
      ${
        state.playlist
          ? `<button class="btn btn-ghost" type="button" data-action="back-to-playlist">${t("К плейлисту")}</button>`
          : ""
      }
    </div>
    <span class="error-code">TuneBridge · ${state.hosted ? t("облачный режим") : t("локальный режим")}</span>
  </div>`;
}

export function screenMarkup(state) {
  switch (state.screen) {
    case "playlist":
      return playlistScreen(state);
    case "review":
      return reviewScreen(state);
    case "job":
      return jobScreen(state);
    case "result":
      return resultScreen(state);
    case "history":
      return historyScreen(state);
    case "cabinet":
      return cabinetScreen(state);
    case "auth":
      return authScreen(state);
    case "error":
      return errorScreen(state);
    default:
      return homeScreen(state);
  }
}

/* ---------------------------------------------------------------- modals */

export function connectModal(state, service) {
  const meta = SERVICE_META[service];
  const connected = isConnected(service);
  const name = profileName(service);
  const subtitle = {
    yandex: t("Публичные плейлисты открываются без входа. Аккаунт — для своих плейлистов."),
    spotify: t("Публичные плейлисты открываются без входа. Аккаунт — для своих плейлистов и сохранения."),
    youtube: t("Публичные плейлисты открываются без входа. Аккаунт — для своих плейлистов и сохранения."),
    soundcloud: t("SoundCloud работает по публичной ссылке — вход не нужен."),
    apple: t("Apple Music работает по публичной ссылке — вход не нужен."),
  }[service];

  let body = "";
  let footer = `<span class="foot-note">${
    state.hosted
      ? t("Данные подключения хранятся в вашем аккаунте зашифрованными")
      : `${t("Данные хранятся в папке")} data/ ${t("на этом компьютере")}`
  }</span>
    <button class="btn btn-ghost" type="button" data-modal-close>${t("Закрыть")}</button>`;

  if (connected) {
    body = `
      <div class="connect-hero">
        ${brandIcon(service)}
        <div class="connect-hero-text">
          <b>${esc(meta.name)}</b>
          <span>${esc(name || t("Аккаунт подключён"))}</span>
        </div>
        <span class="badge badge-auto" style="margin-left:auto">${icon("check")} ${t("активно")}</span>
      </div>
      <div class="auth-status is-ok">${icon("check")} ${t("Подключение работает")}</div>
      <div class="notice">${icon("shield")}<span>${
        state.hosted
          ? t(
              "Подключение привязано к вашему аккаунту Telegram. Другие пользователи его не видят; отключение удалит его из аккаунта, плейлисты в сервисе останутся на месте."
            )
          : `${t("Токен доступа хранится только локально. Отключение удалит его из")} <span class="mono">data/</span>, ${t(
              "плейлисты в сервисе останутся на месте."
            )}`
      }</span></div>`;
    footer = `<button class="btn btn-danger" type="button" data-action="disconnect" data-service="${service}">${icon(
      "trash"
    )} ${t("Отключить")}</button><button class="btn btn-ghost" type="button" data-modal-close>${t("Закрыть")}</button>`;
  } else if (service === "yandex") {
    body = `
      <div class="connect-hero">
        ${brandIcon("yandex")}
        <div class="connect-hero-text"><b>${t("Вход в Яндекс Музыку")}</b><span>${t("Код действует около 5 минут")}</span></div>
      </div>
      <div class="notice">${icon("info")}<span>${t("Публичные плейлисты можно открывать по ссылке без входа. Аккаунт нужен, чтобы видеть свои плейлисты.")}</span></div>
      <ol class="connect-steps">
        <li>${t("Откройте")} <a href="https://ya.ru/device" target="_blank" rel="noreferrer">ya.ru/device</a> ${t("и войдите в аккаунт Яндекса.")}</li>
        <li>${t("Введите код, который появится ниже, и подтвердите доступ.")}</li>
        <li>${t("Вернитесь сюда — подключение завершится автоматически.")}</li>
      </ol>
      <div class="code-box">
        <div>
          <div class="code" data-yandex-code>•••• ••••</div>
          <div class="code-hint" data-yandex-hint>${t("Получаем код у Яндекса…")}</div>
        </div>
        <button class="icon-btn" type="button" data-action="copy-yandex-code" title="${t("Скопировать код")}" aria-label="${t("Скопировать код")}">${icon(
          "copy"
        )}</button>
      </div>
      <div class="auth-status" data-yandex-status><span class="spinner"></span> ${t("Ожидаем подтверждение…")}</div>
      <details class="token-fallback">
        <summary class="link-btn is-quiet" style="display:inline-flex">${t("Ввести токен вручную")}</summary>
        <div class="field mt-14">
          <label class="field-label">OAuth-${t("токен Яндекс Музыки")}</label>
          <textarea class="input" data-yandex-token placeholder="y0_Ag…" spellcheck="false"></textarea>
        </div>
        <button class="btn btn-ghost btn-sm mt-8" type="button" data-action="yandex-token">${t("Подключить по токену")}</button>
      </details>`;
  } else if (service === "spotify") {
    const clientSet = Boolean(state.services.spotify?.client_id_set);
    const redirect = state.services.spotify?.redirect_uri || "http://127.0.0.1:8787/api/auth/spotify/callback";
    if (!clientSet) {
      body = `
        <div class="connect-hero">
          ${brandIcon("spotify")}
          <div class="connect-hero-text"><b>${t("Аккаунт Spotify")}</b><span>${t("Один раз, за пару минут")}</span></div>
        </div>
        <div class="notice">${icon("info")}<span>${t("Импорт по ссылке уже работает без входа. Аккаунт нужен, чтобы открывать свои плейлисты и сохранять музыку в")} Spotify.</span></div>
        <ol class="connect-steps">
          <li>${t("Откройте")} <a href="https://developer.spotify.com/dashboard/create" target="_blank" rel="noreferrer">${t("страницу создания приложения")}</a> ${t("и нажмите")} <b>Create app</b>. ${t("Название и описание — любые.")}</li>
          <li>${t("В приложении откройте")} <b>Edit settings → Redirect URIs</b>, ${t("вставьте адрес ниже и сохраните.")}</li>
          <li>${t("Скопируйте")} <b>Client ID</b> ${t("со страницы приложения и вставьте его ниже.")}</li>
        </ol>
        <div class="field">
          <label class="field-label">Redirect URI — ${t("добавьте в настройках приложения")}</label>
          <div class="field-row">
            <input class="input mono" readonly value="${esc(redirect)}">
            <button class="icon-btn" type="button" data-action="copy-text" data-copy="${esc(
              redirect
            )}" title="${t("Скопировать")}" aria-label="${t("Скопировать")}">${icon("copy")}</button>
          </div>
        </div>
        <div class="field">
          <label class="field-label">Client ID</label>
          <div class="field-row">
            <input class="input mono" data-spotify-client placeholder="${t("Например, 1")}a2b3c4d…" autocomplete="off" spellcheck="false">
            <button class="btn btn-primary" type="button" data-action="spotify-client">${t("Сохранить и войти")}</button>
          </div>
          <span class="field-hint">${t("После сохранения откроется страница входа Spotify.")}</span>
        </div>
        <div class="notice">${icon("shield")}<span>Client ID ${t("не является секретом, но файл")} <span class="mono">data/credentials.json</span> ${t("содержит токен доступа — не публикуйте его.")}</span></div>`;
    } else {
      body = `
        <div class="connect-hero">
          ${brandIcon("spotify")}
          <div class="connect-hero-text"><b>${t("Аккаунт Spotify")}</b><span>Client ID ${esc(
            state.services.spotify?.client_id_masked || ""
          )}</span></div>
        </div>
        <div class="notice">${icon("info")}<span>${t("Импорт по ссылке работает и без входа. Вход нужен только для своих плейлистов и сохранения.")}</span></div>
        <button class="btn btn-primary btn-block" type="button" data-action="spotify-start" style="height:50px">
          ${brandIcon("spotify")} ${t("Войти через")} Spotify
        </button>
        <div class="notice">${icon("info")}<span>${t("Откроется страница Spotify.")} ${t("После подтверждения вы вернётесь сюда автоматически.")}</span></div>
        <div class="field">
          <label class="field-label">Redirect URI</label>
          <div class="field-row">
            <input class="input mono" readonly value="${esc(redirect)}">
            <button class="icon-btn" type="button" data-action="copy-text" data-copy="${esc(
              redirect
            )}" title="${t("Скопировать")}" aria-label="${t("Скопировать")}">${icon("copy")}</button>
          </div>
          <span class="field-hint">${t("Должен совпадать с")} Redirect URI ${t("в настройках вашего приложения.")}</span>
        </div>
        <div class="row-between">
          <button class="link-btn is-quiet" type="button" data-action="spotify-reset">${t("Изменить")} Client ID</button>
          <span class="dim" style="font-size:11.5px">${t("Токен обновится автоматически")}</span>
        </div>`;
    }
  } else if (service === "youtube") {
    const browserImport = state.hosted
      ? `<div class="notice">${icon("info")}<span>${t(
          "В облачном режиме вход выполняется cookie из вашего браузера. Скопируйте cookie на своём устройстве и вставьте её ниже."
        )}</span></div>`
      : `<button class="btn btn-primary btn-block" type="button" data-action="youtube-browser" style="height:50px">${icon(
          "plug"
        )} ${t("Подключить из браузера")}</button>
      <span class="yt-auto-hint">${t("Найдём вход в YouTube в Яндекс Браузере, Opera, Chrome, Edge или Firefox на этом компьютере.")} Cookie ${t(
        "не покидают компьютер."
      )}</span>`;
    body = `
      <div class="connect-hero">
        ${brandIcon("youtube")}
        <div class="connect-hero-text"><b>${t("Вход в")} YouTube Music</b><span>${
          state.hosted ? t("Вручную — из вашего браузера") : t("Один клик — или вручную")
        }</span></div>
      </div>
      <div class="notice">${icon("info")}<span>${t("Публичные плейлисты открываются по ссылке без входа. Аккаунт нужен, чтобы переносить в YouTube Music и видеть свои плейлисты.")}</span></div>
      ${browserImport}
      <details class="token-fallback yt-manual"${state.hosted ? " open" : ""}>
        <summary class="link-btn is-quiet" style="display:inline-flex">${
          state.hosted ? t("Инструкция: скопировать cookie") : t("Не получилось? Вставить cookie вручную")
        }</summary>
        <ol class="connect-steps mt-14">
          <li>${t("Откройте")} <a href="https://music.youtube.com" target="_blank" rel="noreferrer">music.youtube.com</a> ${t("и войдите в аккаунт.")}</li>
          <li>${t("Нажмите")} <kbd class="kbd">F12</kbd>, ${t("откройте вкладку")} <b>Network</b> ${t("и обновите страницу (")}<kbd class="kbd">F5</kbd>).</li>
          <li>${t("В строке фильтра наберите")} <b>youtubei</b> ${t("и щёлкните любой запрос в списке.")}</li>
          <li>${t("Справа откройте")} <b>Headers → Request Headers</b>, ${t("найдите строку")} <b>cookie</b>, ${t("нажмите на неё правой кнопкой")} → <b>Copy value</b>.</li>
        </ol>
        <p class="connect-note">${t("Интерфейс на русском? Это вкладки «Сеть» и «Заголовки», а в меню — «Копировать значение».")}</p>
        <div class="yt-demo" aria-hidden="true">
          <div class="yt-demo-bar">
            <span class="yt-demo-tab is-active">Network</span>
            <span class="yt-demo-tab">Elements</span>
            <span class="yt-demo-tab">Console</span>
            <span class="yt-demo-filter">youtubei</span>
          </div>
          <div class="yt-demo-row is-pick"><span class="yt-demo-method">POST</span> youtubei/v1/browse</div>
          <div class="yt-demo-row"><span class="yt-demo-method">POST</span> youtubei/v1/player</div>
          <div class="yt-demo-divider"></div>
          <div class="yt-demo-row yt-demo-head">Request Headers</div>
          <div class="yt-demo-row is-pick"><span class="yt-demo-key">cookie</span><span class="yt-demo-value">SAPISID=…; __Secure-3PAPISID=…</span><span class="yt-demo-chip">Copy value</span></div>
        </div>
        <div class="field">
          <label class="field-label">${t("Вставьте значение cookie")}</label>
          <textarea class="input" data-youtube-headers placeholder="SAPISID=…; __Secure-3PAPISID=…; SID=…" spellcheck="false" autocomplete="off"></textarea>
          <span class="field-hint">${t("Одна строка. cURL или блок заголовков тоже подойдут.")}</span>
        </div>
        <button class="btn btn-ghost btn-block" type="button" data-action="youtube-connect">${t("Подключить вручную")}</button>
      </details>
      <div class="notice is-warn">${icon("alert")}<span>Cookie ${t("даёт полный доступ к аккаунту — никому его не передавайте. Это неофициальный способ, он может нарушать условия")} YouTube.</span></div>`;
  } else {
    body = `
      <div class="connect-hero">
        ${brandIcon(service)}
        <div class="connect-hero-text"><b>${esc(meta.name)}</b><span>${t("Работает без аккаунта")}</span></div>
      </div>
      <div class="notice">${icon("check")}<span>${t("Для импорта достаточно публичной ссылки на плейлист. Вход и токены не нужны.")}</span></div>`;
    footer = `<button class="btn btn-primary" type="button" data-modal-close>${t("Понятно")}</button>`;
  }

  return {
    title: connected ? meta.name : `${t("Подключить")} ${meta.short}`,
    subtitle,
    body,
    footer,
    size: "is-lg",
  };
}

export function searchModalMarkup(source, target) {
  const query = [source.title, source.artists?.[0]].filter(Boolean).join(" ");
  return {
    query,
    body: `
      <div class="connect-hero">
        ${coverMarkup(source, "cover-md", source.service)}
        <div class="connect-hero-text">
          <b>${esc(source.title || t("Без названия"))}</b>
          <span>${esc(artistsLine(source.artists))} · ${fmtDuration(source.duration_ms)}</span>
        </div>
        <span class="pill" style="margin-left:auto">${brandIcon(target)} ${esc(targetName(target))}</span>
      </div>
      <div class="search-field">
        <div class="input-wrap grow">
          <span class="input-icon">${icon("search")}</span>
          <input class="input" name="query" value="${esc(query)}" autocomplete="off" spellcheck="false" placeholder="${t("Название и исполнитель")}">
        </div>
        <button class="btn btn-ghost" type="button" data-action="run-search">${t("Искать")}</button>
      </div>
      <div class="search-list" data-search-list>
        <div class="auth-status"><span class="spinner"></span> ${t("Ищем в")} ${esc(targetName(target))}…</div>
      </div>`,
    footer: `<button class="btn btn-ghost" type="button" data-modal-close>${t("Отмена")}</button>`,
  };
}

export function searchResults(candidates) {
  if (!candidates.length) {
    return `<div class="empty-state" style="padding:28px 16px">${icon("search")}<b>${t("Ничего не нашлось")}</b><span>${t("Попробуйте изменить запрос — например, убрать уточнение в скобках.")}</span></div>`;
  }
  return candidates
    .map((candidate, index) => {
      const track = candidate.track || {};
      const pct = Math.round((Number(candidate.score) || 0) * 100);
      return `<div class="search-row">
        ${coverMarkup(track, "cover-sm", track.source)}
        <div class="song">
          <div class="song-text">
            <span class="song-title truncate">${esc(track.title || t("Без названия"))}</span>
            <span class="song-meta truncate">${esc(artistsLine(track.artists))} · ${fmtDuration(
        track.duration_ms
      )}${track.album ? ` · ${esc(track.album)}` : ""}</span>
          </div>
        </div>
        <span class="score ${scoreClass(candidate.score)}">${pct}%</span>
        <button class="btn btn-ghost btn-sm" type="button" data-action="pick-candidate" data-index="${index}">${t("Выбрать")}</button>
      </div>`;
    })
    .join("");
}

export function exportModal(state, formats) {
  const count = state.playlist?.track_count || (state.playlist?.tracks || []).length || 0;
  const options = [
    ["m3u", "M3U8", t("Универсальный плейлист для плееров и импорта")],
    ["csv", "CSV", t("Таблица: название, артисты, альбом, длительность")],
    ["json", "JSON", t("Полные данные о треках — для скриптов и бэкапа")],
  ];
  return {
    title: t("Скачать плейлист"),
    subtitle: state.playlist ? `«${state.playlist.title}» · ${fmtTracks(count)}` : t("Файлы создаются локально"),
    body: `
      <div class="export-grid">
        ${options
          .map(
            ([value, label, text]) => `<div class="export-option ${
              formats.includes(value) ? "is-on" : ""
            }" data-action="toggle-format" data-format="${value}" role="checkbox" aria-checked="${
              formats.includes(value)
            }" tabindex="0">
              <span class="export-icon">${icon(value === "json" ? "file-text" : value === "csv" ? "disc" : "music")}</span>
              <span class="export-text"><b>${label}</b><span>${text}</span></span>
              <span class="checkbox">${icon("check")}</span>
            </div>`
          )
          .join("")}
      </div>
      <div class="notice">${icon("info")}<span>${t("Всё упакуется в один")} ZIP ${t("с")} README. ${t("Обложка не входит в архив.")}</span></div>`,
    footer: `<span class="foot-note">${fmtTracks(count)} · ZIP</span>
      <button class="btn btn-ghost" type="button" data-action="telegram">${icon("telegram")} ${t("В Telegram")}</button>
      <button class="btn btn-ghost" type="button" data-modal-close>${t("Отмена")}</button>
      <button class="btn btn-primary" type="button" data-action="download-export">${icon(
        "download"
      )} ${t("Скачать архив")}</button>`,
  };
}

export function telegramChatsMarkup(chats) {
  if (!chats.length) {
    return `<div class="empty-state" style="padding:18px 14px">${icon("search")}<b>${t("Чаты не найдены")}</b><span>${t("Откройте бота в")} Telegram, ${t("нажмите")} Start ${t("и отправьте /")}start — ${t("затем обновите список.")}</span></div>`;
  }
  return chats
    .map(
      (chat) => `<button class="chat-row" type="button" data-action="pick-telegram-chat" data-chat="${esc(
        chat.value
      )}">
        <span class="chat-icon">${icon("telegram")}</span>
        <span class="chat-text"><b>${esc(chat.title || t("Чат"))}</b><span>${esc(
        chat.type === "channel" ? t("канал") : chat.type === "private" ? t("личный чат") : t("группа")
      )} · ${esc(String(chat.value))}</span></span>
        ${icon("chevron-right", "dim")}
      </button>`
    )
    .join("");
}

export function telegramModal(state, archive) {
  const connected = Boolean(state.telegram?.connected);
  const botName = state.telegram?.profile?.name || t("Telegram-бот");
  const count = state.playlist?.track_count || (state.playlist?.tracks || []).length || 0;
  const hasPlaylist = Boolean(state.playlist?.tracks?.length);

  if (!connected) {
    return {
      title: t("Отправка в Telegram"),
      subtitle: t("Через вашего бота — без сторонних сервисов"),
      size: "is-lg",
      body: `
        <div class="connect-hero">
          ${brandIcon("telegram")}
          <div class="connect-hero-text"><b>${t("Свой бот в")} Telegram</b><span>${t("Один раз, за пару минут")}</span></div>
        </div>
        <div class="notice">${icon("info")}<span>TuneBridge ${t("отправит в")} Telegram <b>${t("список треков со ссылками")}</b> ${t("и")} ZIP-${t("архив плейлиста. Бот создаётся за минуту и остаётся вашим.")}</span></div>
        <ol class="connect-steps">
          <li>${t("Откройте")} <a href="https://t.me/BotFather" target="_blank" rel="noreferrer">@BotFather</a> ${t("и отправьте")} <span class="mono">/newbot</span>.</li>
          <li>${t("Придумайте имя и")} username ${t("бота —")} BotFather ${t("пришлёт токен вида")} <span class="mono">123456789:AAH…</span>.</li>
          <li>${t("Вставьте токен ниже. Дальше откройте бота в")} Telegram ${t("и нажмите")} <b>Start</b>.</li>
        </ol>
        <div class="field">
          <label class="field-label">${t("Токен бота")}</label>
          <input class="input mono" data-telegram-token placeholder="123456789:AAH…" autocomplete="off" spellcheck="false">
        </div>
        <div class="notice is-warn">${icon("alert")}<span>${t("Музыкальные файлы")} TuneBridge ${t("не скачивает — сервисы не отдают их официально. В")} Telegram ${t("уходят список треков и архив плейлиста (")}M3U8, CSV, JSON).</span></div>`,
      footer: `<span class="foot-note">${t("Токен хранится в")} data/telegram.json</span>
        <button class="btn btn-ghost" type="button" data-modal-close>${t("Закрыть")}</button>
        <button class="btn btn-primary" type="button" data-action="telegram-connect">${icon(
          "telegram"
        )} ${t("Подключить бота")}</button>`,
    };
  }

  return {
    title: t("Отправить в Telegram"),
    subtitle: `${botName} · «${state.playlist?.title || t("плейлист")}»`,
    size: "is-lg",
    body: `
      <div class="connect-hero">
        ${brandIcon("telegram")}
        <div class="connect-hero-text"><b>${esc(botName)}</b><span>${t("Список треков и архив")}</span></div>
        <span class="badge badge-auto" style="margin-left:auto">${icon("check")} ${t("активно")}</span>
      </div>
      <div class="field">
        <label class="field-label">${t("Куда отправить")}</label>
        <div class="field-row">
          <input class="input mono" data-telegram-chat value="${esc(
            state.telegram?.chat || (state.hosted ? state.account?.telegram_id || "" : "")
          )}" placeholder="${t("Пусто — чат с ботом, или")} @${t("канал")}" autocomplete="off" spellcheck="false">
          ${
            state.hosted
              ? ""
              : `<button class="btn btn-ghost" type="button" data-action="telegram-chats">${t("Найти чаты")}</button>`
          }
        </div>
        <span class="field-hint">${
          state.hosted
            ? t("По умолчанию — личный чат с ботом. Канал укажите через @username, бот должен быть в нём администратором.")
            : `${t("Канал — только через")} @username, ${t("и бот должен быть в нём администратором.")}`
        }</span>
      </div>
      <div class="chat-list" data-telegram-chats></div>
      <div class="export-grid">
        <div class="export-option ${archive ? "is-on" : ""}" data-action="toggle-telegram-archive" role="checkbox" aria-checked="${archive}" tabindex="0">
          <span class="export-icon">${icon("file-text")}</span>
          <span class="export-text"><b>${t("ZIP-архив плейлиста")}</b><span>M3U8, CSV ${t("и")} JSON ${t("одним файлом")}</span></span>
          <span class="checkbox">${icon("check")}</span>
        </div>
      </div>
      <div class="notice">${icon("info")}<span data-telegram-summary>${t("Уйдёт")} ${fmtTracks(count)} ${t("списком")}${
        archive ? t(" плюс архив") : ""
      }. ${t("При первом сообщении")} Telegram ${t("попросит нажать")} Start ${t("у бота.")}</span></div>
      ${
        hasPlaylist
          ? ""
          : `<div class="notice is-warn">${icon("alert")}<span>${t("Сначала загрузите плейлист — отправлять пока нечего.")}</span></div>`
      }`,
    footer: `${
      state.hosted
        ? ""
        : `<button class="link-btn is-quiet" type="button" data-action="telegram-disconnect">${t("Отключить бота")}</button>`
    }
      <button class="btn btn-ghost" type="button" data-modal-close>${t("Закрыть")}</button>
      <button class="btn btn-primary" type="button" data-action="telegram-send" ${
        hasPlaylist ? "" : "disabled"
      }>${icon("send")} ${t("Отправить")}</button>`,
  };
}

export function phoneModal(state) {
  const phone = state.phone || {};
  const url = safeUrl(phone.url);
  const body = phone.enabled
    ? `${
        url
          ? `<div class="phone-pair">
              <div class="phone-qr"><img src="/api/phone/qr.svg" alt="${t("QR-код с адресом TuneBridge")}"></div>
              <div class="phone-info">
                <span class="field-label">${t("Адрес для телефона")}</span>
                <div class="field-row">
                  <input class="input mono" readonly value="${esc(phone.url)}">
                  <button class="icon-btn" type="button" data-action="copy-text" data-copy="${esc(
                    phone.url
                  )}" title="${t("Скопировать")}" aria-label="${t("Скопировать")}">${icon("copy")}</button>
                </div>
                <p class="dim" style="font-size:12px;line-height:1.5;margin:8px 0 0">${t("Отсканируйте")} QR ${t("камерой телефона или введите адрес вручную. Компьютер и телефон должны быть в одной")} Wi-Fi ${t("сети.")}</p>
              </div>
            </div>
            <ol class="connect-steps">
              <li>${t("Подключите телефон к той же")} Wi-Fi ${t("сети, что и компьютер.")}</li>
              <li>${t("Откройте адрес на телефоне — интерфейс сам подстроится под экран.")}</li>
              <li>${t("В меню браузера выберите")} <b>«${t("Добавить на главный экран»")}</b> — ${t("появится иконка")} TuneBridge.</li>
            </ol>`
          : `<div class="notice is-warn">${icon("alert")}<span>${t("Не удалось определить адрес в сети. Проверьте подключение к")} Wi-Fi ${t("и перезапустите")} <span class="mono">start-lan</span>.</span></div>`
      }
      <div class="notice is-warn">${icon("shield")}<span>${t("В этом режиме")} TuneBridge ${t("открыт для всех устройств в вашей")} Wi-Fi ${t("сети — и они увидят подключённые аккаунты. Включайте только в доверенной сети и выключайте после использования.")}</span></div>
      <div class="notice">${icon("info")}<span>${t("Полноценный офлайн-режим (")}PWA) ${t("включается только по")} HTTPS. ${t("По локальному адресу доступна иконка на главном экране и обычная работа в сети.")}</span></div>`
    : `<div class="notice">${icon("info")}<span>${t("Сейчас")} TuneBridge ${t("слушает только этот компьютер. Чтобы открыть его с телефона, запустите приложение в режиме")} Wi-Fi.</span></div>
      <ol class="connect-steps">
        <li>${t("Закройте")} TuneBridge, ${t("если он запущен.")}</li>
        <li>Windows: ${t("двойной клик по")} <span class="mono">start-lan.bat</span>. macOS/Linux: <span class="mono">./start-lan.sh</span>.</li>
        <li>${t("В окне консоли появится адрес вида")} <span class="mono">http://192.168.…:8787</span> — ${t("откройте его на телефоне.")}</li>
      </ol>
      <div class="notice is-warn">${icon("shield")}<span>${t("В режиме Wi-Fi приложение доступно всем в вашей сети.")} Windows ${t("спросит про брандмауэр — разрешите доступ только для частных сетей.")}</span></div>`;

  return {
    title: t("С телефона"),
    subtitle: t("Та же Wi-Fi сеть, без установки"),
    size: "is-lg",
    body: `<div class="connect-hero">
        <span class="phone-hero">${icon("phone")}</span>
        <div class="connect-hero-text"><b>${phone.enabled ? t("Wi-Fi включён") : t("Открыть по Wi-Fi")}</b><span>${
          phone.enabled ? t("Отсканируйте QR") : t("Запуск через start-lan")
        }</span></div>
        ${phone.enabled ? `<span class="badge badge-auto" style="margin-left:auto">${icon("wifi")} ${t("в сети")}</span>` : ""}
      </div>
      ${body}`,
    footer: `<span class="foot-note">TuneBridge · ${t("локальный режим")}</span>
      <button class="btn btn-primary" type="button" data-modal-close>${t("Понятно")}</button>`,
  };
}

export function helpModal(state) {
  return {
    title: t("Как это работает"),
    subtitle: t("Три шага, полный контроль и ничего лишнего."),
    size: "is-lg",
    body: `
      <div class="connect-hero">
        ${brandIcon("demo")}
        <div class="connect-hero-text"><b>TuneBridge</b><span>${
          state.hosted
            ? t("Перенос плейлистов между музыкальными сервисами")
            : t("Локальный помощник для переезда плейлистов")
        }</span></div>
      </div>
      <ol class="connect-steps">
        <li><b>${t("Загрузите плейлист")}</b> ${t("по публичной ссылке — аккаунт для этого не нужен. Свои плейлисты можно открыть из подключённого аккаунта или файлом.")}</li>
        <li><b>${t("Запустите поиск.")}</b> TuneBridge ${t("сравнит название, исполнителя, длительность и версию записи.")}</li>
        <li><b>${t("Проверьте спорные треки")}</b> ${t("и запустите перенос. Всё можно поправить вручную.")}</li>
      </ol>
      <div class="help-list">
        <div class="help-item">${icon("shield")}<div><b>${t("Приватность")}</b><span>${
          state.hosted
            ? t(
                "Подключения хранятся в вашем аккаунте зашифрованными и не видны другим пользователям. Наружу уходят только запросы к музыкальным сервисам."
              )
            : `${t("Токены и кэш совпадений лежат в папке")} data/ ${t("рядом с приложением. Наружу уходят только запросы к самим музыкальным сервисам.")}`
        }</span></div></div>
        <div class="help-item">${icon("spark")}<div><b>${t("Совпадения")}</b><span>${t("От 84% трек принимается автоматически. От 58% до 84% попадает в «Спорные», ниже — в «Не найдены». Любой трек можно заменить вручную.")}</span></div></div>
        <div class="help-item">${icon("info")}<div><b>${t("Источники и вход")}</b><span>${t("Импорт из Яндекс Музыки,")} Spotify, YouTube Music, SoundCloud ${t("и")} Apple Music ${t("работает по ссылке. Вход нужен только для своих плейлистов и сохранения в")} Spotify ${t("или")} YouTube Music.</span></div></div>
        <div class="help-item">${icon("clock")}<div><b>${t("Скорость")}</b><span>${t("Поиск идёт параллельно: около 1–3 минут на 100 треков, ещё около минуты — на добавление.")}</span></div></div>
      </div>
      <div class="help-faq">
        <div class="block-head"><h3>${t("Частые вопросы")}</h3>${icon("info")}</div>
        <details class="faq-item"><summary>${t("Часть треков не нашлась — что делать?")}</summary><p>${t(
          "Откройте «Спорные» и «Не найдены»: трек можно заменить вручную через поиск или исключить. Разные версии (ремикс, live, clean) считаются отдельными записями."
        )}</p></details>
        <details class="faq-item"><summary>${t("YouTube Music не подключается или привязался чужой аккаунт.")}</summary><p>${t(
          "Отключите сервис и подключите заново кнопкой из браузера: в открывшемся окне выберите нужный аккаунт Google. Cookie обновятся автоматически."
        )}</p></details>
        <details class="faq-item"><summary>${t("Spotify просит вход или возвращает ошибку.")}</summary><p>${t(
          "Переподключите Spotify в кабинете. При ошибке лимита подождите минуту и повторите — перенос продолжится с места остановки."
        )}</p></details>
        <details class="faq-item"><summary>${t("Можно перенести приватный плейлист?")}</summary><p>${t(
          "Да: подключите аккаунт источника, и свои плейлисты появятся в списке. Публичные ссылки работают без входа."
        )}</p></details>
        <details class="faq-item"><summary>${t("Куда попадают мои данные и как их удалить?")}</summary><p>${t(
          "Подключения хранятся зашифрованными в вашем аккаунте; отключение сервиса удаляет токены. Удаление аккаунта — по запросу через контакты в политике конфиденциальности."
        )}</p></details>
        <details class="faq-item"><summary>${t("Работает ли TuneBridge без интернета?")}</summary><p>${t(
          "Нет: перенос обращается к музыкальным сервисам. Без сети приложение покажет оболочку и баннер, а переносы продолжатся после восстановления связи."
        )}</p></details>
      </div>
      <div class="notice">${icon("alert")}<span>${t("Используйте приложение для личных плейлистов и соблюдайте условия сервисов. Ответственность за использование лежит на вас.")}</span></div>`,
    footer: `<span class="foot-note">TuneBridge · ${state.hosted ? t("облачный режим") : t("локальный режим")}</span>
      ${legalLinks()}
      <button class="btn btn-primary" type="button" data-modal-close>${t("Понятно")}</button>`,
  };
}

export function installModal(state) {
  const ios =
    /iphone|ipad|ipod/i.test(navigator.userAgent) ||
    (navigator.platform === "MacIntel" && navigator.maxTouchPoints > 1);
  const steps = ios
    ? [
        t("Нажмите «Поделиться» в Safari (квадрат со стрелкой вверх)."),
        t("Выберите «На экран „Домой“»."),
        t("Подтвердите — иконка TuneBridge появится рядом с приложениями."),
      ]
    : [
        t("Откройте меню браузера (три точки или «Поделиться»)."),
        t("Выберите «Установить приложение» или «Добавить на главный экран»."),
        t("Подтвердите установку — TuneBridge откроется как отдельное приложение."),
      ];
  return {
    title: t("Установить TuneBridge"),
    subtitle: t("Иконка на главном экране и работа как приложение."),
    size: "is-sm",
    body: `
      <div class="connect-hero">
        <span class="conn-mark phone-mark">${icon("phone")}</span>
        <div class="connect-hero-text"><b>TuneBridge</b><span>${
          ios ? "iPhone / iPad" : "Android / Chrome / Edge"
        }</span></div>
      </div>
      <ol class="connect-steps">${steps.map((step) => `<li>${step}</li>`).join("")}</ol>
      <div class="notice">${icon("info")}<span>${t(
        "Без сети приложение откроет оболочку, но для переносов нужно подключение к интернету."
      )}</span></div>`,
    footer: `<button class="btn btn-primary" type="button" data-modal-close>${t("Понятно")}</button>`,
  };
}

export function busyModal(job) {
  const pct = jobPercent(job);
  return {
    title: t("Сейчас выполняется другая задача"),
    subtitle: localize(job.title) || t("Перенос уже идёт"),
    size: "is-sm",
    body: `
      <div class="busy-icon">${icon("clock")}</div>
      <p class="modal-sub" style="margin:0">${t("Дождитесь завершения или остановите текущую задачу — параллельный запуск может нарушить лимиты сервисов.")}</p>
      <div class="progress"><div class="progress-bar" style="width:${pct}%"></div></div>
      <div class="row-between"><span class="dim" style="font-size:12px">${esc(
        jobPhaseLabel(job)
      )}</span><span class="mono dim" style="font-size:12px">${pct}%</span></div>`,
    footer: `<button class="btn btn-ghost" type="button" data-modal-close>${t("Закрыть")}</button>
      <button class="btn btn-primary" type="button" data-action="open-active-job">${t("Перейти к задаче")}</button>`,
  };
}
