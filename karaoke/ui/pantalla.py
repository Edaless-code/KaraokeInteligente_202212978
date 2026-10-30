"""Dibujo de la pantalla del karaoke (la que ven el cantante y el público).

Diseño fijo, pensado para leerse de lejos y sin distracciones:

* arriba, el nombre de la canción y una barra de avance;
* en medio, la letra centrada: la línea anterior tenue, la que toca cantar
  resaltada (con ►) y las siguientes como adelanto;
* abajo, una sola línea de estado y las teclas.

La letra siempre ocupa el mismo lugar (no "salta") y la pantalla solo cambia
cuando cambia la línea o el estado. Los detalles técnicos (lo que escucha la
IA, el nivel del sonido) solo se ven si se piden con la tecla (d).
"""

from __future__ import annotations

import textwrap
from dataclasses import dataclass, field

from . import consola
from .consola import color

ANCHO_MAXIMO = 100


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
    tono_estado: str = "cian"


def _envolver(texto: str, ancho: int) -> list[str]:
    return textwrap.wrap(texto, ancho) or [""]


def _centrar(texto: str, ancho: int) -> str:
    return " " * max(0, (ancho - len(texto)) // 2) + texto


def barra_avance(actual: int, total: int, ancho: int) -> str:
    """Barra de avance de la canción: ━━━━━━──────."""
    if total <= 0 or ancho <= 0:
        return ""
    llenas = round(ancho * min(actual, total) / total)
    return color("━" * llenas, "cian") + color("─" * (ancho - llenas), "tenue")


def encabezado(titulo: str, derecha: str = "", ancho: int | None = None) -> list[str]:
    """Encabezado común de todas las pantallas."""
    ancho = ancho or min(consola.ancho(), ANCHO_MAXIMO)
    espacio = max(1, ancho - 4 - len(titulo) - len(derecha))
    return [
        "  " + color(titulo, "negrita", "cian") + " " * espacio + color(derecha, "tenue"),
        color("  " + "─" * (ancho - 4), "tenue"),
    ]


def pie(ayuda: str, ancho: int) -> list[str]:
    renglones = [color("  " + "─" * (ancho - 4), "tenue")]
    for parte in textwrap.wrap(ayuda, ancho - 4):
        renglones.append(color("  " + parte, "tenue"))
    return renglones


def _bloque_letra(vista: VistaKaraoke, util: int, espaciado: bool) -> list[str]:
    """Las líneas visibles de la letra, centradas y siempre con el mismo alto
    (se rellenan con renglones vacíos al inicio y al final de la canción)."""
    total = len(vista.lineas)
    renglones: list[str] = []
    for desplazamiento in range(-vista.previas, vista.siguientes + 1):
        numero = vista.actual + desplazamiento
        if renglones and espaciado:
            renglones.append("")
        if not 0 <= numero < total:
            if numero == total and total and vista.actual >= total - 1 and desplazamiento > 0:
                renglones.append(color(_centrar("♪  fin de la canción  ♪", util + 4), "tenue"))
            else:
                renglones.append("")
            continue
        partes = _envolver(vista.lineas[numero], util)
        for i, parte in enumerate(partes):
            if desplazamiento == 0:
                marca = "►  " if i == 0 else "   "
                texto = _centrar(marca + parte, util + 4)
                renglones.append(color(texto, "negrita", "texto"))
            elif desplazamiento < 0:
                renglones.append(color(_centrar(parte, util + 4), "tenue"))
            else:
                renglones.append(color(_centrar(parte, util + 4), "blanco"))
    return renglones


def componer(vista: VistaKaraoke, alto: int | None = None) -> list[str]:
    """Devuelve los renglones de la pantalla (sin limpiarla)."""
    ancho = min(consola.ancho(), ANCHO_MAXIMO)
    alto = alto or consola.alto()
    util = ancho - 8
    total = len(vista.lineas)

    codigo = f"código {vista.codigo}" if vista.codigo is not None else "sin código"
    renglones = encabezado("KARAOKE INTELIGENTE", f"modo {vista.modo}", ancho)
    renglones.append("")
    renglones.append("  " + color("♪  " + vista.nombre, "negrita", "texto") + color(f"   ·  {codigo}", "tenue"))
    posicion = f" {min(vista.actual + 1, total)} de {total}" if total else ""
    renglones.append("  " + barra_avance(vista.actual + 1, total, ancho - 6 - len(posicion))
                     + color(posicion, "tenue"))

    abajo = ["", "  " + color("● ", vista.tono_estado) + color(vista.estado, "negrita", vista.tono_estado)]
    abajo.append(color(f"  {vista.mensaje}", "amarillo") if vista.mensaje else "")
    for detalle in vista.detalles:
        abajo.append(color(f"  {detalle}", "tenue"))
    if vista.ayuda:
        abajo += pie(vista.ayuda, ancho)

    # La letra va centrada en el espacio libre, con aire entre líneas si cabe.
    libre = alto - len(renglones) - len(abajo) - 1
    letra = _bloque_letra(vista, util, espaciado=True)
    if len(letra) > libre:
        letra = _bloque_letra(vista, util, espaciado=False)
    arriba_vacio = max(1, (libre - len(letra)) // 2)
    renglones += [""] * arriba_vacio + letra
    renglones += [""] * max(1, libre - arriba_vacio - len(letra))
    return renglones + abajo


def dibujar(vista: VistaKaraoke) -> None:
    consola.redibujar(componer(vista))


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
