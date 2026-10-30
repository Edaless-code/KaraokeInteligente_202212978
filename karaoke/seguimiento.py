"""Seguimiento automático de la posición del cantante dentro de la letra.

El ``Seguidor`` recibe las palabras que va transcribiendo el motor de voz y
decide qué línea mostrar:

* **Alineamiento local.** Las últimas palabras escuchadas se alinean
  (Smith-Waterman, igual que en la búsqueda) contra una ventana de la letra
  alrededor de la posición actual: la línea anterior, la actual y las dos
  siguientes. Así una palabra mal reconocida no hace saltar la pantalla.
* **Avance anticipado.** La siguiente línea se muestra cuando ya se cantó
  ``avance`` (70 %) de la línea actual, para que el público lea a tiempo.
* **Repeticiones.** Si las palabras vuelven a coincidir con el inicio de la
  misma línea es una línea "igual" (i); si coinciden con el inicio de la
  canción después de haber avanzado es una repetición de la canción (r).
* **Búsqueda global.** Si en la ventana no hay coincidencia pero varias
  palabras coinciden con claridad en otra parte de la canción (un coro que se
  repite, un salto), se salta allí.
* **Predicción por tempo.** Se mide cuántos segundos tarda el cantante en
  cada palabra. Si hay voz pero la transcripción no reconoce nada durante más
  de lo esperado para la línea, se avanza solo (máximo dos líneas seguidas
  sin confirmación) para que la pantalla no se quede congelada.
* **Anclas de Whisper.** Las frases largas que llegan de Whisper (con unos
  segundos de retraso) se alinean en una ventana más amplia y se compensa el
  retraso con el tempo estimado.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass

from .buscador import alinear, indexar_cancion
from .db import Cancion
from .texto import palabras as normalizar_palabras


@dataclass
class Evento:
    tipo: str  # avance | igual | repetir | salto | prediccion | fin
    linea: int
    detalle: str = ""


class Seguidor:
    def __init__(
        self,
        lineas: list[str],
        linea_inicial: int = 0,
        palabra_inicial: int | None = None,
        umbral_palabra: float = 0.78,
        avance: float = 0.70,
        prediccion: bool = True,
        segundos_por_palabra: float = 0.45,
        segundo: float = 0.0,
    ):
        indice = indexar_cancion(Cancion(0, "", list(lineas)))
        self.lineas = list(lineas)
        self.palabras = indice.palabras
        self.linea_de = indice.linea_de
        self.inicio_linea = indice.inicio_linea
        self.umbral = umbral_palabra
        self.avance = avance
        self.prediccion = prediccion
        self.segundos_por_palabra = segundos_por_palabra
        self.recientes: deque[str] = deque(maxlen=8)
        linea_inicial = max(0, min(linea_inicial, len(lineas) - 1)) if lineas else 0
        self.pos = palabra_inicial if palabra_inicial is not None else self._inicio(linea_inicial)
        self.mostrada = linea_inicial
        self._marcar_cambio(segundo, confirmado=False)
        self.predicciones_seguidas = 0
        self.ultima_coincidencia = segundo
        self.repeticiones_linea = 0

    # ---------------------------------------------------------------- ayudas
    def _inicio(self, linea: int) -> int:
        if linea >= len(self.inicio_linea):
            return len(self.palabras)
        return self.inicio_linea[linea]

    def _fin(self, linea: int) -> int:
        return self._inicio(linea + 1)

    def palabras_de(self, linea: int) -> int:
        return max(1, self._fin(linea) - self._inicio(linea))

    @property
    def total(self) -> int:
        return len(self.lineas)

    @property
    def terminada(self) -> bool:
        return self.mostrada >= self.total

    def _marcar_cambio(self, segundo: float, confirmado: bool) -> None:
        self.cambio_en = segundo
        self.cambio_confirmado = confirmado

    def duracion_esperada(self, linea: int) -> float:
        return self.palabras_de(linea) * self.segundos_por_palabra

    def _linea_para(self, posicion: int) -> int:
        """Línea a mostrar si la próxima palabra a cantar es ``posicion``."""
        if posicion >= len(self.palabras):
            return self.total
        linea = self.linea_de[posicion]
        hecho = (posicion - self._inicio(linea)) / self.palabras_de(linea)
        return linea + 1 if hecho >= self.avance else linea

    def _mostrar(self, linea: int, segundo: float, confirmado: bool) -> bool:
        linea = max(0, min(linea, self.total))
        if linea == self.mostrada:
            return False
        if confirmado and self.cambio_confirmado and linea == self.mostrada + 1:
            # Aprende el tempo del cantante con los cambios confirmados.
            duracion = segundo - self.cambio_en
            observado = duracion / self.palabras_de(self.mostrada)
            if 0.15 <= observado <= 2.0:
                self.segundos_por_palabra = 0.7 * self.segundos_por_palabra + 0.3 * observado
        self.mostrada = linea
        self.repeticiones_linea = 0
        self._marcar_cambio(segundo, confirmado)
        return True

    # -------------------------------------------------------- transcripción
    def escuchar(self, palabras: list[str] | str, segundo: float, retraso: float = 0.0) -> Evento | None:
        """Procesa palabras nuevas. ``retraso`` son los segundos que pasaron
        desde que se cantaron (Whisper entrega con varios segundos de retraso)."""
        nuevas = normalizar_palabras(palabras) if isinstance(palabras, str) else [
            p for p in normalizar_palabras(" ".join(palabras)) if p
        ]
        if not nuevas or not self.palabras:
            return None
        if len(nuevas) > 6:
            return self._anclar(nuevas, segundo, retraso)
        evento = None
        for palabra in nuevas:
            self.recientes.append(palabra)
            evento = self._alinear_recientes(segundo) or evento
        return evento

    def _ventana(self, antes: int = 1, despues: int = 2) -> tuple[int, int]:
        linea = min(self.linea_de[min(self.pos, len(self.palabras) - 1)], self.total - 1)
        return self._inicio(max(0, linea - antes)), self._fin(min(self.total - 1, linea + despues))

    def _alinear_recientes(self, segundo: float) -> Evento | None:
        consulta = list(self.recientes)
        pesos = [1.0] * len(consulta)
        desde, hasta = self._ventana()
        bruto, inicio, fin = alinear(consulta, pesos, self.palabras, self.umbral, desde, hasta, True)
        esperado = fin >= 0 and self.pos <= fin <= self.pos + 2
        if fin < 0 or not (bruto >= 1.6 or (esperado and bruto >= 0.8)):
            # Nada claro cerca: ¿coincide con claridad en otra parte (coro)?
            if len(consulta) >= 4:
                bruto, inicio, fin = alinear(consulta, pesos, self.palabras, self.umbral, exigir_ultima=True)
                if fin >= 0 and bruto >= 3.2:
                    return self._mover(fin + 1, inicio, segundo, "salto")
            return None
        return self._mover(fin + 1, inicio, segundo, "avance")

    def _anclar(self, nuevas: list[str], segundo: float, retraso: float) -> Evento | None:
        pesos = [1.0] * len(nuevas)
        desde, hasta = self._ventana(antes=2, despues=5)
        bruto, inicio, fin = alinear(nuevas, pesos, self.palabras, self.umbral, desde, hasta)
        tipo = "avance"
        if fin < 0 or bruto < 2.5:
            bruto, inicio, fin = alinear(nuevas, pesos, self.palabras, self.umbral)
            tipo = "salto"
            if fin < 0 or bruto < 3.5:
                return None
        self.recientes.clear()
        self.recientes.extend(nuevas[-4:])
        compensacion = int(retraso / max(self.segundos_por_palabra, 0.2))
        destino = min(len(self.palabras), fin + 1 + compensacion)
        return self._mover(destino, inicio, segundo, tipo)

    def _mover(self, posicion: int, inicio: int, segundo: float, tipo: str) -> Evento | None:
        linea_anterior = self.mostrada
        linea_inicio = self.linea_de[inicio] if 0 <= inicio < len(self.linea_de) else 0
        self.ultima_coincidencia = segundo
        self.predicciones_seguidas = 0

        # ¿Volvió a empezar la canción después de haber avanzado?
        if linea_inicio == 0 and inicio <= 1 and linea_anterior >= 2 and posicion < self._fin(1):
            self.pos = posicion
            self.recientes.clear()
            self.mostrada = self._linea_para(posicion)
            self.repeticiones_linea = 0
            self._marcar_cambio(segundo, False)
            return Evento("repetir", self.mostrada, "el cantante repite la canción")

        # ¿Repite la línea que acaba de cantar (línea "igual")?
        if posicion < self.pos and linea_inicio in (linea_anterior, linea_anterior - 1) \
                and inicio <= self._inicio(linea_inicio) + 1:
            self.pos = posicion
            destino = linea_inicio
            if destino != self.mostrada:
                self.mostrada = destino
                self._marcar_cambio(segundo, False)
            self.repeticiones_linea += 1
            return Evento("igual", destino, "repite la misma línea")

        if posicion < self.pos and tipo != "salto":
            return None  # retroceso pequeño: se ignora (eco del reconocimiento)
        self.pos = posicion
        linea = self._linea_para(posicion)
        if tipo != "salto":
            linea = max(linea, self.mostrada)
        if self._mostrar(linea, segundo, True):
            if self.terminada:
                return Evento("fin", self.mostrada)
            return Evento(tipo, self.mostrada)
        return None

    # ------------------------------------------------------------- tiempo
    def tic(self, segundo: float, hay_voz: bool) -> Evento | None:
        """Llamar periódicamente: aplica la predicción por tempo."""
        if not self.prediccion or self.terminada or not hay_voz:
            return None
        if self.predicciones_seguidas >= 2:
            return None
        restante = self.duracion_esperada(self.mostrada)
        if segundo - self.cambio_en < restante * 1.4 + 1.0:
            return None
        if segundo - self.ultima_coincidencia < 1.0:
            return None
        self.predicciones_seguidas += 1
        siguiente = self.mostrada + 1
        self.pos = max(self.pos, self._inicio(siguiente))
        self._mostrar(siguiente, segundo, False)
        if self.terminada:
            return Evento("fin", self.mostrada, "por tempo")
        return Evento("prediccion", self.mostrada, "avance por tempo")

    # ------------------------------------------------- órdenes del operador
    def ir_a_linea(self, linea: int, segundo: float) -> None:
        linea = max(0, min(linea, self.total))
        self.pos = self._inicio(linea)
        self.recientes.clear()
        self.mostrada = linea
        self.predicciones_seguidas = 0
        self._marcar_cambio(segundo, False)

    def continuar(self, segundo: float) -> None:
        self.ir_a_linea(self.mostrada + 1, segundo)

    def atras(self, segundo: float) -> None:
        self.ir_a_linea(self.mostrada - 1, segundo)

    def repetir(self, segundo: float) -> None:
        self.ir_a_linea(0, segundo)
