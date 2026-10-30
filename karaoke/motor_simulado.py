"""Motor de voz simulado: entrega un guion de texto con tiempos como si se
estuviera transcribiendo. No usa NumPy, así que funciona también en Android
(modo de demostración) y en las pruebas."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from .texto import leer_texto
from .transcripcion import Transcripcion


class Motor:
    """Interfaz común de los motores de voz."""

    nombre = "motor"
    idiomas: list[str] = []

    def procesar(self, muestras) -> list[Transcripcion]:
        raise NotImplementedError

    def restringir(self, vocabulario: set[str] | None, idioma: str | None = None) -> None:
        """Limita el canal restringido a ``vocabulario`` (``None`` lo apaga)."""

    def reiniciar(self) -> None:
        """Descarta la frase en curso."""


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

    def procesar(self, muestras) -> list[Transcripcion]:
        """Avanza el reloj según la cantidad de muestras recibidas (el audio
        en sí no se usa)."""
        return self.procesar_hasta(self.segundo + len(muestras) / self.frecuencia)

    def procesar_hasta(self, segundo: float) -> list[Transcripcion]:
        """Entrega lo que se "cantó" hasta ``segundo``."""
        self.segundo = segundo
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
