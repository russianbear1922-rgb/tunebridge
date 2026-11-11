const CACHE = "tunebridge-shell-v10";
const SHELL = [
  "/",
  "/privacy",
  "/terms",
  "/static/css/app.css",
  "/static/css/legal.css",
  "/static/js/app.js",
  "/static/js/api.js",
  "/static/js/store.js",
  "/static/js/views.js",
  "/static/js/ui.js",
  "/static/js/icons.js",
  "/static/js/i18n.js",
  "/static/js/locale-en.js",
  "/static/js/server-i18n.js",
  "/static/img/logo.svg",
  "/static/img/favicon.svg",
  "/static/img/icon-192.png",
  "/manifest.webmanifest",
];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches
      .open(CACHE)
      .then((cache) => cache.addAll(SHELL))
      .then(() => self.skipWaiting())
      .catch(() => self.skipWaiting())
  );
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches
      .keys()
      .then((keys) => Promise.all(keys.filter((key) => key !== CACHE).map((key) => caches.delete(key))))
      .then(() => self.clients.claim())
  );
});

self.addEventListener("fetch", (event) => {
  const request = event.request;
  if (request.method !== "GET") return;
  const url = new URL(request.url);
  if (url.origin !== self.location.origin) return;
  if (url.pathname.startsWith("/api/")) return;

  event.respondWith(
    fetch(request)
      .then((response) => {
        if (response.ok) {
          const copy = response.clone();
          caches.open(CACHE).then((cache) => cache.put(request, copy)).catch(() => {});
        }
        return response;
      })
      .catch(async () => {
        const hit = await caches.match(request);
        if (hit) return hit;
        if (request.mode === "navigate") {
          const shell = await caches.match("/");
          if (shell) return shell;
        }
        return new Response("TuneBridge сейчас недоступен без сети. / TuneBridge is offline right now.", {
          status: 503,
          headers: { "Content-Type": "text/plain; charset=utf-8" },
        });
      })
  );
});
