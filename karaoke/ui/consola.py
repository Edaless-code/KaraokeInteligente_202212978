"""Manejo de la consola: colores, limpiar pantalla y lectura de teclas.

Funciona en Windows (``msvcrt``), en Linux/Android-Termux (``termios``) y
también cuando la entrada viene de un archivo o tubería (pruebas
automatizadas): en ese caso cada renglón de la entrada equivale a una tecla.
"""

from __future__ import annotations

import os
import queue
import shutil
import sys
import threading
import time

ES_WINDOWS = os.name == "nt"

# Paleta fría y mate (la misma idea que la aplicación móvil): azules acero,
# grises y tonos apagados; sin rojos ni colores chillones. Son colores de 256
# tonos, que la consola de Windows 10/11 y las terminales de Linux entienden.
_COLORES = {
    "reset": "\033[0m",
    "negrita": "\033[1m",
    "tenue": "\033[38;5;244m",       # gris para lo secundario
    "texto": "\033[38;5;254m",       # casi blanco: la línea que se canta
    "rojo": "\033[38;5;174m",        # errores: rosa apagado
    "verde": "\033[38;5;108m",       # éxito: verde salvia
    "amarillo": "\033[38;5;180m",    # avisos: arena
    "azul": "\033[38;5;67m",         # azul acero
    "magenta": "\033[38;5;146m",     # lavanda grisácea
    "cian": "\033[38;5;110m",        # acento principal: azul claro mate
    "blanco": "\033[38;5;252m",
    "fondo_azul": "\033[48;5;24m",
}

usar_colores = True


def inicializar(colores: bool = True) -> None:
    """Prepara la consola: UTF-8 y secuencias ANSI (colores) en Windows."""
    global usar_colores
    usar_colores = colores and sys.stdout.isatty()
    for flujo in (sys.stdout, sys.stderr):
        try:
            flujo.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass
    if ES_WINDOWS:
        try:
            import ctypes

            kernel32 = ctypes.windll.kernel32
            kernel32.SetConsoleOutputCP(65001)
            kernel32.SetConsoleCP(65001)
            manejador = kernel32.GetStdHandle(-11)
            modo = ctypes.c_uint32()
            if kernel32.GetConsoleMode(manejador, ctypes.byref(modo)):
                # ENABLE_VIRTUAL_TERMINAL_PROCESSING
                kernel32.SetConsoleMode(manejador, modo.value | 0x0004)
        except Exception:
            usar_colores = False


def color(texto: str, *estilos: str) -> str:
    if not usar_colores or not estilos:
        return texto
    return "".join(_COLORES[e] for e in estilos) + texto + _COLORES["reset"]


def ancho() -> int:
    return max(40, shutil.get_terminal_size((80, 24)).columns)


def alto() -> int:
    return max(16, shutil.get_terminal_size((80, 24)).lines)


def limpiar() -> None:
    if sys.stdout.isatty():
        sys.stdout.write("\033[2J\033[H" if usar_colores else "\n" * 3)
        if not usar_colores:
            os.system("cls" if ES_WINDOWS else "clear")
    else:
        sys.stdout.write("\n" + "-" * 60 + "\n")
    sys.stdout.flush()


_pantalla_completa = False


def entrar_pantalla_completa() -> None:
    """Pantalla alterna (como vim o htop): no deja historial y se redibuja
    en su lugar, sin parpadeo ni texto acumulado."""
    global _pantalla_completa
    if usar_colores and sys.stdout.isatty() and not _pantalla_completa:
        sys.stdout.write("\033[?1049h\033[?25l\033[2J\033[H")
        sys.stdout.flush()
        _pantalla_completa = True


def salir_pantalla_completa() -> None:
    global _pantalla_completa
    if _pantalla_completa:
        sys.stdout.write("\033[?25h\033[?1049l")
        sys.stdout.flush()
        _pantalla_completa = False


def redibujar(renglones: list[str]) -> None:
    """Reemplaza el contenido de la pantalla por ``renglones`` sin borrarla
    primero: cada renglón se escribe encima del anterior y se limpia el resto,
    así la letra no parpadea."""
    if _pantalla_completa:
        alto = shutil.get_terminal_size((80, 24)).lines
        visibles = renglones[: max(1, alto - 1)]
        sys.stdout.write("\033[H" + "\n".join(r + "\033[K" for r in visibles) + "\033[J")
        sys.stdout.flush()
        return
    limpiar()
    print("\n".join(renglones), flush=True)


