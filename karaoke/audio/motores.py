"""Motores de transcripción de voz a texto.

``MotorVosk`` (el que se usa por omisión) se basa en Vosk/Kaldi: es gratuito,
funciona sin internet, es ligero (modelos de ~40 MB), entrega resultados
**parciales mientras la persona canta** (no hay que esperar a que termine la
frase) y existe también para Android. Cada idioma usa su propio modelo.

Por cada idioma se pueden tener dos canales sobre el mismo audio:

* ``libre``        reconoce cualquier palabra del idioma. Sirve para
  identificar la canción y para aprender canciones nuevas.
* ``restringido``  solo reconoce las palabras de la letra (más ``[unk]`` para
  lo demás). Al limitar el vocabulario a la letra, la voz cantada (que es
  mucho más difícil que la hablada) se reconoce bastante mejor.

``MotorWhisper`` (opcional, ``pip install faster-whisper``) usa Whisper de
OpenAI en su versión optimizada para CPU. Es más lento y no entrega
resultados parciales, pero entiende mucho mejor la voz con música de fondo,
por lo que se usa para IDENTIFICAR la canción con una muestra de unos
segundos (el seguimiento línea por línea lo sigue haciendo Vosk).

``MotorSimulado`` no escucha audio: entrega un guion de texto con tiempos.
Sirve para las pruebas automatizadas y para hacer una demostración sin
micrófono.
"""

from __future__ import annotations

import json
import math
import queue
import re
import threading
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from ..texto import leer_texto
from ..transcripcion import Transcripcion
from .limpieza import a_pcm16


class ErrorMotor(Exception):
    """El motor de transcripción no se pudo preparar."""


class Motor:
    nombre = "motor"
    idiomas: list[str] = []

    def procesar(self, muestras: np.ndarray) -> list[Transcripcion]:
        raise NotImplementedError

    def restringir(self, vocabulario: set[str] | None, idioma: str | None = None) -> None:
        """Limita el canal restringido a ``vocabulario`` (``None`` lo apaga)."""

    def reiniciar(self) -> None:
        """Descarta la frase en curso."""


class _Canal:
    def __init__(self, vosk, modelo, frecuencia: int, nombre: str, idioma: str, gramatica=None):
        self.nombre = nombre
        self.idioma = idioma
        if gramatica is None:
            self.reconocedor = vosk.KaldiRecognizer(modelo, frecuencia)
        else:
            self.reconocedor = vosk.KaldiRecognizer(modelo, frecuencia, json.dumps(gramatica))
        self.reconocedor.SetWords(True)
        self._ultimo_parcial = ""

    def aceptar(self, pcm: bytes, segundo: float) -> list[Transcripcion]:
        if self.reconocedor.AcceptWaveform(pcm):
            datos = json.loads(self.reconocedor.Result())
            self._ultimo_parcial = ""
            texto = datos.get("text", "").strip()
            if not texto:
                return []
            confianzas = [p.get("conf", 1.0) for p in datos.get("result", [])]
            confianza = float(sum(confianzas) / len(confianzas)) if confianzas else 1.0
            return [Transcripcion("final", texto, self.nombre, self.idioma, confianza, segundo)]
        texto = json.loads(self.reconocedor.PartialResult()).get("partial", "").strip()
        if texto and texto != self._ultimo_parcial:
            self._ultimo_parcial = texto
            return [Transcripcion("parcial", texto, self.nombre, self.idioma, 1.0, segundo)]
        return []

    def reiniciar(self) -> None:
        self.reconocedor.Reset()
        self._ultimo_parcial = ""


