"""Opción (g): favoritas, géneros o carpetas y portadas (imagen de cada canción)."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from . import consola
from ..portadas import guardar_portada
from .consola import color

if TYPE_CHECKING:
    from .menus import Aplicacion

class Colecciones:
    def __init__(self, app: Aplicacion):
        self.app = app
        self.bd = app.bd
        self.config = app.config
        self.teclado = app.teclado

    def ejecutar(self) -> None:
        while True:
            consola.limpiar()
            consola.titulo("Favoritas, géneros y portadas")
            generos = self.bd.generos()
            favoritas = self.bd.listar_filtradas(favoritas=True)
            print(color(f"  Favoritas: {len(favoritas)}   ·   Géneros o carpetas: "
                        + (", ".join(f"{g} ({n})" for g, n in generos) or "ninguno"), "tenue"))
            print()
            print("  (c) Elegir una canción para marcarla, darle género o portada")
            print("  (v) Ver las favoritas")
            print("  (g) Ver las canciones de un género o carpeta")
            print("  (r) Regresar")
            opcion = self.app.preguntar("Opción: ").lower()[:1]
            if opcion == "c":
                cancion = self.app.elegir_cancion()
                if cancion:
                    self.editar(cancion.codigo)
            elif opcion == "v":
                self.mostrar("Favoritas", favoritas)
            elif opcion == "g":
                genero = self.app.preguntar("Género o carpeta: ")
                if genero:
                    nombre = next((g for g, _ in generos if g.lower() == genero.lower()), genero)
                    self.mostrar(f"Género: {nombre}", self.bd.listar_filtradas(genero=nombre))
            elif opcion in ("r", "q", ""):
                return

    def mostrar(self, titulo: str, canciones) -> None:
        from .pantalla import paginar

        if not canciones:
            consola.aviso("  No hay canciones aquí.")
            self.teclado.pausa()
            return
        paginar([f"  {c:>6}  {n[:50]:<50} {l:>4} líneas" for c, n, l in canciones],
                self.config.por_pagina, self.teclado, f"{titulo} ({len(canciones)})")

    def editar(self, codigo: int) -> None:
        while True:
            cancion = self.bd.obtener_cancion(codigo)
            if cancion is None:
                return
            consola.limpiar()
            consola.titulo(f"[{cancion.codigo}] {cancion.nombre}")
            print(f"  Favorita: {'sí ★' if cancion.favorita else 'no'}")
            print(f"  Género o carpeta: {cancion.genero or '—'}")
            print(f"  Portada: {cancion.portada or '—'}")
            print()
            print("  (v) Marcar o desmarcar como favorita")
            print("  (g) Cambiar el género o carpeta (vacío para quitarlo)")
            print("  (i) Elegir la imagen de portada (JPG, PNG o WEBP)")
            print("  (r) Regresar")
            opcion = self.app.preguntar("Opción: ").lower()[:1]
            if opcion == "v":
                self.bd.marcar_favorita(codigo, not cancion.favorita)
            elif opcion == "g":
                self.bd.establecer_genero(codigo, self.app.preguntar("Género o carpeta: "))
            elif opcion == "i":
                texto = self.app.preguntar("Ruta de la imagen (puede arrastrarla aquí): ").strip().strip('"')
                if not texto:
                    continue
                try:
                    self.bd.establecer_portada(codigo, guardar_portada(self.config.carpeta, codigo, Path(texto)))
                    consola.exito("  Portada guardada.")
                except (OSError, ValueError) as ex:
                    consola.error(f"  No se pudo guardar la portada: {ex}")
                self.teclado.pausa()
            elif opcion in ("r", "q", ""):
                return
