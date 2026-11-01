// Service worker del Karaoke Inteligente: la app se instala en el teléfono o la
// computadora y funciona sin internet.
//   * La app (HTML, JS, CSS, iconos, canciones de ejemplo) se pide primero a la
//     red, para tener siempre la última versión, y si no hay conexión sale de
//     la caché.
//   * Las pistas de audio se guardan completas y se sirven por partes (Range),
//     como las pide el reproductor para adelantar y regresar.
//   * La biblioteca de la IA (CDN) y las fuentes quedan guardadas al usarse.
//     El modelo de Whisper lo guarda la propia biblioteca.
const VERSION = "karaoke-app-v1.2.0-5";
const CACHE_AUDIO = "karaoke-audio";      // no se borra entre versiones
const CACHE_EXTERNOS = "karaoke-externos";
const APP = [
  "./", "app.js", "ia.js", "ia-trabajador.js", "afinacion.js", "estilos.css", "manifest.webmanifest", "icono.png",
  "iconos/icono-192.png", "iconos/icono-512.png", "iconos/icono-maskable-512.png", "iconos/apple-touch-icon.png",
  "datos/canciones.json",
];
const AUDIO = ["audio/Sound_of_You.mp3", "audio/Ghost_of_you_Remastered.mp3"];

self.addEventListener("install", (evento) => {
  evento.waitUntil((async () => {
    await (await caches.open(VERSION)).addAll(APP);
    const audio = await caches.open(CACHE_AUDIO);
    await Promise.allSettled(AUDIO.map(async (u) => (await audio.match(u)) || audio.add(u)));
    await self.skipWaiting();
  })());
});

self.addEventListener("activate", (evento) => {
  evento.waitUntil((async () => {
    for (const nombre of await caches.keys()) {
      if (nombre.startsWith("karaoke-app-") && nombre !== VERSION) await caches.delete(nombre);
    }
    await self.clients.claim();
  })());
});

self.addEventListener("fetch", (evento) => {
  const pedido = evento.request;
  if (pedido.method !== "GET") return;
  const url = new URL(pedido.url);
  if (url.origin === self.location.origin) {
    if (url.pathname.includes("/audio/")) evento.respondWith(audio(evento));
    else evento.respondWith(redPrimero(pedido));
  } else if (/(^|\.)cdn\.jsdelivr\.net$|^fonts\.(googleapis|gstatic)\.com$/.test(url.hostname)) {
    evento.respondWith(cachePrimero(pedido));
  }
});

async function redPrimero(pedido) {
  const cache = await caches.open(VERSION);
  try {
    const respuesta = await fetch(pedido);
    if (respuesta.ok && !respuesta.redirected) cache.put(pedido, respuesta.clone());
    return respuesta;
  } catch {
    return (await cache.match(pedido, { ignoreSearch: true }))
      || (pedido.mode === "navigate" ? cache.match("./") : Response.error());
  }
}

async function cachePrimero(pedido) {
  const cache = await caches.open(CACHE_EXTERNOS);
  const guardada = await cache.match(pedido);
  if (guardada) return guardada;
  const respuesta = await fetch(pedido);
  if (respuesta.ok || respuesta.type === "opaque") cache.put(pedido, respuesta.clone());
  return respuesta;
}

// La pista completa se guarda la primera vez (en segundo plano, para que empiece
// a sonar ya) y después se sirve por partes desde la caché.
async function audio(evento) {
  const pedido = evento.request;
  const direccion = pedido.url.split("#")[0];
  const cache = await caches.open(CACHE_AUDIO);
  const completa = await cache.match(direccion);
  if (!completa) {
    evento.waitUntil(cache.add(direccion).catch(() => {}));
    return fetch(pedido);
  }
  const rango = pedido.headers.get("range");
  if (!rango) return completa;
  const datos = await completa.blob(), total = datos.size;
  const m = /bytes=(\d*)-(\d*)/.exec(rango);
  let inicio = m && m[1] ? Number(m[1]) : 0;
  let fin = m && m[2] ? Number(m[2]) : total - 1;
  if (m && !m[1] && m[2]) { inicio = Math.max(0, total - Number(m[2])); fin = total - 1; }
  fin = Math.min(fin, total - 1);
  if (inicio >= total) return new Response(null, { status: 416, headers: { "Content-Range": `bytes */${total}` } });
  return new Response(datos.slice(inicio, fin + 1), {
    status: 206,
    headers: {
      "Content-Type": completa.headers.get("Content-Type") || "audio/mpeg",
      "Content-Range": `bytes ${inicio}-${fin}/${total}`,
      "Content-Length": String(fin - inicio + 1),
      "Accept-Ranges": "bytes",
    },
  });
}
