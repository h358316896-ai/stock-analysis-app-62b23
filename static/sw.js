// Service Worker for StockAI PWA — v3 (network-first, no aggressive HTML cache)
const CACHE = 'stockai-v3';

self.addEventListener('install', event => {
  self.skipWaiting();
});

self.addEventListener('activate', event => {
  event.waitUntil(
    caches.keys().then(keys => Promise.all(keys.map(k => caches.delete(k))))
  );
  self.clients.claim();
});

self.addEventListener('fetch', event => {
  if (event.request.method !== 'GET') return;
  if (event.request.url.includes('/api/')) return;

  // Only cache static assets (JS, CSS, images), never HTML pages
  const url = event.request.url;
  const isStatic = url.match(/\.(js|css|png|svg|ico|woff2?)$/i);

  if (isStatic) {
    event.respondWith(
      caches.match(event.request).then(cached => {
        const fetchPromise = fetch(event.request).then(response => {
          if (response.status === 200) {
            const clone = response.clone();
            caches.open(CACHE).then(cache => cache.put(event.request, clone));
          }
          return response;
        });
        return cached || fetchPromise;
      })
    );
  }
  // HTML pages: always go to network (no cache)
});
