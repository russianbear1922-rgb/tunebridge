const HISTORY_KEY = "tunebridge.history.v1";

function readHistory() {
  try {
    const raw = localStorage.getItem(HISTORY_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    if (!Array.isArray(parsed)) return [];
    return parsed
      .filter((item) => item && typeof item === "object")
      .slice(0, 50);
  } catch {
    return [];
  }
}

export const state = {
  screen: "home",
  services: {},
  targets: [],
  telegram: { connected: false, profile: null, chat: "" },
  phone: { enabled: false, url: null },
  limits: { max_tracks: 2000 },
  activeJob: null,

  account: null,
  authenticated: false,
  mode: "local",
  hosted: false,
  freeMode: false,
  ads: null,
  botUsername: null,
  packages: [],
  wallet: null,
  walletLoading: false,
  cabinetError: null,
  admin: null,
  adminCodes: [],
  adminError: null,
  adminStats: null,
  adminStatsError: null,
  installReady: false,
  offline: false,
  authBusy: false,
  authError: null,
  pendingPayment: null,

  sourceService: "yandex",
  sourceUrl: "",
  sourceFeedback: null,
  playlists: {},
  playlistsLoading: false,

  playlist: null,
  playlistService: null,
  playlistTitle: "",
  target: null,
  targetOptions: { public: true, privacy: "PRIVATE", formats: ["m3u", "csv", "json"], description: "" },

  matches: [],
  matchMeta: null,
  stats: null,
  reviewFilter: "all",

  job: null,
  result: null,
  resultJob: null,
  searchCandidates: [],
  searchIndex: null,
  pendingConnect: null,

  history: readHistory(),
  error: null,
  sidebarOpen: false,
};

export function persistHistory() {
  try {
    localStorage.setItem(HISTORY_KEY, JSON.stringify(state.history.slice(0, 50)));
  } catch {
    /* localStorage может быть отключён — история просто не сохранится */
  }
}

export function addHistoryEntry(entry) {
  state.history.unshift(entry);
  state.history = state.history.slice(0, 50);
  persistHistory();
}

export function clearHistoryStorage() {
  state.history = [];
  try {
    localStorage.removeItem(HISTORY_KEY);
  } catch {
    /* ignore */
  }
}

export function isConnected(service) {
  return Boolean(state.services?.[service]?.connected);
}

export function profileName(service) {
  const profile = state.services?.[service]?.profile;
  return profile?.name || profile?.login || null;
}

export function resetPlaylistState() {
  state.playlist = null;
  state.playlistService = null;
  state.playlistTitle = "";
  state.matches = [];
  state.matchMeta = null;
  state.stats = null;
  state.result = null;
  state.resultJob = null;
  state.reviewFilter = "all";
}
