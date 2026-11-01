// Cambio de tono sin cambiar la velocidad (AudioWorklet).
//
// Dos cabezas leen el audio de un búfer circular con un retraso que va
// cambiando poco a poco: si el retraso disminuye, el sonido sale más agudo; si
// aumenta, más grave. Cuando una cabeza llega al final de su recorrido salta
// al otro extremo, y para que el salto no se oiga las dos cabezas van
// desfasadas media ventana y se mezclan con seno y coseno: con música (lo que
// leen las dos cabezas casi no se parece) así la potencia queda igual y el
// volumen no baja (medido con Sound of You: −18.4 dB contra −18.3 del original;
// con ventanas sen², que suman 1, bajaba 1.3 dB).
class CambioDeTono extends AudioWorkletProcessor {
  static get parameterDescriptors() {
    return [{ name: "semitonos", defaultValue: 0, minValue: -12, maxValue: 12, automationRate: "k-rate" }];
  }

  constructor() {
    super();
    this.ventana = Math.round(sampleRate * 0.05);          // 50 ms
    this.largo = this.ventana * 2 + 4;
    this.bufer = [new Float32Array(this.largo), new Float32Array(this.largo)];
    this.escritura = 0;
    this.fase = 0;
  }

  leer(canal, retraso) {
    let posicion = this.escritura - retraso;
    while (posicion < 0) posicion += this.largo;
    const i = Math.floor(posicion), fraccion = posicion - i;
    const a = canal[i % this.largo], b = canal[(i + 1) % this.largo];
    return a + (b - a) * fraccion;
  }

  process(entradas, salidas, parametros) {
    const entrada = entradas[0], salida = salidas[0];
    if (!entrada || !entrada.length) return true;
    const semitonos = parametros.semitonos[0];
    const canales = Math.min(entrada.length, salida.length, 2);
    const cuadros = entrada[0].length;
    if (Math.abs(semitonos) < 0.01) {
      // sin cambio: pasa tal cual (y se sigue llenando el búfer para no cortar al activarse)
      for (let i = 0; i < cuadros; i++) {
        for (let c = 0; c < canales; c++) { this.bufer[c][this.escritura] = entrada[c][i]; salida[c][i] = entrada[c][i]; }
        this.escritura = (this.escritura + 1) % this.largo;
      }
      return true;
    }
    const razon = Math.pow(2, semitonos / 12);
    const avance = (razon - 1) / this.ventana;
    const N = this.ventana;
    for (let i = 0; i < cuadros; i++) {
      for (let c = 0; c < canales; c++) this.bufer[c][this.escritura] = entrada[c][i];
      const f1 = this.fase, f2 = (this.fase + 0.5) % 1;
      const g1 = Math.sin(Math.PI * f1), g2 = Math.sin(Math.PI * f2);   // sen² + cos² = 1
      const d1 = (1 - f1) * N + 1, d2 = (1 - f2) * N + 1;
      for (let c = 0; c < canales; c++) {
        const canal = this.bufer[c];
        salida[c][i] = g1 * this.leer(canal, d1) + g2 * this.leer(canal, d2);
      }
      this.escritura = (this.escritura + 1) % this.largo;
      this.fase += avance;
      this.fase -= Math.floor(this.fase);
    }
    return true;
  }
}

registerProcessor("cambio-de-tono", CambioDeTono);
