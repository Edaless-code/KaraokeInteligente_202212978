"""Reproductor de pistas con reloj preciso y control de la voz del artista.

* ``segundo`` dice qué parte de la pista se está **escuchando** (descuenta la
  latencia de la tarjeta de sonido), para que la letra vaya a tiempo.
* ``voz`` (0 a 1) baja la voz del artista: la voz principal casi siempre está
  en el centro de la mezcla estéreo (suena igual en ambos canales). Se estima
  lo que es igual en los dos canales, solo en la banda de la voz
  (180–5000 Hz), y se resta en la medida pedida; los graves (bajo, bombo) y
  los instrumentos abiertos a los lados se quedan.
  La estimación se calcula una vez al abrir la pista, así el ajuste en vivo
  no cuesta nada.
"""

from __future__ import annotations

import threading
from pathlib import Path

import numpy as np

from .fuentes import ErrorAudio, _sounddevice, leer_archivo_audio

FRECUENCIA = 44100
BANDA_VOZ = (180.0, 5000.0)


def voz_del_centro(estereo: np.ndarray, frecuencia: int = FRECUENCIA, tamano: int = 2048) -> np.ndarray:
    """Estima la voz principal: lo que suena **igual en ambos canales**.

    Frecuencia por frecuencia (STFT) se mide qué tan parecidos son L y R
    (2·|L·R̄| / (|L|² + |R|²): 1 si son idénticos, 0 si algo suena solo de un
    lado) y se toma esa fracción del centro (L+R)/2, solo en la banda de la
    voz. Así un instrumento abierto a un lado no se resta. Se procesa por
    bloques para no usar mucha memoria con canciones largas.
    """
    salto = tamano // 4
    ventana = np.hanning(tamano).astype(np.float32)
    frecuencias = np.fft.rfftfreq(tamano, 1.0 / frecuencia)
    bajo, alto = BANDA_VOZ
    banda = np.clip(np.minimum(np.log2(np.maximum(frecuencias, 1.0) / (bajo / 2)),
                               np.log2(alto * 2 / np.maximum(frecuencias, 1.0))), 0.0, 1.0).astype(np.float32)
    total = len(estereo)
    relleno = np.zeros((tamano, 2), dtype=np.float32)
    senal = np.concatenate([relleno, estereo.astype(np.float32), relleno])
    salida = np.zeros(len(senal), dtype=np.float32)
    marcos = (len(senal) - tamano) // salto + 1
    for bloque in range(0, marcos, 512):
        indices = np.arange(bloque, min(marcos, bloque + 512))[:, None] * salto + np.arange(tamano)
        izquierda = np.fft.rfft(senal[indices, 0] * ventana, axis=1)
        derecha = np.fft.rfft(senal[indices, 1] * ventana, axis=1)
        energia = np.abs(izquierda) ** 2 + np.abs(derecha) ** 2 + 1e-9
        parecido = 2 * np.abs(izquierda * np.conj(derecha)) / energia
        centro = 0.5 * (izquierda + derecha) * (parecido ** 2) * banda
        marcos_salida = np.fft.irfft(centro, n=tamano, axis=1).astype(np.float32) * ventana
        np.add.at(salida, indices, marcos_salida)
    salida /= 1.5  # suma de hann² con salto de 1/4
    return salida[tamano: tamano + total]


def mezclar(estereo: np.ndarray, centro: np.ndarray, voz: float) -> np.ndarray:
    """La pista con la voz del centro al ``voz`` (1 = original, 0 = sin voz)."""
    quitar = (1.0 - min(1.0, max(0.0, voz)))
    if quitar <= 0:
        return estereo
    return estereo - quitar * centro[:, None]


class Reproductor:
    def __init__(self, ruta: str | Path, frecuencia: int = FRECUENCIA):
        self.ruta = Path(ruta)
        self.frecuencia = frecuencia
        self.pista = leer_archivo_audio(self.ruta, frecuencia, canales=2)
        self.duracion = len(self.pista) / frecuencia
        self._centro: np.ndarray | None = None
        self.voz = 1.0
        self.posicion = 0
        self.pausado = False
        self.terminada = False
        self._flujo = None
        self._candado = threading.Lock()

    # ------------------------------------------------------------ control
    def iniciar(self, desde: float = 0.0) -> None:
        # La estimación de la voz (~5 s por canción) se prepara mientras suena.
        threading.Thread(target=self._preparar_voz, daemon=True).start()
        sd = _sounddevice()
        self.posicion = int(max(0.0, desde) * self.frecuencia)
        try:
            self._flujo = sd.OutputStream(samplerate=self.frecuencia, channels=2, dtype="float32",
                                          callback=self._al_pedir)
            self._flujo.start()
        except Exception as ex:
            raise ErrorAudio(f"No se pudo reproducir por las bocinas: {ex}") from ex

    def _al_pedir(self, salida, cuadros, _tiempo, _estado) -> None:
        with self._candado:
            if self.pausado or self.terminada:
                salida[:] = 0
                return
            inicio, fin = self.posicion, self.posicion + cuadros
            trozo = self.pista[inicio:fin]
            if self.voz < 1.0 and self._centro is not None and len(trozo):
                trozo = mezclar(trozo, self._centro[inicio:fin], self.voz)
            salida[: len(trozo)] = trozo
            salida[len(trozo):] = 0
            self.posicion = fin
            if fin >= len(self.pista):
                self.terminada = True

    @property
    def latencia(self) -> float:
        try:
            return float(self._flujo.latency) if self._flujo is not None else 0.0
        except Exception:
            return 0.0

    @property
    def segundo(self) -> float:
        """Lo que se está escuchando ahora (no lo que ya se entregó a la tarjeta)."""
        return max(0.0, self.posicion / self.frecuencia - (0.0 if self.pausado else self.latencia))

    def alternar_pausa(self) -> None:
        with self._candado:
            self.pausado = not self.pausado

    def mover(self, segundos: float) -> None:
        with self._candado:
            nueva = self.posicion + int(segundos * self.frecuencia)
            self.posicion = min(max(0, nueva), len(self.pista) - 1)
            self.terminada = False

    def _preparar_voz(self) -> None:
        try:
            self._centro = voz_del_centro(self.pista, self.frecuencia)
        except Exception:  # sin la estimación, el control de voz no hace nada
            self._centro = None

    @property
    def voz_lista(self) -> bool:
        return self._centro is not None

    def ajustar_voz(self, voz: float) -> None:
        """0 = sin la voz del artista, 1 = original (se aplica en cuanto la
        estimación de la voz esté lista)."""
        with self._candado:
            self.voz = min(1.0, max(0.0, voz))

    def detener(self) -> None:
        if self._flujo is not None:
            try:
                self._flujo.stop()
                self._flujo.close()
            finally:
                self._flujo = None
