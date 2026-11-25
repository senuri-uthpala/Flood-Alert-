// FloodAlert LK service worker v5: network-first app shell, API never cached, CORS-checked tile cache.
const SHELL = "fa-shell-v9", TILES = "fa-tiles-v9";
const FILES = ["/", "/css/style.css", "/js/app.js", "/js/i18n.js", "/manifest.json", "/icon.svg", "/logo.svg", "/img/zone.jpg", "/img/street.jpg", "/data/districts.geojson"];
const TILE_HOSTS = ["server.arcgisonline.com"];

self.addEventListener("install", (e) => {
  e.waitUntil(caches.open(SHELL).then((c) => c.addAll(FILES)).then(() => self.skipWaiting()));
});
self.addEventListener("activate", (e) => {
  e.waitUntil(caches.keys()
    .then((ks) => Promise.all(ks.filter((k) => k !== SHELL && k !== TILES).map((k) => caches.delete(k))))
    .then(() => self.clients.claim()));
});
self.addEventListener("fetch", (e) => {
  const req = e.request, url = new URL(req.url);
  if (req.method !== "GET") return;
  if (TILE_HOSTS.some((h) => url.hostname.endsWith(h))) {
    e.respondWith(caches.open(TILES).then(async (c) => {
      const hit = await c.match(req);
      if (hit) return hit;
      try {
        const r = await fetch(req);
        if (r.ok && r.type !== "opaque") c.put(req, r.clone()); // only cache real, readable successes
        return r;
      } catch { return Response.error(); }
    }));
    return;
  }
  if (url.origin !== location.origin || url.pathname.startsWith("/api/") || url.pathname.startsWith("/uploads/")) return;
  e.respondWith(fetch(req).then((r) => {
    if (r.ok) { const copy = r.clone(); caches.open(SHELL).then((c) => c.put(req, copy)); }
    return r;
  }).catch(() => caches.match(req).then((m) => m || caches.match("/"))));
});
