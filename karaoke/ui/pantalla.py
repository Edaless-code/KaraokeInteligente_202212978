"""Dibujo de la pantalla del karaoke (la que ven el cantante y el público).

Se muestra la línea anterior en tono tenue, la línea que toca cantar
resaltada y en grande (amarillo, con una flecha) y las líneas siguientes como
adelanto, para que el público no se atrase ni se adelante al cantante.
"""

from __future__ import annotations

import textwrap
from dataclasses import dataclass, field

from . import consola
from .consola import color


@dataclass
class VistaKaraoke:
    nombre: str
    codigo: int | None
    lineas: list[str]
    actual: int  # índice (base 0) de la línea que toca cantar
    modo: str = "manual"
    estado: str = "CANTANDO"
    mensaje: str = ""
    ayuda: str = ""
    detalles: list[str] = field(default_factory=list)
    previas: int = 1
    siguientes: int = 2


def _envolver(texto: str, ancho: int) -> list[str]:
    return textwrap.wrap(texto, ancho) or [""]


def componer(vista: VistaKaraoke) -> list[str]:
    """Devuelve los renglones de la pantalla (sin limpiarla)."""
    ancho = min(consola.ancho(), 100)
    util = ancho - 6
    renglones: list[str] = []
    barra = "═" * ancho
    renglones.append(color(barra, "cian"))
    codigo = f"[{vista.codigo}] " if vista.codigo is not None else ""
    total = len(vista.lineas)
    posicion = f"línea {min(vista.actual + 1, total)}/{total}" if total else ""
    renglones.append(
        color(f"  KARAOKE INTELIGENTE · modo {vista.modo}", "negrita", "cian")
        + "   "
        + color(posicion, "tenue")
    )
    renglones.append(color(f"  ♪ {codigo}{vista.nombre}", "negrita", "magenta"))
    renglones.append(color(barra, "cian"))
    renglones.append("")

    inicio = max(0, vista.actual - vista.previas)
    fin = min(total, vista.actual + vista.siguientes + 1)
    for numero in range(inicio, fin):
        texto = vista.lineas[numero]
        if numero == vista.actual:
            partes = _envolver(texto.upper(), util)
            for i, parte in enumerate(partes):
                marca = "  ► " if i == 0 else "    "
                renglones.append(color(marca + parte, "negrita", "amarillo"))
        elif numero < vista.actual:
            for parte in _envolver(texto, util):
                renglones.append(color("    " + parte, "tenue"))
        else:
            for parte in _envolver(texto, util):
                renglones.append("    " + parte)
    if vista.actual >= total and total:
        renglones.append(color("  ♪ ♪ ♪  FIN DE LA CANCIÓN  ♪ ♪ ♪", "negrita", "verde"))
    renglones.append("")

    estilo_estado = ("negrita", "verde") if vista.estado.startswith("CANTANDO") else ("negrita", "rojo")
    renglones.append(color(f"  Estado: {vista.estado}", *estilo_estado))
    if vista.mensaje:
        renglones.append(color(f"  {vista.mensaje}", "amarillo"))
    for detalle in vista.detalles:
        renglones.append(color(f"  {detalle}", "tenue"))
    if vista.ayuda:
        renglones.append(color("─" * ancho, "cian"))
        for parte in textwrap.wrap(vista.ayuda, ancho - 2):
            renglones.append(color("  " + parte, "cian"))
    return renglones


def dibujar(vista: VistaKaraoke) -> None:
    consola.limpiar()
    print("\n".join(componer(vista)), flush=True)


def paginar(
    renglones: list[str],
    por_pagina: int,
    teclado: consola.Teclado,
    encabezado: str = "",
) -> None:
    """Muestra ``renglones`` en grupos de ``por_pagina`` (10 en 10)."""
    total = len(renglones)
    paginas = max(1, (total + por_pagina - 1) // por_pagina)
    pagina = 0
    while True:
        consola.limpiar()
        if encabezado:
            consola.titulo(encabezado)
        desde = pagina * por_pagina
        for renglon in renglones[desde : desde + por_pagina]:
            print(renglon)
        print()
        print(color(f"Página {pagina + 1} de {paginas}", "tenue"))
        if paginas == 1:
            teclado.pausa("Presione una tecla para regresar...")
            return
        print(color("[Enter/s] siguiente   [a] anterior   [q] regresar", "cian"))
        opcion = teclado.tecla() or "q"
        if opcion in ("q", "r", "esc"):
            return
        if opcion in ("a", "izquierda", "arriba"):
            pagina = max(0, pagina - 1)
        elif pagina + 1 < paginas:
            pagina += 1
        else:
            return
