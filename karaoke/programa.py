"""Programa tentativo del cantante (archivo de texto "PROGRAMA").

El archivo tiene el nombre de una canción por renglón, en el orden en que se
piensa cantar. Se aceptan numeraciones y viñetas al inicio ("1.", "2)", "-",
"*") y se ignoran los renglones vacíos y los comentarios ("//" o "#")::

    1. Cielito lindo
    2. La cucaracha
    3. De colores

El orden NO es estricto: el cursor siempre sugiere la primera canción
pendiente, pero el usuario puede cantar otra, saltarse canciones, repetir o
abandonar el programa; la canción que se canta se marca como "cantada" sin
importar el orden.
"""

from __future__ import annotations

import re
from pathlib import Path

from .db import BaseDatos, EntradaPrograma
from .texto import leer_texto, normalizar, semejanza

_NUMERACION = re.compile(r"^\s*(?:\d+\s*[.)\-:]+|[-*•])\s*")


def leer_programa(ruta: str | Path) -> list[str]:
    nombres = []
    for renglon in leer_texto(ruta).splitlines():
        renglon = renglon.strip()
        if not renglon or renglon.startswith(("//", "#")):
            continue
        nombre = _NUMERACION.sub("", renglon).strip()
        if nombre:
            nombres.append(nombre)
    return nombres


def resolver_nombre(bd: BaseDatos, nombre: str) -> int | None:
    """Busca el código de una canción por su nombre, tolerando diferencias
    menores (tildes, mayúsculas, un error de dedo)."""
    codigo = bd.existe_nombre(nombre)
    if codigo is not None:
        return codigo
    candidatos = bd.buscar_por_nombre(nombre, limite=2)
    if len(candidatos) == 1:
        return candidatos[0][0]
    if candidatos:
        consulta = normalizar(nombre)
        mejor = max(candidatos, key=lambda c: semejanza(consulta, normalizar(c[1])))
        if semejanza(consulta, normalizar(mejor[1])) >= 0.85:
            return mejor[0]
    return None


def cargar_programa(bd: BaseDatos, nombres: list[str]) -> list[tuple[str, int | None]]:
    """Guarda el programa en la tabla PROGRAMA y devuelve (nombre, código)."""
    entradas = [(n, resolver_nombre(bd, n)) for n in nombres]
    bd.guardar_programa(entradas)
    return entradas


class CursorPrograma:
    """Recorre el programa de forma flexible durante una sesión."""

    def __init__(self, bd: BaseDatos):
        self.bd = bd
        self.activo = True
        self.bd.vincular_programa()

    def entradas(self) -> list[EntradaPrograma]:
        return self.bd.obtener_programa()

    def hay_programa(self) -> bool:
        return bool(self.entradas())

    def pendientes(self) -> list[EntradaPrograma]:
        return [e for e in self.entradas() if e.estado == "pendiente" and e.codigo is not None]

    def siguiente(self) -> EntradaPrograma | None:
        if not self.activo:
            return None
        pendientes = self.pendientes()
        return pendientes[0] if pendientes else None

    def marcar_cantada(self, codigo: int) -> None:
        """Marca como cantada la primera entrada pendiente con ese código (si
        el cantante se adelantó a una canción que estaba más adelante)."""
        for entrada in self.entradas():
            if entrada.codigo == codigo and entrada.estado == "pendiente":
                self.bd.marcar_programa(entrada.orden, "cantada")
                return

    def saltar(self, entrada: EntradaPrograma) -> None:
        self.bd.marcar_programa(entrada.orden, "saltada")

    def prioridad(self, bono: float = 0.1) -> dict[int, float]:
        """Bono de búsqueda para la canción que sigue en el programa."""
        siguiente = self.siguiente()
        return {siguiente.codigo: bono} if siguiente and siguiente.codigo is not None else {}