class MotorVosk(Motor):
    nombre = "Vosk"

    def __init__(self, modelos: dict[str, Path], frecuencia: int = 16000, canal_libre: bool = True):
        try:
            import vosk
        except ImportError as ex:
            raise ErrorMotor("Falta instalar Vosk: pip install vosk") from ex
        vosk.SetLogLevel(-1)
        self._vosk = vosk
        self.frecuencia = frecuencia
        self.modelos = {}
        for idioma, ruta in modelos.items():
            try:
                self.modelos[idioma] = vosk.Model(str(ruta))
            except Exception as ex:
                raise ErrorMotor(f"No se pudo cargar el modelo de voz {ruta}: {ex}") from ex
        if not self.modelos:
            raise ErrorMotor("No hay ningún modelo de voz disponible.")
        self.idiomas = list(self.modelos)
        self.canal_libre = canal_libre
        self.libres = {i: _Canal(vosk, m, frecuencia, "libre", i) for i, m in self.modelos.items()}
        self.restringido: _Canal | None = None
        self.segundo = 0.0

    def activar_idiomas(self, idiomas: list[str]) -> None:
        """Deja escuchando solo los canales libres de esos idiomas (por
        ejemplo, mientras se sigue una canción en inglés no hace falta el
        canal libre en español)."""
        self.libres = {
            i: self.libres.get(i) or _Canal(self._vosk, self.modelos[i], self.frecuencia, "libre", i)
            for i in idiomas
            if i in self.modelos
        }

    def restringir(self, vocabulario: set[str] | None, idioma: str | None = None) -> None:
        if not vocabulario:
            self.restringido = None
            return
        idioma = idioma if idioma in self.modelos else self.idiomas[0]
        gramatica = sorted(vocabulario) + ["[unk]"]
        self.restringido = _Canal(
            self._vosk, self.modelos[idioma], self.frecuencia, "restringido", idioma, gramatica
        )

    def procesar(self, muestras: np.ndarray) -> list[Transcripcion]:
        self.segundo += len(muestras) / self.frecuencia
        pcm = a_pcm16(muestras)
        resultados: list[Transcripcion] = []
        if self.canal_libre:
            for canal in self.libres.values():
                resultados.extend(canal.aceptar(pcm, self.segundo))
        if self.restringido is not None:
            resultados.extend(self.restringido.aceptar(pcm, self.segundo))
        return resultados

    def reiniciar(self) -> None:
        for canal in self.libres.values():
            canal.reiniciar()
        if self.restringido is not None:
            self.restringido.reiniciar()


_ALUCINACIONES = {"music", "música", "musica", "applause", "aplausos", "silence", "subtitles",
                  "thank you", "thanks for watching", "gracias"}


def es_alucinacion(texto: str) -> bool:
    """Whisper a veces "inventa" texto en la música o el silencio ("Music",
    "2.5%", "Thanks for watching"). Se descarta lo que no tiene letras o es
    una de esas frases típicas."""
    limpio = re.sub(r"[^\w\s]", " ", texto.lower()).strip()
    if not re.search(r"[a-záéíóúñ]{2,}", limpio):
        return True
    return " ".join(limpio.split()) in _ALUCINACIONES


class MotorWhisper(Motor):
    """Transcribe ventanas de ``ventana`` segundos con faster-whisper.

    En modo normal la transcripción corre en un hilo aparte y los resultados
    llegan en llamadas posteriores a ``procesar``; con ``sincrono=True``
    (herramientas y pruebas) cada ventana se transcribe en el momento."""

    nombre = "Whisper"

    def __init__(self, modelo: str = "base", idioma: str = "es", frecuencia: int = 16000,
                 ventana: float = 6.0, solape: float = 1.0, carpeta_modelos: str | None = None,
                 sincrono: bool = False, filtro_vad: bool = False):
        try:
            from faster_whisper import WhisperModel
        except ImportError as ex:
            raise ErrorMotor("Falta instalar Whisper: pip install faster-whisper") from ex
        try:
            self.modelo = WhisperModel(modelo, device="cpu", compute_type="int8",
                                       download_root=carpeta_modelos)
        except Exception as ex:
            raise ErrorMotor(f"No se pudo cargar el modelo Whisper «{modelo}»: {ex}") from ex
        self.idioma = idioma
        self.idiomas = [idioma]
        self.frecuencia = frecuencia
        self.ventana = int(ventana * frecuencia)
        self.solape = int(solape * frecuencia)
        self.sincrono = sincrono
        # El filtro de voz interno de Whisper descarta la voz cantada sobre
        # música (se comprobó con Sound of You), por eso va apagado.
        self.filtro_vad = filtro_vad
        self.sugerencia: str | None = None
        self.segundo = 0.0
        self._bufer = np.zeros(0, dtype=np.float32)
        self._resultados: queue.Queue[Transcripcion] = queue.Queue()
        self._pendientes: queue.Queue = queue.Queue(maxsize=1)
        if not sincrono:
            threading.Thread(target=self._trabajar, daemon=True).start()

    def restringir(self, vocabulario: set[str] | None, idioma: str | None = None) -> None:
        # Whisper no admite una gramática; se le da la letra como "sugerencia".
        # Sin canción se vuelve a detectar el idioma automáticamente.
        self.sugerencia = " ".join(sorted(vocabulario))[:600] if vocabulario else None
        self.idioma = idioma if vocabulario and idioma else "auto"

    def _transcribir(self, muestras: np.ndarray, segundo: float) -> None:
        # Con idioma "auto" Whisper detecta el idioma de cada ventana (canciones
        # bilingües, por ejemplo inglés con versos en español).
        idioma = None if self.idioma in (None, "", "auto") else self.idioma
        segmentos, informacion = self.modelo.transcribe(
            muestras, language=idioma, beam_size=1, vad_filter=self.filtro_vad,
            condition_on_previous_text=False, initial_prompt=self.sugerencia,
        )
        for segmento in segmentos:
            texto = segmento.text.strip()
            if texto and not es_alucinacion(texto):
                self._resultados.put(Transcripcion(
                    "final", texto, "libre", informacion.language or self.idioma,
                    float(math.exp(segmento.avg_logprob)), segundo,
                ))

    def _trabajar(self) -> None:
        while True:
            muestras, segundo = self._pendientes.get()
            try:
                self._transcribir(muestras, segundo)
            except Exception:
                pass

    def _enviar(self, muestras: np.ndarray) -> None:
        if self.sincrono:
            self._transcribir(muestras, self.segundo)
            return
        try:
            self._pendientes.put_nowait((muestras, self.segundo))
        except queue.Full:
            pass  # Whisper sigue ocupado: se descarta esta ventana

    def procesar(self, muestras: np.ndarray) -> list[Transcripcion]:
        self.segundo += len(muestras) / self.frecuencia
        self._bufer = np.concatenate([self._bufer, muestras.astype(np.float32)])
        if len(self._bufer) >= self.ventana:
            self._enviar(self._bufer.copy())
            self._bufer = self._bufer[-self.solape :]
        return self.recoger()

    def vaciar(self) -> list[Transcripcion]:
        """Transcribe lo que quede en el búfer (al terminar un archivo)."""
        if len(self._bufer) > self.solape:
            self._enviar(self._bufer.copy())
        self._bufer = np.zeros(0, dtype=np.float32)
        return self.recoger()

    def recoger(self) -> list[Transcripcion]:
        resultados = []
        while True:
            try:
                resultados.append(self._resultados.get_nowait())
            except queue.Empty:
                return resultados

    def reiniciar(self) -> None:
        self._bufer = np.zeros(0, dtype=np.float32)


