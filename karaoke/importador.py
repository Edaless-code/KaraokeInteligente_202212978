"""Lectura de canciones desde un archivo de texto plano (opción "t").

Formato aceptado (se detecta automáticamente):

1. Bloques separados por líneas en blanco. La primera línea de cada bloque es
   el NOMBRE DE LA CANCIÓN y las siguientes son la letra, una línea por renglón::

       Cielito lindo
       De la Sierra Morena, cielito lindo, vienen bajando
       ...

       La cucaracha
       La cucaracha, la cucaracha, ya no puede caminar
       ...

2. Encabezados explícitos: una línea que empieza con ``#`` o con ``NOMBRE:``
   marca el inicio de una canción. En este formato la letra puede tener
   líneas en blanco (separación de estrofas), que se ignoran::

       # Cielito lindo
       De la Sierra Morena...

Las líneas que empiezan con ``//`` son comentarios y se ignoran, igual que
las etiquetas de sección que no se cantan ("Coro", "Chorus (Repeat 2x)",
"[Verso 2]", "(Puente)").
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from .config import Config
from .db import BaseDatos, CancionDuplicada, CancionEnPapelera
from .texto import ajustar_linea, es_etiqueta, leer_texto

_ENCABEZADO = re.compile(r"^\s*(?:#+|nombre\s*:)\s*(.*)$", re.IGNORECASE)


@dataclass
class ResultadoImportacion:
    agregadas: list[tuple[int, str]] = field(default_factory=list)
    omitidas: list[tuple[str, str]] = field(default_factory=list)
    lineas_ajustadas: int = 0


def analizar_texto(texto: str) -> list[tuple[str, list[str]]]:
    """Convierte el contenido del archivo en una lista (nombre, líneas)."""
    renglones = [r.rstrip() for r in texto.replace("\r\n", "\n").replace("\r", "\n").split("\n")]
    renglones = [r for r in renglones if not r.lstrip().startswith("//") and not es_etiqueta(r)]
    explicito = any(_ENCABEZADO.match(r) for r in renglones)
    canciones: list[tuple[str, list[str]]] = []

    if explicito:
        actual: tuple[str, list[str]] | None = None
        for renglon in renglones:
            coincidencia = _ENCABEZADO.match(renglon)
            if coincidencia:
                actual = (coincidencia.group(1).strip(), [])
                canciones.append(actual)
            elif renglon.strip() and actual is not None:
                actual[1].append(renglon.strip())
        return canciones

    bloque: list[str] = []
    for renglon in renglones + [""]:
        if renglon.strip():
            bloque.append(renglon.strip())
        elif bloque:
            canciones.append((bloque[0], bloque[1:]))
            bloque = []
    return canciones


def importar_archivo(bd: BaseDatos, ruta: str | Path, config: Config) -> ResultadoImportacion:
    resultado = ResultadoImportacion()
    maximo = config.caracteres_por_linea
    accion = config.texto("letras", "accion_linea_larga")
    limite = config.entero("letras", "lineas_maximas_cancion")
    for nombre, lineas in analizar_texto(leer_texto(ruta)):
        if not nombre:
            resultado.omitidas.append(("(sin nombre)", "no tiene nombre"))
            continue
        ajustadas: list[str] = []
        for linea in lineas:
            partes = ajustar_linea(linea, maximo, accion)
            if len(partes) != 1 or partes[0] != linea:
                resultado.lineas_ajustadas += 1
            ajustadas.extend(partes)
        if not ajustadas:
            resultado.omitidas.append((nombre, "no tiene letra"))
            continue
        if len(ajustadas) > limite:
            resultado.omitidas.append((nombre, f"tiene más de {limite} líneas"))
            continue
        try:
            codigo = bd.agregar_cancion(nombre, ajustadas, origen="archivo")
            resultado.agregadas.append((codigo, nombre))
        except CancionEnPapelera:
            resultado.omitidas.append((nombre, "está en la papelera (restáurela si la quiere de vuelta)"))
        except CancionDuplicada:
            resultado.omitidas.append((nombre, "ya existe en la base de datos"))
        except ValueError as ex:
            resultado.omitidas.append((nombre, str(ex)))
    return resultado
