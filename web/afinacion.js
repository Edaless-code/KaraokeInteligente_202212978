// Puntuación al cantar.
//
// Compara, palabra por palabra, la nota que canta quien está en el micrófono
// con la nota de la voz original de la pista, y mide si canta cuando toca.
//   * La nota se detecta con YIN (de Cheveigné y Kawahara, 2002): la diferencia
//     de la señal consigo misma desplazada, normalizada; el primer mínimo bajo
//     el umbral es el periodo de la voz.
//   * Las notas se comparan sin importar la octava (cantar una octava abajo de
//     la original también está afinado).
//   * La nota de la pista se calcula solo en las palabras (se conocen sus
//     tiempos) y en la banda de la voz; donde la música no deja oírla, esa
//     palabra cuenta solo para el tiempo.
// Las funciones de cálculo no usan el navegador (se prueban con Node).

export function yin(muestras, frecuencia, { minimo = 80, maximo = 1000, umbral = 0.15 } = {}) {
  const tauMin = Math.max(2, Math.floor(frecuencia / maximo));
  const tauMax = Math.min(Math.floor(frecuencia / minimo), Math.floor(muestras.length / 2));
  if (tauMax <= tauMin + 1) return null;
  const ancho = muestras.length - tauMax;
  const d = new Float32Array(tauMax + 2);
  for (let tau = 1; tau <= tauMax + 1 && tau < muestras.length - ancho + 1; tau++) {
    let suma = 0;
    for (let i = 0; i < ancho; i++) { const x = muestras[i] - muestras[i + tau]; suma += x * x; }
    d[tau] = suma;
  }
  const normal = new Float32Array(tauMax + 2);
  normal[0] = 1;
  let acumulado = 0;
  for (let tau = 1; tau <= tauMax + 1; tau++) { acumulado += d[tau]; normal[tau] = acumulado ? (d[tau] * tau) / acumulado : 1; }
  let tau = -1;
  for (let t = tauMin; t <= tauMax; t++) {
    if (normal[t] < umbral) {
      while (t + 1 <= tauMax && normal[t + 1] < normal[t]) t++;
      tau = t;
      break;
    }
  }
  if (tau < 0) return null;
  const a = normal[tau - 1], b = normal[tau], c = normal[tau + 1];
  const curva = a + c - 2 * b;
  const ajuste = curva ? (a - c) / (2 * curva) : 0;
  return { hz: frecuencia / (tau + Math.max(-1, Math.min(1, ajuste))), claridad: 1 - b };
}

export const aMidi = (hz) => 69 + 12 * Math.log2(hz / 440);
const NOTAS = ["Do", "Do#", "Re", "Re#", "Mi", "Fa", "Fa#", "Sol", "Sol#", "La", "La#", "Si"];
// 69 → "La 4" (notación con octava, como en el piano: el La de 440 Hz es La 4)
export const nombreNota = (midi) => { const n = Math.round(midi); return `${NOTAS[((n % 12) + 12) % 12]} ${Math.floor(n / 12) - 1}`; };
export function rms(muestras) {
  let s = 0;
  for (let i = 0; i < muestras.length; i++) s += muestras[i] * muestras[i];
  return Math.sqrt(s / (muestras.length || 1));
}
// Distancia entre dos notas en semitonos, sin importar la octava (de -6 a 6).
export const distanciaNota = (a, b) => ((((a - b) % 12) + 18) % 12) - 6;
// Qué tan afinada está una nota según su distancia a la original.
export function puntosNota(distancia) {
  const d = Math.abs(distancia);
  if (d <= 0.75) return 1;     // afinado (un cantante real se mueve unos cuartos de tono)
  if (d <= 1.25) return 0.5;   // casi
  return 0;
}

// Nota de la voz original en el tramo central de una palabra (la mediana de
// las notas claras), o null si la música no deja oírla.
export function notaDeReferencia(senal, frecuencia, inicio, fin, { umbral = 0.25, minimoClaros = 0.3 } = {}) {
  const margen = (fin - inicio) * 0.2;
  const desde = Math.floor((inicio + margen) * frecuencia), hasta = Math.floor((fin - margen) * frecuencia);
  const tam = 512, paso = 256, notas = [];
  let cuadros = 0;
  for (let i = desde; i + tam <= Math.max(hasta, desde + tam) && i + tam <= senal.length; i += paso) {
    cuadros++;
    const trozo = senal.subarray(i, i + tam);
    if (rms(trozo) < 0.005) continue;
    const r = yin(trozo, frecuencia, { umbral });
    if (r) notas.push(aMidi(r.hz));
  }
  if (!cuadros || notas.length < Math.max(1, cuadros * minimoClaros)) return null;
  notas.sort((x, y) => x - y);
  return notas[Math.floor(notas.length / 2)];
}

// La nota de la pista sale de la mezcla (con la música alrededor), así que ni la
// propia voz original coincide siempre con ella: medido con Sound of You, la voz
// original saca 0.62 y la misma voz 3 semitonos arriba 0.07. Se escala para que
// cantar como el artista valga ~100 %.
export const CALIBRACION = 0.65;
const PESO_AFINACION = 0.7;

export function estrellas(puntaje) {
  return puntaje >= 90 ? 5 : puntaje >= 75 ? 4 : puntaje >= 60 ? 3 : puntaje >= 40 ? 2 : 1;
}

