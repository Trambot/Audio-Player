const CACHE_NAME = 'riff-vault-cache-v1';

self.addEventListener('install', (event) => {
    event.waitUntil(
        caches.open(CACHE_NAME).then((cache) => {
            return cache.addAll([
                '/',
                '/static/style.css',
                '/static/manifest.json'
            ]);
        })
    );
});

self.addEventListener('fetch', (event) => {
    // For a streaming app, we bypass the cache for audio and just fetch normally
    event.respondWith(
        fetch(event.request).catch(() => caches.match(event.request))
    );
});