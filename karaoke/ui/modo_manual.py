"""Modo manual.

El operador escucha dos o tres palabras del cantante, las teclea y el
programa identifica la canción y la línea; desde ahí se avanza con la tecla
(c). Si hay un PROGRAMA cargado basta con presionar Enter para cantar la
siguiente canción, pero el orden se puede romper en cualquier momento.

Teclas durante la canción:
    c / Enter / →   continuar con la siguiente línea
    i               igual: el cantante repite la misma línea
    r               repetir la canción desde el inicio
    g               ignorar (pausa: el cantante afina o hace ejercicios)
    s               seguir después de ignorar
    a / ←           atrás: regresar una línea (corrige un avance por error)
    b               buscar otra canción (abandona la actual)
    f               finalizar la sesión
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from ..buscador import Resultado
from ..db import Cancion
from ..sesion import CancionEnCurso, SesionKaraoke
from . import consola
from .consola import color
from .pantalla import VistaKaraoke, dibujar

if TYPE_CHECKING:
    from .menus import Aplicacion

AYUDA_CANCION = (
    "[c/Enter] continuar  [i] igual  [r] repetir canción  [g] ignorar  [s] seguir  "
    "[a] atrás  [b] buscar otra  [f] finalizar sesión"
)


class ModoManual:
    def __init__(self, app: Aplicacion):
        self.app = app
        self.bd = app.bd
        self.teclado = app.teclado
        self.buscador = app.buscador
        self.config = app.config
        self.sesion: SesionKaraoke | None = None
        self.mensaje = ""

    # ---------------------------------------------------------------- sesión
    def ejecutar(self) -> None:
        if self.bd.contar_canciones() == 0:
            consola.aviso("No hay canciones en la base de datos. Agréguelas con (f).")
            self.teclado.pausa()
            return
        self.sesion = SesionKaraoke(self.bd, "manual")
        try:
            while not self.sesion.finalizada:
                cancion, linea = self.elegir()
                if cancion is None:
                    continue
                self.cantar(self.sesion.iniciar(cancion, linea))
        finally:
            if not self.sesion.finalizada:
                self.sesion.finalizar()
        self.resumen()

    def resumen(self) -> None:
        consola.limpiar()
        consola.titulo("Fin de la sesión de karaoke")
        cantadas = self.sesion.cantadas if self.sesion else []
        print(f"  Se cantaron {len(cantadas)} canción(es):")
        for numero, interpretacion in enumerate(cantadas, 1):
            estado = "completa" if interpretacion.completada else "incompleta"
            print(f"   {numero:>2}. [{interpretacion.codigo}] {interpretacion.nombre} ({estado})")
        self.teclado.pausa()

    # ----------------------------------------------------- elegir la canción
    def elegir(self) -> tuple[Cancion | None, int]:
        sesion = self.sesion
        consola.limpiar()
        consola.titulo(f"Modo manual · canciones cantadas en la sesión: {len(sesion.cantadas)}")
        siguiente = sesion.programa.siguiente()
        if siguiente:
            print(color(f"  Siguiente en el PROGRAMA: [{siguiente.codigo}] {siguiente.nombre_solicitado}",
                        "negrita", "verde"))
        elif sesion.programa.hay_programa() and sesion.programa.activo:
            print(color("  El programa ya no tiene canciones pendientes.", "tenue"))
        if self.mensaje:
            consola.aviso(f"  {self.mensaje}")
            self.mensaje = ""
        print()
        print("  Escriba 2 o 3 palabras que le escucha al cantante y presione Enter.")
        opciones = []
        if siguiente:
            opciones.append("[Enter] cantar la siguiente del programa")
            opciones.append("[n] elegir otra del programa")
            opciones.append("[x] ya no seguir el programa")
        if sesion.cantadas:
            opciones.append("[r] repetir la última")
        opciones += ["[#código] por código", "[g] ignorar", "[f] finalizar"]
        print(color("  " + "  ".join(opciones), "cian"))
        texto = self.teclado.linea(color("  Palabras: ", "negrita")).strip()
        orden = texto.lower()

        if orden == "f":
            sesion.finalizar()
            return None, 0
        if orden == "g":
            self.esperar_seguir()
            return None, 0
        if orden == "" and siguiente:
            return self.bd.obtener_cancion(siguiente.codigo), 0
        if orden == "":
            return None, 0
        if orden == "n" and siguiente:
            return self.elegir_del_programa(), 0
        if orden == "x" and siguiente:
            sesion.programa.activo = False
            self.mensaje = "Se dejó de seguir el programa en esta sesión."
            return None, 0
        if orden == "r" and sesion.cantadas:
            ultima = sesion.cantadas[-1]
            cancion = self.bd.obtener_cancion(ultima.codigo) if ultima.codigo else None
            return cancion, 0
        codigo = orden.lstrip("#")
        if codigo.isdigit() and (orden.startswith("#") or len(orden.split()) == 1):
            cancion = self.bd.obtener_cancion(int(codigo))
            if cancion is None:
                self.mensaje = f"No existe la canción con código {codigo}."
            return cancion, 0
        if len(orden) < 2:
            self.mensaje = "Escriba al menos una palabra completa de la letra."
            return None, 0
        return self.buscar_palabras(texto)

    def buscar_palabras(self, texto: str) -> tuple[Cancion | None, int]:
        prioridad = self.sesion.programa.prioridad()
        resultados = self.buscador.buscar(texto, prioridad)
        resultados = [r for r in resultados if r.puntaje >= self.buscador.puntaje_minimo * 0.6]
        if not resultados:
            self.mensaje = (f"No se encontró «{texto}» en ninguna letra. Si es una canción nueva "
                            "puede agregarla en (f) o usar el modo automático para aprenderla.")
            return None, 0
        claro = self.buscador.identificar(texto, prioridad)
        elegido: Resultado | None = claro
        if elegido is None:
            elegido = self.elegir_resultado(resultados)
        if elegido is None:
            return None, 0
        return self.bd.obtener_cancion(elegido.codigo), elegido.linea_actual

    def elegir_resultado(self, resultados: list[Resultado]) -> Resultado | None:
        print()
        print("  Coincidencias encontradas:")
        for numero, resultado in enumerate(resultados, 1):
            cancion = self.buscador.canciones[resultado.codigo]
            extracto = cancion.lineas[resultado.linea_actual]
            print(f"   {numero}. [{resultado.codigo}] {resultado.nombre} "
                  f"({int(resultado.puntaje * 100)}%) línea {resultado.linea_actual + 1}: "
                  + color(extracto[:60], "tenue"))
        eleccion = self.teclado.linea(color("  Número de la canción (Enter = 1, c = cancelar): ", "cian"))
        eleccion = eleccion.strip().lower()
        if eleccion == "":
            return resultados[0]
        if eleccion.isdigit() and 1 <= int(eleccion) <= len(resultados):
            return resultados[int(eleccion) - 1]
        return None

    def elegir_del_programa(self) -> Cancion | None:
        pendientes = self.sesion.programa.pendientes()
        for numero, entrada in enumerate(pendientes, 1):
            print(f"   {numero}. [{entrada.codigo}] {entrada.nombre_solicitado}")
        eleccion = self.teclado.linea(color("  Número (Enter = cancelar): ", "cian")).strip()
        if eleccion.isdigit() and 1 <= int(eleccion) <= len(pendientes):
            return self.bd.obtener_cancion(pendientes[int(eleccion) - 1].codigo)
        return None

    def esperar_seguir(self) -> None:
        consola.aviso("  Ignorando: el cantante está afinando o haciendo ejercicios.")
        print(color("  Presione (s) para seguir.", "cian"))
        while (self.teclado.tecla() or "") != "s":
            pass

    # ------------------------------------------------------------ cantar
    def vista(self, curso: CancionEnCurso) -> VistaKaraoke:
        estado = "IGNORANDO (pausa)" if curso.pausada else "CANTANDO"
        if curso.repeticiones_cancion:
            estado += f" · repetición {curso.repeticiones_cancion + 1}"
        return VistaKaraoke(
            nombre=curso.cancion.nombre,
            codigo=curso.cancion.codigo,
            lineas=curso.cancion.lineas,
            actual=curso.actual,
            modo="manual",
            estado=estado,
            mensaje=curso.mensaje,
            ayuda=AYUDA_CANCION,
            previas=self.config.entero("pantalla", "lineas_previas"),
            siguientes=self.config.entero("pantalla", "lineas_siguientes"),
        )

    def cantar(self, curso: CancionEnCurso) -> None:
        sesion = self.sesion
        while True:
            dibujar(self.vista(curso))
            tecla = self.teclado.tecla()
            if tecla in ("c", "\n", "derecha", "abajo", " "):
                if curso.continuar():
                    sesion.terminar(completada=True)
                    self.mensaje = f"Terminó «{curso.cancion.nombre}». Presione r para repetirla."
                    return
            elif tecla == "i":
                curso.igual()
            elif tecla == "r":
                curso.repetir()
            elif tecla == "g":
                curso.ignorar()
            elif tecla == "s":
                curso.seguir()
            elif tecla in ("a", "izquierda", "arriba"):
                curso.atras()
            elif tecla == "b":
                sesion.terminar(completada=False)
                return
            elif tecla == "f":
                sesion.finalizar()
                return
