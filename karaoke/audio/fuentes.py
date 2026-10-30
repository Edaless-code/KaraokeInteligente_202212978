"""Fuentes de audio para el modo automático.

* ``FuenteMicrofono``  captura en vivo con ``sounddevice`` (PortAudio: WASAPI /
  MME en Windows). Si el micrófono no admite 16 kHz se captura a su frecuencia
  nativa y se remuestrea.
* ``FuenteArchivo``    lee un MP3, WAV, FLAC u OGG (con ``miniaudio``; si no
  está instalado se aceptan solo WAV). Sirve para probar el modo automático
  sin cantar: entrega el audio al ritmo real y, si se pide, lo reproduce por
  las bocinas para que se escuche la canción mientras aparece la letra.

Todas entregan bloques mono ``float32`` a ``frecuencia`` (16 kHz por omisión),
que es lo que esperan la limpieza y los motores de transcripción.
"""

from __future__ import annotations

import queue
import threading
import time
import wave
from pathlib import Path

import numpy as np

from .limpieza import a_mono, remuestrear

SEGUNDOS_BLOQUE = 0.1


class ErrorAudio(Exception):
    """Problema con el micrófono, las bocinas o el archivo de audio."""


def _sounddevice():
    try:
        import sounddevice
    except (ImportError, OSError) as ex:  # OSError: falta la biblioteca PortAudio
        raise ErrorAudio(
            "No se pudo usar el audio del sistema (sounddevice/PortAudio): " f"{ex}"
        ) from ex
    return sounddevice


def listar_microfonos() -> list[tuple[int, str, int, int]]:
    """(índice, nombre, canales, frecuencia nativa) de cada entrada de audio."""
    sd = _sounddevice()
    microfonos = []
    for indice, dispositivo in enumerate(sd.query_devices()):
        if dispositivo["max_input_channels"] > 0:
            microfonos.append(
                (
                    indice,
                    dispositivo["name"],
                    dispositivo["max_input_channels"],
                    int(dispositivo["default_samplerate"]),
                )
            )
    return microfonos


def microfono_predeterminado() -> int | None:
    try:
        entrada = _sounddevice().default.device[0]
    except ErrorAudio:
        return None
    return entrada if entrada is not None and entrada >= 0 else None


def _interpretar_dispositivo(dispositivo: str | int | None) -> int | str | None:
    if dispositivo is None or dispositivo == "":
        return None
    if isinstance(dispositivo, int):
        return dispositivo
    return int(dispositivo) if dispositivo.strip().isdigit() else dispositivo


class FuenteAudio:
    nombre = "audio"
    frecuencia = 16000
    terminada = False

    def iniciar(self) -> None:
        raise NotImplementedError

    def leer(self, espera: float = 0.5) -> np.ndarray | None:
        """Siguiente bloque de muestras; ``None`` si no llegó nada a tiempo."""
        raise NotImplementedError

    def detener(self) -> None:
        pass

    def __enter__(self):
        self.iniciar()
        return self

    def __exit__(self, *_):
        self.detener()


