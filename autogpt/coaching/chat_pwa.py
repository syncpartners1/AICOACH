"""Public offline shell for /chat. Private chat HTML and API are always network-only."""
CHAT_SW = r"""
const CACHE = 'chat-shell-v1';
const OFFLINE = '/chat/offline';
const PUBLIC = [OFFLINE, '/static/android-chrome-192x192.png',
                '/static/android-chrome-512x512.png'];
self.addEventListener('install', event => {
  event.waitUntil(caches.open(CACHE).then(cache => cache.addAll(PUBLIC)));
});
self.addEventListener('activate', event => {
  event.waitUntil(Promise.all([
    caches.keys().then(keys => Promise.all(keys.filter(k => k.startsWith('chat-shell-') && k !== CACHE)
      .map(k => caches.delete(k)))),
    self.clients.claim()
  ]));
});
self.addEventListener('fetch', event => {
  // No POST, API, authenticated HTML, redirects, or other private content is cached.
  if (event.request.mode !== 'navigate' || event.request.method !== 'GET') return;
  const url = new URL(event.request.url);
  if (url.origin !== self.location.origin || url.pathname !== '/chat') return;
  event.respondWith(fetch(event.request).catch(() => caches.open(CACHE).then(cache => cache.match(OFFLINE))));
});
"""
