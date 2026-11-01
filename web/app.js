// Karaoke Inteligente · versión web (sin dependencias).
// Mismas ideas que el programa de escritorio: búsqueda tolerante a errores,
// letra adelantada medio segundo, voz del artista en 100/75/50/25 % y modo
// automático que sigue al cantante (con el reconocimiento de voz del navegador).

const ADELANTO = 0.15;              // la línea entra junto con la voz (lo justo para su animación)
const ESPERA_ISLA = 2600;           // ms sin mover el mouse para ocultar la isla
// Idioma del reconocimiento de voz del navegador (escucha uno a la vez).
const VOZ_NAVEGADOR = { es: "es-MX", en: "en-US" };
const NOMBRE_IDIOMA = { es: "Español", en: "Inglés" };
const idiomaVoz = () => (guardado.leer("idioma-voz", "es") === "en" ? "en" : "es");
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
  async borrar(clave) {
    const db = await this.abrir();
    return new Promise((ok) => { const t = db.transaction("archivos", "readwrite"); t.objectStore("archivos").delete(clave); t.oncomplete = ok; t.onerror = ok; });
  },
  async leer(clave) {
    const db = await this.abrir();
    return new Promise((ok) => { const r = db.transaction("archivos").objectStore("archivos").get(clave); r.onsuccess = () => ok(r.result || null); r.onerror = () => ok(null); });
  },
};

// ---------------------------------------------------------------- canciones
let canciones = [], papelera = [], todas = [];
// Por id: favorita, genero, tiempos, portada y las ediciones (nombre, lineas,
// idioma, audio), papelera (fecha en que se borró) o eliminada (para siempre).
const extras = () => guardado.leer("extras", {});
function guardarExtra(id, cambios) { const e = extras(); e[id] = { ...(e[id] || {}), ...cambios }; guardado.escribir("extras", e); }

async function cargarCanciones() {
  let base = [];
  try { base = await (await fetch("datos/canciones.json")).json(); } catch { base = []; }
  const propias = guardado.leer("propias", []);
  const e = extras();
  todas = [...base, ...propias].map((c) => {
    const x = e[c.id] || {};
    // Si se cambió la letra o la pista, los tiempos originales ya no sirven.
    const propiosTiempos = Array.isArray(x.lineas) || x.sinTiemposBase;
    const tiempos = x.tiempos || (propiosTiempos ? null : c.tiempos);
    return { ...c, ...x, tiempos, palabras: propiosTiempos ? null : ajustarPalabras(c.palabras, tiempos) };
  }).filter((c) => !c.eliminada);
  canciones = todas.filter((c) => !c.papelera);
  papelera = todas.filter((c) => c.papelera).sort((a, b) => b.papelera - a.papelera);
}
// Si los tiempos de las líneas se afinaron a mano, las palabras se mueven con su línea.
function ajustarPalabras(palabrasLinea, tiempos) {
  if (!palabrasLinea || !tiempos || palabrasLinea.length !== tiempos.length) return palabrasLinea || null;
  return palabrasLinea.map((fila, i) => {
    if (!fila?.length) return fila;
    const d = tiempos[i] - fila[0][0];
    return Math.abs(d) < 0.01 ? fila : fila.map(([a, b]) => [a + d, b + d]);
  });
}
const porId = (id) => canciones.find((c) => c.id === id);
function guardarPropia(c) {
  const propias = guardado.leer("propias", []).filter((p) => p.id !== c.id);
  propias.push({ id: c.id, codigo: c.codigo, nombre: c.nombre, lineas: c.lineas, idioma: c.idioma, audio: c.audio, tiempos: c.tiempos, propia: true });
  guardado.escribir("propias", propias);
}

// ------------------------------------------------- letras: limpiar e importar
// Mismas reglas que karaoke/importador.py y karaoke/texto.py.
const ETIQUETA = /^\s*(?:\[.*\]|\(.*\)|(?:coro|chorus|estribillo|verso|verse|puente|bridge|intro|outro|pre-?coro|pre-?chorus)\s*\d*\s*(?:\(.*\))?\s*:?)\s*$/i;
const ENCABEZADO = /^\s*(?:#+|nombre\s*:)\s*(.*)$/i;
const MAX_CARACTERES = 80, MAX_LINEAS = 500;
function dividirLinea(linea, maximo = MAX_CARACTERES) {
  if (linea.length <= maximo) return linea ? [linea] : [];
  const partes = []; let actual = "";
  for (let palabra of linea.split(" ")) {
    while (palabra.length > maximo) { if (actual) { partes.push(actual); actual = ""; } partes.push(palabra.slice(0, maximo)); palabra = palabra.slice(maximo); }
    const candidato = actual ? `${actual} ${palabra}` : palabra;
    if (candidato.length <= maximo) actual = candidato; else { partes.push(actual); actual = palabra; }
  }
  if (actual) partes.push(actual);
  return partes;
}
// Quita renglones vacíos y etiquetas ("Coro", "[Verso 2]"), junta espacios y
// divide las líneas muy largas. Devuelve { lineas, ajustadas }.
function limpiarLetra(renglones) {
  let ajustadas = 0;
  const lineas = [];
  for (const crudo of renglones) {
    const linea = crudo.replace(/\s+/g, " ").trim();
    if (!linea || ETIQUETA.test(linea)) continue;
    const partes = dividirLinea(linea);
    if (partes.length > 1) ajustadas++;
    lineas.push(...partes);
  }
  return { lineas: lineas.slice(0, MAX_LINEAS), ajustadas };
}
// Formato de canciones.txt: "# Nombre" (o "Nombre:") antes de cada letra, o
// bloques separados por un renglón vacío con el nombre en el primer renglón.
// Los renglones que empiezan con // son comentarios.
function analizarTexto(texto) {
  const renglones = texto.replace(/\r\n?/g, "\n").split("\n").map((r) => r.trimEnd())
    .filter((r) => !r.trimStart().startsWith("//") && !ETIQUETA.test(r));
  const canciones_ = [];
  if (renglones.some((r) => ENCABEZADO.test(r))) {
    let actual = null;
    for (const r of renglones) {
      const m = r.match(ENCABEZADO);
      if (m) { actual = { nombre: m[1].trim(), renglones: [] }; canciones_.push(actual); }
      else if (r.trim() && actual) actual.renglones.push(r);
    }
  } else {
    let bloque = [];
    for (const r of [...renglones, ""]) {
      if (r.trim()) bloque.push(r.trim());
      else if (bloque.length) { canciones_.push({ nombre: bloque[0], renglones: bloque.slice(1) }); bloque = []; }
    }
  }
  return canciones_.map((c) => ({ nombre: c.nombre.replace(/\s+/g, " ").trim().slice(0, 150), ...limpiarLetra(c.renglones) }));
}
const PALABRAS_ES = new Set("de la que el en y los se no mi tu te por con una un es lo como mas pero yo amor corazon quiero sin las del al eres vida".split(" "));
const PALABRAS_EN = new Set("the you and i to my it in of is that love your dont be so for on me all what when im can".split(" "));
function detectarIdioma(lineas) {
  let es = 0, en = 0;
  for (const p of palabras(lineas.join(" "))) { if (PALABRAS_ES.has(p)) es++; if (PALABRAS_EN.has(p)) en++; }
  return en > es ? "en" : "es";
}
const existeNombre = (nombre, salvo = null) => todas.some((c) => c.id !== salvo && normalizar(c.nombre).trim() === normalizar(nombre).trim());
const siguienteCodigo = () => Math.max(0, ...todas.map((x) => x.codigo || 0)) + 1;

// ------------------------------------------------------- programa del cantante
// Como el archivo PROGRAMA de la consola: las canciones que se van a cantar,
// en orden. La siguiente pendiente tiene prioridad al reconocer (automático) y
// el modo manual pasa a ella al terminar una canción.
const NUMERACION = /^\s*(?:\d+\s*[.)\-:]?|[-•*])\s*/;
const programa = {
  leer() {
    const lista = guardado.leer("programa", []);
    // las que no estaban en la biblioteca se buscan de nuevo (pudieron agregarse)
    for (const e of lista) if (!e.id || !porId(e.id)) e.id = this.resolver(e.nombre);
    return lista;
  },
  escribir(lista) { guardado.escribir("programa", lista); },
  // Nombre exacto (sin tildes ni mayúsculas) o el más parecido, como resolver_nombre.
  resolver(nombre) {
    const n = normalizar(nombre).trim();
    const exacta = canciones.find((c) => normalizar(c.nombre).trim() === n);
    if (exacta) return exacta.id;
    let mejor = null, valor = 0;
    for (const c of canciones) { const v = semejanza(n, normalizar(c.nombre).trim()); if (v > valor) { valor = v; mejor = c; } }
    return valor >= 0.85 ? mejor.id : null;
  },
  agregar(nombres) {
    const lista = this.leer();
    for (const crudo of nombres) {
      const nombre = crudo.replace(NUMERACION, "").trim();
      if (nombre && !nombre.startsWith("//")) lista.push({ nombre, id: this.resolver(nombre), estado: "pendiente" });
    }
    this.escribir(lista);
  },
  siguiente() { return this.leer().find((e) => e.estado === "pendiente" && e.id && porId(e.id)) || null; },
  prioridad() { const s = this.siguiente(); return s ? { [s.id]: 0.12 } : {}; },
  marcarCantada(id) {
    const lista = this.leer(), e = lista.find((x) => x.estado === "pendiente" && x.id === id);
    if (e) { e.estado = "cantada"; this.escribir(lista); }
  },
};