class FuenteMicrofono(FuenteAudio):
    def __init__(self, frecuencia: int = 16000, dispositivo: str | int | None = None):
        self.frecuencia = frecuencia
        self.dispositivo = _interpretar_dispositivo(dispositivo)
        self._cola: queue.Queue[np.ndarray] = queue.Queue(maxsize=200)
        self._flujo = None
        self._frecuencia_captura = frecuencia
        self.desbordes = 0
        self.nombre = "micrófono"

    def iniciar(self) -> None:
        sd = _sounddevice()
        try:
            info = sd.query_devices(self.dispositivo, "input")
        except (ValueError, sd.PortAudioError) as ex:
            raise ErrorAudio(f"No se encontró el micrófono «{self.dispositivo}»: {ex}") from ex
        self.nombre = f"micrófono: {info['name']}"
        try:
            sd.check_input_settings(self.dispositivo, channels=1, samplerate=self.frecuencia)
            self._frecuencia_captura = self.frecuencia
        except Exception:
            self._frecuencia_captura = int(info["default_samplerate"])

        def al_recibir(datos, _cuadros, _tiempo, estado):
            if estado:
                self.desbordes += 1
            try:
                self._cola.put_nowait(datos[:, 0].copy())
            except queue.Full:
                self.desbordes += 1

        try:
            self._flujo = sd.InputStream(
                device=self.dispositivo,
                channels=1,
                samplerate=self._frecuencia_captura,
                dtype="float32",
                blocksize=int(self._frecuencia_captura * SEGUNDOS_BLOQUE),
                callback=al_recibir,
            )
            self._flujo.start()
        except Exception as ex:
            raise ErrorAudio(f"No se pudo abrir el micrófono: {ex}") from ex

    def leer(self, espera: float = 0.5) -> np.ndarray | None:
        try:
            bloque = self._cola.get(timeout=espera)
        except queue.Empty:
            return None
        return remuestrear(bloque, self._frecuencia_captura, self.frecuencia)

    def detener(self) -> None:
        if self._flujo is not None:
            try:
                self._flujo.stop()
                self._flujo.close()
            finally:
                self._flujo = None


def leer_archivo_audio(ruta: str | Path, frecuencia: int = 16000, canales: int = 1) -> np.ndarray:
    """Decodifica un archivo de audio completo a ``float32``.

    Devuelve un arreglo (muestras,) si ``canales`` es 1 o (muestras, canales)."""
    ruta = Path(ruta)
    if not ruta.exists():
        raise ErrorAudio(f"No existe el archivo {ruta}")
    try:
        import miniaudio
    except ImportError:
        miniaudio = None
    if miniaudio is not None:
        try:
            decodificado = miniaudio.decode_file(
                str(ruta),
                output_format=miniaudio.SampleFormat.FLOAT32,
                nchannels=canales,
                sample_rate=frecuencia,
            )
        except miniaudio.DecodeError as ex:
            raise ErrorAudio(f"No se pudo leer el audio {ruta.name}: {ex}") from ex
        muestras = np.frombuffer(decodificado.samples, dtype=np.float32)
        return muestras.reshape(-1, canales) if canales > 1 else muestras
    if ruta.suffix.lower() != ".wav":
        raise ErrorAudio("Para leer MP3 instale miniaudio (pip install miniaudio) o use un WAV.")
    with wave.open(str(ruta), "rb") as archivo:
        ancho = archivo.getsampwidth()
        canales_archivo = archivo.getnchannels()
        frecuencia_archivo = archivo.getframerate()
        datos = archivo.readframes(archivo.getnframes())
    if ancho == 1:
        muestras = (np.frombuffer(datos, dtype=np.uint8).astype(np.float32) - 128) / 128
    elif ancho == 2:
        muestras = np.frombuffer(datos, dtype="<i2").astype(np.float32) / 32768
    elif ancho == 3:
        crudo = np.frombuffer(datos, dtype=np.uint8).reshape(-1, 3)
        enteros = (crudo[:, 0].astype(np.int32) | (crudo[:, 1].astype(np.int32) << 8)
                   | (crudo[:, 2].astype(np.int32) << 16))
        enteros = np.where(enteros >= 1 << 23, enteros - (1 << 24), enteros)
        muestras = enteros.astype(np.float32) / (1 << 23)
    else:
        muestras = np.frombuffer(datos, dtype="<i4").astype(np.float32) / 2**31
    muestras = muestras.reshape(-1, canales_archivo)
    if canales == 1:
        return remuestrear(a_mono(muestras), frecuencia_archivo, frecuencia)
    columnas = [remuestrear(muestras[:, min(c, canales_archivo - 1)], frecuencia_archivo, frecuencia)
                for c in range(canales)]
    return np.stack(columnas, axis=1)


