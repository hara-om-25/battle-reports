// Офлайн-кеш плеєра. Діє лише в папці /player/ і не чіпає основний застосунок.
const CACHE = 'player-v4';
const FILES = ['./', './index.html', './manifest.webmanifest', './icon-192.png', './icon-512.png'];

self.addEventListener('install', e => {
  e.waitUntil(caches.open(CACHE).then(c => c.addAll(FILES)).then(() => self.skipWaiting()));
});
self.addEventListener('activate', e => {
  e.waitUntil(caches.keys().then(keys =>
    Promise.all(keys.filter(k => k.startsWith('player-') && k !== CACHE).map(k => caches.delete(k)))
  ).then(() => self.clients.claim()));
});
// Спершу мережа (щоб оновлення приходили одразу), без мережі — кеш
self.addEventListener('fetch', e => {
  if (e.request.method !== 'GET') return;
  const fresh = e.request.mode === 'navigate'
    ? fetch(e.request.url, { cache: 'reload' })
    : fetch(e.request);
  e.respondWith(fresh.then(resp => {
    if (resp && resp.ok) { const copy = resp.clone(); caches.open(CACHE).then(c => c.put(e.request, copy)); }
    return resp;
  }).catch(() => caches.match(e.request, { ignoreSearch: true }).then(r => r || caches.match('./index.html'))));
});
