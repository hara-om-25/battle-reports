const CACHE = 'battle-reports-v2';
const PRECACHE = ['/battle-reports/', '/battle-reports/index.html'];

self.addEventListener('install', e => {
  e.waitUntil(caches.open(CACHE).then(c => c.addAll(PRECACHE)).then(() => self.skipWaiting()));
});

self.addEventListener('activate', e => {
  e.waitUntil(caches.keys().then(keys =>
    Promise.all(keys.filter(k => k !== CACHE).map(k => caches.delete(k)))
  ).then(() => self.clients.claim()));
});

self.addEventListener('fetch', e => {
  const url = new URL(e.request.url);
  // Sheets API and OAuth must always hit the network — never cache them
  if (url.hostname.includes('googleapis.com') || url.hostname.includes('accounts.google.com')) return;
  if (e.request.method !== 'GET') return;
  e.respondWith(
    fetch(e.request).then(resp => {
      // cache successful GETs (app shell, tailwind, fonts) so they survive offline
      if (resp && (resp.ok || resp.type === 'opaque')) {
        const copy = resp.clone();
        caches.open(CACHE).then(c => c.put(e.request, copy)).catch(() => {});
      }
      return resp;
    }).catch(() =>
      caches.match(e.request).then(r => {
        if (r) return r;
        // запасний варіант — лише для переходів на сторінку, не для скриптів/стилів
        if (e.request.mode === 'navigate') return caches.match('/battle-reports/');
        return new Response('', { status: 504, statusText: 'offline' });
      })
    )
  );
});