class FuenteArchivo(FuenteAudio):
    def __init__(
        self,
        ruta: str | Path,
        frecuencia: int = 16000,
        tiempo_real: bool = True,
        reproducir: bool = False,
        desde_segundo: float = 0.0,
    ):
        self.ruta = Path(ruta)
        self.frecuencia = frecuencia
        self.tiempo_real = tiempo_real
        self.reproducir = reproducir
        self.desde = desde_segundo
        self.nombre = f"archivo: {self.ruta.name}"
        self._muestras = np.zeros(0, dtype=np.float32)
        self._posicion = 0
        self._inicio = 0.0
        self._flujo = None
        self.duracion = 0.0

    def iniciar(self) -> None:
        self._muestras = leer_archivo_audio(self.ruta, self.frecuencia)
        self.duracion = len(self._muestras) / self.frecuencia
        self._posicion = int(self.desde * self.frecuencia)
        self.terminada = False
        if self.reproducir:
            self._iniciar_reproduccion()
        self._inicio = time.monotonic() - self._posicion / self.frecuencia

    def _iniciar_reproduccion(self) -> None:
        """Reproduce el archivo en estéreo a 44.1 kHz por las bocinas."""
        try:
            sd = _sounddevice()
            frecuencia = 44100
            pista = leer_archivo_audio(self.ruta, frecuencia, canales=2)
            pista = pista[int(self.desde * frecuencia) :]
            posicion = [0]

            def al_pedir(salida, cuadros, _tiempo, _estado):
                trozo = pista[posicion[0] : posicion[0] + cuadros]
                salida[: len(trozo)] = trozo
                salida[len(trozo) :] = 0
                posicion[0] += cuadros

            self._flujo = sd.OutputStream(
                samplerate=frecuencia, channels=2, dtype="float32", callback=al_pedir
            )
            self._flujo.start()
        except Exception as ex:  # sin bocinas se sigue sin reproducir
            self._flujo = None
            self.reproducir = False
            self.error_reproduccion = str(ex)

    @property
    def segundo_actual(self) -> float:
        return self._posicion / self.frecuencia

    def leer(self, espera: float = 0.5) -> np.ndarray | None:
        if self._posicion >= len(self._muestras):
            self.terminada = True
            return None
        tamano = int(self.frecuencia * SEGUNDOS_BLOQUE)
        if self.tiempo_real:
            # El bloque se entrega cuando su audio "ya sonó".
            momento = self._inicio + (self._posicion + tamano) / self.frecuencia
            retraso = momento - time.monotonic()
            if retraso > espera:
                time.sleep(espera)
                return None
            if retraso > 0:
                time.sleep(retraso)
        bloque = self._muestras[self._posicion : self._posicion + tamano]
        self._posicion += tamano
        return bloque

    def detener(self) -> None:
        if self._flujo is not None:
            try:
                self._flujo.stop()
                self._flujo.close()
            finally:
                self._flujo = None


class FuenteHilo:
    """Lee una fuente en un hilo aparte para que la interfaz no se congele.

    Llama a ``al_bloque(muestras)`` por cada bloque leído."""

    def __init__(self, fuente: FuenteAudio, al_bloque):
        self.fuente = fuente
        self.al_bloque = al_bloque
        self._parar = threading.Event()
        self._hilo = threading.Thread(target=self._correr, daemon=True)
        self.error: Exception | None = None

    def iniciar(self) -> None:
        self.fuente.iniciar()
        self._hilo.start()

    def _correr(self) -> None:
        try:
            while not self._parar.is_set() and not self.fuente.terminada:
                bloque = self.fuente.leer(0.2)
                if bloque is not None and len(bloque):
                    self.al_bloque(bloque)
        except Exception as ex:
            self.error = ex

    def detener(self) -> None:
        self._parar.set()
        if self._hilo.is_alive():
            self._hilo.join(timeout=2)
        self.fuente.detener()

    @property
    def activo(self) -> bool:
        return self._hilo.is_alive()