def titulo(texto: str, derecha: str = "") -> None:
    """Encabezado de cada pantalla: título a la izquierda, dato a la derecha."""
    largo = min(ancho(), 100) - 4
    espacio = max(1, largo - len(texto) - len(derecha))
    print()
    print("  " + color(texto, "negrita", "cian") + " " * espacio + color(derecha, "tenue"))
    print(color("  " + "─" * largo, "tenue"))


def aviso(texto: str) -> None:
    print(color(texto, "amarillo"))


def error(texto: str) -> None:
    print(color(texto, "rojo", "negrita"))


def exito(texto: str) -> None:
    print(color(texto, "verde"))


class Teclado:
    """Lectura de teclas sueltas (sin Enter) y de renglones completos."""

    def __init__(self) -> None:
        self.interactivo = sys.stdin.isatty()
        self._cola: queue.Queue[str | None] = queue.Queue()
        self._hilo: threading.Thread | None = None
        if not self.interactivo:
            self._hilo = threading.Thread(target=self._leer_entrada, daemon=True)
            self._hilo.start()

    # Entrada redirigida: un hilo lee los renglones y los deja en la cola.
    def _leer_entrada(self) -> None:
        for renglon in sys.stdin:
            self._cola.put(renglon.rstrip("\r\n"))
        self._cola.put(None)

    def _siguiente_renglon(self, espera: float | None) -> str | None:
        try:
            renglon = self._cola.get(timeout=espera)
        except queue.Empty:
            return None
        if renglon is None:
            # Fin de la entrada: se repite para que todos los lectores terminen.
            self._cola.put(None)
            raise EOFError
        return renglon

    def linea(self, mensaje: str = "") -> str:
        """Lee un renglón completo (como ``input``)."""
        if self.interactivo:
            return input(mensaje)
        sys.stdout.write(mensaje)
        sys.stdout.flush()
        renglon = self._siguiente_renglon(None) or ""
        print(renglon)
        return renglon

    def tecla(self, espera: float | None = None) -> str | None:
        """Devuelve la tecla presionada en minúscula ("\\n" para Enter) o
        ``None`` si pasó ``espera`` segundos sin que se presionara nada."""
        if not self.interactivo:
            renglon = self._siguiente_renglon(espera)
            if renglon is None:
                return None
            renglon = renglon.strip().lower()
            return renglon[0] if renglon else "\n"
        if ES_WINDOWS:
            return self._tecla_windows(espera)
        return self._tecla_unix(espera)

    @staticmethod
    def _tecla_windows(espera: float | None) -> str | None:
        import msvcrt

        limite = None if espera is None else time.monotonic() + espera
        while True:
            if msvcrt.kbhit():
                caracter = msvcrt.getwch()
                if caracter in ("\x00", "\xe0"):  # teclas especiales (flechas)
                    especial = msvcrt.getwch()
                    return {"H": "arriba", "P": "abajo", "K": "izquierda", "M": "derecha"}.get(especial, "")
                if caracter == "\x03":
                    raise KeyboardInterrupt
                return "\n" if caracter == "\r" else caracter.lower()
            if limite is not None and time.monotonic() >= limite:
                return None
            time.sleep(0.02)

    @staticmethod
    def _tecla_unix(espera: float | None) -> str | None:
        import select
        import termios
        import tty

        descriptor = sys.stdin.fileno()
        anterior = termios.tcgetattr(descriptor)
        try:
            tty.setcbreak(descriptor)
            listo, _, _ = select.select([sys.stdin], [], [], espera)
            if not listo:
                return None
            caracter = sys.stdin.read(1)
            if caracter == "\x1b":  # flechas: ESC [ A/B/C/D
                listo, _, _ = select.select([sys.stdin], [], [], 0.05)
                if listo:
                    resto = sys.stdin.read(2)
                    return {"[A": "arriba", "[B": "abajo", "[D": "izquierda", "[C": "derecha"}.get(resto, "")
                return "esc"
            return "\n" if caracter in ("\r", "\n") else caracter.lower()
        finally:
            termios.tcsetattr(descriptor, termios.TCSADRAIN, anterior)

    def pausa(self, mensaje: str = "Presione una tecla para continuar...") -> str:
        print(color(mensaje, "tenue"))
        return self.tecla() or ""

    def confirmar(self, mensaje: str) -> bool:
        respuesta = self.linea(f"{mensaje} (s/n): ").strip().lower()
        return respuesta in ("s", "si", "sí", "y", "yes")
