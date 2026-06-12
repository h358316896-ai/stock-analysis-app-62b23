// Service Worker — cache-first for instant repeat loads
const CACHE = 'stockai-v3';
const API_CACHE = 'stockai-api-v3';

// Core files to cache immediately
const PRECACHE = [
  '/',
  '/stock',
  '/manifest.json'
];

// Install: precache core files
self.addEventListener('install', (e) => {
  e.waitUntil(
    caches.open(CACHE).then(c => c.addAll(PRECACHE).catch(() => {}))
  );
  self.skipWaiting();
});

// Activate: clean old caches
self.addEventListener('activate', (e) => {
  e.waitUntil(
    caches.keys().then(keys => Promise.all(
      keys.filter(k => k !== CACHE && k !== API_CACHE).map(k => caches.delete(k))
    ))
  );
  self.clients.claim();
});

// Fetch: cache-first for static, network-first for API
self.addEventListener('fetch', (e) => {
  const url = new URL(e.request.url);

  // API calls: network-first, cache fallback (5 min freshness)
  if (url.pathname.startsWith('/api/')) {
    e.respondWith(
      caches.open(API_CACHE).then(cache =>
        fetch(e.request).then(response => {
          if (response.ok) {
            const clone = response.clone();
            cache.put(e.request, clone);
          }
          return response;
        }).catch(() => cache.match(e.request))
      )
    );
    return;
  }

  // Static assets: cache-first
  e.respondWith(
    caches.match(e.request).then(cached =>
      cached || fetch(e.request).then(response => {
        if (response.ok && e.request.method === 'GET') {
          const clone = response.clone();
          caches.open(CACHE).then(c => c.put(e.request, clone));
        }
        return response;
      })
    )
  );
});
