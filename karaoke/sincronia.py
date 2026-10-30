"""Sincronía entre la letra en pantalla y el audio que se escucha.

Los motores de voz siempre van un poco atrás de la voz: necesitan oír las
palabras antes de reconocerlas (Vosk ~1 s, Whisper varios segundos). Si la
pantalla mostrara la letra en ese momento, la voz siempre iría adelantada.

Con una pista grabada (modo automático desde un archivo) se resuelve igual que
un reproductor de video con subtítulos:

1. El análisis lee el audio ``adelanto`` segundos ANTES de que suene por las
   bocinas (la reproducción arranca con ese retraso).
2. Cada estado de la pantalla se guarda con el segundo de análisis en que se
   produjo (``LineaDeTiempo.guardar``).
3. Se muestra el estado que corresponde a lo que suena en las bocinas más
   ``anticipacion`` segundos (la letra va ~0.5 s adelantada para alcanzar a
   leerla y cantarla a tiempo), descontando la ``latencia`` de los motores.

Con el micrófono (karaoke en vivo) no se puede retrasar al cantante: ahí la
letra se adelanta con ``avance_linea`` y la predicción por tempo, y siempre se
ven las líneas siguientes.
"""

from __future__ import annotations

from collections import deque
from typing import Generic, TypeVar

T = TypeVar("T")


def desfase_pantalla(adelanto: float, anticipacion: float, latencia: float) -> float:
    """Segundos que la pantalla va detrás del análisis (nunca negativo).

    En el instante en que suena el segundo ``p`` el análisis ya va en
    ``p + adelanto``; se quiere mostrar lo que se canta en ``p + anticipacion``,
    que el análisis reconoció ``latencia`` segundos después.
    """
    return max(0.0, adelanto - anticipacion - latencia)


class LineaDeTiempo(Generic[T]):
    """Historial corto de estados de pantalla para mostrarlos con retraso."""

    def __init__(self, desfase: float, conservar: float = 10.0):
        self.desfase = desfase
        self._conservar = max(conservar, desfase + 2.0)
        self._fotos: deque[tuple[float, T]] = deque()

    def guardar(self, segundo: float, foto: T) -> None:
        self._fotos.append((segundo, foto))
        # Se conserva al menos una foto anterior al momento que se muestra.
        while len(self._fotos) > 1 and self._fotos[1][0] <= segundo - self._conservar:
            self._fotos.popleft()

    def reiniciar(self, foto: T) -> None:
        """Tras una orden del operador (c, r, x…) se muestra ya el estado
        nuevo, sin esperar el desfase."""
        self._fotos.clear()
        self._fotos.append((float("-inf"), foto))

    def foto(self, segundo: float) -> T | None:
        """Estado que corresponde mostrar cuando el análisis va en ``segundo``."""
        objetivo = segundo - self.desfase
        elegida = None
        for momento, foto in self._fotos:
            if momento > objetivo:
                break
            elegida = foto
        if elegida is None and self._fotos:
            elegida = self._fotos[0][1]
        return elegida
