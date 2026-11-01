// Trabajador de la IA: corre Whisper dentro del navegador (transformers.js),
// aparte de la página para que no se congele mientras escucha la canción.
//
// Recibe { id, modelo, idioma, audio } (audio: Float32Array mono a 16 kHz) y
// responde con mensajes { id, tipo: "progreso" | "listo" | "error", ... }.
// La primera vez descarga el modelo (queda guardado en el navegador).
import { pipeline, env } from "https://cdn.jsdelivr.net/npm/@huggingface/transformers@3.8.1";

env.allowLocalModels = false;

const FRECUENCIA = 16000;
const VENTANA = 30;   // segundos que Whisper escucha de una vez
const SOLAPE = 2;     // segundos compartidos entre ventanas (no se pierden palabras en el corte)

let tuberia = null;
let modeloCargado = "";

async function cargar(modelo, avisar) {
  if (tuberia && modeloCargado === modelo) return tuberia;
  const archivos = {};
  tuberia = await pipeline("automatic-speech-recognition", modelo, {
    dtype: "q8",
    progress_callback: (p) => {
      if (p.status !== "progress" || !p.total) return;
      archivos[p.file] = [p.loaded, p.total];
      const [cargado, total] = Object.values(archivos).reduce(([a, b], [c, d]) => [a + c, b + d], [0, 0]);
      avisar({ fase: "descarga", progreso: (cargado / total) * 100, megas: Math.round(total / 1e6) });
    },
  });
  modeloCargado = modelo;
  return tuberia;
}

self.onmessage = async ({ data }) => {
  const { id, modelo, idioma, audio } = data;
  const avisar = (datos) => self.postMessage({ id, tipo: "progreso", ...datos });
  try {
    const escuchar = await cargar(modelo, avisar);
    avisar({ fase: "escuchando", progreso: 0 });
    const palabras = [], ventanas = [];
    const paso = (VENTANA - SOLAPE) * FRECUENCIA;
    for (let inicio = 0; inicio < audio.length; inicio += paso) {
      const fin = Math.min(audio.length, inicio + VENTANA * FRECUENCIA);
      const desde = inicio / FRECUENCIA;
      const primera = inicio === 0, ultima = fin >= audio.length;
      const salida = await escuchar(audio.subarray(inicio, fin), {
        return_timestamps: "word", task: "transcribe", ...(idioma ? { language: idioma } : {}),
      });
      // De cada ventana se toma lo que cae fuera de la mitad del solape con
      // sus vecinas, para no repetir ni perder palabras en el corte.
      ventanas.push({ desde, texto: salida.text, palabras: (salida.chunks || []).slice(0, 6).map((c) => [c.text, ...(c.timestamp || [])]) });
      const minimo = primera ? -Infinity : desde + SOLAPE / 2;
      const maximo = ultima ? Infinity : desde + VENTANA - SOLAPE / 2;
      for (const trozo of salida.chunks || []) {
        const texto = (trozo.text || "").trim();
        const [a, b] = trozo.timestamp || [];
        if (!texto || a == null) continue;
        const ini = desde + a, fin_ = desde + (b ?? a + 0.3);
        if (ini >= minimo && ini < maximo) palabras.push({ texto, inicio: ini, fin: Math.max(fin_, ini + 0.05) });
      }
      avisar({ fase: "escuchando", progreso: (fin / audio.length) * 100 });
      if (ultima) break;
    }
    self.postMessage({ id, tipo: "listo", palabras, ventanas });
  } catch (error) {
    self.postMessage({ id, tipo: "error", mensaje: String(error?.message || error) });
  }
};
