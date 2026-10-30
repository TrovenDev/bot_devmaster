"use strict";
const CACHE = "devmaster-offline-v1";
self.addEventListener("install", event => {
  event.waitUntil(caches.open(CACHE).then(cache => cache.addAll(["/offline.html", "/offline.css"])));
});
self.addEventListener("activate", event => {
  event.waitUntil(caches.keys().then(keys => Promise.all(keys.filter(key => key.startsWith("devmaster-offline-") && key !== CACHE).map(key => caches.delete(key)))));
});
// Somente navegações têm fallback. APIs, credenciais e dados de clientes nunca são armazenados.
self.addEventListener("fetch", event => {
  if (event.request.method === "GET" && event.request.url === `${self.location.origin}/offline.css`) {
    event.respondWith(caches.match("/offline.css").then(cached => cached || fetch(event.request)));
    return;
  }
  if (event.request.mode !== "navigate" || new URL(event.request.url).origin !== self.location.origin) return;
  event.respondWith(fetch(event.request).catch(() => caches.match("/offline.html")));
});
