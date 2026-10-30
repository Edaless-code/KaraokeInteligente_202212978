"""Limpieza del sonido antes de transcribirlo.

El micrófono capta la voz del cantante junto con la música de fondo, el ruido
del lugar y zumbidos eléctricos. Para que la transcripción sea menos difícil
cada bloque de audio pasa, en tiempo real, por:

1. **Filtro pasa banda** (por omisión 100 Hz – 4000 Hz). Quita el zumbido de
   la red eléctrica (50/60 Hz), golpes y graves del bajo y la batería, y los
   agudos que no aportan a la inteligibilidad de la voz.
2. **Reducción de ruido por sustracción espectral.** Al empezar se miden unos
   segundos de "silencio" (``segundos_calibracion``) para conocer el espectro
   del ruido; después ese espectro se resta de cada trama y se sigue
   actualizando en las tramas sin voz. Se usa un piso espectral y un
   suavizado temporal de la ganancia para no producir "ruido musical".
3. **Detector de voz (VAD)** por energía con histéresis: indica si en este
   momento alguien canta. Lo usa el modo automático para pausarse solo
   (ignorar) y para reanudar (seguir).
4. **Control automático de ganancia (AGC)** y limitador: nivela el volumen
   para que un cantante lejano o muy fuerte se transcriba igual.

Se implementa con una STFT (tramas de 32 ms con 50 % de traslape y ventana
raíz de Hann) usando solo NumPy, para que funcione igual en Windows y Android.
"""

from __future__ import annotations

import numpy as np

from ..config import Config

TRAMA = 512
SALTO = 256


def a_pcm16(muestras: np.ndarray) -> bytes:
    """Convierte muestras flotantes (-1..1) a PCM de 16 bits (lo que pide Vosk)."""
    return (np.clip(muestras, -1.0, 1.0) * 32767).astype("<i2").tobytes()


def desde_pcm16(datos: bytes) -> np.ndarray:
    return np.frombuffer(datos, dtype="<i2").astype(np.float32) / 32768.0


def a_mono(muestras: np.ndarray) -> np.ndarray:
    muestras = np.asarray(muestras, dtype=np.float32)
    return muestras.mean(axis=1) if muestras.ndim == 2 else muestras


def remuestrear(muestras: np.ndarray, origen: int, destino: int) -> np.ndarray:
    """Cambia la frecuencia de muestreo (interpolación lineal con un filtro
    de promedio previo para evitar el aliasing al reducir)."""
    if origen == destino or len(muestras) == 0:
        return np.asarray(muestras, dtype=np.float32)
    if origen > destino:
        factor = int(round(origen / destino))
        if factor > 1:
            nucleo = np.ones(factor, dtype=np.float32) / factor
            muestras = np.convolve(muestras, nucleo, mode="same")
    duracion = len(muestras) / origen
    nuevas = int(round(duracion * destino))
    tiempo_origen = np.arange(len(muestras)) / origen
    tiempo_destino = np.arange(nuevas) / destino
    return np.interp(tiempo_destino, tiempo_origen, muestras).astype(np.float32)


def nivel_db(muestras: np.ndarray) -> float:
    if len(muestras) == 0:
        return -120.0
    rms = float(np.sqrt(np.mean(np.square(muestras, dtype=np.float64))))
    return 20 * np.log10(rms + 1e-9)


