const CACHE = 'battle-reports-v4';
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
  // The manifest decides orientation, name and icon at install time —
  // a stale cached copy would keep resurrecting old settings.
  if (url.pathname.endsWith('/manifest.json')) return;
  if (e.request.method !== 'GET') return;
  // Сама сторінка береться повз кеш браузера: GitHub Pages віддає її з
  // дозволом «тримай десять хвилин», і перезавантаження показувало старий
  // застосунок навіть тоді, коли новий уже лежав на сервері
  const fresh = e.request.mode === 'navigate'
    ? fetch(e.request.url, { cache: 'reload', credentials: 'same-origin' })
    : fetch(e.request);
  e.respondWith(
    fresh.then(resp => {
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