// Lleva la cuenta durante la canción. `palabras`: por línea, [inicio, fin] de
// cada palabra (los mismos tiempos con que se pinta la letra). `referencia`:
// función (inicio, fin) -> nota de la pista o null (se calcula al llegar a
// cada palabra y se guarda).
export class Calificador {
  constructor(palabras, referencia) {
    this.palabras = palabras.flat().map(([inicio, fin]) => ({ inicio, fin, cuadros: 0, voz: 0, notas: [], ref: undefined }));
    this.referencia = referencia;
  }

  palabraEn(segundo) {
    let bajo = 0, alto = this.palabras.length - 1;
    while (bajo <= alto) {
      const medio = (bajo + alto) >> 1, p = this.palabras[medio];
      if (segundo < p.inicio) alto = medio - 1;
      else if (segundo >= p.fin) bajo = medio + 1;
      else return p;
    }
    return null;
  }

  // Un cuadro del micrófono: en qué segundo de la canción, si hay voz y su nota.
  registrar(segundo, voz, nota) {
    const p = this.palabraEn(segundo);
    if (!p) return;
    p.cuadros++;
    if (!voz) return;
    p.voz++;
    if (p.ref === undefined) p.ref = this.referencia(p.inicio, p.fin);
    if (p.ref !== null && nota !== null && nota !== undefined) p.notas.push(distanciaNota(nota, p.ref));
  }

  // Avance hasta ahora: qué fracción de las palabras ya pasó.
  get avance() {
    const pasadas = this.palabras.filter((p) => p.cuadros > 0).length;
    return this.palabras.length ? pasadas / this.palabras.length : 0;
  }

  resultado() {
    const pasadas = this.palabras.filter((p) => p.cuadros > 0);
    if (!pasadas.length) return { puntaje: 0, afinacion: null, tiempo: 0, estrellas: 1, palabras: 0 };
    // a tiempo: con voz en al menos la mitad de la palabra cuenta completa
    const tiempo = pasadas.reduce((s, p) => s + Math.min(1, p.voz / p.cuadros / 0.5), 0) / pasadas.length;
    const conNota = pasadas.filter((p) => p.notas.length >= 1);
    const cruda = conNota.length >= 3
      ? conNota.reduce((s, p) => s + p.notas.reduce((t, d) => t + puntosNota(d), 0) / p.notas.length, 0) / conNota.length
      : null;
    const afinacion = cruda === null ? null : Math.min(1, cruda / CALIBRACION);
    const valor = afinacion === null ? tiempo : PESO_AFINACION * afinacion + (1 - PESO_AFINACION) * tiempo;
    const puntaje = Math.round(valor * 100);
    return { puntaje, afinacion, tiempo, estrellas: estrellas(puntaje), palabras: pasadas.length };
  }
}

// ------------------------------------------------------- en el navegador
// La voz de la pista: el centro de la mezcla, en la banda de la voz, a 8 kHz.
export async function senalDeVoz(blob) {
  const frecuencia = 8000;
  const datos = await blob.arrayBuffer();
  const audio = await new OfflineAudioContext(1, frecuencia, frecuencia).decodeAudioData(datos);
  const contexto = new OfflineAudioContext(1, audio.length, frecuencia);
  const fuente = contexto.createBufferSource();
  fuente.buffer = audio;
  const graves = contexto.createBiquadFilter(); graves.type = "highpass"; graves.frequency.value = 200;
  const agudos = contexto.createBiquadFilter(); agudos.type = "lowpass"; agudos.frequency.value = 1000;
  fuente.connect(graves).connect(agudos).connect(contexto.destination);   // estéreo → mono: el centro
  fuente.start();
  return { senal: (await contexto.startRendering()).getChannelData(0), frecuencia };
}

// El micrófono de quien canta: cada lectura da si hay voz y su nota.
export class Microfono {
  // `dispositivo`: deviceId del micrófono elegido ("" = el predeterminado).
  async iniciar(dispositivo = "") {
    this.flujo = await navigator.mediaDevices.getUserMedia({
      audio: { echoCancellation: true, noiseSuppression: false, autoGainControl: true,
        ...(dispositivo ? { deviceId: { exact: dispositivo } } : {}) },
    });
    this.contexto = new AudioContext();
    const fuente = this.contexto.createMediaStreamSource(this.flujo);
    // solo la banda de la voz: sin el bajo ni los platillos que se cuelen
    const graves = this.contexto.createBiquadFilter(); graves.type = "highpass"; graves.frequency.value = 120;
    const agudos = this.contexto.createBiquadFilter(); agudos.type = "lowpass"; agudos.frequency.value = 1200;
    this.analizador = this.contexto.createAnalyser();
    this.analizador.fftSize = 2048;
    fuente.connect(graves).connect(agudos).connect(this.analizador);
    this.cuadro = new Float32Array(this.analizador.fftSize);
  }

  leer() {
    if (!this.analizador) return { voz: false, nota: null, nivel: 0 };
    this.analizador.getFloatTimeDomainData(this.cuadro);
    const nivel = rms(this.cuadro);
    if (nivel < 0.012) return { voz: false, nota: null, nivel };
    const r = yin(this.cuadro, this.contexto.sampleRate, { umbral: 0.25 });
    return { voz: true, nota: r ? aMidi(r.hz) : null, nivel };
  }

  detener() {
    this.flujo?.getTracks().forEach((t) => t.stop());
    this.contexto?.close().catch(() => {});
    this.analizador = null;
  }
}
