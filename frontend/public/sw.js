// Minimal service worker: lets the app install and keeps the app shell available.
// Data (/api, /auth) is never cached, so the dashboard always shows live numbers.
const SHELL = 'shell-v1'
self.addEventListener('install', (e) => {
  e.waitUntil(caches.open(SHELL).then((c) => c.addAll(['/', '/manifest.webmanifest', '/icon-192.png'])))
  self.skipWaiting()
})
self.addEventListener('activate', (e) => {
  e.waitUntil(
    caches.keys().then((keys) => Promise.all(keys.filter((k) => k !== SHELL).map((k) => caches.delete(k)))),
  )
  self.clients.claim()
})
self.addEventListener('fetch', (e) => {
  const url = new URL(e.request.url)
  if (e.request.method !== 'GET' || url.origin !== location.origin) return
  if (url.pathname.startsWith('/api') || url.pathname.startsWith('/auth')) return
  if (e.request.mode === 'navigate') {
    e.respondWith(fetch(e.request).catch(() => caches.match('/')))
    return
  }
  e.respondWith(
    fetch(e.request)
      .then((r) => {
        const copy = r.clone()
        void caches.open(SHELL).then((c) => c.put(e.request, copy))
        return r
      })
      .catch(() => caches.match(e.request)),
  )
})
