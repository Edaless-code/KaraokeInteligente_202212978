// Grabar la interpretación: la voz de quien canta (micrófono) mezclada con la
// pista tal como suena (con la voz del artista al nivel elegido).
//
// La pista se retrasa en la grabación lo que tardan las bocinas y el micrófono
// (la latencia del sistema): así la voz no queda atrasada respecto a la música.

const TIPOS = ["audio/webm;codecs=opus", "audio/webm", "audio/mp4", "audio/ogg;codecs=opus"];
export const tipoGrabacion = () => (typeof MediaRecorder !== "undefined" && TIPOS.find((t) => MediaRecorder.isTypeSupported(t))) || "";
export const extension = (tipo) => (tipo.includes("mp4") ? "m4a" : tipo.includes("ogg") ? "ogg" : "webm");
export const sePuedeGrabar = () => typeof MediaRecorder !== "undefined" && !!navigator.mediaDevices?.getUserMedia;

export class Grabadora {
  // `contexto`: el AudioContext de la pista; `salida`: el nodo con la mezcla que suena.
  constructor(contexto, salida) {
    this.contexto = contexto;
    this.salida = salida;
    this.partes = [];
    this.tipo = tipoGrabacion();
  }

  async iniciar() {
    this.flujoMic = await navigator.mediaDevices.getUserMedia({
      audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true },
    });
    const ctx = this.contexto;
    this.destino = ctx.createMediaStreamDestination();
    // la pista, un poco más baja y retrasada lo que tarda el sonido en ir y volver
    this.retraso = ctx.createDelay(1);
    this.retraso.delayTime.value = Math.min(0.5, (ctx.outputLatency || 0) + (ctx.baseLatency || 0) + 0.06);
    this.nivelPista = ctx.createGain();
    this.nivelPista.gain.value = 0.75;
    this.salida.connect(this.retraso).connect(this.nivelPista).connect(this.destino);
    this.mic = ctx.createMediaStreamSource(this.flujoMic);
    this.nivelVoz = ctx.createGain();
    this.nivelVoz.gain.value = 1.3;
    this.mic.connect(this.nivelVoz).connect(this.destino);
    this.grabador = new MediaRecorder(this.destino.stream, this.tipo ? { mimeType: this.tipo } : undefined);
    this.grabador.ondataavailable = (e) => { if (e.data.size) this.partes.push(e.data); };
    this.grabador.start(1000);
    this.inicio = performance.now();
  }

  get segundos() { return this.inicio ? (performance.now() - this.inicio) / 1000 : 0; }
  get grabando() { return this.grabador?.state === "recording"; }

  // Termina y devuelve la grabación (Blob) y cuánto duró.
  detener() {
    return new Promise((ok) => {
      const duracion = this.segundos;
      const terminar = () => {
        this.flujoMic?.getTracks().forEach((t) => t.stop());
        try { this.salida.disconnect(this.retraso); } catch { /* ya desconectado */ }
        try { this.mic.disconnect(); } catch { /* ya desconectado */ }
        ok({ blob: new Blob(this.partes, { type: this.tipo || "audio/webm" }), duracion });
      };
      if (!this.grabador || this.grabador.state === "inactive") return terminar();
      this.grabador.onstop = terminar;
      this.grabador.stop();
    });
  }
}
