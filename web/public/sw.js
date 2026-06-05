const CACHE = 'trading-app-v2'

self.addEventListener('install', e => {
  self.skipWaiting()
})

self.addEventListener('activate', e => {
  // Clear all old caches on activation
  e.waitUntil(
    caches.keys().then(keys =>
      Promise.all(keys.map(k => caches.delete(k)))
    ).then(() => clients.claim())
  )
})

self.addEventListener('fetch', e => {
  const url = new URL(e.request.url)
  // Never cache API calls — only cache static assets from same origin
  const isApi = url.port === '8001' ||
    url.pathname.startsWith('/auth') ||
    url.pathname.startsWith('/watchlist') ||
    url.pathname.startsWith('/signals') ||
    url.pathname.startsWith('/instruments') ||
    url.pathname.startsWith('/trades') ||
    url.pathname.startsWith('/chat') ||
    url.pathname.startsWith('/trend-rr') ||
    url.pathname.startsWith('/smc') ||
    url.pathname.startsWith('/ws') ||
    url.pathname.startsWith('/health')
  if (isApi) return  // Let all API calls go straight to network

  // Cache only static assets
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
