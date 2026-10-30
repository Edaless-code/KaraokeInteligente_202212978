"""Estado de una sesión de karaoke y de la canción que se está cantando.

Lo comparten el modo manual (el operador presiona las teclas) y el modo
automático (las mismas acciones las dispara el sincronizador de audio).

Acciones sobre la canción en curso:

* ``continuar`` (c)  pasa a la siguiente línea.
* ``igual``     (i)  el cantante repite la misma línea: se queda en ella.
* ``repetir``   (r)  vuelve a empezar la misma canción.
* ``ignorar``   (g)  suspende el avance (afinando la voz, ejercicios...).
* ``seguir``    (s)  reanuda después de ignorar.
* ``atras``     (a)  regresa una línea (corrección de un avance por error).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .db import BaseDatos, Cancion, ahora
from .programa import CursorPrograma


@dataclass
class CancionEnCurso:
    cancion: Cancion
    actual: int = 0
    pausada: bool = False
    repeticiones_linea: int = 0
    repeticiones_cancion: int = 0
    mensaje: str = ""
    lineas_mostradas: int = 1
    inicio: str = field(default_factory=ahora)

    @property
    def total(self) -> int:
        return len(self.cancion.lineas)

    @property
    def terminada(self) -> bool:
        return self.actual >= self.total

    @property
    def linea(self) -> str:
        return "" if self.terminada else self.cancion.lineas[self.actual]

    def continuar(self) -> bool:
        """Avanza una línea. Devuelve ``True`` si la canción terminó."""
        if self.pausada:
            self.mensaje = "En pausa: presione (s) para seguir."
            return False
        if not self.terminada:
            self.actual += 1
            self.lineas_mostradas += 1
        self.repeticiones_linea = 0
        self.mensaje = ""
        return self.terminada

    def ir_a(self, linea: int) -> None:
        linea = max(0, min(linea, self.total))
        if linea != self.actual:
            self.lineas_mostradas += 1
            self.repeticiones_linea = 0
        self.actual = linea

    def igual(self) -> None:
        self.repeticiones_linea += 1
        self.mensaje = f"Repitiendo la misma línea (x{self.repeticiones_linea + 1})."

    def repetir(self) -> None:
        self.repeticiones_cancion += 1
        self.actual = 0
        self.repeticiones_linea = 0
        self.pausada = False
        self.lineas_mostradas += 1
        self.mensaje = f"Se repite la canción (vez {self.repeticiones_cancion + 1})."

    def ignorar(self) -> None:
        self.pausada = True
        self.mensaje = "Ignorando: el cantante afina o hace ejercicios. (s) para seguir."

    def seguir(self) -> None:
        self.pausada = False
        self.mensaje = ""

    def atras(self) -> None:
        if self.actual > 0:
            self.actual -= 1
            self.repeticiones_linea = 0
        self.mensaje = "Se regresó una línea."


@dataclass
class Interpretacion:
    codigo: int | None
    nombre: str
    completada: bool
    lineas_mostradas: int


class SesionKaraoke:
    """Una sesión completa: se pueden cantar X canciones hasta finalizar (f)."""

    def __init__(self, bd: BaseDatos, modo: str):
        self.bd = bd
        self.modo = modo
        self.id_sesion = bd.iniciar_sesion(modo)
        self.programa = CursorPrograma(bd)
        self.cantadas: list[Interpretacion] = []
        self.en_curso: CancionEnCurso | None = None
        self.finalizada = False

    def iniciar(self, cancion: Cancion, linea: int = 0) -> CancionEnCurso:
        if self.en_curso is not None:
            self.terminar(completada=self.en_curso.terminada)
        self.en_curso = CancionEnCurso(cancion, actual=max(0, min(linea, len(cancion.lineas) - 1)))
        return self.en_curso

    def terminar(self, completada: bool) -> None:
        """Registra la canción en curso en el historial y en el programa."""
        curso = self.en_curso
        if curso is None:
            return
        self.en_curso = None
        self.bd.registrar_interpretacion(
            self.id_sesion,
            curso.cancion.codigo,
            curso.cancion.nombre,
            self.modo,
            curso.inicio,
            curso.lineas_mostradas,
            completada,
        )
        if curso.cancion.codigo is not None:
            self.programa.marcar_cantada(curso.cancion.codigo)
        self.cantadas.append(
            Interpretacion(curso.cancion.codigo, curso.cancion.nombre, completada, curso.lineas_mostradas)
        )

    def repetir_ultima(self) -> CancionEnCurso | None:
        """Vuelve a cantar la última canción terminada (tecla r al final)."""
        if not self.cantadas or self.cantadas[-1].codigo is None:
            return None
        cancion = self.bd.obtener_cancion(self.cantadas[-1].codigo)
        if cancion is None:
            return None
        curso = self.iniciar(cancion)
        curso.repeticiones_cancion = 1
        curso.mensaje = "Se repite la canción."
        return curso

    def finalizar(self) -> list[Interpretacion]:
        if self.en_curso is not None:
            self.terminar(completada=self.en_curso.terminada)
        self.bd.terminar_sesion(self.id_sesion)
        self.finalizada = True
        return self.cantadas
