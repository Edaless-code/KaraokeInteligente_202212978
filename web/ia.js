// La IA de la versión web: escucha la pista con Whisper (en ia-trabajador.js)
// y con lo que oyó, palabra por palabra y con su tiempo:
//   * sincroniza una letra ya escrita (en qué segundo empieza cada línea y cada
//     palabra), igual que karaoke/alineacion.py en la consola;
//   * o escribe la letra si solo se subió el audio, igual que
//     frases_por_pausas en karaoke/audio/desde_audio.py.
// Las funciones de texto no usan el navegador (se prueban con Node).

// ------------------------------------------------------------ texto (como Python)
export function normalizar(texto) {
  return texto.toLowerCase().replace(/ñ/g, "\u0000").normalize("NFKD").replace(/[̀-ͯ]/g, "")
    .replace(/\u0000/g, "ñ").replace(/['’]/g, "").replace(/[^a-z0-9ñ ]+/g, " ").replace(/\s+/g, " ").trim();
}
export const palabras = (texto) => { const n = normalizar(texto); return n ? n.split(" ") : []; };

// Parecido entre dos palabras (0..1) como difflib.SequenceMatcher.ratio.
function bloquesComunes(a, b) {
  if (!a || !b) return 0;
  let mejor = 0, ia = 0, ib = 0;
  for (let i = 0; i < a.length; i++) {
    for (let j = 0; j < b.length; j++) {
      let k = 0;
      while (i + k < a.length && j + k < b.length && a[i + k] === b[j + k]) k++;
      if (k > mejor) { mejor = k; ia = i; ib = j; }
    }
  }
  if (!mejor) return 0;
  return mejor + bloquesComunes(a.slice(0, ia), b.slice(0, ib)) + bloquesComunes(a.slice(ia + mejor), b.slice(ib + mejor));
}
export function semejanza(a, b) {
  if (a === b) return 1;
  if (!a || !b) return 0;
  if (Math.abs(a.length - b.length) > Math.floor(Math.max(a.length, b.length) / 2) + 1) return 0;
  return (2 * bloquesComunes(a, b)) / (a.length + b.length);
}

// ------------------------------------------- alineamiento (karaoke/alineacion.py)
const COINCIDE = 2.0, PARECIDA = 1.0, DISTINTA = -1.0, SALTO_LETRA = -0.7, SALTO_IA = -0.5, BONO_SEGUIDA = 0.5;
function puntaje(a, b) {
  if (a === b) return COINCIDE;
  const s = semejanza(a, b);
  if (s >= 0.78) return COINCIDE * s;
  if (s >= 0.6) return PARECIDA * s;
  return DISTINTA;
}
// Para cada palabra de la letra, el índice de la palabra oída con que se alineó.
export function alinearPalabras(letra, oidas) {
  const n = letra.length, m = oidas.length;
  if (!n || !m) return new Array(n).fill(null);
  const menos = -Infinity, matriz = () => Array.from({ length: n + 1 }, () => new Float64Array(m + 1).fill(menos));
  const coincide = matriz(), salto = matriz();
  const desdeC = Array.from({ length: n + 1 }, () => new Uint8Array(m + 1));
  const desdeS = Array.from({ length: n + 1 }, () => new Uint8Array(m + 1));
  const memo = new Map();
  const p = (i, j) => { const k = i * (m + 1) + j; if (!memo.has(k)) memo.set(k, puntaje(letra[i], oidas[j])); return memo.get(k); };
  salto[0][0] = 0;
  for (let j = 1; j <= m; j++) { salto[0][j] = 0; desdeS[0][j] = 4; }
  for (let i = 1; i <= n; i++) { salto[i][0] = salto[i - 1][0] + SALTO_LETRA; desdeS[i][0] = 2; }
  for (let i = 1; i <= n; i++) {
    const extra = i === n ? 0 : SALTO_IA;
    for (let j = 1; j <= m; j++) {
      const pj = p(i - 1, j - 1);
      const seguida = coincide[i - 1][j - 1] + (pj > 0 ? BONO_SEGUIDA : 0), suelta = salto[i - 1][j - 1];
      if (seguida >= suelta) { coincide[i][j] = seguida + pj; desdeC[i][j] = 1; } else { coincide[i][j] = suelta + pj; desdeC[i][j] = 0; }
      let mejor = coincide[i - 1][j] + SALTO_LETRA, paso = 1;
      for (const [valor, desde] of [[salto[i - 1][j] + SALTO_LETRA, 2], [coincide[i][j - 1] + extra, 3], [salto[i][j - 1] + extra, 4]]) {
        if (valor > mejor || (valor === mejor && desde > paso)) { mejor = valor; paso = desde; }
      }
      salto[i][j] = mejor; desdeS[i][j] = paso;
    }
  }
  const resultado = new Array(n).fill(null);
  let i = n, j = m, estado = coincide[n][m] >= salto[n][m] ? "c" : "s";
  while (i > 0) {
    if (estado === "c") {
      if (p(i - 1, j - 1) > 0) resultado[i - 1] = j - 1;
      estado = desdeC[i][j] === 1 ? "c" : "s"; i--; j--;
    } else {
      const paso = desdeS[i][j];
      if (paso === 1 || paso === 2) i--; else j--;
      estado = paso === 1 || paso === 3 ? "c" : "s";
    }
  }
  return resultado;
}

function partesOidas(oidas) {
  const tokens = [], inicios = [], fines = [];
  for (const o of oidas) {
    const partes = palabras(o.texto), paso = (o.fin - o.inicio) / Math.max(1, partes.length);
    partes.forEach((parte, k) => { tokens.push(parte); inicios.push(o.inicio + paso * k); fines.push(o.inicio + paso * (k + 1)); });
  }
  return { tokens, inicios, fines };
}

// Inicio de cada línea según lo oído; las líneas sin palabras oídas se
// reparten entre sus vecinas (karaoke/alineacion.py: sincronia + _completar).
function sincronia(lineas, oidas, duracion) {
  const letra = [], lineaDe = [];
  lineas.forEach((l, n) => palabras(l).forEach((p) => { letra.push(p); lineaDe.push(n); }));
  const { tokens, inicios: tiempoDe } = partesOidas(oidas);
  const pareja = alinearPalabras(letra, tokens);
  const inicios = new Array(lineas.length).fill(null);
  pareja.forEach((j, k) => { if (j !== null && inicios[lineaDe[k]] === null) inicios[lineaDe[k]] = tiempoDe[j]; });
  return completar(inicios, lineas, duracion);
}
function completar(inicios, lineas, duracion) {
  const n = inicios.length, pesos = lineas.map((l) => Math.max(1, palabras(l).length));
  const r = [...inicios];
  let conocidos = r.map((t, i) => (t !== null ? i : -1)).filter((i) => i >= 0);
  if (!conocidos.length) {
    const total = pesos.reduce((a, b) => a + b, 0) || 1;
    let acumulado = 0;
    return r.map((_, i) => { const t = (duracion * acumulado) / total; acumulado += pesos[i]; return t; });
  }
  let ultimo = -1;
  for (const i of conocidos) { if (r[i] <= ultimo) r[i] = null; else ultimo = r[i]; }
  conocidos = r.map((t, i) => (t !== null ? i : -1)).filter((i) => i >= 0);
  for (let i = conocidos[0] - 1; i >= 0; i--) r[i] = Math.max(0, r[i + 1] - pesos[i] * 0.45);
  for (let c = 0; c + 1 < conocidos.length; c++) {
    const a = conocidos[c], b = conocidos[c + 1];
    if (b - a < 2) continue;
    const total = pesos.slice(a, b).reduce((x, y) => x + y, 0);
    let acumulado = pesos[a];
    for (let i = a + 1; i < b; i++) { r[i] = r[a] + ((r[b] - r[a]) * acumulado) / total; acumulado += pesos[i]; }
  }
  for (let i = conocidos[conocidos.length - 1] + 1; i < n; i++) r[i] = Math.min(Math.max(duracion, r[i - 1]), r[i - 1] + pesos[i - 1] * 0.45);
  return r.map((t) => Math.round(t * 100) / 100);
}

const dura = (trozo) => Math.min(0.9, Math.max(0.25, 0.12 + 0.055 * trozo.length));
function repartir(trozos, desde, hasta) {
  const duraciones = trozos.map(dura), total = duraciones.reduce((a, b) => a + b, 0) || 1;
  const escala = Math.min(1, Math.max(0, hasta - desde) / total);
  let t = desde;
  return duraciones.map((d) => { const par = [t, t + d * escala]; t += d * escala; return par; });
}
function compartir(tiempos, j, antes, trozo) {
  const [inicio, fin] = tiempos[j], largo = antes.reduce((a, t) => a + t.length, 0);
  const corte = inicio + ((fin - inicio) * largo) / Math.max(1, largo + trozo.length);
  tiempos[j] = [corte, fin];
  return corte;
}

// Inicio de cada línea y (inicio, fin) de cada palabra tal como se muestra
// (karaoke/alineacion.py: tiempos_de_palabras).
export function tiemposDePalabras(lineas, oidas, duracion) {
  const total = duracion || (oidas.length ? oidas[oidas.length - 1].fin : 0);
  const base = sincronia(lineas, oidas, total);
  const trozos = lineas.map((l) => l.split(/\s+/).filter(Boolean));
  const letra = [], dueno = [];
  trozos.forEach((fila, i) => fila.forEach((t, j) => palabras(t).forEach((p) => { letra.push(p); dueno.push(`${i},${j}`); })));
  const { tokens, inicios: ini, fines: fin } = partesOidas(oidas);
  const pareja = alinearPalabras(letra, tokens);
  const oido = new Map();
  pareja.forEach((j, k) => {
    if (j === null) return;
    const actual = oido.get(dueno[k]);
    if (!actual) oido.set(dueno[k], [ini[j], fin[j]]);
    else { actual[0] = Math.min(actual[0], ini[j]); actual[1] = Math.max(actual[1], fin[j]); }
  });
  let ultimo = -1;
  trozos.forEach((fila, i) => fila.forEach((_, j) => {
    const t = oido.get(`${i},${j}`);
    if (!t) return;
    if (t[0] <= ultimo) oido.delete(`${i},${j}`); else ultimo = t[0];
  }));

  const resultado = [];
  let finAnterior = 0;
  trozos.forEach((fila, i) => {
    const siguiente = i + 1 < base.length ? base[i + 1] : Math.max(total, base[i] + 4);
    if (!fila.length) { resultado.push([]); return; }
    const conocidas = fila.map((_, j) => j).filter((j) => oido.has(`${i},${j}`));
    let tiempos = new Array(fila.length).fill(null);
    if (!conocidas.length) {
      const inicio = Math.max(base[i], finAnterior);
      tiempos = repartir(fila, inicio, Math.max(inicio, siguiente - 0.2));
    } else {
      for (const j of conocidas) tiempos[j] = [...oido.get(`${i},${j}`)];
      const primera = conocidas[0];
      if (primera) {
        let hasta = tiempos[primera][0];
        let desde = Math.max(finAnterior, hasta - fila.slice(0, primera).reduce((a, t) => a + dura(t), 0));
        if (hasta - desde < 0.1 * primera) { desde = hasta; hasta = compartir(tiempos, primera, fila.slice(0, primera), fila[primera]); }
        tiempos.splice(0, primera, ...repartir(fila.slice(0, primera), desde, hasta));
      }
      for (let c = 0; c + 1 < conocidas.length; c++) {
        const a = conocidas[c], b = conocidas[c + 1];
        if (b - a < 2) continue;
        let desde = tiempos[a][1], hasta = tiempos[b][0];
        if (hasta - desde < 0.1 * (b - a - 1)) { desde = hasta; hasta = compartir(tiempos, b, fila.slice(a + 1, b), fila[b]); }
        tiempos.splice(a + 1, b - a - 1, ...repartir(fila.slice(a + 1, b), desde, hasta));
      }
      const ultima = conocidas[conocidas.length - 1];
      if (ultima < fila.length - 1) {
        const desde = tiempos[ultima][1];
        const hasta = Math.min(siguiente - 0.1, desde + fila.slice(ultima + 1).reduce((a, t) => a + dura(t), 0));
        tiempos.splice(ultima + 1, fila.length - ultima - 1, ...repartir(fila.slice(ultima + 1), desde, Math.max(desde, hasta)));
      }
    }
    const limpias = [];
    tiempos.forEach(([a, b], j) => {
      a = Math.max(a, j === 0 ? finAnterior : limpias[j - 1][0] + 0.01);
      const tope = j + 1 < tiempos.length ? tiempos[j + 1][0] : Math.min(siguiente, a + 3);
      b = Math.min(Math.max(b, a + 0.08), Math.max(tope, a + 0.08));
      limpias.push([Math.round(a * 100) / 100, Math.round(b * 100) / 100]);
    });
    resultado.push(limpias);
    finAnterior = limpias[limpias.length - 1][1];
  });
  const inicios = resultado.map((f, i) => (f.length ? f[0][0] : base[i]));
  for (let i = 1; i < inicios.length; i++) inicios[i] = Math.max(inicios[i], inicios[i - 1]);
  return { tiempos: inicios.map((t) => Math.round(t * 100) / 100), palabras: resultado };
}

// ------------------------------- letra desde el audio (frases_por_pausas)
const MAYUSCULA_NORMAL = new Set(["i", "i'm", "i'll", "i've", "i'd", "god", "oh", "dios"]);
const ALUCINACIONES = new Set(["music", "musica", "applause", "aplausos", "silence", "subtitles", "thank you",
  "thanks for watching", "gracias", "subtitulos", "amara org"]);
const esAlucinacion = (texto) => { const n = normalizar(texto); return !/[a-zñ]{2,}/.test(n) || ALUCINACIONES.has(n); };

// Agrupa las palabras con tiempo en líneas: una línea termina en una pausa del
// cantante, al final de una oración o cuando la siguiente palabra empieza con
// mayúscula (así escribe Whisper el inicio de un verso). Devuelve la letra con
// los tiempos de cada línea y de cada palabra.
export function letraDesdePalabras(oidas, { pausa = 0.55, maximo = 80 } = {}) {
  const grupos = [];
  let actual = [];
  const cerrar = () => { if (actual.length) grupos.push(actual); actual = []; };
  for (const o of oidas) {
    const texto = o.texto.replace(/[^\p{L}\p{N}\s'’,.!?¿¡-]/gu, "").trim();
    if (!texto) continue;
    if (actual.length) {
      const anterior = actual[actual.length - 1];
      const limpio = texto.replace(/^[¿¡"'(]+/, "").toLowerCase();
      const nuevoVerso = /^\p{Lu}/u.test(texto) && !MAYUSCULA_NORMAL.has(limpio) && actual.length >= 3;
      const largoActual = actual.map((p) => p.texto).join(" ").length;
      const silencio = o.inicio - anterior.fin;
      if (silencio >= pausa || (largoActual >= 40 && silencio >= pausa * 0.4) || /[.?!]$/.test(anterior.texto)
          || nuevoVerso || largoActual + 1 + texto.length > maximo) cerrar();
    }
    actual.push({ texto, inicio: o.inicio, fin: o.fin });
  }
  cerrar();
  const lineas = [], tiempos = [], porPalabra = [];
  for (const g of grupos) {
    const texto = g.map((p) => p.texto).join(" ").replace(/^[\s.,]+|[\s,]+$/g, "");
    if (!texto || esAlucinacion(texto)) continue;
    // la IA a veces repite la misma línea en bucle: más de 3 veces seguidas, fuera
    if (lineas.length >= 3 && lineas.slice(-3).every((l) => l.toLowerCase() === texto.toLowerCase())) continue;
    lineas.push(texto);
    tiempos.push(Math.round(g[0].inicio * 100) / 100);
    porPalabra.push(texto.split(/\s+/).map((_, k) => {
      const p = g[Math.min(k, g.length - 1)];
      return [Math.round(p.inicio * 100) / 100, Math.round(p.fin * 100) / 100];
    }));
  }
  return { lineas, tiempos, palabras: porPalabra };
}

// "Ghost_of_you (Official Audio).mp3" -> "Ghost of you" (karaoke/nombres_audio.py)
export function nombreDesdeArchivo(nombreArchivo) {
  const tallo = nombreArchivo.replace(/\.[^.]+$/, "");
  let n = tallo.replace(/[_.]/g, " ").replace(/[([]?\b(official|audio|video|lyrics?|letra|hq|hd|mp3|final|mix|master)\b[)\]]?/gi, " ");
  n = n.replace(/[([]\s*[)\]]/g, " ").replace(/\s+/g, " ").replace(/\s*-\s*$/, "").replace(/^[\s-]+|[\s-]+$/g, "");
  return n || tallo;
}

// ------------------------------------------------------- en el navegador
export const MODELOS = {
  rapido: { id: "Xenova/whisper-base", nombre: "Rápido", detalle: "≈ 80 MB, menos preciso" },
  preciso: { id: "Xenova/whisper-small", nombre: "Preciso", detalle: "≈ 250 MB, tarda más" },
};
const FRECUENCIA = 16000;

// Decodifica el audio (MP3, WAV, OGG…) en mono a 16 kHz, como lo pide Whisper.
export async function decodificar(blob) {
  const contexto = new OfflineAudioContext(1, FRECUENCIA, FRECUENCIA);
  const audio = await contexto.decodeAudioData(await blob.arrayBuffer());
  const mono = new Float32Array(audio.length);
  for (let c = 0; c < audio.numberOfChannels; c++) {
    const canal = audio.getChannelData(c);
    for (let i = 0; i < canal.length; i++) mono[i] += canal[i] / audio.numberOfChannels;
  }
  return { muestras: mono, duracion: audio.duration };
}

let trabajador = null, siguienteId = 1;
const pendientes = new Map();
function obtenerTrabajador() {
  if (trabajador) return trabajador;
  trabajador = new Worker(new URL("./ia-trabajador.js", import.meta.url), { type: "module" });
  trabajador.onmessage = ({ data }) => {
    const p = pendientes.get(data.id);
    if (!p) return;
    if (data.tipo === "progreso") p.alProgreso?.(data);
    else {
      pendientes.delete(data.id);
      if (data.tipo === "listo") { globalThis.__iaDepuracion = { ventanas: data.ventanas, palabras: data.palabras }; p.ok(data.palabras); }
      else p.mal(new Error(data.mensaje));
    }
  };
  trabajador.onerror = (e) => {
    for (const p of pendientes.values()) p.mal(new Error(e.message || "no se pudo descargar la IA; revisa la conexión a internet"));
    pendientes.clear(); trabajador = null;
  };
  return trabajador;
}

// Escucha el audio y devuelve las palabras con su tiempo y la duración.
// alProgreso({ fase: "decodificando" | "descarga" | "escuchando", progreso: 0..100 })
export async function escuchar(blob, { idioma = "es", modelo = "rapido", alProgreso } = {}) {
  alProgreso?.({ fase: "decodificando", progreso: 0 });
  const { muestras, duracion } = await decodificar(blob);
  const id = siguienteId++;
  const oidas = await new Promise((ok, mal) => {
    pendientes.set(id, { ok, mal, alProgreso });
    obtenerTrabajador().postMessage({ id, modelo: (MODELOS[modelo] || MODELOS.rapido).id, idioma, audio: muestras }, [muestras.buffer]);
  });
  return { palabras: oidas, duracion };
}

// Sincroniza una letra escrita con su pista: { tiempos, palabras }.
export async function sincronizarLetra(blob, lineas, opciones = {}) {
  const { palabras: oidas, duracion } = await escuchar(blob, opciones);
  if (!oidas.length) throw new Error("La IA no escuchó voz en la pista");
  return { ...tiemposDePalabras(lineas, oidas, duracion), oidas: oidas.length };
}

// Escribe la letra desde el audio: { lineas, tiempos, palabras }.
// También devuelve lo oído y la duración, para realinear si se corrige la letra.
export async function letraDesdeAudio(blob, opciones = {}) {
  const { palabras: oidas, duracion } = await escuchar(blob, opciones);
  const resultado = letraDesdePalabras(oidas);
  if (!resultado.lineas.length) throw new Error("La IA no escuchó letra en la pista");
  return { ...resultado, oidas, duracion };
}