// ------------------------------------------------------------------ historial
// Cada interpretación: canción, modo, inicio y fin, hasta qué línea llegó y si
// se completó (como la tabla HISTORIAL de la consola).
const historial = {
  leer: () => guardado.leer("historial", []),
  iniciar(cancion, modo) {
    this.terminar(false);
    esc.interpretacion = { id: cancion.id, nombre: cancion.nombre, modo, sesion: esc.sesion, inicio: Date.now(), lineas: cancion.lineas.length, hasta: 0 };
  },
  avance(linea) { if (esc.interpretacion) esc.interpretacion.hasta = Math.max(esc.interpretacion.hasta, linea); },
  terminar(completada) {
    const i = esc.interpretacion;
    if (!i) return;
    esc.interpretacion = null;
    if (!completada && i.hasta < 1 && Date.now() - i.inicio < 8000) return;   // se abrió por error
    const lista = this.leer();
    lista.unshift({ ...i, fin: Date.now(), completada });
    guardado.escribir("historial", lista.slice(0, 500));
    if (completada) programa.marcarCantada(i.id);
  },
};

// ------------------------------------------ editar, borrar y la papelera
async function eliminarCancion(c) {
  const si = await dialogo({ titulo: `¿Eliminar «${c.nombre}»?`, mensaje: "Pasa a la papelera; desde ahí la puedes recuperar.", aceptar: "Eliminar", peligro: true });
  if (!si) return;
  guardarExtra(c.id, { papelera: Date.now() });
  await cargarCanciones();
  location.hash = "biblioteca";
  avisar(`«${c.nombre}» está en la papelera`, { texto: "Deshacer", accion: () => recuperarCancion(c.id) });
}
async function recuperarCancion(id) {
  guardarExtra(id, { papelera: null });
  await cargarCanciones(); navegar();
  avisar("Canción recuperada");
}
async function eliminarParaSiempre(c) {
  const e = extras();
  if (c.propia) {
    guardado.escribir("propias", guardado.leer("propias", []).filter((p) => p.id !== c.id));
    delete e[c.id];
    await archivos.borrar("audio:" + c.id);
  } else {
    e[c.id] = { eliminada: true };   // las de ejemplo vienen del sitio: solo se ocultan
  }
  await archivos.borrar("portada:" + c.id);
  guardado.escribir("extras", e);
}

// Diálogo propio (en lugar de prompt/confirm): devuelve true/false, o el texto
// escrito si lleva campo (null al cancelar).
function dialogo({ titulo, mensaje = "", campo = null, aceptar = "Aceptar", cancelar = "Cancelar", peligro = false }) {
  return new Promise((ok) => {
    const d = document.createElement("dialog");
    d.className = "dialogo";
    d.innerHTML = `
      <form method="dialog">
        <h2>${escapar(titulo)}</h2>
        ${mensaje ? `<p class="nota">${escapar(mensaje)}</p>` : ""}
        ${campo ? `<input class="campo" name="valor" autocomplete="off" maxlength="${campo.max || 120}" value="${escapar(campo.valor || "")}" placeholder="${escapar(campo.placeholder || "")}" ${campo.lista?.length ? 'list="dialogo-lista"' : ""}>
          ${campo.lista?.length ? `<datalist id="dialogo-lista">${campo.lista.map((v) => `<option value="${escapar(v)}">`).join("")}</datalist>` : ""}` : ""}
        <div class="dialogo-botones">
          <button class="boton ${peligro ? "peligro" : ""}" value="aceptar">${escapar(aceptar)}</button>
          <button class="boton secundario" value="cancelar" formnovalidate>${escapar(cancelar)}</button>
        </div>
      </form>`;
    document.body.append(d);
    d.addEventListener("close", () => {
      const si = d.returnValue === "aceptar";
      const valor = campo ? (si ? d.querySelector("input").value : null) : si;
      d.remove(); ok(valor);
    });
    d.showModal();
    const entrada = d.querySelector("input");
    if (entrada) { entrada.focus(); entrada.select(); } else d.querySelector('[value="aceptar"]').focus();
  });
}