_TIEMPO = re.compile(r"^\s*(?:(\d+):)?(\d+(?:\.\d+)?)\s+(.*)$")


@dataclass
class _Frase:
    inicio: float
    texto: str
    palabras: list[str] = field(default_factory=list)


class MotorSimulado(Motor):
    """Entrega un guion de texto como si se estuviera transcribiendo.

    Formato del guion (un renglón por frase, ``minutos:segundos texto``)::

        0:03 I heard the sound of you
        0:07 in every thing I do

    Las palabras de cada frase salen como resultados parciales, una cada
    ``segundos_por_palabra``, y al final la frase completa como resultado final.
    """

    nombre = "simulado"

    def __init__(self, guion: str | list[tuple[float, str]], frecuencia: int = 16000,
                 segundos_por_palabra: float = 0.35, idioma: str = "es"):
        if isinstance(guion, str):
            guion = self.leer_guion(guion)
        self.frases = [_Frase(t, x, x.split()) for t, x in sorted(guion)]
        self.frecuencia = frecuencia
        self.paso = segundos_por_palabra
        self.idiomas = [idioma]
        self.idioma = idioma
        self.segundo = 0.0
        self._entregadas: dict[int, int] = {}

    @staticmethod
    def leer_guion(texto_o_ruta: str) -> list[tuple[float, str]]:
        texto = leer_texto(texto_o_ruta) if Path(texto_o_ruta).is_file() else texto_o_ruta
        frases = []
        for renglon in texto.splitlines():
            coincidencia = _TIEMPO.match(renglon)
            if coincidencia and coincidencia.group(3).strip():
                minutos = float(coincidencia.group(1) or 0)
                frases.append((minutos * 60 + float(coincidencia.group(2)), coincidencia.group(3).strip()))
        return frases

    @property
    def duracion(self) -> float:
        if not self.frases:
            return 0.0
        ultima = self.frases[-1]
        return ultima.inicio + len(ultima.palabras) * self.paso + 1

    def procesar(self, muestras: np.ndarray) -> list[Transcripcion]:
        self.segundo += len(muestras) / self.frecuencia
        resultados = []
        for numero, frase in enumerate(self.frases):
            if frase.inicio > self.segundo:
                break
            entregadas = self._entregadas.get(numero, 0)
            if entregadas > len(frase.palabras):
                continue
            visibles = min(len(frase.palabras), int((self.segundo - frase.inicio) / self.paso) + 1)
            if visibles > entregadas and visibles <= len(frase.palabras):
                self._entregadas[numero] = visibles
                resultados.append(Transcripcion(
                    "parcial", " ".join(frase.palabras[:visibles]), "libre", self.idioma, 1.0, self.segundo))
            if self.segundo >= frase.inicio + len(frase.palabras) * self.paso:
                self._entregadas[numero] = len(frase.palabras) + 1
                resultados.append(Transcripcion("final", frase.texto, "libre", self.idioma, 1.0, self.segundo))
        return resultados
