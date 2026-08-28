const CACHE = 'mosaic-shell-v0.2.0-ui2';
const SHELL = ['/', '/static/styles.css', '/static/app.js', '/static/icon.svg', '/static/manifest.webmanifest'];

self.addEventListener('install', event => {
  event.waitUntil(caches.open(CACHE).then(cache => cache.addAll(SHELL)).then(() => self.skipWaiting()));
});

self.addEventListener('activate', event => {
  event.waitUntil(
    caches.keys()
      .then(keys => Promise.all(keys.filter(key => key !== CACHE).map(key => caches.delete(key))))
      .then(() => self.clients.claim()),
  );
});

self.addEventListener('fetch', event => {
  const request = event.request;
  const url = new URL(request.url);
  if (
    request.method !== 'GET'
    || url.origin !== location.origin
    || url.pathname.startsWith('/api/')
    || url.pathname.startsWith('/health/')
  ) return;

  const fallback = request.mode === 'navigate' ? '/' : request;
  event.respondWith(
    fetch(request)
      .then(response => {
        if (response.ok) {
          const cacheKey = request.mode === 'navigate' ? '/' : request;
          caches.open(CACHE).then(cache => cache.put(cacheKey, response.clone()));
        }
        return response;
      })
      .catch(() => caches.match(fallback)),
  );
});