class LimpiadorAudio:
    def __init__(
        self,
        frecuencia: int = 16000,
        pasa_altos: float = 100.0,
        pasa_bajos: float = 4000.0,
        reduccion_ruido: bool = True,
        factor_sustraccion: float = 1.0,
        segundos_calibracion: float = 1.5,
        control_ganancia: bool = True,
        nivel_objetivo_db: float = -20.0,
        piso: float = 0.25,
    ):
        self.frecuencia = frecuencia
        self.reduccion_ruido = reduccion_ruido
        self.alfa = factor_sustraccion
        self.piso = piso
        self.control_ganancia = control_ganancia
        self.objetivo = 10 ** (nivel_objetivo_db / 20)

        self.ventana = np.sqrt(np.hanning(TRAMA + 1)[:TRAMA]).astype(np.float32)
        frecuencias = np.fft.rfftfreq(TRAMA, 1 / frecuencia)
        # Máscara pasa banda con bordes suaves (coseno de 60 Hz).
        transicion = 60.0
        subida = np.clip((frecuencias - (pasa_altos - transicion / 2)) / transicion, 0, 1)
        bajada = np.clip(((pasa_bajos + transicion / 2) - frecuencias) / transicion, 0, 1)
        self.mascara = (0.5 - 0.5 * np.cos(np.pi * subida)) * (0.5 - 0.5 * np.cos(np.pi * bajada))

        self.tramas_calibracion = max(1, int(segundos_calibracion * frecuencia / SALTO))
        self.reiniciar()

    @classmethod
    def desde_config(cls, config: Config) -> "LimpiadorAudio":
        return cls(
            frecuencia=config.entero("audio", "frecuencia_muestreo"),
            pasa_altos=config.decimal("audio", "filtro_pasa_altos_hz"),
            pasa_bajos=config.decimal("audio", "filtro_pasa_bajos_hz"),
            reduccion_ruido=config.booleano("audio", "reduccion_ruido"),
            factor_sustraccion=config.decimal("audio", "factor_sustraccion"),
            segundos_calibracion=config.decimal("audio", "segundos_calibracion"),
            control_ganancia=config.booleano("audio", "control_ganancia"),
            nivel_objetivo_db=config.decimal("audio", "nivel_objetivo_db"),
        )

    def reiniciar(self) -> None:
        self._pendiente = np.zeros(0, dtype=np.float32)
        self._salida = np.zeros(TRAMA, dtype=np.float32)
        self._suma_ruido = np.zeros(TRAMA // 2 + 1)
        self._tramas = 0
        self.ruido: np.ndarray | None = None
        self._ganancia_anterior = np.ones(TRAMA // 2 + 1)
        self._agc = 1.0
        self._resto_voz = 0
        self.voz_activa = False
        self.nivel_entrada_db = -120.0
        self.nivel_db = -120.0
        self.relacion_senal_ruido_db = 0.0

    @property
    def calibrado(self) -> bool:
        return self.ruido is not None

    # ------------------------------------------------------------------ STFT
    def _procesar_trama(self, trama: np.ndarray) -> tuple[np.ndarray, bool]:
        espectro = np.fft.rfft(trama * self.ventana)
        potencia = espectro.real**2 + espectro.imag**2
        energia = float(np.sum(potencia * self.mascara))

        if self.ruido is None:
            self._suma_ruido += potencia
            self._tramas += 1
            if self._tramas >= self.tramas_calibracion:
                self.ruido = self._suma_ruido / self._tramas
            ganancia = self.mascara
            hay_voz = False
        else:
            energia_ruido = float(np.sum(self.ruido * self.mascara)) + 1e-12
            relacion = energia / energia_ruido
            self.relacion_senal_ruido_db = 10 * np.log10(relacion + 1e-12)
            hay_voz = relacion > 4.0  # 6 dB por encima del ruido
            if relacion < 2.0:
                # Trama sin voz: se actualiza lentamente el perfil del ruido.
                self.ruido = 0.92 * self.ruido + 0.08 * potencia
            if self.reduccion_ruido:
                ganancia = np.sqrt(
                    np.maximum(1.0 - self.alfa * self.ruido / (potencia + 1e-12), self.piso**2)
                )
                ganancia = 0.4 * self._ganancia_anterior + 0.6 * ganancia
                self._ganancia_anterior = ganancia
                ganancia = ganancia * self.mascara
            else:
                ganancia = self.mascara
        limpia = np.fft.irfft(espectro * ganancia, TRAMA).astype(np.float32) * self.ventana
        return limpia, hay_voz

    def procesar(self, bloque: np.ndarray) -> np.ndarray:
        """Limpia un bloque de muestras (mono, flotantes, a ``frecuencia``) y
        devuelve las muestras limpias disponibles (latencia de 16 ms)."""
        bloque = np.asarray(bloque, dtype=np.float32)
        self.nivel_entrada_db = nivel_db(bloque)
        self._pendiente = np.concatenate([self._pendiente, bloque])
        salidas = []
        voz_en_bloque = False
        while len(self._pendiente) >= TRAMA:
            trama = self._pendiente[:TRAMA]
            self._pendiente = self._pendiente[SALTO:]
            limpia, hay_voz = self._procesar_trama(trama)
            voz_en_bloque |= hay_voz
            self._salida += limpia
            salidas.append(self._salida[:SALTO].copy())
            self._salida = np.concatenate([self._salida[SALTO:], np.zeros(SALTO, dtype=np.float32)])
        salida = np.concatenate(salidas) if salidas else np.zeros(0, dtype=np.float32)

        # Detector de voz con "cola" de ~0.3 s para no cortar entre sílabas.
        if voz_en_bloque:
            self._resto_voz = int(0.3 * self.frecuencia)
        else:
            self._resto_voz = max(0, self._resto_voz - len(bloque))
        self.voz_activa = voz_en_bloque or self._resto_voz > 0

        if self.control_ganancia and len(salida):
            rms = float(np.sqrt(np.mean(salida.astype(np.float64) ** 2))) + 1e-9
            if self.voz_activa:
                deseada = float(np.clip(self.objetivo / rms, 0.5, 10.0))
                # Baja rápido (evita saturar) y sube despacio (evita bombeo).
                factor = 0.5 if deseada < self._agc else 0.05
                self._agc += factor * (deseada - self._agc)
            salida = salida * self._agc
            # Limitador suave: nunca satura.
            salida = np.tanh(salida * 1.1) / np.tanh(1.1)
        self.nivel_db = nivel_db(salida)
        return salida.astype(np.float32)

    def procesar_todo(self, muestras: np.ndarray, bloque: int = 1600) -> np.ndarray:
        """Limpia una señal completa (útil para archivos y pruebas)."""
        partes = [self.procesar(muestras[i : i + bloque]) for i in range(0, len(muestras), bloque)]
        return np.concatenate(partes) if partes else np.zeros(0, dtype=np.float32)


def aislar_voz_estereo(estereo: np.ndarray, intensidad: float = 1.0, piso: float = 0.15) -> np.ndarray:
    """Separa la voz de una grabación estéreo (canción ya mezclada).

    En casi todas las mezclas la voz principal está en el CENTRO (suena igual
    en el canal izquierdo y en el derecho), mientras que muchos instrumentos
    están abiertos a los lados. Se calcula el canal medio M = (L+R)/2 y el
    lateral S = (L-R)/2; el espectro de S sirve como estimación de lo que NO
    es voz y se resta del espectro de M (sustracción espectral). Devuelve una
    señal mono con la voz realzada.
    """
    estereo = np.asarray(estereo, dtype=np.float32)
    if estereo.ndim != 2 or estereo.shape[1] < 2:
        return a_mono(estereo)
    medio = (estereo[:, 0] + estereo[:, 1]) / 2
    lateral = (estereo[:, 0] - estereo[:, 1]) / 2
    trama, salto = 1024, 512
    ventana = np.sqrt(np.hanning(trama + 1)[:trama]).astype(np.float32)
    total = len(medio)
    relleno = (-(total - trama) % salto) if total > trama else trama - total
    medio = np.concatenate([np.zeros(salto, np.float32), medio, np.zeros(relleno + salto, np.float32)])
    lateral = np.concatenate([np.zeros(salto, np.float32), lateral, np.zeros(relleno + salto, np.float32)])
    cuadros = 1 + (len(medio) - trama) // salto
    indices = np.arange(trama)[None, :] + salto * np.arange(cuadros)[:, None]
    espectro_m = np.fft.rfft(medio[indices] * ventana, axis=1)
    espectro_s = np.fft.rfft(lateral[indices] * ventana, axis=1)
    potencia_m = np.abs(espectro_m) ** 2 + 1e-12
    potencia_s = np.abs(espectro_s) ** 2
    ganancia = np.sqrt(np.maximum(1.0 - intensidad * potencia_s / potencia_m, piso**2))
    tramas = np.fft.irfft(espectro_m * ganancia, trama, axis=1).astype(np.float32) * ventana
    salida = np.zeros(len(medio), dtype=np.float32)
    for numero in range(cuadros):
        salida[numero * salto : numero * salto + trama] += tramas[numero]
    return salida[salto : salto + total]
