// Karaoke Inteligente · versión web (sin dependencias).
// Mismas ideas que el programa de escritorio: búsqueda tolerante a errores,
// letra adelantada medio segundo, voz del artista en 100/75/50/25 % y modo
// automático que sigue al cantante (con el reconocimiento de voz del navegador).

const ADELANTO = 0.5;               // la letra se muestra medio segundo antes
const NIVELES_VOZ = [1, 0.75, 0.5, 0.25];
const $ = (s, r = document) => r.querySelector(s);
const contenido = $("#contenido");

// ------------------------------------------------------------------ texto
const normalizar = (t) => t.toLowerCase().normalize("NFD").replace(/[̀-ͯ]/g, "")
  .replace(/ñ/g, "n").replace(/['’]/g, "").replace(/[^a-z0-9\s]/g, " ");
const palabras = (t) => normalizar(t).split(/\s+/).filter(Boolean);
const escapar = (t) => t.replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

function semejanza(a, b) {          // 0..1, distancia de edición normalizada
  if (a === b) return 1;
  const m = a.length, n = b.length;
  if (!m || !n) return 0;
  let previo = Array.from({ length: n + 1 }, (_, j) => j);
  for (let i = 1; i <= m; i++) {
    const fila = [i];
    for (let j = 1; j <= n; j++) {
      fila[j] = Math.min(previo[j] + 1, fila[j - 1] + 1, previo[j - 1] + (a[i - 1] === b[j - 1] ? 0 : 1));
    }
    previo = fila;
  }
  return 1 - previo[n] / Math.max(m, n);
}

// --------------------------------------------------------------- almacenamiento
const guardado = {
  leer(clave, defecto) { try { return JSON.parse(localStorage.getItem("karaoke:" + clave)) ?? defecto; } catch { return defecto; } },
  escribir(clave, valor) { try { localStorage.setItem("karaoke:" + clave, JSON.stringify(valor)); } catch { /* sin espacio */ } },
};
// Los MP3 e imágenes que agrega el usuario van en IndexedDB (no caben en localStorage).
const archivos = {
  db: null,
  async abrir() {
    if (this.db) return this.db;
    this.db = await new Promise((ok, mal) => {
      const r = indexedDB.open("karaoke", 1);
      r.onupgradeneeded = () => r.result.createObjectStore("archivos");
      r.onsuccess = () => ok(r.result);
      r.onerror = () => mal(r.error);
    });
    return this.db;
  },
  async guardar(clave, blob) {
    const db = await this.abrir();
    return new Promise((ok, mal) => { const t = db.transaction("archivos", "readwrite"); t.objectStore("archivos").put(blob, clave); t.oncomplete = ok; t.onerror = () => mal(t.error); });
  },
  async leer(clave) {
    const db = await this.abrir();
    return new Promise((ok) => { const r = db.transaction("archivos").objectStore("archivos").get(clave); r.onsuccess = () => ok(r.result || null); r.onerror = () => ok(null); });
  },
};

// ---------------------------------------------------------------- canciones
let canciones = [];
const extras = () => guardado.leer("extras", {});   // por id: favorita, genero, tiempos, portada
function guardarExtra(id, cambios) { const e = extras(); e[id] = { ...(e[id] || {}), ...cambios }; guardado.escribir("extras", e); }

async function cargarCanciones() {
  let base = [];
  try { base = await (await fetch("datos/canciones.json")).json(); } catch { base = []; }
  const propias = guardado.leer("propias", []);
  const e = extras();
  canciones = [...base, ...propias].map((c) => ({ ...c, ...(e[c.id] || {}), tiempos: (e[c.id] || {}).tiempos || c.tiempos }));
}
const porId = (id) => canciones.find((c) => c.id === id);
function guardarPropia(c) {
  const propias = guardado.leer("propias", []).filter((p) => p.id !== c.id);
  propias.push({ id: c.id, codigo: c.codigo, nombre: c.nombre, lineas: c.lineas, idioma: c.idioma, audio: c.audio, tiempos: c.tiempos, propia: true });
  guardado.escribir("propias", propias);
}

// Portada: la imagen elegida o un arte generado con los colores de la paleta.
function arte(c) {
  let h = 0; for (const ch of c.nombre) h = (h * 31 + ch.charCodeAt(0)) >>> 0;
  const tonos = [[214, 46], [196, 40], [226, 38], [184, 34], [240, 30]];
  const [t1, s1] = tonos[h % tonos.length], t2 = (t1 + 24 + (h % 30)) % 360;
  const inicial = escapar(c.nombre.trim()[0] || "♪").toUpperCase();
  return `<svg class="arte" viewBox="0 0 100 100" preserveAspectRatio="xMidYMid slice" aria-hidden="true">
    <defs><linearGradient id="g${h}" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0" stop-color="hsl(${t1} ${s1}% 32%)"/><stop offset="1" stop-color="hsl(${t2} ${s1 - 8}% 14%)"/></linearGradient></defs>
    <rect width="100" height="100" fill="url(#g${h})"/>
    ${[18, 30, 42].map((r, i) => `<circle cx="${70 - i * 4}" cy="${30 + i * 3}" r="${r}" fill="none" stroke="rgba(255,255,255,${0.08 + i * 0.03})"/>`).join("")}
    <text x="12" y="88" font-family="Inter, system-ui" font-weight="800" font-size="30" fill="rgba(255,255,255,.88)">${inicial}</text></svg>`;
}
const urlsPortada = {};
async function portadaHTML(c) {
  if (c.portada) {
    if (!urlsPortada[c.id]) { const b = await archivos.leer("portada:" + c.id); if (b) urlsPortada[c.id] = URL.createObjectURL(b); }
    if (urlsPortada[c.id]) return `<img src="${urlsPortada[c.id]}" alt="">`;
  }
  return arte(c);
}
const corazon = (lleno) => lleno
  ? `<svg viewBox="0 0 24 24"><path d="M12 21 10.6 19.7C5.4 15 2 12 2 8.4 2 5.4 4.4 3 7.4 3c1.7 0 3.4.8 4.6 2.1C13.2 3.8 14.9 3 16.6 3 19.6 3 22 5.4 22 8.4c0 3.6-3.4 6.6-8.6 11.3z"/></svg>`
  : `<svg viewBox="0 0 24 24"><path d="M16.6 3c-1.7 0-3.4.8-4.6 2.1C10.8 3.8 9.1 3 7.4 3 4.4 3 2 5.4 2 8.4c0 3.6 3.4 6.6 8.6 11.3L12 21l1.4-1.3C18.6 15 22 12 22 8.4 22 5.4 19.6 3 16.6 3zm-4.5 15.2-.1.1-.1-.1C7.1 14 4 11.2 4 8.4 4 6.5 5.5 5 7.4 5c1.5 0 3 1 3.6 2.4h2C13.6 6 15.1 5 16.6 5 18.5 5 20 6.5 20 8.4c0 2.8-3.1 5.6-7.9 9.8z"/></svg>`;

// Tiempos aproximados (proporcionales a las palabras) cuando no hay exactos.
function tiemposAproximados(lineas, duracion) {
  const pesos = lineas.map((l) => Math.max(1, palabras(l).length));
  const total = pesos.reduce((a, b) => a + b, 0), inicio = Math.min(8, duracion * 0.08), util = Math.max(1, duracion - inicio - 4);
  let acumulado = 0;
  return pesos.map((p) => { const t = inicio + util * acumulado / total; acumulado += p; return +t.toFixed(2); });
}
function lineaEn(tiempos, segundo) {
  let actual = -1;
  for (let i = 0; i < tiempos.length; i++) { if (tiempos[i] - ADELANTO <= segundo) actual = i; else break; }
  return actual;
}

// --------------------------------------------------------------- búsqueda
// Encuentra canción y línea a partir de unas palabras (tolera errores de dedo).
function buscar(texto, limite = 5) {
  const consulta = palabras(texto);
  if (!consulta.length) return [];
  const resultados = [];
  for (const c of canciones) {
    const fichas = [];
    c.lineas.forEach((l, i) => palabras(l).forEach((p) => fichas.push({ p, linea: i })));
    let mejor = { puntaje: 0, linea: 0, fin: 0 };
    for (let inicio = 0; inicio < fichas.length; inicio++) {
      let puntaje = 0, k = inicio;
      for (const q of consulta) {
        let encontrado = false;
        for (let salto = 0; salto < 2 && k + salto < fichas.length; salto++) {
          if (semejanza(q, fichas[k + salto].p) >= 0.72) { puntaje += semejanza(q, fichas[k + salto].p); k += salto + 1; encontrado = true; break; }
        }
        if (!encontrado) puntaje -= 0.25;
      }
      if (puntaje > mejor.puntaje) mejor = { puntaje, linea: fichas[inicio].linea, fin: fichas[Math.min(k, fichas.length) - 1]?.linea ?? 0 };
    }
    const nombre = semejanza(normalizar(texto).trim(), normalizar(c.nombre).trim());
    const valor = Math.max(mejor.puntaje / consulta.length, nombre);
    if (valor >= 0.5) resultados.push({ cancion: c, linea: nombre > mejor.puntaje / consulta.length ? 0 : mejor.fin, valor });
  }
  return resultados.sort((a, b) => b.valor - a.valor).slice(0, limite);
}

// ------------------------------------------------------------------ audio
// Reproductor con control de la voz del artista: la voz principal suele estar
// en el centro de la mezcla estéreo; se estima el centro (L+R)/2 solo en la
// banda de la voz (180–5000 Hz) y se resta de ambos canales en la medida pedida.
class Reproductor {
  constructor(url) {
    this.audio = new Audio(url);
    this.audio.preload = "auto";
    this.voz = 1;
    this.ctx = null;
  }
  preparar() {
    if (this.ctx) return;
    const Ctx = window.AudioContext || window.webkitAudioContext;
    if (!Ctx) return;
    const ctx = new Ctx(), fuente = ctx.createMediaElementSource(this.audio);
    const separar = ctx.createChannelSplitter(2), unir = ctx.createChannelMerger(2);
    const mitadL = ctx.createGain(), mitadR = ctx.createGain(); mitadL.gain.value = mitadR.gain.value = 0.5;
    const pasaAltos = ctx.createBiquadFilter(); pasaAltos.type = "highpass"; pasaAltos.frequency.value = 180;
    const pasaBajos = ctx.createBiquadFilter(); pasaBajos.type = "lowpass"; pasaBajos.frequency.value = 5000;
    this.quitar = ctx.createGain(); this.quitar.gain.value = -(1 - (this.voz ?? 1));
    fuente.connect(separar);
    separar.connect(unir, 0, 0); separar.connect(unir, 1, 1);           // la mezcla original
    separar.connect(mitadL, 0); separar.connect(mitadR, 1);
    mitadL.connect(pasaAltos); mitadR.connect(pasaAltos);               // centro = (L+R)/2
    pasaAltos.connect(pasaBajos); pasaBajos.connect(this.quitar);
    this.quitar.connect(unir, 0, 0); this.quitar.connect(unir, 0, 1);   // −centro en ambos canales
    unir.connect(ctx.destination);
    this.ctx = ctx;
  }
  async reproducir() { this.preparar(); if (this.ctx?.state === "suspended") await this.ctx.resume(); await this.audio.play(); }
  pausar() { this.audio.pause(); }
  get pausado() { return this.audio.paused; }
  get segundo() { return this.audio.currentTime || 0; }
  get duracion() { return isFinite(this.audio.duration) ? this.audio.duration : 0; }
  mover(s) { this.audio.currentTime = Math.max(0, Math.min(this.duracion || 0, this.segundo + s)); }
  ir(s) { this.audio.currentTime = s; }
  ajustarVoz(nivel) {
    this.voz = nivel;
    if (this.quitar) this.quitar.gain.setTargetAtTime(-(1 - nivel), this.ctx.currentTime, 0.08);  // sin chasquidos
  }
  detener() { this.audio.pause(); this.audio.src = ""; this.ctx?.close(); }
}
async function urlAudio(c) {
  if (!c.audio) return null;
  if (c.audio.startsWith("idb:")) { const b = await archivos.leer(c.audio.slice(4)); return b ? URL.createObjectURL(b) : null; }
  return c.audio;
}

// ---------------------------------------------------------------- avisos
let temporizadorAviso;
function avisar(texto) {
  const a = $("#aviso"); a.textContent = texto; a.classList.add("visible");
  clearTimeout(temporizadorAviso); temporizadorAviso = setTimeout(() => a.classList.remove("visible"), 2600);
}
const reloj = (s) => `${Math.floor(s / 60)}:${String(Math.floor(s % 60)).padStart(2, "0")}`;

// --------------------------------------------------------------- escenario
const esc = { modo: null, cancion: null, linea: 0, reproductor: null, tiempos: null, raf: 0, pausado: false, reconocedor: null, sincronizando: null };
const ICON = {
  menos5: `<svg viewBox="0 0 24 24"><path d="M12 5V1L7 6l5 5V7a6 6 0 1 1-6 6H4a8 8 0 1 0 8-8Zm-1.1 11h-.9v-3.3l-1 .3v-.7l1.8-.6h.1zm4.3-1.8c0 .3 0 .6-.1.8l-.3.6-.4.4-.6.1-.6-.1-.4-.4-.3-.6-.1-.8v-.7c0-.3 0-.6.1-.8l.3-.6.4-.4.6-.1.6.1.4.4.3.6.1.8zm-.9-.8-.1-.5-.1-.3-.2-.2h-.4l-.2.2-.1.3v1.9l.1.3.2.2h.4l.2-.2.1-.3.1-.5z"/></svg>`,
  mas5: `<svg viewBox="0 0 24 24"><path d="M12 5V1l5 5-5 5V7a6 6 0 1 0 6 6h2a8 8 0 1 1-8-8Zm-1.1 11h-.9v-3.3l-1 .3v-.7l1.8-.6h.1zm4.3-1.8c0 .3 0 .6-.1.8l-.3.6-.4.4-.6.1-.6-.1-.4-.4-.3-.6-.1-.8v-.7c0-.3 0-.6.1-.8l.3-.6.4-.4.6-.1.6.1.4.4.3.6.1.8zm-.9-.8-.1-.5-.1-.3-.2-.2h-.4l-.2.2-.1.3v1.9l.1.3.2.2h.4l.2-.2.1-.3.1-.5z"/></svg>`,
  inicio: `<svg viewBox="0 0 24 24"><path d="M12 5V1L7 6l5 5V7a6 6 0 1 1-6 6H4a8 8 0 1 0 8-8Z"/></svg>`,
  voz: `<svg viewBox="0 0 24 24"><path d="M9 13a4 4 0 1 0 0-8 4 4 0 0 0 0 8Zm0 2c-2.7 0-8 1.3-8 4v2h16v-2c0-2.7-5.3-4-8-4Zm7.8-9.6-1.6 1.7a3.6 3.6 0 0 1 0 4.2l1.6 1.7a5.8 5.8 0 0 0 0-7.6ZM20 2.1l-1.6 1.6a8.8 8.8 0 0 1 0 12.2L20 17.6A11.1 11.1 0 0 0 20 2.1Z"/></svg>`,
  atras: `<svg viewBox="0 0 24 24"><path d="M6 6h2v12H6zm3.5 6 8.5 6V6z"/></svg>`,
  igual: `<svg viewBox="0 0 24 24"><path d="M7 7h10v3l4-4-4-4v3H5v6h2V7Zm10 10H7v-3l-4 4 4 4v-3h12v-6h-2v4Zm-4-2V9h-1l-2 1v1h1.5v4H13Z"/></svg>`,
  repetir: `<svg viewBox="0 0 24 24"><path d="M12 5V1L7 6l5 5V7a6 6 0 1 1-6 6H4a8 8 0 1 0 8-8Z"/></svg>`,
  play: `<svg viewBox="0 0 24 24"><path d="M8 5v14l11-7z"/></svg>`,
  pausa: `<svg viewBox="0 0 24 24"><path d="M6 19h4V5H6v14Zm8-14v14h4V5h-4Z"/></svg>`,
  siguiente: `<svg viewBox="0 0 24 24"><path d="M8.6 16.6 13.2 12 8.6 7.4 10 6l6 6-6 6z"/></svg>`,
  mic: `<svg viewBox="0 0 24 24"><path d="M12 14a3 3 0 0 0 3-3V5a3 3 0 1 0-6 0v6a3 3 0 0 0 3 3Zm5-3a5 5 0 0 1-10 0H5a7 7 0 0 0 6 6.92V21h2v-3.08A7 7 0 0 0 19 11h-2Z"/></svg>`,
};

function abrirEscenario(modo, cancion, linea = 0) {
  cerrarEscenario(true);
  Object.assign(esc, { modo, cancion, linea, pausado: false, tiempos: null, aviso: "" });
  $("#escenario").hidden = false;
  document.body.style.overflow = "hidden";
  pintarEscenario();
  if (modo === "pista") iniciarPista();
  if (modo === "automatico") iniciarAutomatico();
}
function cerrarEscenario(silencioso) {
  cancelAnimationFrame(esc.raf);
  esc.reproductor?.detener(); esc.reproductor = null;
  try { esc.reconocedor?.stop(); } catch { /* ya detenido */ }
  esc.reconocedor = null; esc.sincronizando = null;
  $("#escenario").hidden = true;
  document.body.style.overflow = "";
  if (!silencioso && esc.cancion && esc.modo !== "automatico") {
    const veces = guardado.leer("veces", {}); veces[esc.cancion.id] = (veces[esc.cancion.id] || 0) + 1; guardado.escribir("veces", veces);
  }
}

function pintarLetra(lineas, actual, extra = {}) {
  const l = (i) => (i >= 0 && i < lineas.length ? lineas[i] : "");
  const caja = $("#esc-letra");
  if (caja.dataset.actual !== String(actual)) { caja.classList.remove("cambio"); void caja.offsetWidth; caja.classList.add("cambio"); caja.dataset.actual = actual; }
  $("#l-previa").textContent = extra.previa ?? l(actual - 1);
  $("#l-actual").textContent = extra.actual ?? (actual >= lineas.length ? "Fin de la canción" : l(Math.max(actual, 0)));
  $("#l-siguiente").textContent = extra.siguiente ?? (actual >= lineas.length ? "" : l(Math.max(actual, 0) + 1));
  $("#l-despues").textContent = extra.despues ?? (actual >= lineas.length ? "" : l(Math.max(actual, 0) + 2));
}
function estado(texto, clase = "") { const e = $("#esc-estado"); e.textContent = texto; e.className = "chip " + clase; }

function pintarEscenario() {
  const c = esc.cancion;
  $("#esc-nombre").textContent = c ? c.nombre : "Modo automático";
  const isla = $("#isla");
  if (esc.modo === "pista") {
    isla.innerHTML = `
      <div class="barra-tiempo"><span id="t-actual">0:00</span><input id="t-barra" type="range" min="0" max="100" step="0.1" value="0" aria-label="Posición"><span id="t-total">0:00</span></div>
      <div class="fila">
        <button class="control" data-accion="menos5">${ICON.menos5}−5 s</button>
        <button class="control" data-accion="inicio">${ICON.inicio}Inicio</button>
        <button class="control" data-accion="mas5">${ICON.mas5}+5 s</button>
        <button class="control" data-accion="sincronizar" title="Marcar con toques el inicio de cada línea">${ICON.siguiente}Afinar</button>
      </div>
      <div class="etiqueta-voz"><span>Voz del artista</span><span class="tenue">al bajarla se escucha mejor a quien canta</span></div>
      <div class="niveles" role="group" aria-label="Voz del artista">${NIVELES_VOZ.map((n) => `<button data-voz="${n}" class="${n === 1 ? "activo" : ""}">${n * 100} %</button>`).join("")}</div>
      <div style="height:12px"></div>
      <button class="boton" data-accion="pausa" id="b-principal">${ICON.pausa} Pausa</button>`;
    const barra = $("#t-barra");
    barra.addEventListener("input", () => esc.reproductor && esc.reproductor.ir(barra.value / 100 * esc.reproductor.duracion));
  } else {
    isla.innerHTML = `
      <div class="fila">
        <button class="control" data-accion="atras">${ICON.atras}Atrás</button>
        <button class="control" data-accion="igual">${ICON.igual}Igual</button>
        <button class="control" data-accion="repetir">${ICON.repetir}Repetir</button>
        <button class="control" data-accion="pausa" id="b-pausa">${ICON.pausa}Pausa</button>
      </div>
      <button class="boton ${esc.modo === "automatico" ? "automatico" : ""}" data-accion="continuar">${ICON.siguiente} ${esc.modo === "automatico" ? "Siguiente línea" : "Continuar"}</button>`;
    actualizarManual();
  }
}

// ---- modo pista (reproducir con letra)
// `desde` y `voz` los usa el modo automático: al reconocer la canción la pista
// entra donde va el cantante, con la voz del artista bajada.
async function iniciarPista(desde = 0, voz = 1) {
  const c = esc.cancion, url = await urlAudio(c);
  if (!url) { pintarLetra([], 0, { actual: "Esta canción no tiene pista de audio", siguiente: "Agrégale un MP3 desde «Agregar canción»." }); return; }
  esc.reproductor = new Reproductor(url);
  esc.reproductor.ajustarVoz(voz);
  document.querySelectorAll("[data-voz]").forEach((x) => x.classList.toggle("activo", +x.dataset.voz === voz));
  if (desde > 0) {
    const a = esc.reproductor.audio;
    if (a.readyState >= 1) a.currentTime = desde;
    else a.addEventListener("loadedmetadata", () => { a.currentTime = desde; }, { once: true });
  }
  estado("PREPARANDO", "intro");
  $("#esc-sub").textContent = "Cargando…";
  try { await esc.reproductor.reproducir(); } catch { estado("EN PAUSA", "pausa"); avisar("Toca «Reproducir» para empezar"); }
  const bucle = () => { actualizarPista(); esc.raf = requestAnimationFrame(bucle); };
  bucle();
}
function actualizarPista() {
  const r = esc.reproductor, c = esc.cancion;
  if (!r) return;
  const duracion = r.duracion, s = r.segundo;
  if (!esc.tiempos && duracion) esc.tiempos = c.tiempos || tiemposAproximados(c.lineas, duracion);
  $("#esc-sub").textContent = `${reloj(s)} / ${reloj(duracion)}`;
  $("#t-actual").textContent = reloj(s); $("#t-total").textContent = reloj(duracion);
  if (duracion && document.activeElement !== $("#t-barra")) $("#t-barra").value = (s / duracion) * 100;
  $("#esc-progreso").style.width = `${duracion ? (s / duracion) * 100 : 0}%`;
  $("#b-principal").innerHTML = r.pausado ? `${ICON.play} Reproducir` : `${ICON.pausa} Pausa`;
  if (!esc.tiempos) return;
  if (esc.sincronizando) {
    estado("AFINANDO", "intro");
    const i = esc.sincronizando.marcas.length;
    pintarLetra(c.lineas, i, { previa: c.lineas[i - 1] || "", actual: c.lineas[i] ?? "¡Listo!" });
    $("#esc-mensaje").textContent = i < c.lineas.length ? "Toca la letra (o espacio) justo cuando empieza esta línea" : "Tiempos guardados";
    return;
  }
  const actual = lineaEn(esc.tiempos, s);
  if (r.pausado) estado("EN PAUSA", "pausa");
  else if (actual < 0) estado("INTRO", "intro");
  else estado("SONANDO");
  if (actual < 0) {
    pintarLetra(c.lineas, 0, { previa: "" });
    $("#esc-mensaje").textContent = `La letra empieza en ${Math.max(0, Math.ceil(esc.tiempos[0] - ADELANTO - s))} s`;
  } else {
    pintarLetra(c.lineas, r.audio.ended ? c.lineas.length : actual);
    $("#esc-mensaje").textContent = esc.aviso && performance.now() < esc.avisoHasta ? esc.aviso
      : (c.tiempos ? "" : "Tiempos aproximados · toca «Afinar» para marcarlos a tu ritmo");
  }
}
// "Afinar": la canción vuelve al inicio y cada toque marca el inicio de una línea.
function empezarSincronizacion() {
  esc.sincronizando = { marcas: [] };
  esc.reproductor.ir(0); esc.reproductor.reproducir();
  avisar("Toca la letra cuando empiece cada línea");
}
function marcarLinea() {
  const s = esc.sincronizando, c = esc.cancion;
  s.marcas.push(+(esc.reproductor.segundo + ADELANTO * 0.4).toFixed(2));   // compensa el tiempo de reacción
  if (s.marcas.length >= c.lineas.length) {
    c.tiempos = s.marcas; esc.tiempos = s.marcas; esc.sincronizando = null;
    guardarExtra(c.id, { tiempos: s.marcas });
    if (c.propia) guardarPropia(c);
    esc.reproductor.ir(0);
    avisar("Tiempos guardados: la letra irá exacta");
  }
}

// ---- modo manual y automático
function actualizarManual() {
  const c = esc.cancion;
  if (!c) { pintarLetra([], 0, { previa: "", actual: "Cante y la letra aparecerá aquí", siguiente: "Reconocemos la canción con unas cuantas palabras.", despues: "" }); return; }
  $("#esc-sub").textContent = `Línea ${Math.min(esc.linea + 1, c.lineas.length)} de ${c.lineas.length}${esc.modo === "automatico" ? " · automático" : ""}`;
  $("#esc-progreso").style.width = `${Math.min(1, esc.linea / c.lineas.length) * 100}%`;
  estado(esc.pausado ? "EN PAUSA" : (esc.linea >= c.lineas.length ? "TERMINÓ" : (esc.modo === "automatico" ? "SIGUIENDO" : "CANTANDO")), esc.pausado ? "pausa" : "");
  const pausa = $("#b-pausa"); if (pausa) pausa.innerHTML = esc.pausado ? `${ICON.play}Seguir` : `${ICON.pausa}Pausa`;
  pintarLetra(c.lineas, esc.linea);
  if (esc.modo === "manual") $("#esc-mensaje").textContent = esc.pausado ? "En pausa mientras el cantante afina. Toca «Seguir»." : "Toca la letra o presiona C / Enter para avanzar";
}
function accion(nombre) {
  const r = esc.reproductor;
  switch (nombre) {
    case "cerrar": cerrarEscenario(); return;
    case "menos5": r?.mover(-5); return;
    case "mas5": r?.mover(5); return;
    case "inicio": r?.ir(0); return;
    case "sincronizar": if (r) empezarSincronizacion(); return;
    case "pausa":
      if (esc.modo === "pista") { if (r) (r.pausado ? r.reproducir() : r.pausar()); return; }
      esc.pausado = !esc.pausado; break;
    case "continuar": if (!esc.pausado && esc.cancion) esc.linea = Math.min(esc.cancion.lineas.length, esc.linea + 1); break;
    case "atras": esc.linea = Math.max(0, esc.linea - 1); break;
    case "igual": break;
    case "repetir": esc.linea = 0; break;
  }
  if (esc.modo !== "pista") actualizarManual();
}

// Modo automático: el reconocimiento de voz del navegador (Chrome, Edge, Safari)
// identifica la canción con unas palabras y avanza la letra al ritmo del cantante.
function iniciarAutomatico() {
  const Rec = window.SpeechRecognition || window.webkitSpeechRecognition;
  actualizarManual();
  if (!Rec) { $("#esc-mensaje").textContent = "Este navegador no tiene reconocimiento de voz. Use Chrome o Edge."; return; }
  const rec = new Rec();
  rec.continuous = true; rec.interimResults = true; rec.lang = "en-US";
  let oido = [];
  rec.onresult = (ev) => {
    let texto = "";
    for (let i = ev.resultIndex; i < ev.results.length; i++) texto += ev.results[i][0].transcript + " ";
    const nuevas = palabras(texto);
    if (!nuevas.length || esc.pausado) return;
    oido = [...oido, ...nuevas].slice(-14);
    $("#esc-mensaje").textContent = "Escuchado: " + texto.trim().slice(-80);
    if (!esc.cancion) {
      const [mejor] = buscar(oido.join(" "), 1);
      if (mejor && mejor.valor >= 0.7 && oido.length >= 4) {
        esc.cancion = mejor.cancion; esc.linea = mejor.linea;
        rec.lang = mejor.cancion.idioma === "es" ? "es-ES" : "en-US";
        avisar(`Canción identificada: ${mejor.cancion.nombre}`);
        if (entrarConPista(mejor.cancion, mejor.linea)) return;
        pintarEscenario();
      }
      return;
    }
    seguir(oido);
  };
  rec.onend = () => { if (esc.reconocedor === rec) try { rec.start(); } catch { /* se reintenta solo */ } };
  rec.onerror = (e) => { if (e.error === "not-allowed") $("#esc-mensaje").textContent = "Permita el micrófono para usar el modo automático."; };
  esc.reconocedor = rec;
  try { rec.start(); } catch { /* ya iniciado */ }
  $("#esc-mensaje").textContent = "Escuchando… empiece a cantar";
}
// Si la canción reconocida tiene pista y tiempos, la pista entra justo donde va
// el cantante (a media línea, más lo que tardó el reconocimiento) con la voz del
// artista al 25 %, y desde ahí la letra sigue a la pista.
const VOZ_AL_RECONOCER = 0.25, LATENCIA_RECONOCIMIENTO = 0.8;
function puntoDeEntrada(tiempos, linea, fraccion = 0.6, latencia = LATENCIA_RECONOCIMIENTO) {
  if (!tiempos?.length) return 0;
  linea = Math.min(Math.max(linea, 0), tiempos.length - 1);
  const inicio = tiempos[linea], fin = linea + 1 < tiempos.length ? tiempos[linea + 1] : inicio + 4;
  return Math.max(0, inicio + fraccion * (fin - inicio) + latencia);
}
function entrarConPista(cancion, linea) {
  if (!cancion.audio || !cancion.tiempos || cancion.tiempos.length !== cancion.lineas.length) return false;
  const rec = esc.reconocedor; esc.reconocedor = null;
  try { rec?.stop(); } catch { /* ya detenido */ }
  Object.assign(esc, { modo: "pista", tiempos: cancion.tiempos, pausado: false });
  pintarEscenario();
  iniciarPista(puntoDeEntrada(cancion.tiempos, linea), VOZ_AL_RECONOCER);
  esc.aviso = "Canción reconocida: la pista entra donde vas cantando, con la voz del artista al 25 %";
  esc.avisoHasta = performance.now() + 6000;
  return true;
}

// Avanza cuando las últimas palabras oídas coinciden con el final de la línea
// actual (70 %) o con el comienzo de las siguientes.
function seguir(oido) {
  const c = esc.cancion, recientes = oido.slice(-6);
  const puntaje = (linea) => {
    const p = palabras(c.lineas[linea] || "");
    if (!p.length) return 0;
    let coinciden = 0;
    for (const q of recientes) if (p.some((x) => semejanza(q, x) >= 0.75)) coinciden++;
    return coinciden / Math.min(p.length, recientes.length);
  };
  let mejor = esc.linea, valor = puntaje(esc.linea);
  for (let i = esc.linea + 1; i <= Math.min(c.lineas.length - 1, esc.linea + 2); i++) {
    const v = puntaje(i); if (v > valor + 0.15) { valor = v; mejor = i; }
  }
  if (mejor !== esc.linea && valor >= 0.5) { esc.linea = mejor; actualizarManual(); }
}

// Eventos del escenario
$("#escenario").addEventListener("click", (e) => {
  const b = e.target.closest("[data-accion]");
  if (b) { accion(b.dataset.accion); return; }
  const v = e.target.closest("[data-voz]");
  if (v && esc.reproductor) {
    esc.reproductor.ajustarVoz(+v.dataset.voz);
    document.querySelectorAll("[data-voz]").forEach((x) => x.classList.toggle("activo", x === v));
    return;
  }
  if (e.target.closest("#esc-letra")) {
    if (esc.sincronizando) marcarLinea();
    else if (esc.modo === "manual" || esc.modo === "automatico") accion("continuar");
    else if (esc.reproductor) accion("pausa");
  }
});
document.addEventListener("keydown", (e) => {
  if ($("#escenario").hidden || e.target.matches("input, textarea")) return;
  const tecla = e.key.toLowerCase();
  if (esc.sincronizando && (tecla === " " || tecla === "enter")) { e.preventDefault(); marcarLinea(); return; }
  const mapa = { escape: "cerrar", c: "continuar", enter: "continuar", arrowright: esc.modo === "pista" ? "mas5" : "continuar",
    arrowleft: esc.modo === "pista" ? "menos5" : "atras", a: "atras", i: "igual", r: "repetir", g: "pausa", s: "pausa", " ": "pausa" };
  if (mapa[tecla]) { e.preventDefault(); accion(mapa[tecla]); }
});

// ------------------------------------------------------------------ vistas
const vistas = {
  async inicio() {
    const destacada = canciones.find((c) => c.audio) || canciones[0];
    contenido.innerHTML = `
      <p class="antetitulo">Karaoke inteligente</p>
      <h1>¿Qué cantamos hoy?</h1>
      ${destacada ? `
      <section class="destacada">
        <div class="portada">${await portadaHTML(destacada)}</div>
        <div>
          <p class="antetitulo">Canción destacada</p>
          <h2 style="margin:4px 0 6px">${escapar(destacada.nombre)}</h2>
          <p class="nota">La pista suena y la letra va medio segundo adelantada. Baja la voz del artista para que se escuche la tuya.</p>
          <div class="acciones"><button class="boton" data-cantar="${destacada.id}">${ICON.play} Reproducir con letra</button></div>
        </div>
      </section>` : ""}
      <h2>Elige cómo seguir la letra</h2>
      <div class="modos">
        <a class="tarjeta modo" href="#manual"><span class="icono-modo">${ICON.siguiente}</span><span><strong>Modo manual</strong><span class="nota">Escribe 2 o 3 palabras que escuches y avanza con un toque.</span></span></a>
        <a class="tarjeta modo auto" href="#automatico"><span class="icono-modo">${ICON.mic}</span><span><strong>Modo automático</strong><span class="nota">Canta: se reconoce la canción y la letra te sigue.</span></span></a>
        <a class="tarjeta modo" href="#agregar"><span class="icono-modo"><svg viewBox="0 0 24 24"><path d="M11 5h2v6h6v2h-6v6h-2v-6H5v-2h6z"/></svg></span><span><strong>Agregar canción</strong><span class="nota">Pega tu letra y, si quieres, su MP3.</span></span></a>
      </div>`;
  },

  async biblioteca(parametros) {
    const filtro = parametros.get("filtro") || "";
    const generos = [...new Set(canciones.map((c) => c.genero).filter(Boolean))].sort();
    const lista = canciones.filter((c) => !filtro || (filtro === "favoritas" ? c.favorita : c.genero === filtro));
    const tarjetas = await Promise.all(lista.map(async (c) => `
      <button class="cancion" data-ver="${c.id}">
        <div class="portada">${await portadaHTML(c)}${c.favorita ? `<span class="favorita">${corazon(true)}</span>` : ""}</div>
        <strong>${escapar(c.nombre)}</strong>
        <span>${c.lineas.length} líneas${c.genero ? " · " + escapar(c.genero) : ""}${c.audio ? "" : " · sin pista"}</span>
      </button>`));
    contenido.innerHTML = `
      <p class="antetitulo">${canciones.length} canciones</p>
      <h1>Biblioteca</h1>
      <div class="filtros">
        ${[["", "Todas"], ["favoritas", "Favoritas"], ...generos.map((g) => [g, g])].map(([v, t]) =>
          `<button class="chip ${v === filtro ? "activo" : ""}" data-filtro="${escapar(v)}">${escapar(t)}</button>`).join("")}
      </div>
      ${lista.length ? `<div class="rejilla">${tarjetas.join("")}</div>`
        : `<p class="nota">${filtro === "favoritas" ? "Aún no hay favoritas: toca el corazón en una canción." : "No hay canciones aquí."}</p>`}`;
  },

  async cancion(parametros) {
    const c = porId(parametros.get("id"));
    if (!c) { location.hash = "biblioteca"; return; }
    const grupos = [];
    for (let i = 0; i < c.lineas.length; i += 10) grupos.push(c.lineas.slice(i, i + 10));
    contenido.innerHTML = `
      <div class="detalle">
        <div class="portada">${await portadaHTML(c)}</div>
        <div>
          <p class="antetitulo">Código ${c.codigo}${c.ejemplo ? " · canción de ejemplo" : ""}</p>
          <h1 style="margin-bottom:10px">${escapar(c.nombre)}</h1>
          <div class="filtros">
            <span class="chip">${c.lineas.length} líneas</span>
            <span class="chip">${c.idioma === "en" ? "Inglés" : "Español"}</span>
            <button class="chip" data-genero="${c.id}">Género: ${escapar(c.genero || "ninguno")}</button>
            <button class="chip" data-portada="${c.id}">${c.portada ? "Cambiar portada" : "Agregar portada"}</button>
          </div>
          <div class="acciones">
            ${c.audio ? `<button class="boton" data-cantar="${c.id}">${ICON.play} Reproducir con letra</button>` : ""}
            <button class="boton ${c.audio ? "secundario" : ""}" data-manual="${c.id}">${ICON.siguiente} ${c.audio ? "Cantar sin pista" : "Cantar"}</button>
            <button class="boton-icono" data-favorita="${c.id}" aria-label="Favorita" style="color:${c.favorita ? "var(--acento-texto)" : "var(--texto-2)"}">${corazon(c.favorita)}</button>
          </div>
          ${grupos.map((g, i) => `<p class="grupo-lineas">LÍNEAS ${i * 10 + 1}–${i * 10 + g.length}</p><ol class="lineas" start="${i * 10 + 1}" style="counter-reset: linea ${i * 10}">${g.map((l) => `<li>${escapar(l)}</li>`).join("")}</ol>`).join("")}
          ${c.ejemplo ? `<p class="nota tenue" style="margin-top:20px">Letra y grabación © ${escapar(c.autor || "")}. Todos los derechos reservados.</p>` : ""}
        </div>
      </div>`;
  },

  manual() {
    contenido.innerHTML = `
      <p class="antetitulo">Modo manual</p>
      <h1>¿Qué está cantando?</h1>
      <p class="nota">Escribe 2 o 3 palabras que escuches. Toleramos errores de dedo.</p>
      <input class="campo" id="busqueda" placeholder="Por ejemplo: follow me everywhere" autocomplete="off" autofocus>
      <div id="resultados" style="margin-top:16px"></div>`;
    const campo = $("#busqueda"), caja = $("#resultados");
    let temporizador;
    campo.addEventListener("input", () => {
      clearTimeout(temporizador);
      temporizador = setTimeout(async () => {
        const encontrados = buscar(campo.value);
        caja.innerHTML = encontrados.length || !campo.value.trim() ? (await Promise.all(encontrados.map(async (r) => `
          <button class="tarjeta resultado" data-manual="${r.cancion.id}" data-linea="${r.linea}">
            <span class="mini">${await portadaHTML(r.cancion)}</span>
            <span><strong>${escapar(r.cancion.nombre)}</strong><br><span class="extracto">Línea ${r.linea + 1}: ${escapar(r.cancion.lineas[r.linea])}</span></span>
          </button>`))).join("") : `<p class="nota">No encontramos esas palabras en ninguna canción.</p>`;
      }, 160);
    });
  },

  automatico() {
    const soportado = !!(window.SpeechRecognition || window.webkitSpeechRecognition);
    contenido.innerHTML = `
      <p class="antetitulo">Modo automático</p>
      <h1>Canta y la letra te sigue</h1>
      <div class="tarjeta">
        <p style="margin-top:0">El reconocimiento de voz escucha al cantante, identifica la canción con unas cuantas palabras y avanza la letra sola. Los mismos controles sirven para corregirla.</p>
        <ul class="nota">
          <li>Canta cerca del micrófono; si suena música, mejor con audífonos.</li>
          <li>Funciona en Chrome, Edge y Safari (en el teléfono también).</li>
        </ul>
        <button class="boton automatico" id="empezar-auto" ${soportado ? "" : "disabled"}>${ICON.mic} Empezar a escuchar</button>
        ${soportado ? "" : `<p class="nota" style="color:var(--aviso)">Este navegador no tiene reconocimiento de voz. Ábrelo en Chrome o Edge.</p>`}
      </div>`;
    $("#empezar-auto")?.addEventListener("click", () => abrirEscenario("automatico", null));
  },

  agregar() {
    contenido.innerHTML = `
      <p class="antetitulo">Biblioteca</p>
      <h1>Agregar canción</h1>
      <form id="form-agregar" class="tarjeta" style="display:grid;gap:14px">
        <label>Nombre de la canción<input class="campo" name="nombre" required maxlength="150" placeholder="Mi canción"></label>
        <label>Letra (una línea por renglón)<textarea class="campo" name="letra" required placeholder="Pega aquí la letra…"></textarea></label>
        <label>Pista de audio (opcional, MP3 / WAV / OGG)<input class="campo" type="file" name="audio" accept="audio/*"></label>
        <p class="nota" style="margin:0">Con la pista podrás reproducirla con la letra. Al principio los tiempos son aproximados; con «Afinar» los marcas a tu ritmo con toques.</p>
        <button class="boton" type="submit">Guardar canción</button>
      </form>`;
    $("#form-agregar").addEventListener("submit", async (e) => {
      e.preventDefault();
      const datos = new FormData(e.target), nombre = datos.get("nombre").trim();
      const lineas = datos.get("letra").split(/\r?\n/).map((l) => l.trim())
        .filter((l) => l && !/^[\[(].*[\])]$/.test(l) && !/^(coro|chorus|verso|verse|puente|bridge|intro|outro)\b/i.test(l));
      if (!nombre || !lineas.length) { avisar("Escribe el nombre y la letra"); return; }
      if (canciones.some((c) => normalizar(c.nombre).trim() === normalizar(nombre).trim())) { avisar("Ya existe una canción con ese nombre"); return; }
      const id = "propia-" + Date.now();
      const c = { id, codigo: Math.max(0, ...canciones.map((x) => x.codigo || 0)) + 1, nombre, lineas,
        idioma: /\b(the|you|and|love|my|is)\b/i.test(lineas.join(" ")) ? "en" : "es", audio: null, tiempos: null, propia: true };
      const archivo = datos.get("audio");
      if (archivo && archivo.size) {
        if (archivo.size > 40 * 1024 * 1024) { avisar("La pista pesa más de 40 MB"); return; }
        await archivos.guardar("audio:" + id, archivo); c.audio = "idb:audio:" + id;
      }
      guardarPropia(c); await cargarCanciones();
      avisar("Canción guardada"); location.hash = `cancion?id=${id}`;
    });
  },
};

// ------------------------------------------------------------ navegación
async function navegar() {
  const [ruta, consulta] = (location.hash.slice(1) || "inicio").split("?");
  const parametros = new URLSearchParams(consulta || "");
  const vista = vistas[ruta] || vistas.inicio;
  document.querySelectorAll("[data-ruta]").forEach((a) => a.classList.toggle("activa", a.dataset.ruta === (ruta === "cancion" ? "biblioteca" : ruta)));
  await vista(parametros);
  contenido.focus({ preventScroll: true });
  window.scrollTo(0, 0);
}
window.addEventListener("hashchange", navegar);

contenido.addEventListener("click", async (e) => {
  const t = (s) => e.target.closest(s);
  if (t("[data-cantar]")) abrirEscenario("pista", porId(t("[data-cantar]").dataset.cantar));
  else if (t("[data-manual]")) { const b = t("[data-manual]"); abrirEscenario("manual", porId(b.dataset.manual), +(b.dataset.linea || 0)); }
  else if (t("[data-ver]")) location.hash = `cancion?id=${t("[data-ver]").dataset.ver}`;
  else if (t("[data-filtro]") !== null && t("[data-filtro]")) location.hash = `biblioteca?filtro=${encodeURIComponent(t("[data-filtro]").dataset.filtro)}`;
  else if (t("[data-favorita]")) {
    const c = porId(t("[data-favorita]").dataset.favorita); c.favorita = !c.favorita;
    guardarExtra(c.id, { favorita: c.favorita }); avisar(c.favorita ? "Agregada a favoritas" : "Quitada de favoritas"); navegar();
  } else if (t("[data-genero]")) {
    const c = porId(t("[data-genero]").dataset.genero);
    const genero = prompt("Género o carpeta (vacío para quitarlo):", c.genero || "");
    if (genero !== null) { c.genero = genero.trim().slice(0, 60); guardarExtra(c.id, { genero: c.genero }); navegar(); }
  } else if (t("[data-portada]")) {
    const c = porId(t("[data-portada]").dataset.portada), entrada = document.createElement("input");
    entrada.type = "file"; entrada.accept = "image/*";
    entrada.onchange = async () => {
      const f = entrada.files[0]; if (!f) return;
      if (f.size > 15 * 1024 * 1024) { avisar("La imagen pesa más de 15 MB"); return; }
      await archivos.guardar("portada:" + c.id, f); delete urlsPortada[c.id];
      c.portada = true; guardarExtra(c.id, { portada: true }); avisar("Portada guardada"); navegar();
    };
    entrada.click();
  }
});

await cargarCanciones();
navegar();
