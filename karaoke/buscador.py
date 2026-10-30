"""Búsqueda de canciones a partir de unas cuantas palabras de la letra.

Se usa en el modo manual (el operador teclea dos o tres palabras que escucha)
y en el modo automático (las palabras vienen de la transcripción del audio).

Algoritmo:

1. Se construye en memoria un índice con todas las letras: la secuencia de
   palabras normalizadas de cada canción y la línea a la que pertenece cada
   palabra. Las palabras muy frecuentes ("la", "de", "y"...) pesan menos que
   las raras (peso tipo IDF).
2. Para tolerar errores de dedo o de transcripción dos palabras se consideran
   iguales si su semejanza (``difflib``) supera ``semejanza_palabra``.
3. Para cada canción candidata se calcula un alineamiento local
   (Smith-Waterman) entre las palabras buscadas y la letra. El alineamiento
   respeta el orden de las palabras pero permite huecos, de modo que una
   palabra mal escuchada no impide encontrar la canción.
4. El puntaje es el peso de las palabras alineadas entre el peso total de la
   consulta (0..1). Se informa la canción, la línea donde empieza y termina la
   coincidencia y la posición de la siguiente palabra a cantar.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from functools import lru_cache

from .config import Config
from .db import BaseDatos, Cancion
from .texto import palabras, semejanza


@dataclass
class IndiceCancion:
    codigo: int
    nombre: str
    lineas: list[str]
    palabras: list[str]
    linea_de: list[int]
    inicio_linea: list[int]


@dataclass
class Resultado:
    codigo: int
    nombre: str
    puntaje: float
    linea_inicio: int  # índice (base 0) de la línea donde empieza la coincidencia
    linea_fin: int  # índice (base 0) de la línea donde termina
    palabra_siguiente: int  # índice de la palabra que sigue a la coincidencia
    evidencia: float = 0.0  # peso de las palabras que coincidieron
    bono: float = 0.0  # prioridad extra (siguiente del PROGRAMA)

    @property
    def orden(self) -> float:
        """Puntaje para ordenar y desempatar (puede pasar de 1 con el bono)."""
        return self.puntaje + self.bono

    @property
    def linea_actual(self) -> int:
        return self.linea_fin


def indexar_cancion(cancion: Cancion) -> IndiceCancion:
    lista: list[str] = []
    linea_de: list[int] = []
    inicio: list[int] = []
    for numero, linea in enumerate(cancion.lineas):
        inicio.append(len(lista))
        for palabra in palabras(linea):
            lista.append(palabra)
            linea_de.append(numero)
    return IndiceCancion(cancion.codigo, cancion.nombre, cancion.lineas, lista, linea_de, inicio)


def alinear(
    consulta: list[str],
    pesos: list[float],
    letra: list[str],
    umbral: float,
    desde: int = 0,
    hasta: int | None = None,
    exigir_ultima: bool = False,
) -> tuple[float, int, int]:
    """Alineamiento local de ``consulta`` contra ``letra[desde:hasta]``.

    Con ``exigir_ultima`` solo se aceptan alineamientos que terminan en la
    última palabra de la consulta (lo que importa al seguir al cantante es
    dónde está AHORA, no la coincidencia más larga del pasado).

    Devuelve (puntaje bruto, índice de la primera palabra alineada, índice de
    la última palabra alineada) con índices absolutos en ``letra``.
    """
    hasta = len(letra) if hasta is None else min(hasta, len(letra))
    desde = max(0, desde)
    columnas = hasta - desde
    if not consulta or columnas <= 0:
        return 0.0, -1, -1
    peso_medio = sum(pesos) / len(pesos)
    hueco_letra = 0.15 * peso_medio  # palabra de la letra que no se escuchó
    anterior = [0.0] * (columnas + 1)
    inicio_anterior = [-1] * (columnas + 1)
    mejor, mejor_ini, mejor_fin = 0.0, -1, -1
    ultima = len(consulta) - 1
    for i, palabra in enumerate(consulta):
        peso = pesos[i]
        hueco_consulta = 0.5 * peso  # palabra escuchada que no está en la letra
        actual = [0.0] * (columnas + 1)
        inicio_actual = [-1] * (columnas + 1)
        for j in range(1, columnas + 1):
            parecido = semejanza(palabra, letra[desde + j - 1])
            if parecido >= umbral:
                diagonal = anterior[j - 1] + peso * parecido
            else:
                diagonal = anterior[j - 1] - peso
            arriba = anterior[j] - hueco_consulta
            izquierda = actual[j - 1] - hueco_letra
            valor, ini = 0.0, -1
            if diagonal > valor:
                valor = diagonal
                ini = inicio_anterior[j - 1] if inicio_anterior[j - 1] >= 0 else desde + j - 1
            if arriba > valor:
                valor, ini = arriba, inicio_anterior[j]
            if izquierda > valor:
                valor, ini = izquierda, inicio_actual[j - 1]
            actual[j] = valor
            inicio_actual[j] = ini
            # Solo cuenta como final una columna donde hubo coincidencia real.
            if (valor > mejor and parecido >= umbral and diagonal == valor
                    and (not exigir_ultima or i == ultima)):
                mejor, mejor_ini, mejor_fin = valor, ini, desde + j - 1
        anterior, inicio_anterior = actual, inicio_actual
    return mejor, mejor_ini, mejor_fin


class Buscador:
    def __init__(self, bd: BaseDatos, config: Config):
        self.bd = bd
        self.umbral_palabra = config.decimal("busqueda", "semejanza_palabra")
        self.puntaje_minimo = config.decimal("busqueda", "puntaje_minimo")
        self.maximo_resultados = config.entero("busqueda", "resultados_maximos")
        self.evidencia_minima = config.decimal("busqueda", "evidencia_minima")
        self._revision = -1
        self.canciones: dict[int, IndiceCancion] = {}
        self._frecuencia: dict[str, int] = {}
        self._contiene: dict[str, set[int]] = {}
        self._total_lineas = 1
        self.refrescar()

    # ----------------------------------------------------------------- índice
    def refrescar(self, forzar: bool = False) -> None:
        if not forzar and self._revision == self.bd.revision:
            return
        self._revision = self.bd.revision
        self.canciones = {c: indexar_cancion(x) for c, x in self.bd.todas_las_letras().items()}
        self._frecuencia = {}
        self._contiene = {}
        total = 0
        for indice in self.canciones.values():
            for numero in range(len(indice.lineas)):
                total += 1
                fin = (
                    indice.inicio_linea[numero + 1]
                    if numero + 1 < len(indice.inicio_linea)
                    else len(indice.palabras)
                )
                for palabra in set(indice.palabras[indice.inicio_linea[numero] : fin]):
                    self._frecuencia[palabra] = self._frecuencia.get(palabra, 0) + 1
            for palabra in indice.palabras:
                self._contiene.setdefault(palabra, set()).add(indice.codigo)
        self._total_lineas = max(1, total)
        self._similares.cache_clear()

    @property
    def vocabulario(self) -> set[str]:
        self.refrescar()
        return set(self._contiene)

    def peso(self, palabra: str) -> float:
        frecuencia = self._frecuencia.get(palabra)
        if frecuencia is None:
            # Palabra desconocida: peso medio (pudo ser un error de transcripción).
            return 1.0
        return max(0.35, min(2.0, math.log(1 + self._total_lineas / frecuencia) / 2))

    @lru_cache(maxsize=20_000)
    def _similares(self, palabra: str) -> frozenset[int]:
        """Canciones que contienen una palabra parecida a ``palabra``."""
        if palabra in self._contiene and len(palabra) <= 2:
            return frozenset(self._contiene[palabra])
        codigos: set[int] = set()
        for otra, en in self._contiene.items():
            if otra == palabra or (
                abs(len(otra) - len(palabra)) <= 3 and semejanza(palabra, otra) >= self.umbral_palabra
            ):
                codigos |= en
        return frozenset(codigos)

    # --------------------------------------------------------------- búsqueda
    def buscar(
        self,
        texto: str | list[str],
        prioridad: dict[int, float] | None = None,
        solo: set[int] | None = None,
        limite: int | None = None,
    ) -> list[Resultado]:
        """Busca las palabras en todas las letras.

        ``prioridad`` suma un pequeño bono a algunas canciones (por ejemplo, la
        siguiente del PROGRAMA). ``solo`` restringe la búsqueda a esos códigos.
        """
        self.refrescar()
        consulta = palabras(texto) if isinstance(texto, str) else [p for p in texto if p]
        if not consulta or not self.canciones:
            return []
        pesos = [self.peso(p) for p in consulta]
        total = sum(pesos)

        votos: dict[int, float] = {}
        for palabra, peso in zip(consulta, pesos):
            for codigo in self._similares(palabra):
                votos[codigo] = votos.get(codigo, 0.0) + peso
        if solo is not None:
            votos = {c: v for c, v in votos.items() if c in solo}
        # Solo se alinean las canciones que comparten suficientes palabras.
        candidatos = sorted(votos, key=votos.get, reverse=True)[:60]
        candidatos = [c for c in candidatos if votos[c] >= 0.25 * total]

        resultados: list[Resultado] = []
        for codigo in candidatos:
            indice = self.canciones[codigo]
            bruto, ini, fin = alinear(consulta, pesos, indice.palabras, self.umbral_palabra)
            if fin < 0:
                continue
            puntaje = min(1.0, bruto / total)
            bono = prioridad.get(codigo, 0.0) if prioridad else 0.0
            resultados.append(
                Resultado(
                    codigo,
                    indice.nombre,
                    round(puntaje, 3),
                    indice.linea_de[ini],
                    indice.linea_de[fin],
                    fin + 1,
                    round(bruto, 3),
                    bono,
                )
            )
        resultados.sort(key=lambda r: (-r.orden, r.codigo))
        return resultados[: limite or self.maximo_resultados]

    def identificar(
        self,
        texto: str | list[str],
        prioridad: dict[int, float] | None = None,
        margen: float = 0.08,
        minimo: float | None = None,
        evidencia: float | None = None,
    ) -> Resultado | None:
        """Devuelve la canción solo si el resultado es claro: supera el puntaje
        mínimo, tiene suficiente evidencia (varias palabras significativas,
        no una sola palabra común como "the" o "la") y le saca ``margen`` a la
        segunda canción."""
        resultados = self.buscar(texto, prioridad, limite=2)
        minimo = self.puntaje_minimo if minimo is None else minimo
        evidencia = self.evidencia_minima if evidencia is None else evidencia
        if not resultados or resultados[0].orden < minimo or resultados[0].evidencia < evidencia:
            return None
        if len(resultados) > 1 and resultados[0].orden - resultados[1].orden < margen:
            return None
        return resultados[0]
