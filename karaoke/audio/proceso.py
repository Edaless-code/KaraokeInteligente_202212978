"""Cadena de audio del modo automático: fuente → limpieza → motores de voz.

``ProcesadorAudio`` se puede usar paso a paso (``paso()``, para pruebas y
herramientas) o en un hilo aparte (``iniciar()``), dejando los resultados en
una cola que lee la interfaz. Así la pantalla nunca se congela mientras se
transcribe.
"""

from __future__ import annotations

import queue
import threading
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from ..config import Config
from .fuentes import FuenteArchivo, FuenteAudio
from .limpieza import LimpiadorAudio
from .modelos import idiomas_disponibles, ruta_modelo
from .motores import ErrorMotor, Motor, MotorSimulado, MotorVosk, MotorWhisper, Transcripcion


@dataclass
class Resultado:
    segundo: float
    voz: bool
    nivel_db: float
    transcripciones: list[Transcripcion] = field(default_factory=list)
    terminado: bool = False


def whisper_disponible() -> bool:
    try:
        import faster_whisper  # noqa: F401
    except ImportError:
        return False
    return True


def crear_motores(config: Config, idiomas: list[str], sincrono: bool = False) -> tuple[list[Motor], list[str]]:
    """Crea los motores según ``[audio] motor`` (hibrido | vosk | whisper).

    Devuelve (motores, avisos). En modo híbrido se usa Vosk para seguir la
    letra en tiempo real y Whisper (si está instalado) para identificar."""
    eleccion = config.texto("audio", "motor").lower()
    avisos: list[str] = []
    motores: list[Motor] = []
    if eleccion == "simulado":
        guion = config.ruta("audio", "guion_simulado")
        if not guion.exists():
            raise ErrorMotor(f"No existe el guion del motor simulado: {guion}")
        return [MotorSimulado(str(guion), config.entero("audio", "frecuencia_muestreo"))], avisos
    if eleccion in ("hibrido", "híbrido", "vosk"):
        disponibles = [i for i in idiomas if i in idiomas_disponibles(config)] or idiomas_disponibles(config)
        if disponibles:
            motores.append(MotorVosk({i: ruta_modelo(config, i) for i in disponibles},
                                     config.entero("audio", "frecuencia_muestreo")))
        else:
            avisos.append("No hay modelos de Vosk; use el diagnóstico (d) para descargarlos.")
    if eleccion in ("hibrido", "híbrido", "whisper"):
        if whisper_disponible():
            try:
                motores.append(MotorWhisper(config.texto("audio", "modelo_whisper"), "auto",
                                            config.entero("audio", "frecuencia_muestreo"),
                                            sincrono=sincrono))
            except ErrorMotor as ex:
                avisos.append(str(ex))
        elif eleccion == "whisper":
            avisos.append("Whisper no está instalado (pip install faster-whisper).")
    if not motores:
        raise ErrorMotor("No hay ningún motor de voz disponible. " + " ".join(avisos))
    return motores, avisos


def crear_limpiador(config: Config, fuente: FuenteAudio) -> LimpiadorAudio:
    limpiador = LimpiadorAudio.desde_config(config)
    if isinstance(fuente, FuenteArchivo) and fuente.aislar_voz:
        # En una canción ya mezclada el "ruido" es la música: restarlo daña la
        # voz (se comprobó con las pruebas). Se deja el filtro de banda y el AGC.
        limpiador.reduccion_ruido = False
    return limpiador


class ProcesadorAudio:
    def __init__(self, fuente: FuenteAudio, limpiador: LimpiadorAudio | None, motores: list[Motor]):
        self.fuente = fuente
        self.limpiador = limpiador
        self.motores = motores
        self.frecuencia = fuente.frecuencia
        self.segundo = 0.0
        self.cola: queue.Queue[Resultado] = queue.Queue()
        self._vocabulario: tuple | None = None
        self._candado = threading.Lock()
        self._parar = threading.Event()
        self._hilo: threading.Thread | None = None
        self.error: Exception | None = None
        self.terminado = False

    @property
    def nombres_motores(self) -> str:
        return " + ".join(m.nombre for m in self.motores)

    def pedir_vocabulario(self, vocabulario: set[str] | None, idioma: str | None) -> None:
        """Se aplica antes del siguiente bloque (seguro entre hilos)."""
        with self._candado:
            self._vocabulario = (vocabulario, idioma)

    def _aplicar_vocabulario(self) -> None:
        with self._candado:
            pedido, self._vocabulario = self._vocabulario, None
        if pedido is not None:
            for motor in self.motores:
                motor.restringir(*pedido)

    def procesar(self, bloque: np.ndarray) -> Resultado:
        self._aplicar_vocabulario()
        self.segundo += len(bloque) / self.frecuencia
        if self.limpiador is not None:
            limpio = self.limpiador.procesar(bloque)
            voz, nivel = self.limpiador.voz_activa, self.limpiador.nivel_entrada_db
        else:
            limpio, voz, nivel = bloque, True, -20.0
        transcripciones: list[Transcripcion] = []
        if len(limpio):
            for motor in self.motores:
                transcripciones.extend(motor.procesar(limpio))
        return Resultado(self.segundo, voz, nivel, transcripciones)

    def paso(self) -> Resultado:
        """Lee y procesa un bloque (modo sin hilos)."""
        bloque = self.fuente.leer(0.2)
        if bloque is None:
            if self.fuente.terminada:
                pendientes = []
                for motor in self.motores:
                    if hasattr(motor, "vaciar"):
                        pendientes.extend(motor.vaciar())
                self.terminado = True
                return Resultado(self.segundo, False, -120.0, pendientes, terminado=True)
            return Resultado(self.segundo, False, -120.0)
        return self.procesar(bloque)

    # ------------------------------------------------------------ con hilo
    def iniciar(self) -> None:
        self.fuente.iniciar()
        self._hilo = threading.Thread(target=self._correr, daemon=True)
        self._hilo.start()

    def _correr(self) -> None:
        try:
            while not self._parar.is_set():
                resultado = self.paso()
                if resultado.transcripciones or resultado.terminado or len(self.cola.queue) < 50:
                    self.cola.put(resultado)
                if resultado.terminado:
                    return
        except Exception as ex:  # se informa en la pantalla
            self.error = ex
            self.cola.put(Resultado(self.segundo, False, -120.0, terminado=True))

    def detener(self) -> None:
        self._parar.set()
        if self._hilo is not None and self._hilo.is_alive():
            self._hilo.join(timeout=3)
        self.fuente.detener()


def ruta_relativa(config: Config, texto: str) -> Path:
    ruta = Path(texto.strip().strip('"'))
    if not ruta.is_absolute() and not ruta.exists():
        ruta = config.carpeta / ruta
    return ruta
