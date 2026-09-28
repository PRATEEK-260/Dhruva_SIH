// DHRUVA service worker: the boat phone must open, decode a capsule and speak
// with its radio off. Everything it needs is cached on the first online visit.
//
// - Pages and built assets: network first, cache fallback, so an online phone
//   always gets the latest build and an offline one gets the last it saw.
// - Voice clips and fonts: cache first; they never change within a version.
// - /api is never cached: an advisory must be live or say it is not.

const VERSION = "dhruva-v1";
const LANGS = ["ta", "ml", "or", "hi"];
const STATES = ["safe", "caution", "unsafe", "blocked", "unavailable"];
const PRECACHE = ["/", "/boat", ...LANGS.flatMap((l) => STATES.map((s) => `/voice/${l}/${s}.wav`))];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches
      .open(VERSION)
      .then((c) => c.addAll(PRECACHE))
      .then(() => self.skipWaiting()),
  );
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches
      .keys()
      // Only this worker's own versions; the phone's saved voice cache stays.
      .then((keys) => Promise.all(keys.filter((k) => /^dhruva-v\d+$/.test(k) && k !== VERSION).map((k) => caches.delete(k))))
      .then(() => self.clients.claim()),
  );
});

async function cacheFirst(request) {
  const hit = await caches.match(request);
  if (hit) return hit;
  const res = await fetch(request);
  if (res.ok || res.type === "opaque") (await caches.open(VERSION)).put(request, res.clone());
  return res;
}

async function networkFirst(request) {
  try {
    const res = await fetch(request);
    if (res.ok) (await caches.open(VERSION)).put(request, res.clone());
    return res;
  } catch {
    const hit = await caches.match(request, { ignoreSearch: true });
    if (hit) return hit;
    // Any app route falls back to the app shell; the router takes it from there.
    if (request.mode === "navigate") {
      const shell = await caches.match("/boat");
      if (shell) return shell;
    }
    throw new Error("offline and not cached");
  }
}

self.addEventListener("fetch", (event) => {
  const { request } = event;
  if (request.method !== "GET") return;
  const url = new URL(request.url);
  if (url.origin === self.location.origin && url.pathname.startsWith("/api")) return;
  if (url.pathname.startsWith("/voice/") || url.host.includes("fonts.g")) {
    event.respondWith(cacheFirst(request));
    return;
  }
  if (url.origin === self.location.origin) event.respondWith(networkFirst(request));
});