function descargar(nombre, texto) {
  const url = URL.createObjectURL(new Blob([texto], { type: "text/plain;charset=utf-8" }));
  const a = Object.assign(document.createElement("a"), { href: url, download: nombre });
  document.body.append(a); a.click(); a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 2000);
}
function exportarBiblioteca() {
  const texto = ["// Biblioteca del Karaoke Inteligente, exportada el " + new Date().toLocaleString("es"),
    "// Formato: # Nombre y debajo su letra. Se puede volver a importar.", "",
    ...canciones.map((c) => [`# ${c.nombre}`, ...(c.ejemplo ? [`// © ${c.autor || ""}. Todos los derechos reservados.`] : []), ...c.lineas, ""].join("\n"))].join("\n");
  descargar("canciones.txt", texto);
  avisar(`${canciones.length} canciones exportadas a canciones.txt`);
}
async function importarTexto(archivo) {
  if (archivo.size > 2 * 1024 * 1024) { avisar("El archivo pesa más de 2 MB"); return; }
  const encontradas = analizarTexto(await archivo.text());
  const agregadas = [], omitidas = [];
  const propias = guardado.leer("propias", []);
  for (const c of encontradas) {
    if (!c.nombre) { omitidas.push("(sin nombre)"); continue; }
    if (!c.lineas.length) { omitidas.push(`${c.nombre} (sin letra)`); continue; }
    if (existeNombre(c.nombre) || agregadas.some((a) => normalizar(a.nombre) === normalizar(c.nombre))) { omitidas.push(`${c.nombre} (ya existía)`); continue; }
    const nueva = { id: `propia-${Date.now()}-${agregadas.length}`, codigo: siguienteCodigo() + agregadas.length, nombre: c.nombre,
      lineas: c.lineas, idioma: detectarIdioma(c.lineas), audio: null, tiempos: null, propia: true };
    agregadas.push(nueva); propias.push(nueva);
  }
  guardado.escribir("propias", propias);
  await cargarCanciones();
  await dialogo({
    titulo: agregadas.length ? `Se agregaron ${agregadas.length} canción(es)` : "No se agregó ninguna canción",
    mensaje: [agregadas.length ? agregadas.map((a) => a.nombre).join(", ") + "." : "",
      omitidas.length ? `Omitidas: ${omitidas.join(", ")}.` : ""].filter(Boolean).join(" "),
    aceptar: "Listo", cancelar: "Cerrar",
  });
  location.hash = "biblioteca";
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
// Inicio y fin de cada palabra de la línea i (tal como se muestra, separada por
// espacios): los de la IA si los hay; si no, repartidos según su largo, igual
// que en karaoke/alineacion.py.
const duraPalabra = (t) => Math.min(0.9, Math.max(0.25, 0.12 + 0.055 * t.length));
const trozos = (linea) => linea.split(/\s+/).filter(Boolean);
function tiemposDePalabras(c, i) {
  if (esc.palabras[i]) return esc.palabras[i];
  const fila = trozos(c.lineas[i] || "");
  let r = c.palabras?.[i];
  if (!r || r.length !== fila.length) {
    const t = esc.tiempos, inicio = t[i], siguiente = t[i + 1] ?? inicio + 4;
    const durs = fila.map(duraPalabra), total = durs.reduce((a, b) => a + b, 0) || 1;
    const escala = Math.min(1, Math.max(0.3, siguiente - inicio - 0.2) / total);
    let x = inicio;
    r = durs.map((d) => { const par = [x, x + d * escala]; x += d * escala; return par; });
  }
  return (esc.palabras[i] = r);
}
// Pinta de azul cada palabra de la línea actual conforme se canta.
function pintarPalabras(c, i, segundo) {
  if (i < 0 || i >= c.lineas.length) return;
  const tiempos = tiemposDePalabras(c, i), spans = $("#l-actual").children;
  for (let k = 0; k < spans.length; k++) {
    const [a, b] = tiempos[k] || [Infinity, Infinity];
    const p = segundo <= a ? 0 : segundo >= b ? 1 : (segundo - a) / (b - a);
    const texto = p.toFixed(3);
    if (spans[k].dataset.p === texto) continue;
    spans[k].dataset.p = texto;
    spans[k].style.setProperty("--p", texto);
    spans[k].classList.toggle("cantando", p > 0 && p < 1);
  }
}
function lineaEn(tiempos, segundo) {
  let actual = -1;
  for (let i = 0; i < tiempos.length; i++) { if (tiempos[i] - ADELANTO <= segundo) actual = i; else break; }
  return actual;
}

// --------------------------------------------------------------- búsqueda
// Encuentra canción y línea a partir de unas palabras (tolera errores de dedo).
function buscar(texto, limite = 5, prioridad = {}) {
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
    const valor = Math.max(mejor.puntaje / consulta.length, nombre) + (prioridad[c.id] || 0);
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
function avisar(texto, boton = null) {
  const a = $("#aviso");
  a.textContent = texto;
  a.classList.toggle("con-accion", !!boton);
  if (boton) {
    const b = Object.assign(document.createElement("button"), { textContent: boton.texto, className: "aviso-accion" });
    b.addEventListener("click", () => { a.classList.remove("visible"); boton.accion(); });
    a.append(b);
  }
  a.classList.add("visible");
  clearTimeout(temporizadorAviso);
  temporizadorAviso = setTimeout(() => a.classList.remove("visible"), boton ? 6000 : 2600);
}
const reloj = (s) => `${Math.floor(s / 60)}:${String(Math.floor(s % 60)).padStart(2, "0")}`;

// --------------------------------------------------------------- escenario
const esc = { modo: null, cancion: null, linea: 0, reproductor: null, tiempos: null, raf: 0, pausado: false, reconocedor: null, sincronizando: null, palabras: {}, desfase: 0 };
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
  afinar: `<svg viewBox="0 0 24 24"><path d="M3 17v2h6v-2H3ZM3 5v2h10V5H3Zm10 16v-2h8v-2h-8v-2h-2v6h2ZM7 9v2H3v2h4v2h2V9H7Zm14 4v-2H11v2h10Zm-6-4h2V7h4V5h-4V3h-2v6Z"/></svg>`,
  editar: `<svg viewBox="0 0 24 24"><path d="M3 17.2V21h3.8l11-11-3.8-3.8-11 11ZM20.7 7a1 1 0 0 0 0-1.4l-2.3-2.3a1 1 0 0 0-1.4 0l-1.8 1.8 3.8 3.8L20.7 7Z"/></svg>`,
  basura: `<svg viewBox="0 0 24 24"><path d="M6 19a2 2 0 0 0 2 2h8a2 2 0 0 0 2-2V7H6v12ZM19 4h-3.5l-1-1h-5l-1 1H5v2h14V4Z"/></svg>`,
  importar: `<svg viewBox="0 0 24 24"><path d="M5 20h14v-2H5v2Zm7-3 5-5h-3V4h-4v8H7l5 5Z"/></svg>`,
  exportar: `<svg viewBox="0 0 24 24"><path d="M5 20h14v-2H5v2ZM12 4 7 9h3v6h4V9h3l-5-5Z"/></svg>`,
  recuperar: `<svg viewBox="0 0 24 24"><path d="M13 3a9 9 0 0 0-9 9H1l4 4 4-4H6a7 7 0 1 1 2.1 5l-1.4 1.4A9 9 0 1 0 13 3Z"/></svg>`,
  lista: `<svg viewBox="0 0 24 24"><path d="M3 6h12v2H3V6Zm0 5h12v2H3v-2Zm0 5h8v2H3v-2Zm14-3h2v3h3v2h-3v3h-2v-3h-3v-2h3v-3Z"/></svg>`,
  arriba: `<svg viewBox="0 0 24 24"><path d="m7.4 15.4 4.6-4.6 4.6 4.6L18 14l-6-6-6 6z"/></svg>`,
  abajo: `<svg viewBox="0 0 24 24"><path d="M7.4 8.6 12 13.2l4.6-4.6L18 10l-6 6-6-6z"/></svg>`,
  quitar: `<svg viewBox="0 0 24 24"><path d="m6.4 5 5.6 5.6L17.6 5 19 6.4 13.4 12l5.6 5.6-1.4 1.4-5.6-5.6L6.4 19 5 17.6l5.6-5.6L5 6.4z"/></svg>`,
  saltar: `<svg viewBox="0 0 24 24"><path d="m6 18 8.5-6L6 6v12Zm10-12v12h2V6h-2Z"/></svg>`,
  reloj: `<svg viewBox="0 0 24 24"><path d="M12 2a10 10 0 1 0 0 20 10 10 0 0 0 0-20Zm0 18a8 8 0 1 1 0-16 8 8 0 0 1 0 16Zm.5-13H11v6l5.2 3.2.8-1.3-4.5-2.7V7Z"/></svg>`,
  mic: `<svg viewBox="0 0 24 24"><path d="M12 14a3 3 0 0 0 3-3V5a3 3 0 1 0-6 0v6a3 3 0 0 0 3 3Zm5-3a5 5 0 0 1-10 0H5a7 7 0 0 0 6 6.92V21h2v-3.08A7 7 0 0 0 19 11h-2Z"/></svg>`,
};

function abrirEscenario(modo, cancion, linea = 0) {
  cerrarEscenario(true);
  Object.assign(esc, { modo, cancion, linea, pausado: false, tiempos: null, aviso: "", palabras: {}, oido: [], sesion: Date.now(),
    desfase: +guardado.leer("desfase", 0) || 0 });
  if (cancion) historial.iniciar(cancion, modo);
  $("#escenario").hidden = false;
  document.body.style.overflow = "hidden";
  pintarEscenario();
  mostrarIsla();
  if (modo === "pista") iniciarPista();
  if (modo === "automatico") iniciarAutomatico();
}
function cerrarEscenario(silencioso) {
  cancelAnimationFrame(esc.raf);
  esc.reproductor?.detener(); esc.reproductor = null;
  try { esc.reconocedor?.stop(); } catch { /* ya detenido */ }
  esc.reconocedor = null; esc.sincronizando = null;
  $("#escenario").hidden = true;
  $("#escenario").classList.remove("quieto");
  clearTimeout(temporizadorIsla);
  document.body.style.overflow = "";
  // con pista basta llegar a la última línea; sin pista, pasarla
  const i = esc.interpretacion;
  historial.terminar(!!i && i.hasta >= i.lineas - (esc.modo === "pista" ? 1 : 0));
  if (!silencioso) navegar();   // el programa y el historial cambian al cantar
}

function pintarLetra(lineas, actual, extra = {}) {
  const l = (i) => (i >= 0 && i < lineas.length ? lineas[i] : "");
  const caja = $("#esc-letra");
  if (caja.dataset.actual !== String(actual)) { caja.classList.remove("cambio"); void caja.offsetWidth; caja.classList.add("cambio"); caja.dataset.actual = actual; }
  $("#l-previa").textContent = extra.previa ?? l(actual - 1);
  const elActual = $("#l-actual");
  if (extra.conPalabras && extra.actual === undefined && actual < lineas.length) {
    // cada palabra en su <span> para irla pintando (solo se arma al cambiar de línea)
    const clave = `${Math.max(actual, 0)}|${lineas.length}`;
    if (elActual.dataset.palabras !== clave) {
      elActual.dataset.palabras = clave;
      elActual.innerHTML = trozos(l(Math.max(actual, 0))).map((t) => `<span class="p">${escapar(t)}</span>`).join(" ");
    }
  } else {
    delete elActual.dataset.palabras;
    elActual.textContent = extra.actual ?? (actual >= lineas.length ? "Fin de la canción" : l(Math.max(actual, 0)));
  }
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
      <div class="isla-controles">
        <button class="mini" data-accion="inicio" aria-label="Desde el inicio" title="Desde el inicio">${ICON.inicio}</button>
        <button class="mini" data-accion="menos5" aria-label="Regresar 5 segundos" title="−5 s (←)">${ICON.menos5}</button>
        <button class="redondo" data-accion="pausa" id="b-principal" aria-label="Pausa" title="Pausa (espacio)">${ICON.pausa}</button>
        <button class="mini" data-accion="mas5" aria-label="Adelantar 5 segundos" title="+5 s (→)">${ICON.mas5}</button>
        <button class="mini" data-accion="sincronizar" aria-label="Afinar la sincronía" title="Afinar: marca con toques el inicio de cada línea">${ICON.afinar}</button>
      </div>
      <div class="niveles" role="group" aria-label="Voz del artista" title="Voz del artista: al bajarla se escucha mejor a quien canta">
        <span class="niveles-icono" aria-hidden="true">${ICON.voz}</span>${NIVELES_VOZ.map((n) => `<button data-voz="${n}" class="${n === 1 ? "activo" : ""}" aria-label="Voz del artista al ${n * 100} %">${n * 100} %</button>`).join("")}
      </div>`;
    const barra = $("#t-barra");
    barra.addEventListener("input", () => esc.reproductor && esc.reproductor.ir(barra.value / 100 * esc.reproductor.duracion));
    barra.addEventListener("change", () => barra.blur());   // que la isla se pueda ocultar después
  } else {
    isla.innerHTML = `
      <div class="isla-controles cuadricula">
        <button class="mini con-texto" data-accion="atras" title="Atrás (A)">${ICON.atras}<span>Atrás</span></button>
        <button class="mini con-texto" data-accion="igual" title="Igual (I)">${ICON.igual}<span>Igual</span></button>
        <button class="mini con-texto" data-accion="repetir" title="Repetir (R)">${ICON.repetir}<span>Repetir</span></button>
        <button class="mini con-texto" data-accion="pausa" id="b-pausa" title="Pausa (G / S)">${ICON.pausa}<span>Pausa</span></button>
        ${esc.modo === "automatico" ? `<button class="mini con-texto idioma" data-accion="idioma" id="b-idioma" title="Idioma en que se canta (L)" aria-label="Cambiar idioma"><b>${idiomaVoz().toUpperCase()}</b><span>${NOMBRE_IDIOMA[idiomaVoz()]}</span></button>` : ""}
      </div>
      <button class="boton ${esc.modo === "automatico" ? "automatico" : ""}" data-accion="continuar" title="C / Enter">${ICON.siguiente} ${esc.modo === "automatico" ? "Siguiente línea" : "Continuar"}</button>`;
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
  const duracion = r.duracion, reloj_ = r.segundo, s = reloj_ + esc.desfase;   // desfase: [ y ] afinan la letra
  if (!esc.tiempos && duracion) esc.tiempos = c.tiempos || tiemposAproximados(c.lineas, duracion);
  $("#esc-sub").textContent = `${reloj(reloj_)} / ${reloj(duracion)}`;
  $("#t-actual").textContent = reloj(reloj_); $("#t-total").textContent = reloj(duracion);
  if (duracion && document.activeElement !== $("#t-barra")) $("#t-barra").value = (reloj_ / duracion) * 100;
  $("#esc-progreso").style.width = `${duracion ? (reloj_ / duracion) * 100 : 0}%`;
  const principal = $("#b-principal");
  if (principal.dataset.pausado !== String(r.pausado)) {
    principal.dataset.pausado = String(r.pausado);
    principal.innerHTML = r.pausado ? ICON.play : ICON.pausa;
    principal.setAttribute("aria-label", r.pausado ? "Reproducir" : "Pausa");
    if (r.pausado) mostrarIsla(); else programarOcultarIsla();
  }
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
    pintarLetra(c.lineas, 0, { previa: "", conPalabras: true });
    pintarPalabras(c, 0, s);
    $("#esc-mensaje").textContent = `La letra empieza en ${Math.max(0, Math.ceil(esc.tiempos[0] - ADELANTO - s))} s`;
  } else {
    const linea = r.audio.ended ? c.lineas.length : actual;
    historial.avance(linea);
    if (r.audio.ended && esc.interpretacion) historial.terminar(true);
    pintarLetra(c.lineas, linea, { conPalabras: true });
    pintarPalabras(c, linea, s);
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
  s.marcas.push(+Math.max(0, esc.reproductor.segundo - 0.1).toFixed(2));   // compensa el tiempo de reacción
  if (s.marcas.length >= c.lineas.length) {
    c.palabras = ajustarPalabras(c.palabras, s.marcas);
    c.tiempos = s.marcas; esc.tiempos = s.marcas; esc.sincronizando = null; esc.palabras = {};
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
  const pausa = $("#b-pausa"); if (pausa) pausa.innerHTML = esc.pausado ? `${ICON.play}<span>Seguir</span>` : `${ICON.pausa}<span>Pausa</span>`;
  pintarLetra(c.lineas, esc.linea);
  historial.avance(esc.linea);
  const termino = esc.linea >= c.lineas.length;
  if (termino && esc.interpretacion) historial.terminar(true);
  const siguiente = programa.siguiente();
  if (termino && esc.modo === "automatico") {
    // como en la consola: al terminar una canción se espera la siguiente
    $("#esc-mensaje").textContent = siguiente ? `Terminó. Siguiente en el programa: ${siguiente.nombre}` : "Terminó la canción. Esperando la siguiente…";
    clearTimeout(esc.esperaSiguiente);
    esc.esperaSiguiente = setTimeout(() => {
      if (esc.modo !== "automatico" || esc.cancion !== c) return;
      esc.cancion = null; esc.linea = 0; esc.oido = [];
      cambiarIdiomaVoz(idiomaVoz(), false);
      pintarEscenario();
    }, 3000);
  } else if (esc.modo === "manual") {
    $("#esc-mensaje").textContent = esc.pausado ? "En pausa mientras el cantante afina. Toca «Seguir»."
      : termino ? (siguiente ? `Terminó. Continuar pasa a la siguiente del programa: ${siguiente.nombre}` : "Terminó la canción. Toca ✕ para elegir otra.")
      : "Toca la letra o presiona C / Enter para avanzar";
  }
}
function accion(nombre) {
  const r = esc.reproductor;
  switch (nombre) {
    case "cerrar": cerrarEscenario(); return;
    case "menos5": r?.mover(-5); return;
    case "mas5": r?.mover(5); return;
    case "inicio": r?.ir(0); return;
    case "sincronizar": if (r) empezarSincronizacion(); return;
    case "idioma": {
      const nuevo = (esc.reconocedor?.lang || VOZ_NAVEGADOR[idiomaVoz()]).startsWith("es") ? "en" : "es";
      cambiarIdiomaVoz(nuevo);
      avisar(`Escuchando en ${NOMBRE_IDIOMA[nuevo].toLowerCase()}`);
      return;
    }
    case "pausa":
      if (esc.modo === "pista") { if (r) (r.pausado ? r.reproducir() : r.pausar()); return; }
      esc.pausado = !esc.pausado; break;
    case "continuar": {
      if (esc.pausado || !esc.cancion) break;
      if (esc.linea >= esc.cancion.lineas.length && esc.modo === "manual") {
        const siguiente = programa.siguiente();
        if (siguiente) { abrirEscenario("manual", porId(siguiente.id)); return; }
      }
      esc.linea = Math.min(esc.cancion.lineas.length, esc.linea + 1);
      break;
    }
    case "atras": esc.linea = Math.max(0, esc.linea - 1); break;
    case "igual": break;
    case "repetir": esc.linea = 0; if (esc.cancion && !esc.interpretacion) historial.iniciar(esc.cancion, esc.modo); break;
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
  rec.continuous = true; rec.interimResults = true; rec.lang = VOZ_NAVEGADOR[idiomaVoz()];
  rec.onresult = (ev) => {
    let texto = "";
    for (let i = ev.resultIndex; i < ev.results.length; i++) texto += ev.results[i][0].transcript + " ";
    const nuevas = palabras(texto);
    if (!nuevas.length || esc.pausado) return;
    const oido = esc.oido = [...esc.oido, ...nuevas].slice(-14);
    $("#esc-mensaje").textContent = "Escuchado: " + texto.trim().slice(-80);
    if (!esc.cancion) {
      const [mejor] = buscar(oido.join(" "), 1, programa.prioridad());
      if (mejor && mejor.valor >= 0.7 && oido.length >= 4) {
        esc.cancion = mejor.cancion; esc.linea = mejor.linea;
        historial.iniciar(mejor.cancion, "automatico");
        avisar(`Canción identificada: ${mejor.cancion.nombre}`);
        if (entrarConPista(mejor.cancion, mejor.linea)) return;
        cambiarIdiomaVoz(mejor.cancion.idioma === "en" ? "en" : "es", false);
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
  $("#esc-mensaje").textContent = `Escuchando en ${idiomaVoz() === "en" ? "inglés" : "español"}… empiece a cantar`;
}
// Cambia el idioma en que escucha (se reinicia el reconocimiento para que
// tome el nuevo). `recordar`: guardarlo como preferido.
function cambiarIdiomaVoz(idioma, recordar = true) {
  if (recordar) guardado.escribir("idioma-voz", idioma);
  const boton = $("#b-idioma");
  if (boton) boton.innerHTML = `<b>${idioma.toUpperCase()}</b><span>${NOMBRE_IDIOMA[idioma]}</span>`;
  const rec = esc.reconocedor;
  if (rec && rec.lang !== VOZ_NAVEGADOR[idioma]) {
    rec.lang = VOZ_NAVEGADOR[idioma];
    try { rec.stop(); } catch { /* se reinicia solo con el idioma nuevo */ }
  }
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
    else if (esc.reproductor && !esc.islaOcultaAlTocar) ocultarIsla(true);   // tocar la letra oculta o muestra la isla
  }
});
document.addEventListener("keydown", (e) => {
  if ($("#escenario").hidden || e.target.matches("input, textarea")) return;
  const tecla = e.key.toLowerCase();
  if (esc.sincronizando && (tecla === " " || tecla === "enter")) { e.preventDefault(); marcarLinea(); return; }
  const mapa = { escape: "cerrar", c: "continuar", enter: "continuar", arrowright: esc.modo === "pista" ? "mas5" : "continuar",
    arrowleft: esc.modo === "pista" ? "menos5" : "atras", a: "atras", i: "igual", r: "repetir", g: "pausa", s: "pausa", " ": "pausa",
    ...(esc.modo === "automatico" ? { l: "idioma" } : {}) };
  if (mapa[tecla]) { e.preventDefault(); accion(mapa[tecla]); return; }
  if (esc.modo === "pista" && (tecla === "[" || tecla === "]")) {   // afinar la letra a mano, de 0.1 en 0.1 s
    esc.desfase = Math.round((esc.desfase + (tecla === "]" ? 0.1 : -0.1)) * 10) / 10;
    guardado.escribir("desfase", esc.desfase);
    avisar(esc.desfase === 0 ? "Letra junto con la voz" : `Letra ${Math.abs(esc.desfase).toFixed(1)} s ${esc.desfase > 0 ? "antes" : "después"}`);
  }
});

// La isla se oculta si no se mueve el mouse (o no se toca la pantalla) y
// vuelve en cuanto hay movimiento. Se queda mientras la canción está en pausa,
// mientras se afina o si el puntero o el foco del teclado están en ella.
let temporizadorIsla = 0;
function mostrarIsla() {
  const escenario = $("#escenario");
  if (escenario.hidden) return;
  escenario.classList.remove("quieto");
  programarOcultarIsla();
}
function programarOcultarIsla() {
  clearTimeout(temporizadorIsla);
  temporizadorIsla = setTimeout(() => ocultarIsla(), ESPERA_ISLA);
}
function ocultarIsla(forzar = false) {
  const escenario = $("#escenario"), isla = $("#isla");
  if (escenario.hidden) return;
  const enPausa = esc.modo === "pista" ? (!esc.reproductor || esc.reproductor.pausado) : esc.pausado;
  const ocupada = isla.matches(":hover") || isla.querySelector(":focus-visible") || esc.sincronizando;
  if (!forzar && (enPausa || ocupada)) { programarOcultarIsla(); return; }
  clearTimeout(temporizadorIsla);
  escenario.classList.add("quieto");
}
$("#escenario").addEventListener("pointerdown", () => {
  esc.islaOcultaAlTocar = $("#escenario").classList.contains("quieto");
  mostrarIsla();
});
$("#escenario").addEventListener("pointermove", (e) => { if (e.pointerType === "mouse") mostrarIsla(); });
$("#escenario").addEventListener("wheel", mostrarIsla, { passive: true });
document.addEventListener("keydown", () => mostrarIsla());

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
          <p class="nota">La pista suena y cada palabra se pinta al cantarla. Baja la voz del artista para que se escuche la tuya.</p>
          <div class="acciones"><button class="boton" data-cantar="${destacada.id}">${ICON.play} Reproducir con letra</button></div>
        </div>
      </section>` : ""}
      ${(() => { const s = programa.siguiente(), c = s && porId(s.id); return c ? `
      <a class="tarjeta siguiente-programa" href="#programa">
        <span class="icono-modo">${ICON.lista}</span>
        <span><span class="antetitulo">Sigue en tu programa</span><strong>${escapar(c.nombre)}</strong></span>
        <span class="tenue">Ver programa</span>
      </a>` : ""; })()}
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
        <span>Código ${c.codigo} · ${c.lineas.length} líneas${c.genero ? " · " + escapar(c.genero) : ""}${c.audio ? "" : " · sin pista"}</span>
      </button>`));
    contenido.innerHTML = `
      <div class="encabezado-vista">
        <div><p class="antetitulo">${canciones.length} canciones</p><h1>Biblioteca</h1></div>
        <div class="acciones-vista">
          <a class="boton secundario chico" href="#agregar">${ICON.importar}<span>Agregar o importar</span></a>
          <button class="boton secundario chico" data-exportar>${ICON.exportar}<span>Exportar</span></button>
          ${papelera.length ? `<a class="boton fantasma chico" href="#papelera">${ICON.basura}<span>Papelera (${papelera.length})</span></a>` : ""}
        </div>
      </div>
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
            <button class="boton-icono" data-favorita="${c.id}" aria-label="Favorita" title="Favorita" style="color:${c.favorita ? "var(--acento-texto)" : "var(--texto-2)"}">${corazon(c.favorita)}</button>
            <button class="boton-icono" data-al-programa="${c.id}" aria-label="Agregar al programa" title="Agregar al programa del cantante">${ICON.lista}</button>
            <a class="boton-icono" href="#editar?id=${c.id}" aria-label="Editar" title="Corregir la letra o el nombre">${ICON.editar}</a>
            <button class="boton-icono" data-eliminar="${c.id}" aria-label="Eliminar" title="Eliminar (se puede recuperar)">${ICON.basura}</button>
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
        <p class="etiqueta-campo">¿En qué idioma vas a cantar?</p>
        <div class="niveles idiomas" role="radiogroup" aria-label="Idioma en que se canta">
          ${["es", "en"].map((i) => `<button role="radio" data-idioma-voz="${i}" aria-checked="${idiomaVoz() === i}" class="${idiomaVoz() === i ? "activo" : ""}">${i === "es" ? "Español" : "Inglés"}</button>`).join("")}
        </div>
        <p class="nota" style="margin:8px 0 16px">El navegador escucha un idioma a la vez. Al reconocer la canción cambia solo a su idioma, y durante el karaoke lo cambias con el botón ES/EN o la tecla L.</p>
        <button class="boton automatico" id="empezar-auto" ${soportado ? "" : "disabled"}>${ICON.mic} Empezar a escuchar</button>
        ${soportado ? "" : `<p class="nota" style="color:var(--aviso)">Este navegador no tiene reconocimiento de voz. Ábrelo en Chrome o Edge.</p>`}
      </div>`;
    $("#empezar-auto")?.addEventListener("click", () => abrirEscenario("automatico", null));
    contenido.querySelectorAll("[data-idioma-voz]").forEach((b) => b.addEventListener("click", () => {
      guardado.escribir("idioma-voz", b.dataset.idiomaVoz);
      contenido.querySelectorAll("[data-idioma-voz]").forEach((x) => {
        x.classList.toggle("activo", x === b); x.setAttribute("aria-checked", String(x === b));
      });
    }));
  },

  agregar() {
    contenido.innerHTML = `
      <p class="antetitulo">Biblioteca</p>
      <h1>Agregar canciones</h1>
      ${formularioCancion()}
      <section class="tarjeta" style="margin-top:20px">
        <h2 style="margin-top:0">Importar desde un archivo de texto</h2>
        <p class="nota">Varias canciones a la vez, en el formato de <code>canciones.txt</code>: el nombre en el primer renglón y la letra debajo, con un renglón vacío entre canciones (o <code># Nombre</code> antes de cada letra). Las etiquetas como «Coro» o «[Verso 2]» se quitan solas y las que ya existen se omiten.</p>
        <label class="boton secundario" style="width:max-content">${ICON.importar} Elegir archivo .txt<input type="file" id="importar-txt" accept=".txt,text/plain" hidden></label>
      </section>`;
    $("#importar-txt").addEventListener("change", (e) => e.target.files[0] && importarTexto(e.target.files[0]));
    activarFormulario(null);
  },

  editar(parametros) {
    const c = porId(parametros.get("id"));
    if (!c) { location.hash = "biblioteca"; return; }
    contenido.innerHTML = `
      <p class="antetitulo">Código ${c.codigo}</p>
      <h1>Corregir «${escapar(c.nombre)}»</h1>
      ${formularioCancion(c)}
      <div class="acciones" style="justify-content:flex-end">
        <button class="boton fantasma" data-eliminar="${c.id}">${ICON.basura} Eliminar canción</button>
      </div>`;
    activarFormulario(c);
  },

  programa() {
    const lista = programa.leer(), siguiente = programa.siguiente();
    const sig = siguiente && porId(siguiente.id);
    const estados = { pendiente: "Pendiente", cantada: "Cantada", saltada: "Saltada" };
    contenido.innerHTML = `
      <div class="encabezado-vista">
        <div><p class="antetitulo">Sesión</p><h1>Programa del cantante</h1></div>
        ${lista.length ? `<div class="acciones-vista">
          <button class="boton secundario chico" data-programa-reiniciar>${ICON.recuperar}<span>Reiniciar avance</span></button>
          <button class="boton fantasma chico" data-programa-vaciar>${ICON.basura}<span>Vaciar</span></button></div>` : ""}
      </div>
      <p class="nota">Las canciones que se van a cantar, en orden. En el modo automático la siguiente tiene prioridad al reconocer, y en el manual se pasa a ella al terminar la anterior.</p>
      ${sig ? `<section class="tarjeta siguiente-programa grande">
        <span class="icono-modo">${ICON.play}</span>
        <span><span class="antetitulo">Sigue</span><strong>${escapar(sig.nombre)}</strong></span>
        <span class="acciones" style="margin:0">
          ${sig.audio ? `<button class="boton chico" data-cantar="${sig.id}">${ICON.play}<span>Con pista</span></button>` : ""}
          <button class="boton ${sig.audio ? "secundario" : ""} chico" data-manual="${sig.id}">${ICON.siguiente}<span>${sig.audio ? "Sin pista" : "Cantar"}</span></button>
        </span>
      </section>` : ""}
      <form class="agregar-programa" id="form-programa">
        <input class="campo" name="nombre" list="nombres-canciones" placeholder="Nombre de la canción" autocomplete="off" maxlength="150">
        <datalist id="nombres-canciones">${canciones.map((c) => `<option value="${escapar(c.nombre)}">`).join("")}</datalist>
        <button class="boton" type="submit">${ICON.lista} Agregar</button>
      </form>
      <details class="pegar-lista">
        <summary>Pegar una lista o cargar el archivo PROGRAMA</summary>
        <textarea class="campo" id="lista-programa" rows="6" placeholder="Una canción por renglón; se aceptan números como «1. Sound of You»"></textarea>
        <div class="acciones">
          <button class="boton secundario chico" data-programa-pegar>${ICON.lista}<span>Agregar la lista</span></button>
          <label class="boton secundario chico">${ICON.importar}<span>Cargar PROGRAMA.txt</span><input type="file" id="archivo-programa" accept=".txt,text/plain" hidden></label>
        </div>
      </details>
      ${lista.length ? `<ol class="lista lista-programa">${lista.map((e, i) => {
        const c = e.id && porId(e.id);
        return `<li class="fila-lista ${e.estado} ${siguiente === e ? "es-siguiente" : ""}">
          <span class="orden">${i + 1}</span>
          <div><strong>${escapar(c ? c.nombre : e.nombre)}</strong>
            <span class="nota">${c ? `Código ${c.codigo}` : "No está en la biblioteca"} · <span class="estado-${e.estado}">${siguiente === e ? "Sigue" : estados[e.estado]}</span></span></div>
          <button class="boton-icono chico" data-programa-mover="${i}" data-dir="-1" aria-label="Subir" ${i === 0 ? "disabled" : ""}>${ICON.arriba}</button>
          <button class="boton-icono chico" data-programa-mover="${i}" data-dir="1" aria-label="Bajar" ${i === lista.length - 1 ? "disabled" : ""}>${ICON.abajo}</button>
          <button class="boton-icono chico" data-programa-estado="${i}" aria-label="${e.estado === "pendiente" ? "Saltar" : "Volver a pendiente"}" title="${e.estado === "pendiente" ? "Saltar" : "Volver a pendiente"}">${e.estado === "pendiente" ? ICON.saltar : ICON.recuperar}</button>
          <button class="boton-icono chico" data-programa-quitar="${i}" aria-label="Quitar del programa">${ICON.quitar}</button>
        </li>`; }).join("")}</ol>`
        : `<p class="vacio">El programa está vacío. Agrega canciones con el nombre, pega una lista o usa el botón de la lista en cada canción.</p>`}`;
    $("#form-programa").addEventListener("submit", (e) => {
      e.preventDefault();
      const nombre = new FormData(e.target).get("nombre").trim();
      if (!nombre) return;
      programa.agregar([nombre]); navegar();
      avisar(programa.resolver(nombre) ? `«${nombre}» agregada al programa` : `«${nombre}» agregada (aún no está en la biblioteca)`);
    });
    $("#archivo-programa").addEventListener("change", async (e) => {
      const f = e.target.files[0]; if (!f || f.size > 512 * 1024) return;
      programa.agregar((await f.text()).split(/\r?\n/).filter((r) => r.trim() && !r.trim().startsWith("#")));
      navegar(); avisar("Programa cargado");
    });
  },

  historial() {
    const lista = historial.leer();
    const completas = lista.filter((h) => h.completada).length;
    const conteo = {};
    for (const h of lista) { const k = h.id; conteo[k] = conteo[k] || { nombre: h.nombre, veces: 0, completas: 0 }; conteo[k].veces++; if (h.completada) conteo[k].completas++; }
    const top = Object.entries(conteo).sort((a, b) => b[1].veces - a[1].veces).slice(0, 10);
    const maximo = top[0]?.[1].veces || 1;
    const modos = { manual: "Manual", automatico: "Automático", pista: "Con pista" };
    const porDia = {};
    for (const h of lista.slice(0, 60)) (porDia[new Date(h.inicio).toLocaleDateString("es", { weekday: "long", day: "numeric", month: "long" })] ||= []).push(h);
    contenido.innerHTML = `
      <div class="encabezado-vista">
        <div><p class="antetitulo">Sesión</p><h1>Historial</h1></div>
        ${lista.length ? `<div class="acciones-vista"><button class="boton fantasma chico" data-historial-borrar>${ICON.basura}<span>Borrar historial</span></button></div>` : ""}
      </div>
      ${lista.length ? `
      <div class="cifras">
        <div><strong>${lista.length}</strong><span>interpretaciones</span></div>
        <div><strong>${completas}</strong><span>completas (${Math.round(completas * 100 / lista.length)} %)</span></div>
        <div><strong>${Object.keys(conteo).length}</strong><span>canciones distintas</span></div>
      </div>
      <h2>Más cantadas</h2>
      <ol class="lista ranking">${top.map(([id, d], i) => `
        <li class="fila-lista"><span class="orden">${i + 1}</span>
          <div><strong>${escapar(d.nombre)}</strong><span class="barra"><span style="width:${(d.veces / maximo) * 100}%"></span></span></div>
          <span class="tenue">${d.veces} ${d.veces === 1 ? "vez" : "veces"}</span></li>`).join("")}</ol>
      <h2>Últimas interpretaciones</h2>
      ${Object.entries(porDia).map(([dia, hs]) => `
        <p class="grupo-lineas">${escapar(dia.toUpperCase())}</p>
        <div class="lista">${hs.map((h) => `
          <div class="fila-lista">
            <span class="tenue hora">${new Date(h.inicio).toLocaleTimeString("es", { hour: "2-digit", minute: "2-digit" })}</span>
            <div><strong>${escapar(h.nombre)}</strong><span class="nota">${modos[h.modo] || h.modo} · llegó a la línea ${Math.min(h.hasta + 1, h.lineas)} de ${h.lineas}</span></div>
            <span class="chip ${h.completada ? "completa" : ""}">${h.completada ? "Completa" : "Incompleta"}</span>
          </div>`).join("")}</div>`).join("")}`
      : `<p class="vacio">Todavía no hay interpretaciones. Lo que se cante en cualquier modo aparecerá aquí.</p>`}`;
  },

  mas() {
    const enlaces = [
      ["#programa", ICON.lista, "Programa del cantante", "Las canciones de esta noche, en orden"],
      ["#historial", ICON.reloj, "Historial", "Canciones cantadas y estadísticas"],
      ["#agregar", ICON.importar, "Agregar canciones", "Escribir, pegar o importar un .txt"],
      ["#papelera", ICON.basura, `Papelera${papelera.length ? ` (${papelera.length})` : ""}`, "Recuperar canciones eliminadas"],
    ];
    contenido.innerHTML = `
      <p class="antetitulo">Karaoke inteligente</p>
      <h1>Más</h1>
      <div class="modos">${enlaces.map(([href, icono, titulo, nota]) => `
        <a class="tarjeta modo" href="${href}"><span class="icono-modo">${icono}</span><span><strong>${titulo}</strong><span class="nota">${nota}</span></span></a>`).join("")}</div>
      <p class="nota tenue" style="margin-top:28px">Edgar Alessandro Chocon Oliva · Carné 202212978</p>`;
  },

  papelera() {
    contenido.innerHTML = `
      <div class="encabezado-vista">
        <div><p class="antetitulo">Biblioteca</p><h1>Papelera</h1></div>
        ${papelera.length ? `<div class="acciones-vista"><button class="boton fantasma chico" data-vaciar>${ICON.basura}<span>Vaciar papelera</span></button></div>` : ""}
      </div>
      <p class="nota">Las canciones eliminadas quedan aquí hasta que las recuperes o las elimines para siempre.</p>
      ${papelera.length ? `<div class="lista">${papelera.map((c) => `
        <div class="fila-lista">
          <div><strong>${escapar(c.nombre)}</strong><span class="nota">Código ${c.codigo} · ${c.lineas.length} líneas · eliminada el ${new Date(c.papelera).toLocaleDateString("es")}</span></div>
          <button class="boton secundario chico" data-recuperar="${c.id}">${ICON.recuperar}<span>Recuperar</span></button>
          <button class="boton fantasma chico" data-borrar-siempre="${c.id}" aria-label="Eliminar para siempre">${ICON.basura}<span>Eliminar</span></button>
        </div>`).join("")}</div>` : `<p class="vacio">La papelera está vacía.</p>`}`;
  },
};

// Formulario de una canción: nueva (c = null) o para corregirla.
function formularioCancion(c = null) {
  const idioma = c?.idioma || "es";
  return `
    <form id="form-cancion" class="tarjeta formulario">
      <label>Nombre de la canción<input class="campo" name="nombre" required maxlength="150" placeholder="Mi canción" value="${escapar(c?.nombre || "")}"></label>
      <label>Letra (una línea por renglón)<textarea class="campo" name="letra" required rows="12" placeholder="Pega aquí la letra…">${escapar(c ? c.lineas.join("\n") : "")}</textarea></label>
      <div class="dos-columnas">
        <label>Idioma
          <select class="campo" name="idioma">
            ${c ? "" : `<option value="auto">Detectar solo</option>`}
            <option value="es" ${c && idioma === "es" ? "selected" : ""}>Español</option>
            <option value="en" ${c && idioma === "en" ? "selected" : ""}>Inglés</option>
          </select>
        </label>
        <label>${c?.audio ? "Cambiar la pista" : "Pista de audio (opcional)"}<input class="campo" type="file" name="audio" accept="audio/*"></label>
      </div>
      ${c?.audio ? `<label class="casilla"><input type="checkbox" name="quitar-audio"> Quitar la pista de esta canción</label>` : ""}
      <p class="nota" style="margin:0">${c ? "Si cambias la letra o la pista, los tiempos vuelven a ser aproximados; con «Afinar» los marcas de nuevo." : "Las etiquetas como «Coro» o «[Verso 2]» se quitan solas. Con la pista podrás reproducirla con la letra; al principio los tiempos son aproximados y con «Afinar» los marcas a tu ritmo."}</p>
      <div class="acciones" style="margin:0">
        <button class="boton" type="submit">${c ? "Guardar cambios" : "Guardar canción"}</button>
        ${c ? `<a class="boton secundario" href="#cancion?id=${c.id}">Cancelar</a>` : ""}
      </div>
    </form>`;
}
function activarFormulario(c) {
  $("#form-cancion").addEventListener("submit", async (e) => {
    e.preventDefault();
    const datos = new FormData(e.target), nombre = datos.get("nombre").replace(/\s+/g, " ").trim();
    const { lineas, ajustadas } = limpiarLetra(datos.get("letra").split(/\r?\n/));
    if (!nombre || !lineas.length) { avisar("Escribe el nombre y la letra"); return; }
    if (existeNombre(nombre, c?.id)) { avisar("Ya existe una canción con ese nombre"); return; }
    const idioma = datos.get("idioma") === "auto" ? detectarIdioma(lineas) : datos.get("idioma");
    const archivo = datos.get("audio");
    if (archivo && archivo.size > 40 * 1024 * 1024) { avisar("La pista pesa más de 40 MB"); return; }
    const id = c?.id || "propia-" + Date.now();
    let audio = c ? c.audio : null;
    if (archivo && archivo.size) { await archivos.guardar("audio:" + id, archivo); audio = "idb:audio:" + id; }
    else if (datos.get("quitar-audio")) { await archivos.borrar("audio:" + id); audio = null; }
    if (!c) {
      const propias = guardado.leer("propias", []);
      propias.push({ id, codigo: siguienteCodigo(), nombre, lineas, idioma, audio, tiempos: null, propia: true });
      guardado.escribir("propias", propias);
    } else {
      const cambios = { nombre, idioma, audio };
      const cambioLetra = lineas.join("\n") !== c.lineas.join("\n");
      if (cambioLetra) cambios.lineas = lineas;
      if (cambioLetra || audio !== c.audio) Object.assign(cambios, { tiempos: null, sinTiemposBase: true });
      guardarExtra(id, cambios);
    }
    await cargarCanciones();
    avisar(c ? "Cambios guardados" : (ajustadas ? `Canción guardada (${ajustadas} línea(s) larga(s) divididas)` : "Canción guardada"));
    location.hash = `cancion?id=${id}`;
  });
}

// ------------------------------------------------------------ navegación
async function navegar() {
  const [ruta, consulta] = (location.hash.slice(1) || "inicio").split("?");
  const parametros = new URLSearchParams(consulta || "");
  const vista = vistas[ruta] || vistas.inicio;
  document.querySelectorAll("[data-ruta]").forEach((a) => a.classList.toggle("activa",
    a.dataset.ruta === ruta || (a.dataset.grupo || "").split(" ").includes(ruta)));
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
  } else if (t("[data-eliminar]")) eliminarCancion(porId(t("[data-eliminar]").dataset.eliminar));
  else if (t("[data-recuperar]")) recuperarCancion(t("[data-recuperar]").dataset.recuperar);
  else if (t("[data-borrar-siempre]")) {
    const c = papelera.find((x) => x.id === t("[data-borrar-siempre]").dataset.borrarSiempre);
    if (c && await dialogo({ titulo: `¿Eliminar «${c.nombre}» para siempre?`, mensaje: "Ya no se podrá recuperar.", aceptar: "Eliminar para siempre", peligro: true })) {
      await eliminarParaSiempre(c); await cargarCanciones(); navegar(); avisar("Canción eliminada para siempre");
    }
  } else if (t("[data-vaciar]")) {
    if (await dialogo({ titulo: `¿Vaciar la papelera?`, mensaje: `Se eliminarán para siempre ${papelera.length} canción(es).`, aceptar: "Vaciar", peligro: true })) {
      for (const c of [...papelera]) await eliminarParaSiempre(c);
      await cargarCanciones(); navegar(); avisar("Papelera vacía");
    }
  } else if (t("[data-exportar]")) exportarBiblioteca();
  else if (t("[data-al-programa]")) {
    const c = porId(t("[data-al-programa]").dataset.alPrograma);
    programa.agregar([c.nombre]);
    avisar(`«${c.nombre}» agregada al programa`, { texto: "Ver", accion: () => { location.hash = "programa"; } });
  } else if (t("[data-programa-mover]")) {
    const b = t("[data-programa-mover]"), lista = programa.leer(), i = +b.dataset.programaMover, j = i + +b.dataset.dir;
    if (j >= 0 && j < lista.length) { [lista[i], lista[j]] = [lista[j], lista[i]]; programa.escribir(lista); navegar(); }
  } else if (t("[data-programa-estado]")) {
    const lista = programa.leer(), e = lista[+t("[data-programa-estado]").dataset.programaEstado];
    e.estado = e.estado === "pendiente" ? "saltada" : "pendiente"; programa.escribir(lista); navegar();
  } else if (t("[data-programa-quitar]")) {
    const lista = programa.leer(); lista.splice(+t("[data-programa-quitar]").dataset.programaQuitar, 1); programa.escribir(lista); navegar();
  } else if (t("[data-programa-pegar]")) {
    const texto = $("#lista-programa").value;
    if (texto.trim()) { programa.agregar(texto.split(/\r?\n/)); navegar(); avisar("Lista agregada al programa"); }
  } else if (t("[data-programa-reiniciar]")) {
    programa.escribir(programa.leer().map((e) => ({ ...e, estado: "pendiente" }))); navegar();
  } else if (t("[data-programa-vaciar]")) {
    if (await dialogo({ titulo: "¿Vaciar el programa?", aceptar: "Vaciar", peligro: true })) { programa.escribir([]); navegar(); }
  } else if (t("[data-historial-borrar]")) {
    if (await dialogo({ titulo: "¿Borrar el historial?", mensaje: "Se borran todas las interpretaciones y estadísticas.", aceptar: "Borrar", peligro: true })) { guardado.escribir("historial", []); navegar(); }
  }
  else if (t("[data-genero]")) {
    const c = porId(t("[data-genero]").dataset.genero);
    const generos = [...new Set(canciones.map((x) => x.genero).filter(Boolean))].sort();
    const genero = await dialogo({ titulo: "Género o carpeta", mensaje: "Déjalo vacío para quitarlo.", campo: { valor: c.genero || "", placeholder: "Por ejemplo: Baladas", lista: generos, max: 60 }, aceptar: "Guardar" });
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
