const CACHE = 'trading-app-v1'
const ASSETS = ['/', '/assets/']

self.addEventListener('install', e => {
  self.skipWaiting()
})

self.addEventListener('activate', e => {
  e.waitUntil(clients.claim())
})

self.addEventListener('fetch', e => {
  // Only cache same-origin static assets; pass API calls through
  const url = new URL(e.request.url)
  if (url.pathname.startsWith('/auth') || url.pathname.startsWith('/signals') || 
      url.pathname.startsWith('/instruments') || url.pathname.startsWith('/ws')) {
    return
  }
  e.respondWith(
    caches.match(e.request).then(r => r || fetch(e.request).then(res => {
      if (res.status === 200 && e.request.method === 'GET') {
        const clone = res.clone()
        caches.open(CACHE).then(c => c.put(e.request, clone))
      }
      return res
    }))
  )
})
